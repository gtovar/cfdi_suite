from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
# Importamos el parser nativo de Starlette para alterar su configuración global
from starlette.formparsers import MultiPartParser

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

    # ARQ pool — opcional: si Redis no está disponible, el sistema sigue funcionando
    # en modo sync. Jobs >50k solo se despachan a ARQ cuando el pool existe.
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        app.state.arq_pool = await create_pool(
            RedisSettings(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                conn_timeout=2,
                max_connections=20,
            )
        )
        print("ARQ: conectado a Redis")
    except Exception:
        app.state.arq_pool = None
        print("ARQ: Redis no disponible — canvas_pipeline corre en modo sync")

    yield

    if getattr(app.state, "arq_pool", None):
        await app.state.arq_pool.close()


app = FastAPI(title="cfdi-suite-api", version="0.1.0", lifespan=_lifespan)
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


@app.post("/api/cfdi/analyze", response_model=AnalyzeCfdiResponse)
def analyze_cfdi(payload: AnalyzeCfdiRequest) -> AnalyzeCfdiResponse:
    return run_analyze_cfdi(payload.xml)
