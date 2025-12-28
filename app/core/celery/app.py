"""
Celery Application

Celery configuration and application setup for task distribution.
"""

from celery import Celery
from kombu import Queue, Exchange

from app.config import settings

# Create Celery application
celery_app = Celery(
    "scheduler_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_acks_late=settings.celery_task_acks_late,
    task_reject_on_worker_lost=settings.celery_task_reject_on_worker_lost,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Worker settings
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    worker_concurrency=4,

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_extended=True,  # Store additional result metadata

    # Task execution settings
    task_time_limit=1800,  # 30 minutes hard limit
    task_soft_time_limit=1500,  # 25 minutes soft limit

    # Retry settings
    task_default_retry_delay=60,  # 1 minute default retry delay
    task_max_retries=3,

    # Queue configuration
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
        Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
        Queue("scheduled", Exchange("scheduled"), routing_key="scheduled"),
    ),

    # Task routing
    task_routes={
        "app.core.celery.tasks.high_priority_*": {"queue": "high_priority"},
        "app.core.celery.tasks.low_priority_*": {"queue": "low_priority"},
        "app.core.celery.tasks.scheduled_*": {"queue": "scheduled"},
    },

    # Beat schedule (for periodic tasks defined in code)
    beat_schedule={
        # Example: cleanup task every hour
        # "cleanup-expired-idempotency-keys": {
        #     "task": "app.core.celery.tasks.cleanup_idempotency_keys",
        #     "schedule": 3600,
        # },
    },

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.core.celery"])


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks after Celery is configured."""
    # Tasks can be added dynamically here
    pass
