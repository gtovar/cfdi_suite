FROM python:3.12-slim

WORKDIR /app

# Agrega herramientas de desarrollo para poder compilar extensiones de C/C++
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

CMD ["sh", "-c", "if [ \"$MODE\" = \"worker\" ]; then arq app.workers.pdf_worker.WorkerSettings & mkdir -p /tmp/empty && cd /tmp/empty && python3 -m http.server ${PORT:-8080}; else uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}; fi"]
