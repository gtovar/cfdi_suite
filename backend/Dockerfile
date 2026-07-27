# Imagen base fijada por digest: el tag `3.12-slim` es mutable y hoy apunta a
# una imagen distinta cada vez que Docker Hub lo republica, así que dos builds
# del mismo commit pueden no producir el mismo contenedor.
#
# Para actualizarla (revisar el changelog de la base antes de subir el digest):
#   TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull" \
#     | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
#   curl -sI -H "Authorization: Bearer $TOKEN" \
#     -H "Accept: application/vnd.oci.image.index.v1+json" \
#     https://registry-1.docker.io/v2/library/python/manifests/3.12-slim \
#     | grep -i docker-content-digest
# (o `docker buildx imagetools inspect python:3.12-slim` si hay daemon)
#
# Digest tomado el 2026-07-26. Es el índice multi-arquitectura, no el manifest
# de una sola plataforma: incluye linux/amd64, que es lo que corre Cloud Run.
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libxml2-dev \
    libxslt-dev \
    libxml2 \
    libxslt1.1 \
    libgobject-2.0-0 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# Un solo comando, limpio y directo para tu API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
