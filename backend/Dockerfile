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

# Por defecto, la imagen arranca la API web
CMD ["sh", "-c", "if [ '$MODE' = 'worker' ]; then (while true; do echo -e 'HTTP/1.1 200 OK\nContent-Type: application/json\n\n{\"status\":\"alive\"}' | nc -l -p 8080; done & python3 -m arq app.workers.pdf_worker.WorkerSettings); else uvicorn app.main:app --host 0.0.0.0 --port 8080; fi"]
