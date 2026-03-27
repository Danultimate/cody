FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingestion/requirements.txt ingestion_requirements.txt
RUN pip install --no-cache-dir -r ingestion_requirements.txt

COPY api/ .
COPY ingestion/github_loader.py ingestion/ast_chunker.py ingestion/embedder.py ingestion/db.py ./ingestion/

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
