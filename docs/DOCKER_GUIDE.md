# Docker & Dashboards Guide

Quick reference for Docker commands and web dashboards.

---

## 🚀 Quick Start

```bash
# Start infrastructure only (PostgreSQL, Redis, RabbitMQ)
docker-compose -f docker/docker-compose.dev.yml up -d postgres redis rabbitmq

# Start all dashboards
docker-compose -f docker/docker-compose.dev.yml up -d grafana prometheus pgadmin redis-commander flower

# Start everything
docker-compose -f docker/docker-compose.dev.yml up -d
```

---

## 🎛️ Dashboard URLs

| Dashboard | URL | Credentials | Purpose |
|-----------|-----|-------------|---------|
| **RabbitMQ** | http://localhost:15672 | `guest` / `guest` | Message broker queues |
| **pgAdmin** | http://localhost:5050 | `admin@admin.com` / `admin` | PostgreSQL database |
| **Redis Commander** | http://localhost:8081 | None | Redis keys & values |
| **Flower** | http://localhost:5555 | None | Celery workers & tasks |
| **Grafana** | http://localhost:3000 | `admin` / `admin` | Metrics dashboards |
| **Prometheus** | http://localhost:9090 | None | Raw metrics queries |

---

## 📋 Common Docker Commands

### Service Management

```bash
# View running containers
docker-compose -f docker/docker-compose.dev.yml ps

# View logs
docker-compose -f docker/docker-compose.dev.yml logs -f postgres
docker-compose -f docker/docker-compose.dev.yml logs -f redis
docker-compose -f docker/docker-compose.dev.yml logs -f rabbitmq

# Restart a service
docker-compose -f docker/docker-compose.dev.yml restart grafana

# Stop all services
docker-compose -f docker/docker-compose.dev.yml down

# Stop and remove volumes (⚠️ deletes data)
docker-compose -f docker/docker-compose.dev.yml down -v
```

### Container Shell Access

```bash
# PostgreSQL
docker exec -it docker-postgres-1 psql -U postgres -d scheduler_db

# Redis
docker exec -it docker-redis-1 redis-cli

# RabbitMQ
docker exec -it docker-rabbitmq-1 rabbitmqctl list_queues
```

---

## 🔍 Database Queries (PostgreSQL)

```bash
# Connect to PostgreSQL
docker exec -it docker-postgres-1 psql -U postgres -d scheduler_db

# List tables
\dt

# View task executions
SELECT id, celery_task_id, task_name, status, created_at FROM task_executions;

# View scheduled jobs
SELECT id, name, trigger_type, is_active FROM scheduled_jobs;
```

---

## 🔑 Redis Commands

```bash
# Connect to Redis CLI
docker exec -it docker-redis-1 redis-cli

# List all keys
KEYS *

# Get idempotency keys
KEYS idem:*

# Get Celery task results
KEYS celery-task-meta-*

# Get specific key value
GET "idem:your-key"
```

---

## 🐰 RabbitMQ Commands

```bash
# List queues
docker exec docker-rabbitmq-1 rabbitmqctl list_queues name messages consumers

# List exchanges
docker exec docker-rabbitmq-1 rabbitmqctl list_exchanges

# Purge a queue
docker exec docker-rabbitmq-1 rabbitmqctl purge_queue default
```

---

## 📊 Grafana Setup

### Adding Prometheus Data Source

1. Open http://localhost:3000
2. Login: `admin` / `admin`
3. Go to **Connections** → **Data sources** → **Add data source**
4. Select **Prometheus**
5. Set URL: `http://prometheus:9090`
6. Click **Save & test**

### Useful PromQL Queries

```promql
# Application health
up

# Total scheduled jobs
scheduler_jobs_total

# Celery task counts
celery_tasks_total

# API request rate
rate(api_requests_total[5m])

# Task execution duration (p95)
histogram_quantile(0.95, rate(celery_task_duration_seconds_bucket[5m]))
```

---

## 🔧 pgAdmin Setup

### Connecting to PostgreSQL

1. Open http://localhost:5050
2. Login: `admin@admin.com` / `admin`
3. Right-click **Servers** → **Register** → **Server**
4. **General** tab: Name = `Scheduler DB`
5. **Connection** tab:
   - Host: `postgres` (or `localhost` if outside Docker)
   - Port: `5432`
   - Username: `postgres`
   - Password: `postgres`
6. Click **Save**

---

## 🌸 Flower (Celery Dashboard)

Access: http://localhost:5555

Features:
- View active/processed/failed tasks
- Monitor worker status
- Inspect task details and results
- Real-time task graphs

---

## 📦 Service Ports Summary

| Service | Port | Protocol |
|---------|------|----------|
| FastAPI | 8000 | HTTP |
| PostgreSQL | 5432 | TCP |
| Redis | 6379 | TCP |
| RabbitMQ | 5672 | AMQP |
| RabbitMQ UI | 15672 | HTTP |
| pgAdmin | 5050 | HTTP |
| Redis Commander | 8081 | HTTP |
| Flower | 5555 | HTTP |
| Grafana | 3000 | HTTP |
| Prometheus | 9090 | HTTP |
