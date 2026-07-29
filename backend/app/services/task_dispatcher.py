import json
import os
import time
from google.cloud import tasks_v2
from google.api_core.exceptions import AlreadyExists, DeadlineExceeded, InternalServerError, InvalidArgument, ServiceUnavailable
import sentry_sdk

from .template_ids import validate_template_id

GCP_PROJECT = os.getenv("GCP_PROJECT", "ultra-acre-431617-p0")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")
QUEUE_NAME = os.getenv("CFDI_QUEUE_NAME", "pdf-generator-queue")
API_URL = os.getenv("API_URL", "https://TU_URL_DE_CLOUD_RUN.a.run.app")

# Identidad con la que Cloud Tasks firma los tokens OIDC de las tareas. Es la
# misma SA con la que corre el servicio (deploy-backend.yml, --service-account),
# así que la tarea llega firmada por quien la creó.
#
# Requisito de IAM: la SA necesita roles/iam.serviceAccountUser SOBRE SÍ MISMA
# para poder hacer actAs al crear la tarea. Sin ese binding, create_task falla
# con PermissionDenied. No estaba en la spec original de #26; se añadió al
# aplicar la Fase 2.
_OIDC_SERVICE_ACCOUNT = os.getenv(
    "OIDC_SERVICE_ACCOUNT",
    "cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com",
)


def _oidc_token() -> dict:
    """Bloque oidc_token para el http_request de una tarea de Cloud Tasks.

    El `audience` tiene que ser exactamente la misma cadena que el receptor
    valida (internal_auth._AUDIENCE, que también lee API_URL). Si no coinciden,
    la verificación falla y Cloud Tasks reintenta en bucle hasta agotar la cola.
    """
    return {
        "service_account_email": _OIDC_SERVICE_ACCOUNT,
        "audience": API_URL,
    }

_client = None
_TRANSIENT_TASK_ERRORS = (DeadlineExceeded, InternalServerError, ServiceUnavailable)


class TaskEnqueueUncertainError(RuntimeError):
    """Cloud Tasks pudo haber aceptado la tarea aunque no respondió.

    El llamador debe conservar el XML: borrar el insumo en este caso puede
    hacer fallar una tarea que Cloud Tasks ya registró. La regla lifecycle de
    GCS limpia ese respaldo si finalmente no hubo tarea.
    """


def get_tasks_client():
    global _client
    if _client is None:
        _client = tasks_v2.CloudTasksClient()
    return _client


def _create_task_idempotently(client, parent: str, task: dict, task_id: str) -> str:
    """Crea una Cloud Task con nombre estable para poder reintentar sin duplicar.

    La UI de XMLs sueltos reintenta peticiones cuando una respuesta se pierde.
    Sin nombre determinista, un timeout entre Cloud Tasks y Cloud Run podía
    convertir un reintento legítimo en dos conversiones del mismo XML.
    """
    task_name = client.task_path(GCP_PROJECT, GCP_REGION, QUEUE_NAME, task_id)
    task["name"] = task_name
    for attempt in range(3):
        try:
            return client.create_task(request={"parent": parent, "task": task}).name
        except AlreadyExists:
            return task_name
        except _TRANSIENT_TASK_ERRORS as exc:
            if attempt == 2:
                raise TaskEnqueueUncertainError(
                    "Cloud Tasks no confirmó la creación de la tarea"
                ) from exc
            time.sleep(0.25 * (2**attempt))

def enqueue_pdf_generation(job_id: str, xml_b64: str, template_id: str, html_shell: str = None, batch_id: str = None):
    # Este borde también protege invocaciones internas que no pasan por HTTP.
    validate_template_id(template_id)
    client = get_tasks_client()  # Se inicializa de forma segura aquí
    parent = client.queue_path(GCP_PROJECT, GCP_REGION, QUEUE_NAME)
    payload = {
        "job_id": job_id,
        "xml_b64": xml_b64,
        "template_id": template_id,
        "html_shell": html_shell,
        "batch_id": batch_id
    }
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/internal/generate-pdf",
            "oidc_token": _oidc_token(),
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }
    return _create_task_idempotently(client, parent, task, f"pdf-{job_id}")

def enqueue_zip_extraction(gcs_path: str, batch_id: str, template_id: str):
    """
    Encola la extracción de un ZIP como Cloud Task en vez de correrla como
    BackgroundTask en memoria — así el trabajo sobrevive al reciclaje de
    instancias de Cloud Run y Cloud Tasks reintenta si falla a medio camino.
    """
    # Validar antes de crear/enviar la Cloud Task, no sólo al consumirla.
    validate_template_id(template_id)
    client = get_tasks_client()
    parent = client.queue_path(GCP_PROJECT, GCP_REGION, QUEUE_NAME)
    payload = {
        "gcs_path": gcs_path,
        "batch_id": batch_id,
        "template_id": template_id,
    }
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/internal/extract-zip",
            "oidc_token": _oidc_token(),
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }
    response = client.create_task(request={"parent": parent, "task": task})
    return response.name

def enqueue_cfdi_analysis(batch_id: str, filename: str, gcs_path: str, job_id: str | None = None):
    """Inyecta el análisis asíncrono de un CFDI a la cola de Cloud Tasks.

    gcs_path apunta al XML ya subido a GCS (xml_temp_analysis/{batch_id}/{filename})
    -- antes era una llave de Redis con TTL de 1h y sin respaldo si Upstash
    perdía el valor (ver auditoría de resiliencia 2026-07-23); GCS es durable."""
    client = get_tasks_client()  # <-- ¡Fijamos esto! Antes llamabas a client.queue_path pero la variable local no existía en esta función.
    parent = client.queue_path(GCP_PROJECT, GCP_REGION, QUEUE_NAME)

    payload = {
        "batch_id": batch_id,
        "filename": filename,
        "gcs_path": gcs_path,  # <-- Enviamos la ruta de acceso en lugar del string pesado
        # Los lotes durables asignan un id por archivo. Los lotes antiguos no
        # lo traen, por compatibilidad con las tareas que ya estaban creadas.
        "job_id": job_id,
    }

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/cfdi/batch/worker-task",
            "oidc_token": _oidc_token(),
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }
    try:
        # Un nombre estable convierte un retry de /start (incluso después de
        # que ya se escribió su marcador GCS) en una operación segura. El
        # formato sólo usa letras, dígitos y guiones; UUIDs caben con margen
        # en el límite de 500 caracteres de Cloud Tasks.
        task_id = f"analysis-{batch_id}-{job_id}" if job_id else None
        if task_id:
            return _create_task_idempotently(client, parent, task, task_id)
        return client.create_task(request={"parent": parent, "task": task}).name
    except InvalidArgument as e:
        if "Task size too large" in str(e):
            # Le avisamos a Sentry adjuntando el nombre del archivo culpable
            sentry_sdk.set_tag("batch_id", batch_id)
            sentry_sdk.set_context("archivo_culpable", {"nombre": filename})
            sentry_sdk.capture_exception(e)
        raise e # Lo volvemos a lanzar pa
