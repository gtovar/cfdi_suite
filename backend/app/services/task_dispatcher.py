import json
import os
from google.cloud import tasks_v2

# Configuración que debes tener en tus variables de entorno
GCP_PROJECT = os.getenv("GCP_PROJECT", "ultra-acre-431617-p0")
GCP_REGION = "us-central1"
QUEUE_NAME = "pdf-generator-queue" 

# La URL pública de tu API de Cloud Run (ej. https://cfdi-suite-api-xyz.a.run.app)
API_URL = os.getenv("API_URL", "https://TU_URL_DE_CLOUD_RUN.a.run.app")

def enqueue_pdf_generation(job_id: str, xml_b64: str, template_id: str, html_shell: str = None):
    """Encola un trabajo en Google Cloud Tasks."""
    
    client = tasks_v2.CloudTasksClient()
    
    # Construye la ruta de la cola
    parent = client.queue_path(GCP_PROJECT, GCP_REGION, QUEUE_NAME)

    # El payload que le mandaremos al endpoint interno
    payload = {
        "job_id": job_id,
        "xml_b64": xml_b64,
        "template_id": template_id,
        "html_shell": html_shell
    }

    # Construimos la petición HTTP que Google Tasks hará por nosotros
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/internal/generate-pdf",
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }

    # Mandamos la tarea a la cola
    response = client.create_task(request={"parent": parent, "task": task})
    print(f"Tarea encolada en Cloud Tasks: {response.name}")
    return response.name
