FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m cnpuser

# Copy only dependency manifests first so the pip install layer is cached
# independently of source changes.
COPY ./shared/pyproject.toml /app/shared/pyproject.toml
COPY ./backend/pyproject.toml /app/backend/pyproject.toml

# Stub __init__.py so editable installs can resolve package metadata.
# The real source is copied below and takes over at runtime.
RUN mkdir -p /app/shared/shared \
             /app/backend/api/schemas \
             /app/backend/core \
             /app/backend/db \
             /app/backend/k8s \
             /app/backend/gitlab \
             /app/backend/services && \
    touch /app/shared/shared/__init__.py \
          /app/backend/__init__.py \
          /app/backend/api/__init__.py \
          /app/backend/api/schemas/__init__.py \
          /app/backend/core/__init__.py \
          /app/backend/db/__init__.py \
          /app/backend/k8s/__init__.py \
          /app/backend/gitlab/__init__.py \
          /app/backend/services/__init__.py

RUN pip install --no-cache-dir -e /app/shared && \
    pip install --no-cache-dir -e /app/backend

# Copy actual source (overwrites stubs; editable installs already wired).
COPY --chown=cnpuser:cnpuser ./backend /app/backend
COPY --chown=cnpuser:cnpuser ./shared /app/shared

USER cnpuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ || exit 1

CMD uvicorn backend.main:app --host 0.0.0.0 --port 8000
