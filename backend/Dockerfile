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
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.txt

FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    libgobject-2.0-0 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . .

# El contenedor corría como root. En Cloud Run el panel lo calificó
# NO_EXPLOTABLE (gVisor aísla el kernel), pero cuesta dos líneas y es lo que
# limita el daño si el servicio se migra a GKE o se corre en local con Docker.
# Va después del COPY para que el chown alcance los archivos ya copiados.
RUN useradd -m -u 1000 app && chown -R app:app /app

# HOME explícito, no opcional: credentials.py:9 y fiel_config.py:9 guardan la
# llave Fernet y los datos cifrados en `Path.home()/.cfdi-suite`, y lo crean en
# el primer uso con mkdir(mode=0o700). Path.home() lee la variable HOME antes
# de caer al /etc/passwd, y si el runtime la deja heredada en /root el usuario
# `app` no puede escribir ahí y el flujo de emisores/FIEL revienta. Fijándola
# aquí el resultado es el mismo en Docker local, Cloud Run y GKE.
ENV HOME=/home/app
USER app

ENV PYTHONUNBUFFERED=1

# Cloud Run no usa HEALTHCHECK (tiene sus propios probes); esto sirve para
# Docker local y CI. La ruta es /api/health, no /health -- ver main.py:154.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

# Un solo comando, limpio y directo para tu API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
