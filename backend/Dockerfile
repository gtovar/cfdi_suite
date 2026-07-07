FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Reemplaza la última línea de tu Dockerfile por esta:
CMD ["sh", "-c", "if [ '$MODE' = 'worker' ]; then (python3 -m arq app.workers.pdf_worker.WorkerSettings & uvicorn app.main:app --host 0.0.0.0 --port 8080); else uvicorn app.main:app --host 0.0.0.0 --port 8080; fi"]
