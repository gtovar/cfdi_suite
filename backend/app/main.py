from __future__ import annotations
from .observability import run_infrastructure_self_diagnostic

import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import sentry_sdk 
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
# Importamos el parser nativo de Starlette para alterar su configuración global
from starlette.formparsers import MultiPartParser

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from .contracts import AnalysisIssue, AnalyzeCfdiRequest, AnalyzeCfdiResponse
from .observability import record_analyze_cfdi_error
from .routers.batch import router as batch_router
from .routers.emisores import router as emisores_router
from .routers.pdf import router as pdf_router
from .routers.rfc_validation import fiel_router
from .routers.templates import router as templates_router
from .routers.rfc_validation import router as rfc_router
from .routers.sat_enquiry import router as sat_router
from .services.analyze_cfdi import run_analyze_cfdi

# === PARCHE GLOBAL DE SEGURIDAD PARA MULTIPART ===
# Incrementamos el límite por sección a 100 MB para soportar tus XMLs masivos de 50 MB
MultiPartParser.max_part_size = 100 * 1024 * 1024

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def _lifespan(app: FastAPI):
    (_BACKEND_ROOT / "shells").mkdir(exist_ok=True)
    (_BACKEND_ROOT / "templates" / "html").mkdir(parents=True, exist_ok=True)

    # app.state.arq_pool ya no se usa, toda la carga va por Cloud Tasks

    yield

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0, # Captura el 100% de las transacciones para medir rendimiento
)

app = FastAPI(title="cfdi-suite-api", version="0.1.0", lifespan=_lifespan)

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

_allowed_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(batch_router)
app.include_router(emisores_router)
app.include_router(pdf_router)
app.include_router(templates_router)
app.include_router(sat_router)
app.include_router(rfc_router)
app.include_router(fiel_router)


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
    return {"status": "ok"}

# Agrega este endpoint justo debajo de tu ruta de /api/health
@app.get("/api/infrastructure/diagnose")
def get_infra_diagnostic() -> dict[str, Any]:
    """
    Endpoint clínico de autodiagnóstico para evaluar la salud de Cloud Run, Vercel y Cloud Tasks.
    """
    report = run_infrastructure_self_diagnostic()
    return {
        "status": report.status,
        "verdict": report.verdict,
        "evidence": report.evidence,
        "recommendations": report.recommendations
    }

@app.post("/api/cfdi/analyze", response_model=AnalyzeCfdiResponse)
def analyze_cfdi(payload: AnalyzeCfdiRequest) -> AnalyzeCfdiResponse:
    return run_analyze_cfdi(payload.xml)
