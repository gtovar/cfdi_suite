import json
import os
from google.cloud import tasks_v2

GCP_PROJECT = os.getenv("GCP_PROJECT", "ultra-acre-431617-p0")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")
QUEUE_NAME = os.getenv("CFDI_QUEUE_NAME", "pdf-generator-queue") 
API_URL = os.getenv("API_URL", "https://TU_URL_DE_CLOUD_RUN.a.run.app")

_client = None

def get_tasks_client():
    global _client
    if _client is None:
        _client = tasks_v2.CloudTasksClient()
    return _client

def enqueue_pdf_generation(job_id: str, xml_b64: str, template_id: str, html_shell: str = None):
    client = get_tasks_client()  # Se inicializa de forma segura aquí
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
    response = client.create_task(request={"parent": parent, "task": task})
    return response.name

def enqueue_cfdi_analysis(batch_id: str, filename: str, xml_str: str):
    """Inyecta el análisis asíncrono de un CFDI a la cola de Cloud Tasks."""
    parent = client.queue_path(GCP_PROJECT, GCP_REGION, QUEUE_NAME)
    
    payload = {
        "batch_id": batch_id,
        "filename": filename,
        "xml_str": xml_str
    }
    
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/cfdi/batch/worker-task",
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }
    
    client.create_task(request={"parent": parent, "task": task})
