# The same API, packaged so it runs anywhere a container runs: locally, on
# Azure Container Apps, or on App Service. Azure Functions deploys from source
# instead (see function_app.py), so this image is the portable alternative
# rather than a second way of doing the same thing.
FROM python:3.12-slim AS base

# pymssql ships manylinux wheels, so no FreeTDS build step is needed; curl is
# here only for the healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes, so
# an edit to the application code rebuilds in seconds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the service actually imports. etl/db.py holds the connection
# helper, with its retry loop for the serverless database waking up.
COPY api/ ./api/
COPY etl/db.py ./etl/db.py

# Run as a non-root user; nothing here needs to write to disk.
RUN useradd --create-home --uid 10001 skylens
USER skylens

EXPOSE 8000
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
