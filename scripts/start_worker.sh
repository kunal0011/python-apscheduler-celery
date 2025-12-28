#!/bin/bash
# Start Celery worker

set -e

echo "Starting Celery worker..."

exec poetry run celery -A app.core.celery.app worker \
    --loglevel=info \
    --concurrency=4 \
    --queues=default,high_priority,low_priority,scheduled
