from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from backend.app.routers.sat_enquiry import (
    _DIVERZA_BASE,
    _call_diverza,
    _is_uuid,
)


class DiverzaSsrfCharacterizationTests(unittest.TestCase):
    """Caracteriza el comportamiento actual antes de cambiar la mitigación SSRF.

    Estos tests no proponen todavía una implementación. Verifican dos hipótesis:
    1. Un UUID con salto de línea final debe ser rechazado por el contrato.
    2. Un UUID válido debe producir exactamente el destino Diverza esperado.
    """

    def test_rechaza_uuid_con_salto_de_linea_final(self):
        uuid_con_salto = "a1b2c3d4-e5f6-4a7b-8c9d-ef1234567890\n"

        self.assertFalse(_is_uuid(uuid_con_salto))

    def test_call_diverza_usa_exactamente_el_destino_esperado(self):
        uuid = "a1b2c3d4-e5f6-4a7b-8c9d-ef1234567890"
        response = MagicMock()
        response.text = "ok"
        response.status_code = 200
        response.raise_for_status = MagicMock()
        put = AsyncMock(return_value=response)

        async def run() -> str:
            async with httpx.AsyncClient() as client:
                return await _call_diverza(client, uuid, {"a": 1})

        with patch("httpx.AsyncClient.put", put):
            result = asyncio.run(run())

        self.assertEqual(result, "ok")
        put.assert_awaited_once()
        called_url = put.await_args.args[0]
        self.assertEqual(
            called_url,
            f"{_DIVERZA_BASE}/{uuid}/sat_cfdi_enquiry",
        )
