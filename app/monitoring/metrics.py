"""
Prometheus Metrics

Metrics collection for monitoring the scheduler system.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# Application info
app_info = Info("scheduler_app", "Scheduler application information")

# Job metrics
scheduler_jobs_total = Gauge(
    "scheduler_jobs_total",
    "Total number of scheduled jobs",
)

jobs_created_counter = Counter(
    "scheduler_jobs_created_total",
    "Total jobs created",
    ["trigger_type"],
)

jobs_deleted_counter = Counter(
    "scheduler_jobs_deleted_total",
    "Total jobs deleted",
    ["trigger_type"],
)

job_execution_counter = Counter(
    "scheduler_job_executions_total",
    "Total job executions",
    ["status"],  # success, error, missed
)

job_execution_duration = Histogram(
    "scheduler_job_execution_duration_seconds",
    "Job execution duration in seconds",
    ["job_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# Celery task metrics
celery_task_counter = Counter(
    "celery_tasks_total",
    "Total Celery tasks",
    ["task_name", "status"],  # success, failure, retry
)

celery_task_duration = Histogram(
    "celery_task_duration_seconds",
    "Celery task duration in seconds",
    ["task_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

tasks_submitted_counter = Counter(
    "scheduler_tasks_submitted_total",
    "Total tasks submitted for immediate execution",
    ["task_name"],
)

# Idempotency metrics
idempotency_hits_counter = Counter(
    "idempotency_hits_total",
    "Idempotency cache hits (duplicates prevented)",
    ["task_name"],
)

idempotency_misses_counter = Counter(
    "idempotency_misses_total",
    "Idempotency cache misses (new executions)",
)

idempotency_lock_acquired_counter = Counter(
    "idempotency_locks_acquired_total",
    "Idempotency locks acquired",
)

# API metrics
api_requests_total = Counter(
    "api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status_code"],
)

api_request_duration = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Resource metrics
active_workers = Gauge(
    "celery_active_workers",
    "Number of active Celery workers",
)

queue_length = Gauge(
    "celery_queue_length",
    "Number of tasks in queue",
    ["queue_name"],
)

redis_connections = Gauge(
    "redis_active_connections",
    "Number of active Redis connections",
)

db_pool_size = Gauge(
    "db_pool_size",
    "Database connection pool size",
)

db_pool_checked_out = Gauge(
    "db_pool_checked_out",
    "Number of database connections checked out",
)


def initialize_metrics(app_name: str, version: str) -> None:
    """Initialize application metrics."""
    app_info.info({
        "app_name": app_name,
        "version": version,
    })
