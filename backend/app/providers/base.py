from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


ProviderMode = Literal["primary", "fallback", "comparison", "bridge"]
ProviderProfile = Literal["ingreso", "pagos", "unknown"]
ProviderIssueCode = Literal[
    "parse_failed",
    "runtime_failed",
    "unsupported_capability",
    "rows_unavailable",
    "findings_unavailable",
]


@dataclass(frozen=True)
class ProviderCapabilities:
    supported_profiles: tuple[ProviderProfile, ...] = ("unknown",)
    supports_ingreso_rows: bool = False
    supports_pago_rows: bool = False
    supports_findings: bool = False


@dataclass(frozen=True)
class ProviderDocumentSignal:
    profile: ProviderProfile = "unknown"
    reason: str | None = None


@dataclass(frozen=True)
class ProviderIssue:
    code: ProviderIssueCode
    message: str
    stage: Literal["profile", "parse", "extract"]
    public_message: str | None = None


@dataclass(frozen=True)
class ProviderDiagnostics:
    bridge: bool = False
    fallback_eligible: bool = False
    fallback_reason: str | None = None
    warning_messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderResult:
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    document_signal: ProviderDocumentSignal = field(default_factory=ProviderDocumentSignal)
    structured_cfdi: dict[str, Any] | None = None
    ingreso_rows: list[dict[str, str]] = field(default_factory=list)
    pago_rows: list[dict[str, str]] = field(default_factory=list)
    provider_issues: list[ProviderIssue] = field(default_factory=list)
    diagnostics: ProviderDiagnostics = field(default_factory=ProviderDiagnostics)


class CfdiAnalysisProvider(Protocol):
    name: str
    mode: ProviderMode
    version: str | None

    def analyze(self, xml: str) -> ProviderResult:
        ...
