import json
import os
from google.cloud import tasks_v2
from google.api_core.exceptions import InvalidArgument
import sentry_sdk

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

def enqueue_cfdi_analysis(batch_id: str, filename: str, redis_key: str):
    """Inyecta el análisis asíncrono de un CFDI a la cola de Cloud Tasks."""
    client = get_tasks_client()  # <-- ¡Fijamos esto! Antes llamabas a client.queue_path pero la variable local no existía en esta función.
    parent = client.queue_path(GCP_PROJECT, GCP_REGION, QUEUE_NAME)
    
    payload = {
        "batch_id": batch_id,
        "filename": filename,
        "redis_key": redis_key  # <-- Enviamos la ruta de acceso en lugar del string pesado
    }
    
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/cfdi/batch/worker-task",
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }
    try:
        client.create_task(request={"parent": parent, "task": task})
    except InvalidArgument as e:
        if "Task size too large" in str(e):
            # Le avisamos a Sentry adjuntando el nombre del archivo culpable
            sentry_sdk.set_tag("batch_id", batch_id)
            sentry_sdk.set_context("archivo_culpable", {
                "nombre": filename,
                "tamaño_caracteres": len(xml_str)
            })
            sentry_sdk.capture_exception(e)
        raise e # Lo volvemos a lanzar pa
