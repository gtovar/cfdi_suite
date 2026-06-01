from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .policy import (
    ANALYZE_CFDI_XML_MAX_CHARS,
    FALLBACK_REASON_PROVIDER_RUNTIME_FAILURE,
)


class AnalyzeCfdiRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=ANALYZE_CFDI_XML_MAX_CHARS)


class AnalysisIssue(BaseModel):
    code: Literal[
        "PROFILE_DETECTION_FAILED",
        "CFDI_PARSE_FAILED",
        "INGRESO_EXTRACTION_FAILED",
        "PAGO_EXTRACTION_FAILED",
        "UNSUPPORTED_CAPABILITY",
        "ENGINE_RUNTIME_FAILED",
        "RESULT_DEGRADED",
    ]
    message: str
    stage: Literal["profile", "parse", "extract"]
    fatal: bool


class AnalyzeCfdiMeta(BaseModel):
    contractVersion: Literal["v1"] = "v1"
    capability: Literal["analyze_cfdi"] = "analyze_cfdi"
    provider: str
    providerMode: Literal["primary", "fallback", "comparison", "bridge"]
    degraded: bool
    requestId: str
    providerVersion: str | None = None
    warnings: list[str] = Field(default_factory=list)
    timingMs: int | None = None
    fallbackReason: Literal[FALLBACK_REASON_PROVIDER_RUNTIME_FAILURE] | None = None


class AnalyzeCfdiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    profile: Literal["ingreso", "pagos", "unknown"]
    cfdi: dict[str, Any] | None
    ingresoRows: list[dict[str, str]]
    ingresoRowHeader: dict[str, str] = Field(default_factory=dict)
    pagoRows: list[dict[str, str]]
    issues: list[AnalysisIssue]
    meta: AnalyzeCfdiMeta
