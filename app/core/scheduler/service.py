"""
Scheduler Service

APScheduler wrapper with distributed coordination for job scheduling.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
)

from app.config import settings
from app.core.scheduler.distributed_lock import DistributedLockManager
from app.core.celery.app import celery_app
from app.monitoring.metrics import (
    scheduler_jobs_total,
    job_execution_counter,
    job_execution_duration,
)

logger = logging.getLogger(__name__)

# Redis client for distributed locking in the standalone function
import redis
_redis_client: Optional[redis.Redis] = None

def _get_redis_client() -> redis.Redis:
    """Get or create Redis client for distributed locking."""
    global _redis_client
    if _redis_client is None:
        from app.config import settings
        _redis_client = redis.from_url(str(settings.redis_url))
    return _redis_client


def execute_celery_task(
    task_name: str,
    task_args: List[Any],
    task_kwargs: Dict[str, Any],
    idempotency_key: Optional[str] = None,
    queue: str = "default",
    job_id: Optional[str] = None,
) -> Optional[str]:
    """
    Execute task via Celery with distributed locking.
    
    This is a standalone function (not a method) so APScheduler can serialize it
    for storage in the job store.
    
    Uses Redis distributed lock to ensure only one instance executes the job.
    """
    import time
    
    # Generate lock key based on job_id and current minute (for time-based dedup)
    current_minute = int(time.time() // 60)
    lock_key = f"scheduler_lock:{job_id or task_name}:{current_minute}"
    
    try:
        redis_client = _get_redis_client()
        
        # Try to acquire lock (expires in 55 seconds to cover the minute window)
        acquired = redis_client.set(lock_key, "1", nx=True, ex=55)
        
        if not acquired:
            logger.info(f"Skipping duplicate execution for {task_name} (lock not acquired)")
            return None
        
        logger.info(f"Acquired lock for {task_name}, executing...")
        
    except Exception as e:
        # If Redis fails, fall back to executing (better than not executing at all)
        logger.warning(f"Failed to check distributed lock: {e}, proceeding with execution")
    
    # Add idempotency key to headers if provided
    headers = {}
    if idempotency_key:
        headers["idempotency_key"] = idempotency_key

    result = celery_app.send_task(
        task_name,
        args=task_args,
        kwargs=task_kwargs,
        queue=queue,
        headers=headers,
    )

    logger.info(f"Submitted Celery task {task_name} with ID {result.id}")
    return result.id


@dataclass
class ScheduledJobInfo:
    """Information about a scheduled job."""
    id: str
    name: str
    next_run_time: Optional[datetime]
    trigger: str


class SchedulerService:
    """
    APScheduler service with distributed coordination.

    Features:
    - PostgreSQL job store for persistence across restarts
    - Distributed locking to prevent duplicate job execution
    - Integration with Celery for task execution
    - Automatic failover in multi-node deployments
    """

    def __init__(self):
        """Initialize scheduler service."""
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._lock_manager: Optional[DistributedLockManager] = None
        self._started = False

    @property
    def scheduler(self) -> AsyncIOScheduler:
        """Get scheduler instance, creating if needed."""
        if self._scheduler is None:
            self._scheduler = self._create_scheduler()
        return self._scheduler

    def _create_scheduler(self) -> AsyncIOScheduler:
        """Create and configure APScheduler."""
        jobstores = {
            "default": SQLAlchemyJobStore(url=settings.scheduler_jobstore_url)
        }

        executors = {
            "default": ThreadPoolExecutor(20),
        }

        job_defaults = {
            "coalesce": settings.scheduler_coalesce,
            "max_instances": settings.scheduler_max_instances,
            "misfire_grace_time": settings.scheduler_misfire_grace_time,
        }

        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="UTC",
        )

        # Add event listeners
        scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)
        scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)

        return scheduler

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Handle successful job execution."""
        job_execution_counter.labels(status="success").inc()
        logger.info(f"Job {event.job_id} executed successfully")

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Handle job execution error."""
        job_execution_counter.labels(status="error").inc()
        logger.error(
            f"Job {event.job_id} failed with exception: {event.exception}",
            exc_info=event.exception,
        )

    def _on_job_missed(self, event: JobExecutionEvent) -> None:
        """Handle missed job execution."""
        job_execution_counter.labels(status="missed").inc()
        logger.warning(f"Job {event.job_id} missed scheduled run time")

    async def start(self) -> None:
        """Start the scheduler."""
        if self._started:
            logger.warning("Scheduler already started")
            return

        self._lock_manager = DistributedLockManager()
        await self._lock_manager.connect()

        self.scheduler.start()
        self._started = True

        scheduler_jobs_total.set(len(self.scheduler.get_jobs()))
        logger.info("Scheduler started successfully")

    async def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler."""
        if not self._started:
            return

        self.scheduler.shutdown(wait=wait)
        
        if self._lock_manager:
            await self._lock_manager.close()

        self._started = False
        logger.info("Scheduler shutdown complete")

    def _create_trigger(
        self,
        trigger_type: str,
        trigger_config: Dict[str, Any],
    ):
        """Create APScheduler trigger from configuration."""
        if trigger_type == "cron":
            return CronTrigger(**trigger_config)
        elif trigger_type == "interval":
            return IntervalTrigger(**trigger_config)
        elif trigger_type == "date":
            return DateTrigger(**trigger_config)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")

    async def add_job(self, job_data: Any, job_id: Optional[str] = None) -> ScheduledJobInfo:
        """
        Add a new scheduled job.

        Args:
            job_data: Job creation data
            job_id: Optional job ID (uses name if not provided)

        Returns:
            Information about the created job
        """
        trigger = self._create_trigger(job_data.trigger_type, job_data.trigger_config)

        # Use provided job_id or fall back to job name
        effective_job_id = job_id or job_data.name

        # Create wrapper function that submits to Celery
        job = self.scheduler.add_job(
            func=execute_celery_task,  # Use standalone function
            trigger=trigger,
            id=effective_job_id,
            name=job_data.name,
            kwargs={
                "task_name": job_data.task_name,
                "task_args": job_data.task_args or [],
                "task_kwargs": job_data.task_kwargs or {},
                "idempotency_key": job_data.idempotency_key,
                "queue": getattr(job_data, "queue", "default"),
                "job_id": effective_job_id,  # For distributed locking
            },
            replace_existing=False,
        )

        scheduler_jobs_total.inc()
        logger.info(f"Added job: {job_data.name} with ID: {effective_job_id}")

        return ScheduledJobInfo(
            id=job.id,
            name=job.name,
            next_run_time=job.next_run_time,
            trigger=str(job.trigger),
        )

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        try:
            self.scheduler.remove_job(job_id)
            scheduler_jobs_total.dec()
            logger.info(f"Removed job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            return False

    async def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job."""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Paused job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {e}")
            return False

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Resumed job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {e}")
            return False

    async def reschedule_job(
        self,
        job_id: str,
        trigger_type: str,
        trigger_config: Dict[str, Any],
    ) -> ScheduledJobInfo:
        """Reschedule a job with a new trigger."""
        trigger = self._create_trigger(trigger_type, trigger_config)
        job = self.scheduler.reschedule_job(job_id, trigger=trigger)

        logger.info(f"Rescheduled job: {job_id}")

        return ScheduledJobInfo(
            id=job.id,
            name=job.name,
            next_run_time=job.next_run_time,
            trigger=str(job.trigger),
        )

    def get_jobs(self) -> List[ScheduledJobInfo]:
        """Get all scheduled jobs."""
        jobs = self.scheduler.get_jobs()
        return [
            ScheduledJobInfo(
                id=job.id,
                name=job.name,
                next_run_time=job.next_run_time,
                trigger=str(job.trigger),
            )
            for job in jobs
        ]

    def get_job(self, job_id: str) -> Optional[ScheduledJobInfo]:
        """Get a specific job by ID."""
        job = self.scheduler.get_job(job_id)
        if job:
            return ScheduledJobInfo(
                id=job.id,
                name=job.name,
                next_run_time=job.next_run_time,
                trigger=str(job.trigger),
            )
        return None


# Global scheduler service instance
scheduler_service = SchedulerService()


if __name__ == "__main__":
    """Run scheduler as standalone process."""
    import asyncio

    async def main():
        await scheduler_service.start()
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await scheduler_service.shutdown()

    asyncio.run(main())
