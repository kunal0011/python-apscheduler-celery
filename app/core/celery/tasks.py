"""
Celery Task Definitions

Example tasks and base task classes for the scheduler system.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from celery import Task, shared_task
from celery.exceptions import Reject, Retry

from app.core.celery.app import celery_app
from app.core.celery.idempotent import idempotent_task
from app.monitoring.metrics import (
    celery_task_counter,
    celery_task_duration,
)

logger = logging.getLogger(__name__)


class BaseTask(Task):
    """
    Base task class with common functionality.

    Features:
    - Automatic retry on specific exceptions
    - Structured logging
    - Metrics collection
    """

    autoretry_for = (ConnectionError, TimeoutError)
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes max backoff
    retry_jitter = True

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        """Called before task execution."""
        logger.info(
            f"Task starting: {self.name}",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "task_args": args,
                "task_kwargs": kwargs,
            },
        )

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        """Called on successful task completion."""
        celery_task_counter.labels(task_name=self.name, status="success").inc()
        logger.info(
            f"Task completed successfully: {self.name}",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "result": str(retval)[:100],
            },
        )

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Called on task failure."""
        celery_task_counter.labels(task_name=self.name, status="failure").inc()
        logger.error(
            f"Task failed: {self.name}",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "error": str(exc),
            },
            exc_info=True,
        )

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Called when task is being retried."""
        celery_task_counter.labels(task_name=self.name, status="retry").inc()
        logger.warning(
            f"Task retrying: {self.name}",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "error": str(exc),
                "retry_count": self.request.retries,
            },
        )


# Example tasks

@celery_app.task(base=BaseTask, bind=True)
def example_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Example task for testing.

    Args:
        data: Task input data

    Returns:
        Processed result
    """
    logger.info(f"Processing example task with data: {data}")

    result = {
        "processed": True,
        "input": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "worker": self.request.hostname,
    }

    return result


@celery_app.task(base=BaseTask, bind=True)
@idempotent_task(ttl=3600)
def idempotent_example_task(self, order_id: str) -> Dict[str, Any]:
    """
    Example idempotent task.

    This task will only execute once for a given order_id within the TTL.

    Args:
        order_id: Order identifier

    Returns:
        Processing result
    """
    logger.info(f"Processing order: {order_id}")

    # Simulate processing
    result = {
        "order_id": order_id,
        "status": "processed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return result


@celery_app.task(base=BaseTask, bind=True, queue="high_priority")
def high_priority_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """High priority task example."""
    logger.info(f"Processing high priority task: {data}")
    return {"status": "completed", "priority": "high", "data": data}


@celery_app.task(base=BaseTask, bind=True, queue="low_priority")
def low_priority_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """Low priority task example."""
    logger.info(f"Processing low priority task: {data}")
    return {"status": "completed", "priority": "low", "data": data}


@celery_app.task(base=BaseTask, bind=True)
def scheduled_task(
    self,
    task_name: str,
    task_args: list,
    task_kwargs: dict,
) -> Dict[str, Any]:
    """
    Task wrapper for scheduled job execution.

    Called by APScheduler to execute tasks.
    """
    logger.info(f"Executing scheduled task: {task_name}")

    # Forward to the actual task
    result = celery_app.send_task(
        task_name,
        args=task_args,
        kwargs=task_kwargs,
    )

    return {
        "forwarded_task_id": result.id,
        "task_name": task_name,
    }


@celery_app.task(base=BaseTask, bind=True)
def cleanup_idempotency_keys(self) -> Dict[str, Any]:
    """
    Periodic task to clean up expired idempotency records.

    This task runs periodically to remove stale idempotency records
    from both Redis and PostgreSQL.
    """
    logger.info("Running idempotency cleanup")

    # Cleanup logic would go here
    # In practice, Redis handles TTL automatically
    # This is for PostgreSQL backup records

    return {
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
