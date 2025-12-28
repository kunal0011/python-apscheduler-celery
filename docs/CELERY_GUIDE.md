# Celery Deep Dive: Complete Guide

Understanding Celery, message brokers, result backends, workers, idempotency, and production deployment.

---

## Table of Contents
1. [What is Celery?](#what-is-celery)
2. [Why RabbitMQ?](#why-rabbitmq-message-broker)
3. [Why Redis?](#why-redis-result-backend)
4. [How Workers Work](#how-workers-work)
5. [Idempotency Explained](#idempotency-explained)
6. [Production Deployment](#production-deployment)

---

## What is Celery?

Celery is a **distributed task queue** that enables you to run code asynchronously outside of your main application.

### The Problem It Solves

```
WITHOUT CELERY:
┌─────────────┐      Request         ┌─────────────┐
│   Client    │ ──────────────────→  │   FastAPI   │
│             │                      │             │
│  Waiting... │ ← 30 seconds later   │  Processing │
│  Waiting... │                      │  heavy task │
│  Waiting... │ ←─────────────────   │             │
└─────────────┘      Response        └─────────────┘

WITH CELERY:
┌─────────────┐      Request         ┌─────────────┐
│   Client    │ ──────────────────→  │   FastAPI   │
│             │ ←─────────────────   │ "Task queued│
│  Continues  │   Instant Response   │ ID: abc123" │
│  working    │                      └──────┬──────┘
└─────────────┘                             │
                                            ▼
                                     ┌─────────────┐
                                     │   Celery    │ ← Processes in background
                                     │   Worker    │
                                     └─────────────┘
```

---

## Why RabbitMQ? (Message Broker)

### Role of Message Broker

The message broker is the **middleman** between your application and workers.

```
┌──────────┐    "Do this task"    ┌──────────────┐    "Task ready"    ┌──────────┐
│ FastAPI  │ ──────────────────→  │   RabbitMQ   │ ──────────────────→ │  Worker  │
│ (Producer)│                     │   (Broker)   │                     │(Consumer)│
└──────────┘                      └──────────────┘                     └──────────┘
```

### Why Not Send Directly to Worker?

| Issue | Without Broker | With RabbitMQ |
|-------|---------------|---------------|
| **Worker offline** | Task lost forever | Message persisted, retried |
| **Spike in traffic** | Workers overwhelmed | Queue buffers requests |
| **Multiple workers** | How to distribute? | Round-robin automatic |
| **Worker crashes** | Task lost forever | Task requeued to another worker |
| **Prioritization** | No way to prioritize | Multiple queues with priorities |

### How RabbitMQ Works Here

```
                        ┌─────────────────────────────────────────┐
                        │              RABBITMQ                    │
                        │                                         │
FastAPI sends task ──→  │  ┌─────────────────────────────────┐   │
                        │  │     EXCHANGES                    │   │
                        │  │  ┌─────────┐ ┌─────────────────┐│   │
                        │  │  │ default │ │  high_priority  ││   │
                        │  │  └────┬────┘ └────────┬────────┘│   │
                        │  └───────┼───────────────┼─────────┘   │
                        │          ▼               ▼              │
                        │  ┌─────────────────────────────────┐   │
                        │  │     QUEUES                       │   │
                        │  │  ┌─────────┐ ┌─────────────────┐│   │
                        │  │  │ default │ │  high_priority  ││   │  ──→ Workers
                        │  │  │ (5 msgs)│ │    (2 msgs)     ││   │      consume
                        │  │  └─────────┘ └─────────────────┘│   │
                        │  └─────────────────────────────────┘   │
                        └─────────────────────────────────────────┘
```

### Our Queue Configuration
**File**: `app/core/celery/app.py`

```python
task_queues = (
    Queue("default", Exchange("default"), routing_key="default"),
    Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
    Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
    Queue("scheduled", Exchange("scheduled"), routing_key="scheduled"),
)
```

---

## Why Redis? (Result Backend)

### Role of Result Backend

The result backend stores **task results** so you can retrieve them later.

```
┌──────────┐                     ┌──────────┐                     ┌─────────┐
│  Worker  │  "Result: {...}"   │  Redis   │  "Get result"      │ FastAPI │
│          │ ─────────────────→ │          │ ←───────────────── │         │
│          │                     │ Stores   │ ─────────────────→ │ Shows   │
│          │                     │ result   │  "{...}"           │ to user │
└──────────┘                     └──────────┘                     └─────────┘
```

### Why Not Use RabbitMQ for Results?

| Feature | RabbitMQ | Redis |
|---------|----------|-------|
| **Speed** | Good | Faster (in-memory) |
| **Key-Value Storage** | No | Yes (perfect for results) |
| **TTL (auto-expire)** | Manual | Built-in |
| **Querying by Task ID** | Difficult | Easy: `GET celery-task-meta-{id}` |

### What's Stored in Redis

```
# Task Result
KEY: celery-task-meta-abc123-def456
VALUE: {
  "status": "SUCCESS",
  "result": {"processed": true, "data": {...}},
  "date_done": "2025-12-28T09:30:00+00:00",
  "traceback": null
}
TTL: 86400 (1 day, configurable)

# Idempotency Key (our custom usage)
KEY: idem:order-12345
VALUE: {"task_id": "abc123", "status": "completed"}
TTL: 3600 (1 hour)
```

### Redis Also Used For:
1. **Distributed locks** (prevent duplicate scheduler execution)
2. **Idempotency keys** (prevent duplicate task execution)
3. **Rate limiting** (if implemented)

---

## How Workers Work

### Worker Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         CELERY WORKER PROCESS                               │
│                                                                            │
│  celery -A app.core.celery.app worker --concurrency=4                     │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                      MAIN PROCESS (PID: 1000)                        │  │
│  │                                                                      │  │
│  │   - Manages child processes                                         │  │
│  │   - Connects to RabbitMQ                                            │  │
│  │   - Receives messages from queues                                   │  │
│  │   - Distributes to pool workers                                     │  │
│  └──────────────────────────────┬──────────────────────────────────────┘  │
│                                 │                                          │
│            ┌────────────────────┼────────────────────┐                    │
│            ▼                    ▼                    ▼                    │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐          │
│  │ ForkPoolWorker-1 │ │ ForkPoolWorker-2 │ │ ForkPoolWorker-3 │ ...      │
│  │   (PID: 1001)    │ │   (PID: 1002)    │ │   (PID: 1003)    │          │
│  │                  │ │                  │ │                  │          │
│  │ Executes tasks   │ │ Executes tasks   │ │ Executes tasks   │          │
│  │ independently    │ │ independently    │ │ independently    │          │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘          │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Where Workers Are Created

Workers are **NOT created inside your FastAPI app**. They are **separate processes**.

```bash
# This command creates worker processes
celery -A app.core.celery.app worker --concurrency=4

# Breakdown:
# -A app.core.celery.app  → Import Celery app from this module
# worker                   → Start in worker mode
# --concurrency=4          → Create 4 child processes to execute tasks
```

### Pool Types

| Pool | Best For | How It Works |
|------|----------|--------------|
| **prefork** (default) | CPU-bound tasks | Multiple processes |
| **eventlet** | I/O-bound tasks | Greenlets (cooperative threading) |
| **gevent** | I/O-bound tasks | Greenlets |
| **solo** | Debugging | Single process, no concurrency |

---

## Idempotency Explained

### What is Idempotency?

**Idempotent operation**: Running it multiple times produces the same result as running it once.

```
IDEMPOTENT:
  process_payment("order-123")  →  $100 charged
  process_payment("order-123")  →  $100 charged (same, not $200)
  process_payment("order-123")  →  $100 charged (still same)

NOT IDEMPOTENT:
  process_payment("order-123")  →  $100 charged
  process_payment("order-123")  →  $200 charged (double charge!)
  process_payment("order-123")  →  $300 charged (triple charge!!)
```

### How Idempotency Works in This System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        IDEMPOTENCY FLOW                                      │
│                                                                              │
│  Task arrives: process_order(order_id="123")                                │
│                                                                              │
│      ┌─────────────────────────────────────────────────────────────────┐    │
│      │ Step 1: Generate idempotency key                                 │    │
│      │         key = "idem:process_order:123"                           │    │
│      └─────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│      ┌─────────────────────────────────────────────────────────────────┐    │
│      │ Step 2: Try to acquire lock in Redis                            │    │
│      │         SET idem:process_order:123 "processing" NX EX 3600      │    │
│      └─────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│              ┌────────────────┴────────────────┐                            │
│              ▼                                 ▼                            │
│      ┌──────────────────┐            ┌──────────────────┐                   │
│      │ Lock acquired    │            │ Lock NOT acquired│                   │
│      │ (First request)  │            │ (Duplicate!)     │                   │
│      └────────┬─────────┘            └────────┬─────────┘                   │
│               │                               │                              │
│               ▼                               ▼                              │
│      ┌──────────────────┐            ┌──────────────────┐                   │
│      │ Execute task     │            │ Skip execution   │                   │
│      │ Store result     │            │ Return cached or │                   │
│      │ Release lock     │            │ None             │                   │
│      └──────────────────┘            └──────────────────┘                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation

**File**: `app/core/celery/idempotent.py`

```python
@idempotent_task(ttl=3600)  # Prevent duplicate for 1 hour
def process_payment(order_id: str):
    # Even if called 10 times in 1 hour,
    # this only executes ONCE for the same order_id
    charge_customer(order_id)
```

---

## Production Deployment

### Do You Need Separate Processes?

**YES!** In production, you typically run **4 separate processes**:

| Process | Purpose | How to Run |
|---------|---------|------------|
| 1. **FastAPI** | Handle HTTP requests | `uvicorn app.main:app` |
| 2. **Celery Worker** | Execute tasks | `celery -A app.core.celery.app worker` |
| 3. **Celery Beat** | Periodic task scheduler | `celery -A app.core.celery.app beat` |
| 4. **APScheduler** | Custom job scheduler | Runs inside FastAPI (lifespan) |

### Production Architecture

```
                                    LOAD BALANCER
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ▼                    ▼                    ▼
            ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
            │   FastAPI    │     │   FastAPI    │     │   FastAPI    │
            │  Instance 1  │     │  Instance 2  │     │  Instance 3  │
            │ + APScheduler│     │ + APScheduler│     │ + APScheduler│
            └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
                   │                    │                    │
                   └────────────────────┼────────────────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │    RabbitMQ      │
                              │  (Message Broker)│
                              └────────┬─────────┘
                                       │
             ┌─────────────────────────┼─────────────────────────┐
             │                         │                         │
             ▼                         ▼                         ▼
    ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
    │  Celery Worker   │     │  Celery Worker   │     │  Celery Worker   │
    │   (4 processes)  │     │   (4 processes)  │     │   (4 processes)  │
    │                  │     │                  │     │                  │
    │  Machine 1       │     │  Machine 2       │     │  Machine 3       │
    └──────────────────┘     └──────────────────┘     └──────────────────┘
```

### Docker Compose Production Example

```yaml
services:
  # API Servers (can scale)
  api:
    image: my-scheduler:latest
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    deploy:
      replicas: 3  # Run 3 instances

  # Celery Workers (can scale)
  worker:
    image: my-scheduler:latest
    command: celery -A app.core.celery.app worker --concurrency=4
    deploy:
      replicas: 5  # Run 5 worker containers × 4 processes = 20 workers

  # Celery Beat (ONLY ONE!)
  beat:
    image: my-scheduler:latest
    command: celery -A app.core.celery.app beat
    deploy:
      replicas: 1  # MUST be exactly 1

  # Infrastructure
  rabbitmq:
    image: rabbitmq:3-management
  
  redis:
    image: redis:7-alpine
  
  postgres:
    image: postgres:15-alpine
```

### Kubernetes Deployment

```yaml
# Worker Deployment (Scalable)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
spec:
  replicas: 10  # 10 pods × 4 concurrency = 40 workers
  template:
    spec:
      containers:
        - name: worker
          image: my-scheduler:latest
          command: ["celery", "-A", "app.core.celery.app", "worker", "--concurrency=4"]
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
```

### How Tasks Get Distributed

```
Task submitted: process_order("123")
        │
        ▼
   ┌──────────┐
   │ RabbitMQ │  ──→  Round-robin to available workers
   └──────────┘
        │
        ├──→ Worker A (Machine 1) - BUSY
        ├──→ Worker B (Machine 1) - BUSY  
        ├──→ Worker C (Machine 2) - IDLE ✓ Gets the task
        └──→ Worker D (Machine 2) - BUSY
```

### Why Multiple Workers?

| Benefit | Explanation |
|---------|-------------|
| **Parallelism** | Process many tasks simultaneously |
| **Fault tolerance** | If one worker dies, others continue |
| **Scalability** | Add more workers as load increases |
| **Isolation** | One failing task doesn't affect others |

---

## Summary

| Component | Purpose | Runs As |
|-----------|---------|---------|
| **FastAPI** | HTTP API + APScheduler | Web server process |
| **RabbitMQ** | Message queue (task delivery) | Separate service |
| **Redis** | Result storage + Locks + Idempotency | Separate service |
| **Celery Worker** | Task execution | Separate worker process(es) |
| **PostgreSQL** | Persistent job & execution data | Separate service |

### Minimum Production Setup

You need to run **at least**:

```bash
# Terminal 1: API Server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Celery Worker(s)
celery -A app.core.celery.app worker --concurrency=4

# Plus Docker containers for:
# - RabbitMQ
# - Redis
# - PostgreSQL
```

For high availability, scale each component independently based on load.
