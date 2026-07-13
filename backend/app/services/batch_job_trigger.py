"""
batch_job_trigger.py — Dispara el Cloud Run Job de shards para batches
grandes ("artillería pesada", Capa 1 de docs/propuesta-arquitectura-batch.md).

APAGADO POR DEFECTO (BATCH_JOB_ENABLED=false) — importar este módulo o tener
este código en el repo no cambia nada del comportamiento actual. Solo se
activa configurando BATCH_JOB_ENABLED=true y un BATCH_JOB_THRESHOLD real en
las variables de entorno del servicio, después de:
  1. desplegar el Job en sí (ver infra/deploy-batch-shard-job.sh, no se
     ejecuta solo — hay que correrlo a mano con confirmación explícita), y
  2. decidir el umbral real (ver la sección "Ronda 0.5" del documento — el
     costo nunca es la razón para el umbral, es la latencia de arranque en
     frío de una tarea nueva de Cloud Run Job frente a un worker ya caliente
     del camino actual para batches chicos).
"""
from __future__ import annotations

import math
import os

BATCH_JOB_ENABLED = os.getenv("BATCH_JOB_ENABLED", "false").lower() == "true"
# Default deliberadamente altísimo: aunque alguien active BATCH_JOB_ENABLED
# sin fijar un umbral real, esto no dispara nada por accidente.
BATCH_JOB_THRESHOLD = int(os.getenv("BATCH_JOB_THRESHOLD", "999999999"))
BATCH_JOB_SHARD_SIZE = int(os.getenv("BATCH_JOB_SHARD_SIZE", "100"))

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "ultra-acre-431617-p0")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")
BATCH_JOB_NAME = os.getenv("BATCH_JOB_NAME", "cfdi-batch-shard")


def should_use_batch_job(total_xmls: int) -> bool:
    return BATCH_JOB_ENABLED and total_xmls >= BATCH_JOB_THRESHOLD


def trigger_batch_shard_job(
    batch_id: str, total_xmls: int, template_id: str, zip_gcs_path: str | None = None
) -> str:
    """
    Dispara UNA ejecución del Job `cfdi-batch-shard`, con tantas tareas como
    shards de BATCH_JOB_SHARD_SIZE hagan falta para cubrir total_xmls.
    No bloquea a que termine — devuelve el nombre de la operación de larga
    duración para loguearlo.

    Precondición (camino de siempre, zip_gcs_path=None): el manifiesto del
    batch (pdf:batch_ids:{batch_id} en Redis) y los XMLs
    (xml_temp/{job_id}.xml en GCS) ya deben existir completos — llamar esto
    solo después de que la extracción del ZIP haya terminado.

    zip_gcs_path (opcional, default None por compatibilidad con llamadores
    existentes): ruta del ZIP original en GCS. Si se pasa, se propaga como
    ZIP_GCS_PATH a cada tarea vía env var -- ver batch_shard_worker.py, que
    usa su presencia para decidir si lee sus XMLs directo del ZIP remoto
    (lecturas por rango, sin xml_temp/) en vez del camino de siempre.
    """
    # Import perezoso: google-cloud-run solo hace falta si este camino está
    # activo — así no se vuelve una dependencia dura del arranque normal.
    from google.cloud import run_v2

    n_tasks = math.ceil(total_xmls / BATCH_JOB_SHARD_SIZE)
    client = run_v2.JobsClient()
    job_path = client.job_path(GCP_PROJECT_ID, GCP_REGION, BATCH_JOB_NAME)

    env = [
        run_v2.EnvVar(name="BATCH_ID", value=batch_id),
        run_v2.EnvVar(name="TEMPLATE_ID", value=template_id),
        run_v2.EnvVar(name="SHARD_SIZE", value=str(BATCH_JOB_SHARD_SIZE)),
    ]
    if zip_gcs_path:
        env.append(run_v2.EnvVar(name="ZIP_GCS_PATH", value=zip_gcs_path))

    request = run_v2.RunJobRequest(
        name=job_path,
        overrides=run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(env=env)
            ],
            task_count=n_tasks,
        ),
    )
    operation = client.run_job(request=request)
    return operation.operation.name
