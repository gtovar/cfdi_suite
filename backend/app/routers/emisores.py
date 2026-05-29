from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, field_validator

from ..credentials import delete_emisor, load_all, set_emisor

router = APIRouter(prefix="/api/emisores", tags=["emisores"])


class EmisorCreate(BaseModel):
    rfc: str
    pac: Literal["diverza"] = "diverza"
    credential_id: str
    credential_token: str
    certificate_number: str = ""

    @field_validator("rfc")
    @classmethod
    def rfc_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("credential_id", "credential_token")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("No puede estar vacío")
        return v.strip()


class EmisorPublic(BaseModel):
    rfc: str
    pac: str
    credential_id: str
    certificate_number: str


def _to_public(rfc: str, entry: dict) -> EmisorPublic:
    return EmisorPublic(
        rfc=rfc,
        pac=entry.get("pac", "diverza"),
        credential_id=entry.get("credential_id", ""),
        certificate_number=entry.get("certificate_number", ""),
    )


@router.get("", response_model=list[EmisorPublic])
def list_emisores() -> list[EmisorPublic]:
    return [_to_public(rfc, entry) for rfc, entry in load_all().items()]


@router.post("", response_model=EmisorPublic, status_code=201)
def create_emisor(body: EmisorCreate) -> EmisorPublic:
    existing = load_all()
    if body.rfc in existing:
        raise HTTPException(status_code=409, detail=f"El emisor {body.rfc} ya existe")
    set_emisor(body.rfc, body.model_dump())
    return _to_public(body.rfc, body.model_dump())


@router.put("/{rfc}", response_model=EmisorPublic)
def update_emisor(rfc: str, body: EmisorCreate) -> EmisorPublic:
    rfc = rfc.upper()
    existing = load_all()
    if rfc not in existing:
        raise HTTPException(status_code=404, detail=f"Emisor {rfc} no encontrado")
    set_emisor(rfc, body.model_dump(exclude={"rfc"}) | {"rfc": rfc})
    return _to_public(rfc, body.model_dump())


@router.delete("/{rfc}", status_code=204)
def remove_emisor(rfc: str) -> Response:
    if not delete_emisor(rfc.upper()):
        raise HTTPException(status_code=404, detail=f"Emisor {rfc.upper()} no encontrado")
    return Response(status_code=204)
