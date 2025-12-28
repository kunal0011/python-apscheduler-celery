# System Flow: Job Creation to Execution

Complete step-by-step explanation of how scheduled jobs work in this system.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT REQUEST                                  │
│                    POST /api/v1/jobs (Job Creation)                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FASTAPI SERVER                                  │
│  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────────────────────┐ │
│  │   Routes    │→ │ Scheduler Svc   │→ │         PostgreSQL               │ │
│  │ scheduler.py│  │   service.py    │  │  ├─ scheduled_jobs (our table)  │ │
│  └─────────────┘  └─────────────────┘  │  └─ apscheduler_jobs (APSched)  │ │
│                          │              └──────────────────────────────────┘ │
│                          ▼                                                   │
│                   ┌─────────────────┐                                        │
│                   │   APScheduler   │ ← Triggers at scheduled time           │
│                   │  (AsyncIO)      │                                        │
│                   └────────┬────────┘                                        │
└────────────────────────────┼────────────────────────────────────────────────┘
                             │
                             ▼ execute_celery_task()
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RABBITMQ                                        │
│                         Message Broker                                       │
│  ┌─────────┐  ┌─────────┐  ┌──────────────┐  ┌───────────────┐             │
│  │ default │  │ high_   │  │ low_priority │  │   scheduled   │             │
│  │  queue  │  │priority │  │    queue     │  │     queue     │             │
│  └─────────┘  └─────────┘  └──────────────┘  └───────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CELERY WORKERS                                     │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                │
│  │ ForkPoolWorker │  │ ForkPoolWorker │  │ ForkPoolWorker │  ...           │
│  │      -1        │  │      -2        │  │      -3        │                │
│  └────────────────┘  └────────────────┘  └────────────────┘                │
│           │                   │                   │                          │
│           └───────────────────┼───────────────────┘                          │
│                               ▼                                              │
│                    Task Execution Result                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              REDIS                                           │
│  ┌──────────────────┐  ┌────────────────────────────────────────────────┐  │
│  │ Celery Results   │  │ celery-task-meta-{task_id} = {status, result}  │  │
│  └──────────────────┘  └────────────────────────────────────────────────┘  │
│  ┌──────────────────┐  ┌────────────────────────────────────────────────┐  │
│  │ Idempotency Keys │  │ idem:{key} = {task_id, status}                 │  │
│  └──────────────────┘  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Flow

### Phase 1: Job Creation (API Request)

#### Step 1.1: Client Sends POST Request
```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-cron-job",
    "trigger_type": "cron",
    "trigger_config": {"second": "*/30"},
    "task_name": "app.core.celery.tasks.example_task",
    "task_kwargs": {"data": {"key": "value"}}
  }'
```

#### Step 1.2: FastAPI Route Handler
**File**: `app/api/routes/scheduler.py`

```python
@router.post("", response_model=JobResponse)
async def create_job(job_data: JobCreate, db: DbSession, scheduler: SchedulerServiceDep):
    # Generate UUID for the job
    job_id = uuid.uuid4()
    
    # Create job in APScheduler
    scheduled_job = await scheduler.add_job(job_data, job_id=str(job_id))
    
    # Save to PostgreSQL
    db_job = ScheduledJob(id=job_id, ...)
    db.add(db_job)
    await db.commit()
```

#### Step 1.3: SchedulerService.add_job()
**File**: `app/core/scheduler/service.py`

```python
async def add_job(self, job_data, job_id=None):
    # Create trigger (CronTrigger, IntervalTrigger, or DateTrigger)
    trigger = self._create_trigger(job_data.trigger_type, job_data.trigger_config)
    
    # Register with APScheduler
    job = self.scheduler.add_job(
        func=execute_celery_task,  # Standalone function
        trigger=trigger,
        id=job_id,
        kwargs={
            "task_name": job_data.task_name,
            "task_args": job_data.task_args,
            "task_kwargs": job_data.task_kwargs,
            "idempotency_key": job_data.idempotency_key,
        },
    )
```

#### Step 1.4: Data Persisted to PostgreSQL

**Two tables are updated:**

| Table | Purpose | Data Stored |
|-------|---------|-------------|
| `scheduled_jobs` | Our application table | Job metadata, status, run counts |
| `apscheduler_jobs` | APScheduler's job store | Serialized job, trigger, next_run_time |

```sql
-- scheduled_jobs (our table)
INSERT INTO scheduled_jobs (id, name, trigger_type, task_name, status, ...)
VALUES ('48b2cad9-...', 'my-cron-job', 'cron', 'example_task', 'active', ...);

-- apscheduler_jobs (APScheduler's table)
INSERT INTO apscheduler_jobs (id, next_run_time, job_state)
VALUES ('48b2cad9-...', 1766913630, <pickled_job_object>);
```

---

### Phase 2: Scheduled Trigger (APScheduler)

#### Step 2.1: APScheduler Monitors Time

APScheduler runs in the FastAPI process and continuously checks:
```python
# Inside APScheduler (every second)
for job in jobs:
    if job.next_run_time <= current_time:
        execute_job(job)
        update_next_run_time(job)
```

#### Step 2.2: Trigger Fires at Scheduled Time

When `next_run_time` is reached (e.g., at :00 and :30 seconds):

```
[14:35:30] APScheduler: Job 48b2cad9-... triggered
[14:35:30] Calling execute_celery_task(...)
```

#### Step 2.3: execute_celery_task() Submits to Celery

**File**: `app/core/scheduler/service.py`

```python
def execute_celery_task(task_name, task_args, task_kwargs, idempotency_key, queue):
    # Prepare headers for idempotency
    headers = {}
    if idempotency_key:
        headers["idempotency_key"] = idempotency_key
    
    # Submit task to Celery via RabbitMQ
    result = celery_app.send_task(
        task_name,
        args=task_args,
        kwargs=task_kwargs,
        queue=queue,
        headers=headers,
    )
    return result.id
```

---

### Phase 3: Message Queue (RabbitMQ)

#### Step 3.1: Task Published to Queue

Celery serializes the task and publishes to RabbitMQ:

```
Exchange: default
Routing Key: default
Queue: default
Message: {
  "task": "app.core.celery.tasks.example_task",
  "id": "abc123-task-id",
  "kwargs": {"data": {"key": "value"}},
  "headers": {"idempotency_key": null}
}
```

#### Step 3.2: Message Waiting for Consumer

```
RabbitMQ Queues:
├── default          (1 message waiting)
├── high_priority    (0 messages)
├── low_priority     (0 messages)
└── scheduled        (0 messages)
```

---

### Phase 4: Celery Worker Execution

#### Step 4.1: Worker Picks Up Task

A Celery worker process consumes the message:

```
[Worker] Task app.core.celery.tasks.example_task[abc123] received
```

#### Step 4.2: Task Function Executes

**File**: `app/core/celery/tasks.py`

```python
@celery_app.task(base=BaseTask, bind=True)
def example_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
    # BaseTask.before_start() - logging
    logger.info(f"Task starting: {self.name}")
    
    # Actual task logic
    result = {
        "processed": True,
        "input": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "worker": self.request.hostname,
    }
    
    # BaseTask.on_success() - metrics
    return result
```

#### Step 4.3: Task Lifecycle Hooks

The `BaseTask` class provides lifecycle hooks:

| Hook | When Called | Action |
|------|-------------|--------|
| `before_start()` | Before execution | Log task start, record metrics |
| `on_success()` | After successful completion | Increment success counter |
| `on_failure()` | On exception | Increment failure counter, log error |
| `on_retry()` | Before retry | Increment retry counter |

---

### Phase 5: Result Storage (Redis)

#### Step 5.1: Celery Stores Result in Redis

After task completes, Celery stores the result:

```
Key: celery-task-meta-abc123-task-id
Value: {
  "status": "SUCCESS",
  "result": {
    "processed": true,
    "input": {"key": "value"},
    "timestamp": "2025-12-28T09:05:30+00:00",
    "worker": "celery@Kunals-MacBook-Pro.local"
  },
  "date_done": "2025-12-28T09:05:30.015+00:00",
  "task_id": "abc123-task-id"
}
TTL: 86400 seconds (1 day)
```

#### Step 5.2: Idempotency Key (If Provided)

If task has idempotency enabled:

```
Key: idem:order-123
Value: {"task_id": "abc123", "status": "completed"}
TTL: 3600 seconds (1 hour)
```

---

### Phase 6: Monitoring & Observability

#### Step 6.1: Prometheus Metrics Updated

```python
# Counters incremented
celery_task_counter.labels(task_name="example_task", status="success").inc()
job_execution_counter.labels(status="success").inc()
```

#### Step 6.2: Flower Dashboard Updated

Flower queries Celery and shows:
- Task ID
- Task name
- kwargs
- Result
- Received time
- Started time
- Runtime
- Worker

#### Step 6.3: Logs Generated

```
[14:35:30] INFO - Task starting: app.core.celery.tasks.example_task
[14:35:30] INFO - Processing example task with data: {'key': 'value'}
[14:35:30] INFO - Task completed successfully: app.core.celery.tasks.example_task
[14:35:30] INFO - Task succeeded in 0.002s: {'processed': True, ...}
```

---

## Data Flow Summary

| Step | Component | Action | Storage |
|------|-----------|--------|---------|
| 1 | Client | POST /api/v1/jobs | - |
| 2 | FastAPI | Validate & create job | PostgreSQL: `scheduled_jobs` |
| 3 | SchedulerService | Register with APScheduler | PostgreSQL: `apscheduler_jobs` |
| 4 | APScheduler | Wait for trigger time | In-memory + PostgreSQL |
| 5 | APScheduler | Trigger fires | - |
| 6 | execute_celery_task | Submit to Celery | RabbitMQ: message queue |
| 7 | RabbitMQ | Hold message | In-memory + disk |
| 8 | Celery Worker | Consume & execute | - |
| 9 | Celery | Store result | Redis: `celery-task-meta-*` |
| 10 | Prometheus | Collect metrics | In-memory + scrape |
| 11 | Flower | Display dashboard | Query Celery API |

---

## Why 2 Executions Per Minute?

Your cron trigger `{"second": "*/30"}` means:

```
Minute :00  →  Second 00  →  Task executed
            →  Second 30  →  Task executed
Minute :01  →  Second 00  →  Task executed
            →  Second 30  →  Task executed
...
```

**Total: 2 executions per minute** (at :00 and :30 of each minute)

---

## Key Components Reference

| Component | Location | Purpose |
|-----------|----------|---------|
| API Routes | `app/api/routes/scheduler.py` | Job CRUD endpoints |
| Scheduler Service | `app/core/scheduler/service.py` | APScheduler wrapper |
| Celery App | `app/core/celery/app.py` | Celery configuration |
| Task Definitions | `app/core/celery/tasks.py` | Task implementations |
| Database Models | `app/db/models/job.py` | SQLAlchemy models |
| Idempotency | `app/core/idempotency/service.py` | Duplicate prevention |
