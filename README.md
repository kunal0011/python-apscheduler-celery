# Idempotent Scheduler System

A production-grade distributed task scheduling system with idempotency guarantees using Python, APScheduler, Celery, Redis, PostgreSQL, and FastAPI.

## Features

- **Idempotent Task Execution**: Exactly-once execution guarantees with configurable TTL
- **Distributed Scheduling**: APScheduler with PostgreSQL job store for persistent, distributed scheduling
- **Task Distribution**: Celery workers with RabbitMQ for reliable task processing
- **Distributed Locking**: Redis-based locks to prevent duplicate job execution
- **Production Monitoring**: Prometheus metrics and Grafana dashboards
- **RESTful API**: FastAPI endpoints for job and task management

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   FastAPI API   │────▶│   APScheduler   │────▶│  Celery Workers │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   PostgreSQL    │     │      Redis      │     │    RabbitMQ     │
│   (Job Store)   │     │  (Locks/Cache)  │     │  (Msg Broker)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Poetry (for dependency management)

### Development Setup

1. **Clone and install dependencies**:
   ```bash
   git clone <repository-url>
   cd python-apscheduler-celery
   poetry install
   ```

2. **Start infrastructure services**:
   ```bash
   docker-compose -f docker/docker-compose.dev.yml up -d postgres redis rabbitmq
   ```

3. **Run database migrations**:
   ```bash
   poetry run alembic upgrade head
   ```

4. **Start the application**:
   ```bash
   # Terminal 1: API Server
   poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

   # Terminal 2: Celery Worker
   poetry run celery -A app.core.celery.app worker --loglevel=info

   # Terminal 3: Scheduler
   poetry run python -m app.core.scheduler.service
   ```

### Using Docker Compose

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up --build

# View logs
docker-compose -f docker/docker-compose.yml logs -f
```

## API Endpoints

### Jobs (Scheduled Tasks)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/jobs` | Create a new scheduled job |
| GET | `/api/v1/jobs` | List all jobs |
| GET | `/api/v1/jobs/{job_id}` | Get job details |
| DELETE | `/api/v1/jobs/{job_id}` | Remove a job |
| POST | `/api/v1/jobs/{job_id}/pause` | Pause a job |
| POST | `/api/v1/jobs/{job_id}/resume` | Resume a job |

### Tasks (Immediate Execution)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tasks/submit` | Submit a task for immediate execution |
| GET | `/api/v1/tasks/{task_id}` | Get task status |
| GET | `/api/v1/tasks/{task_id}/result` | Get task result |

### Health Checks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Basic health check |
| GET | `/health/ready` | Readiness probe |
| GET | `/health/live` | Liveness probe |

## Configuration

Configuration is managed via environment variables. See `.env.example` for all options.

## Monitoring

- **Prometheus Metrics**: Available at `/metrics`
- **Grafana Dashboards**: Pre-configured dashboards in `monitoring/grafana/dashboards/`

## Testing

```bash
# Run unit tests
poetry run pytest tests/unit/ -v

# Run integration tests
docker-compose -f docker/docker-compose.test.yml up -d
poetry run pytest tests/integration/ -v

# Run with coverage
poetry run pytest --cov=app --cov-report=html
```

## Project Structure

```
app/
├── api/              # FastAPI routes and dependencies
├── core/             # Core modules (scheduler, celery, idempotency)
├── db/               # Database models and session management
├── schemas/          # Pydantic schemas
└── monitoring/       # Metrics and logging configuration
```

## License

MIT License
