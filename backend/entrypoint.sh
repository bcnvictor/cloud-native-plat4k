#!/bin/sh
set -e

alembic -c /app/backend/alembic.ini upgrade head

exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
