#!/bin/bash
# Start APScheduler process

set -e

echo "Starting APScheduler..."

exec poetry run python -m app.core.scheduler.service
