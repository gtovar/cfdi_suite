from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .contracts import AnalysisIssue, AnalyzeCfdiRequest, AnalyzeCfdiResponse
from .observability import record_analyze_cfdi_error
from .services.analyze_cfdi import run_analyze_cfdi


app = FastAPI(title="cfdi-platform-api", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    del request, exc
    response = AnalyzeCfdiResponse(
        profile="unknown",
        cfdi=None,
        ingresoRows=[],
        pagoRows=[],
        issues=[
            AnalysisIssue(
                code="CFDI_PARSE_FAILED",
                message="El request de análisis CFDI es inválido.",
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
