import base64
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional

# Importa tu función generadora real
from ..services.pdf_pipeline import generate

router = APIRouter(prefix="/api/internal", tags=["Worker"])

# Modelo de datos que Google Tasks nos va a mandar
class GeneratePdfPayload(BaseModel):
    job_id: str
    xml_b64: str
    template_id: str
    html_shell: Optional[str] = None

@router.post("/generate-pdf")
async def internal_generate_pdf(payload: GeneratePdfPayload, request: Request):
    """
    Este endpoint es llamado EXCLUSIVAMENTE por Google Cloud Tasks.
    """
    # 1. Medida de seguridad (Opcional pero recomendada): 
    # Validar que la petición venga de Cloud Tasks leyendo sus headers internos
    if "x-cloudtasks-queuename" not in request.headers:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo Cloud Tasks.")

    print(f"Iniciando generación de PDF pesada para Job ID: {payload.job_id}")
    
    try:
        # 2. Decodificamos el XML
        xml_bytes = base64.b64decode(payload.xml_b64)
        
        # 3. Generamos el PDF de forma síncrona/intensiva
        # Como esto lo llama Cloud Tasks en background, no importa que tarde 2 minutos
        pdf_bytes = generate(xml_bytes, payload.template_id, payload.html_shell)
        
        # 4. AQUI DECIDES QUÉ HACER CON EL PDF
        # Puedes guardarlo en un bucket de Google Cloud Storage (Recomendado)
        # O guardarlo en Upstash Redis temporalmente:
        # await redis.set(f"pdf:result:{payload.job_id}", pdf_bytes, ex=3600)
        # await redis.set(f"pdf:status:{payload.job_id}", "done", ex=3600)
        
        print(f"PDF {payload.job_id} generado con éxito.")
        return {"status": "success", "message": "PDF generado"}

    except Exception as e:
        print(f"Error generando PDF {payload.job_id}: {e}")
        # Retornamos error 500 para que Cloud Tasks sepa que falló y lo reintente luego
        raise HTTPException(status_code=500, detail=str(e))
