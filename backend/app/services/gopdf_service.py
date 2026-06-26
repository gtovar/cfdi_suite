import httpx
import json
from typing import Any

GOPDFSUIT_URL = "http://localhost:8080/api/v1/generate" # Tu contenedor de Go

async def generate_invoice_gopdf(cfdi_data: dict[str, Any], template_id: str) -> bytes:
    # Mapeamos los datos limpios que ya extrae tu backend
    payload = {
        "template_id": template_id,
        "data": {
            "uuid": cfdi_data.get("uuid"),
            "emisor": cfdi_data.get("emisor"),
            "receptor": cfdi_data.get("receptor"),
            "subtotal": cfdi_data.get("subtotal"),
            "total": cfdi_data.get("total"),
            # Aquí van los miles de registros en un array plano de JSON
            "conceptos": cfdi_data.get("conceptos", []) 
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(GOPDFSUIT_URL, json=payload, timeout=30.0)
        if response.status_code != 200:
            raise RuntimeError(f"GoPdfSuit falló: {response.text}")
        
        return response.content # Bytes listos del PDF
