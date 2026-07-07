import asyncio
from fastapi import Response
from fastapi.responses import StreamingResponse
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

# --- NUEVO CÓDIGO PARA EL FRONTEND ---

@router.post("/cfdi/pdf/start")
async def start_pdf_generation(
    file: UploadFile = File(...),
    engine: str = Form("canvas_pipeline"),
    template: Optional[str] = Form(None)
):
    """
    Recibe el XML del frontend y genera un Job ID para procesarlo.
    """
    # 1. Generamos un ID único para este trabajo
    job_id = str(uuid.uuid4())
    
    # 2. Leemos el contenido del archivo subido
    xml_content = await file.read()
    
    # [AQUÍ LUEGO CONECTAREMOS EL PROCESAMIENTO EN SEGUNDO PLANO]
    # Por ahora solo imprimiremos en consola para verificar que llega
    print(f"Recibida petición de PDF del frontend. Job ID asignado: {job_id}")
    print(f"Motor solicitado: {engine}, Template: {template}")
    
    # 3. Devolvemos el jobId al frontend exactamente como lo espera
    return {"jobId": job_id}

@router.get("/cfdi/pdf/{job_id}/progress")
async def pdf_progress(job_id: str):
    """
    Se comunica con el frontend por Server-Sent Events (SSE) 
    para reportar el estado de la generación del PDF.
    """
    async def event_generator():
        # 1. Le decimos al frontend que estamos trabajando en ello
        yield 'data: {"status": "converting"}\n\n'
        
        # Simulamos un pequeño tiempo de espera de 2 segundos para que la UI respire
        await asyncio.sleep(2)
        
        # 2. Le decimos al frontend que ya terminamos.
        # Esto hará que el frontend pase a la fase de descarga.
        yield 'data: {"status": "done"}\n\n'

    # Devolvemos la respuesta como un flujo de eventos (stream)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/cfdi/pdf/{job_id}/download")
async def download_pdf(job_id: str):
    """
    Endpoint final donde el frontend descarga el documento.
    """
    print(f"Frontend solicitando descarga del PDF para el Job: {job_id}")
    
    # Este es el código binario mínimo para que el navegador reconozca un archivo como PDF.
    # Por ahora es un PDF en blanco de prueba.
    dummy_pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000109 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n176\n%%EOF"
    
    return Response(
        content=dummy_pdf_bytes, 
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cfdi_{job_id}.pdf"'
        }
    )
