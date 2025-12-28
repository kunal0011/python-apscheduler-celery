#!/bin/bash
# Start the FastAPI server

set -e

echo "Starting API server..."

# Run database migrations
poetry run alembic upgrade head

# Start the server
exec poetry run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info
