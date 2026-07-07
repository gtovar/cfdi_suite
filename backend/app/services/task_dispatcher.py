import json
import os
# Importamos la versión asíncrona del cliente de Google
from google.cloud import tasks_v2

GCP_PROJECT = os.getenv("GCP_PROJECT", "ultra-acre-431617-p0")
GCP_REGION = "us-central1"
QUEUE_NAME = "pdf-generator-queue" 
API_URL = os.getenv("API_URL", "https://TU_URL_DE_CLOUD_RUN.a.run.app")

# Añadimos 'async' a la función
async def enqueue_pdf_generation(job_id: str, xml_b64: str, template_id: str, html_shell: str = None):
    """Encola un trabajo en Google Cloud Tasks de forma asíncrona."""
    
    # Usamos el cliente asíncrono
    client = tasks_v2.CloudTasksAsyncClient()
    parent = client.queue_path(GCP_PROJECT, GCP_REGION, QUEUE_NAME)

    payload = {
        "job_id": job_id,
        "xml_b64": xml_b64,
        "template_id": template_id,
        "html_shell": html_shell
    }

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/internal/generate-pdf",
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }

    # Usamos 'await' para la llamada de red
    response = await client.create_task(request={"parent": parent, "task": task})
    return response.name
