#!/usr/bin/env bash
# deploy-batch-shard-job.sh — Define (o actualiza) el Cloud Run Job de shards
# para la Capa 1 de docs/propuesta-arquitectura-batch.md (Ronda 1).
#
# NO SE EJECUTA AUTOMÁTICAMENTE POR NINGÚN PIPELINE. Correr esto a mano,
# después de confirmación explícita, desde la raíz del repo:
#
#   PROJECT_ID=ultra-acre-431617-p0 ./infra/deploy-batch-shard-job.sh
#
# Reutiliza la misma imagen de contenedor que cfdi-suite-api (mismo
# Dockerfile, mismas deps de sistema para WeasyPrint/pango/cairo) — solo
# cambia el comando de arranque, que en vez de levantar uvicorn corre el
# entrypoint de la tarea (app/workers/batch_shard_worker.py).
#
# Definir el Job aquí NO ejecuta ninguna tarea ni cuesta nada — Cloud Run
# Jobs es serverless: se cobra únicamente cuando se dispara una ejecución
# (ver la sección "Ronda 0.5" del documento para el cálculo de costo real:
# ~$0.0001-0.17 por batch según tamaño, $0 en reposo).
#
# BATCH_ID / TEMPLATE_ID / SHARD_SIZE se pasan POR EJECUCIÓN vía
# --update-env-vars (ver app.services.batch_job_trigger.trigger_batch_shard_job),
# no aquí — el Job definido es el mismo para cualquier batch.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Define PROJECT_ID, ej. PROJECT_ID=ultra-acre-431617-p0}"
REGION="${REGION:-us-central1}"
JOB_NAME="${JOB_NAME:-cfdi-batch-shard}"
# Misma imagen que cfdi-suite-api (ver backend/cloudbuild.yaml) — evita
# mantener un segundo Dockerfile/build para el Job. Registro real confirmado
# 2026-07-12 (Artifact Registry, no gcr.io): buscar la imagen exacta con
# `gcloud run revisions describe <revision> --region=us-central1
# --format="value(spec.containers[0].image)"` si se quiere fijar un sha256
# específico en vez de :latest.
IMAGE="${IMAGE:-us-central1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/cfdi-suite-api:latest}"

# TODO antes de correr esto de verdad: confirmar de dónde sale
# REDIS_PASSWORD en este entorno. deploy-backend.yml (el servicio principal)
# lo pasa como GitHub secret en texto plano vía --update-env-vars — para el
# Job, considerar Secret Manager (--set-secrets=REDIS_PASSWORD=...) en vez de
# repetir el mismo patrón, ya que este script vive en el repo (no en un
# workflow con secrets de GitHub).
#
# BUG ENCONTRADO Y CORREGIDO 2026-07-12, EN VIVO, durante la primera prueba
# real (batch de 2000 XMLs vía el sitio web): esta lista original de
# --set-env-vars NO incluía PUSHER_APP_ID/PUSHER_KEY/PUSHER_SECRET/
# PUSHER_CLUSTER. Efecto: el Job procesaba los XMLs y actualizaba Redis
# correctamente (done_count subía de verdad), pero
# app.services.realtime.publish_batch_progress no podía avisar a Pusher sin
# esas credenciales (get_pusher() se apaga en silencio si faltan, no
# crashea) — resultado: el usuario veía 0% fijo en el navegador mientras el
# batch se procesaba de verdad por dentro. Se corrigió con
# `gcloud run jobs update --update-env-vars=PUSHER_...` a mitad de esa
# corrida (no retroactivo: las tareas ya en vuelo en ese momento no lo
# heredaron, solo las ejecuciones nuevas). Este script ya lo incluye para
# que no se repita en un despliegue futuro desde cero.
gcloud run jobs deploy "${JOB_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --command="python" \
  --args="-m,app.workers.batch_shard_worker" \
  --cpu=1 \
  --memory=2Gi \
  --task-timeout=600 \
  --max-retries=1 \
  --set-env-vars="GCS_BUCKET_NAME=cfdi-suite-uploads-706861124428,REDIS_HOST=dashing-aphid-43185.upstash.io,REDIS_PORT=6379,PUSHER_CLUSTER=us2"
  # REDIS_PASSWORD, PUSHER_APP_ID, PUSHER_KEY, PUSHER_SECRET: agregar aquí
  # --set-secrets o --update-env-vars según se resuelva el TODO de arriba,
  # antes de correr este script contra el proyecto real — no se dejan en
  # texto plano en este archivo versionado en git.

echo ""
echo "Job '${JOB_NAME}' definido en ${REGION}. NO se ejecutó ninguna tarea todavía."
echo ""
echo "Para probarlo manualmente con un batch_id real ya extraído (manifiesto"
echo "pdf:batch_ids:{batch_id} completo en Redis, XMLs ya en xml_temp/ de GCS):"
echo ""
echo "  gcloud run jobs execute ${JOB_NAME} --region=${REGION} --tasks=1 \\"
echo "    --update-env-vars=BATCH_ID=<batch_id-real>,TEMPLATE_ID=default,SHARD_SIZE=100"
