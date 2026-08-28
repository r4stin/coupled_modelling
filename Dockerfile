FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
COPY coupled_modelling/requirements.txt coupled_modelling/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r coupled_modelling/requirements.txt

COPY openapi.yaml ./
COPY docker/graphdb-repo-config.ttl docker/
COPY backend/ backend/

EXPOSE 5000
WORKDIR /app/backend

# Bootstrap GraphDB (no-op once done), then serve on all interfaces.
CMD ["sh", "-c", "python seed_graphdb.py && exec flask --app api run --host=0.0.0.0 --port=5000"]
