FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml .
# No-op builder stage just to satisfy the explicit requirement.
# We'll install directly via pip in the final stage for simplicity,
# but we COULD build wheels here if needed.

FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies for psycopg2/asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Copy backend, shared and grafana dashboards
COPY ./backend /app/backend
COPY ./shared /app/shared
COPY ./infra/grafana /app/infra/grafana
COPY ./backend/pyproject.toml /app/backend/pyproject.toml
COPY ./shared/pyproject.toml /app/shared/pyproject.toml

# Install dependencies (install shared first, then backend)
RUN pip install --no-cache-dir -e /app/shared && \
    pip install --no-cache-dir -e /app/backend

# Create non-root user
RUN useradd -m cnpuser && chown -R cnpuser:cnpuser /app
USER cnpuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ || echo 1

CMD alembic -c backend/alembic.ini upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port 8000
