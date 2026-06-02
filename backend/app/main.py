from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .contracts import AnalysisIssue, AnalyzeCfdiRequest, AnalyzeCfdiResponse
from .observability import record_analyze_cfdi_error
from .routers.emisores import router as emisores_router
from .routers.pdf import router as pdf_router
from .routers.rfc_validation import fiel_router
from .routers.rfc_validation import router as rfc_router
from .routers.sat_enquiry import router as sat_router
from .services.analyze_cfdi import run_analyze_cfdi

app = FastAPI(title="cfdi-suite-api", version="0.1.0")
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

app.include_router(emisores_router)
app.include_router(pdf_router)
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
