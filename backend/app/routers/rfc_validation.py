from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..fiel_config import delete_fiel, fiel_rfc, load_fiel, save_fiel

router = APIRouter(prefix="/api/rfc", tags=["rfc"])
fiel_router = APIRouter(prefix="/api/fiel", tags=["fiel"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RfcValidateRequest(BaseModel):
    rfc: str
    razonSocial: str | None = None


class RfcFormatResult(BaseModel):
    rfc: str
    formatoValido: bool
    digitoVerificador: bool
    tipo: str | None = None  # "FISICA" | "MORAL"
    esGenerico: bool = False
    error: str | None = None


class RfcSatResult(BaseModel):
    rfc: str
    existeEnLrfc: bool | None = None
    razonSocialValida: bool | None = None
    error: str | None = None


class FielStatus(BaseModel):
    configurada: bool
    rfc: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_format(rfc: str) -> RfcFormatResult:
    from satcfdi.models.rfc import RFC

    rfc_upper = rfc.strip().upper()
    try:
        rfc_obj = RFC(rfc_upper)
    except ValueError:
        return RfcFormatResult(rfc=rfc_upper, formatoValido=False, digitoVerificador=False, error="Formato de RFC inválido")

    return RfcFormatResult(
        rfc=rfc_upper,
        formatoValido=True,
        digitoVerificador=rfc_obj.is_valid(),
        tipo=rfc_obj.type.name,
        esGenerico=rfc_obj.is_generic(),
    )


def _validate_sat(rfc: str, razon_social: str | None, signer) -> RfcSatResult:
    from satcfdi.portal import SATFacturaElectronica

    portal = SATFacturaElectronica(signer)
    portal.login()

    existe = None
    razon_valida = None
    try:
        existe = bool(portal.rfc_valid(rfc.upper()))
    except Exception as exc:
        return RfcSatResult(rfc=rfc.upper(), error=f"Error consultando LRFC: {exc}")

    if razon_social and existe:
        try:
            razon_valida = bool(portal.legal_name_valid(rfc.upper(), razon_social.upper()))
        except Exception as exc:
            return RfcSatResult(rfc=rfc.upper(), existeEnLrfc=existe, error=f"Error validando razón social: {exc}")

    return RfcSatResult(rfc=rfc.upper(), existeEnLrfc=existe, razonSocialValida=razon_valida)


# ---------------------------------------------------------------------------
# RFC validation endpoints
# ---------------------------------------------------------------------------


@router.post("/validate/format", response_model=RfcFormatResult)
def validate_rfc_format(body: RfcValidateRequest) -> RfcFormatResult:
    return _validate_format(body.rfc)


@router.post("/validate/sat", response_model=RfcSatResult)
def validate_rfc_sat(body: RfcValidateRequest) -> RfcSatResult:
    fiel_data = load_fiel()
    if not fiel_data:
        raise HTTPException(status_code=409, detail="FIEL no configurada. Configura tu e.Firma en Ajustes.")

    cer_bytes, key_bytes, password = fiel_data
    try:
        from satcfdi.models import Signer
        signer = Signer.load(certificate=cer_bytes, key=key_bytes, password=password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error cargando FIEL: {exc}") from exc

    try:
        return _validate_sat(body.rfc, body.razonSocial, signer)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error en portal SAT: {exc}") from exc


# ---------------------------------------------------------------------------
# FIEL configuration endpoints
# ---------------------------------------------------------------------------


@fiel_router.get("/status", response_model=FielStatus)
def get_fiel_status() -> FielStatus:
    rfc = fiel_rfc()
    return FielStatus(configurada=rfc is not None, rfc=rfc)


@fiel_router.post("/configure", response_model=FielStatus)
async def configure_fiel(
    cer: UploadFile = File(...),
    key: UploadFile = File(...),
    password: str = Form(...),
) -> FielStatus:
    cer_bytes = await cer.read()
    key_bytes = await key.read()

    try:
        from satcfdi.models import Signer
        Signer.load(certificate=cer_bytes, key=key_bytes, password=password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Credenciales FIEL inválidas: {exc}") from exc

    save_fiel(cer_bytes, key_bytes, password)
    rfc = fiel_rfc()
    return FielStatus(configurada=True, rfc=rfc)


@fiel_router.delete("/", response_model=FielStatus)
def remove_fiel() -> FielStatus:
    delete_fiel()
    return FielStatus(configurada=False, rfc=None)
