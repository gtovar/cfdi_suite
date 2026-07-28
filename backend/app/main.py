from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import sentry_sdk 
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.formparsers import MultiPartParser

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from .contracts import AnalysisIssue, AnalyzeCfdiResponse
from .rate_limits import rate_limit
from .security import verify_user_identity
from .observability import record_analyze_cfdi_error
from .routers.batch import router as batch_router
from .routers.emisores import router as emisores_router
from .routers.pdf import router as pdf_router
from .routers.rfc_validation import fiel_router
from .routers.templates import router as templates_router
from .routers.rfc_validation import router as rfc_router
from .routers.sat_enquiry import router as sat_router
from .routers.pusher_auth import router as pusher_auth_router
from .services.analyze_cfdi import run_analyze_cfdi
from .services import redis_safety
from .middleware import RouteBodySizeLimitMiddleware
from google.api_core.exceptions import InvalidArgument

# === PARCHE GLOBAL DE SEGURIDAD PARA MULTIPART ===
# Incrementamos el límite por sección a 100 MB para soportar tus XMLs masivos de 50 MB
MultiPartParser.max_part_size = 100 * 1024 * 1024

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if os.getenv("REQUIRE_API_AUTH", "").lower() == "true" and not os.getenv(
        "API_BEARER_TOKEN"
    ):
        raise RuntimeError(
            "API_BEARER_TOKEN must be configured when REQUIRE_API_AUTH=true"
        )
    (_BACKEND_ROOT / "shells").mkdir(exist_ok=True)
    (_BACKEND_ROOT / "templates" / "html").mkdir(parents=True, exist_ok=True)
    yield

# === INICIALIZACIÓN DE SENTRY ===

def _sentry_strip_sensitive(event, hint):
    breadcrumbs = event.get("breadcrumbs", {}).get("values")
    if breadcrumbs:
        for crumb in breadcrumbs:
            url = (crumb.get("data") or {}).get("url")
            if isinstance(url, str) and "?" in url:
                crumb["data"]["url"] = url.split("?")[0]
    request = event.get("request")
    if request and isinstance(request.get("url"), str) and "?" in request["url"]:
        request["url"] = request["url"].split("?")[0]
    logentry = event.get("logentry", {})
    if logentry and isinstance(logentry.get("message"), str):
        logentry["message"] = re.sub(r"\?[^\s\"]+", "?[REDACTED]", logentry["message"])
    return event

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
    before_send=_sentry_strip_sensitive,
)


class _SanitizeQueryParams(logging.Filter):
    """Redacta query params en todos los mensajes de log.

    Evita que signed URLs con tokens aparezcan en stdout -> Cloud Logging.
    Cubre el caso que Sentry before_send no ve (prints y logger.info directos).
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = re.sub(r"\?[^\s\"]+", "?[REDACTED]", str(record.msg))
        return True


logging.getLogger().addFilter(_SanitizeQueryParams())

app = FastAPI(
    title="cfdi-suite-api",
    version="0.1.0",
    lifespan=_lifespan,
    dependencies=[Depends(verify_user_identity)],
)


@app.exception_handler(InvalidArgument)
async def google_invalid_argument_handler(request: Request, exc: InvalidArgument):
    # Enviar el error detallado a Sentry con esteroides
    if "Task size too large" in str(exc):
        sentry_sdk.capture_exception(exc, tags={
            "mecanismo": "cloud_tasks",
            "error_infra": "task_payload_limit_100kb"
        })

        # Devolver una respuesta clara que el frontend pueda entender
        return JSONResponse(
            status_code=413, # Cambiamos a 413 para indicar que el contenido es muy grande
            content={"message": "Uno de los archivos XML excede el límite de 100KB permitido por la cola de tareas."}
        )

    # Reportar cualquier otro error de argumentos de Google
    sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=400, content={"message": "Solicitud inválida"}
    )


@app.exception_handler(HTTPException)
async def _sanitize_5xx_detail(request: Request, exc: HTTPException):
    if exc.status_code == 503:
        return JSONResponse(
            status_code=503,
            content={"detail": "Servicio temporalmente no disponible. Intenta de nuevo."},
        )
    if exc.status_code >= 500:
        sentry_sdk.capture_message(f"5xx detail sanitizado: {str(exc.detail)[:200]}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "Error interno del servidor"},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)},
    )

# --- INICIO CLOUD TRACE ---
# Inyectamos el líquido fluorescente (Google Cloud Trace) en toda la tubería.
provider = TracerProvider()
try:
    cloud_trace_exporter = CloudTraceSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(cloud_trace_exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    print("Cloud Trace activado con éxito.")
except Exception as e:
    print(f"Cloud Trace inactivo (probable entorno local sin credenciales GCP): {e}")
# --- FIN CLOUD TRACE ---

app.add_middleware(GZipMiddleware, minimum_size=1000)
# Debe permanecer exterior a FastAPI/Starlette: así cuenta el stream ASGI
# antes de que el parser multipart lo copie a SpooledTemporaryFile.
app.add_middleware(RouteBodySizeLimitMiddleware)
_allowed_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(batch_router)
app.include_router(emisores_router)
app.include_router(pdf_router)
app.include_router(templates_router)
app.include_router(sat_router)
app.include_router(rfc_router)
app.include_router(fiel_router)
app.include_router(pusher_auth_router)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    del request
    public_message = "El request de análisis CFDI es inválido."
    for err in exc.errors():
        if err.get("type") == "string_too_long":
            limit = err.get("ctx", {}).get("max_length", 0)
            public_message = (
                f"El XML es demasiado grande. "
                f"Límite: {limit:,} caracteres."
            )
            break
    response = AnalyzeCfdiResponse(
        profile="unknown",
        cfdi=None,
        ingresoRows=[],
        pagoRows=[],
        issues=[
            AnalysisIssue(
                code="CFDI_PARSE_FAILED",
                message=public_message,
                stage="parse",
                fatal=True,
            )
        ],
        meta={
            "provider": "platform",
            "providerMode": "primary",
            "degraded": False,
            "requestId": str(uuid4()),
            "providerVersion": None,
            "warnings": [],
            "timingMs": None,
            "fallbackReason": None,
        },
    )
    record_analyze_cfdi_error(response, http_status=422)
    return JSONResponse(status_code=422, content=response.model_dump())


@app.get("/api/health")
def health() -> dict[str, str]:
    # Solo lee la bandera en memoria -- NUNCA debe hacer una llamada real a
    # Redis (el presupuesto de cuota son ~11 peticiones/min, ver Paso 6 de
    # docs/plan-implementacion-resiliencia-redis-2026-07-23.md).
    if redis_safety.is_degraded():
        return {"status": "degraded", "realtime": "unavailable"}
    return {"status": "ok"}


@app.post("/api/cfdi/analyze", response_model=AnalyzeCfdiResponse)
async def analyze_cfdi(
    file: UploadFile = File(...),
    _rate=rate_limit(30),
) -> AnalyzeCfdiResponse:
    raw = await file.read()
    return run_analyze_cfdi(raw.decode("utf-8", errors="replace"))
