"""
Scheduler Routes - Job Management Endpoints

API endpoints for creating, managing, and monitoring scheduled jobs.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, SchedulerServiceDep
from app.schemas.job import (
    JobCreate,
    JobUpdate,
    JobResponse,
    JobListResponse,
    TriggerUpdate,
)
from app.db.models.job import ScheduledJob, JobStatus
from app.monitoring.metrics import (
    jobs_created_counter,
    jobs_deleted_counter,
)

router = APIRouter()


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_data: JobCreate,
    db: DbSession,
    scheduler: SchedulerServiceDep,
) -> JobResponse:
    """
    Create a new scheduled job.

    The job will be registered with APScheduler and persisted to the database.
    Trigger types supported: cron, interval, date.
    """
    import uuid
    try:
        # Generate UUID for the job
        job_id = uuid.uuid4()
        
        # Create job in scheduler with UUID as ID
        scheduled_job = await scheduler.add_job(job_data, job_id=str(job_id))

        # Create database record
        db_job = ScheduledJob(
            id=job_id,
            name=job_data.name,
            trigger_type=job_data.trigger_type,
            trigger_config=job_data.trigger_config,
            task_name=job_data.task_name,
            task_args=job_data.task_args or [],
            task_kwargs=job_data.task_kwargs or {},
            idempotency_key=job_data.idempotency_key,
            max_instances=job_data.max_instances,
            coalesce=job_data.coalesce,
            next_run_time=scheduled_job.next_run_time,
            status=JobStatus.ACTIVE,
        )
        db.add(db_job)
        await db.commit()
        await db.refresh(db_job)

        jobs_created_counter.labels(trigger_type=job_data.trigger_type).inc()

        return JobResponse.model_validate(db_job)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job with name '{job_data.name}' already exists",
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create job: {str(e)}",
        )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    db: DbSession,
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
) -> JobListResponse:
    """
    List all scheduled jobs with optional filtering.
    """
    query = select(ScheduledJob)
    
    if status_filter:
        query = query.where(ScheduledJob.status == status_filter)
    
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    jobs = result.scalars().all()

    # Get total count
    count_query = select(ScheduledJob)
    if status_filter:
        count_query = count_query.where(ScheduledJob.status == status_filter)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return JobListResponse(
        jobs=[JobResponse.model_validate(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    db: DbSession,
) -> JobResponse:
    """
    Get details of a specific job.
    """
    result = await db.execute(
        select(ScheduledJob).where(ScheduledJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return JobResponse.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    db: DbSession,
    scheduler: SchedulerServiceDep,
) -> None:
    """
    Delete a scheduled job.

    Removes the job from both the scheduler and database.
    """
    result = await db.execute(
        select(ScheduledJob).where(ScheduledJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Remove from scheduler
    await scheduler.remove_job(str(job_id))

    # Delete from database
    await db.delete(job)
    await db.commit()

    jobs_deleted_counter.labels(trigger_type=job.trigger_type).inc()


@router.post("/{job_id}/pause", response_model=JobResponse)
async def pause_job(
    job_id: UUID,
    db: DbSession,
    scheduler: SchedulerServiceDep,
) -> JobResponse:
    """
    Pause a scheduled job.

    The job will not execute until resumed.
    """
    result = await db.execute(
        select(ScheduledJob).where(ScheduledJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status == JobStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is already paused",
        )

    # Pause in scheduler
    await scheduler.pause_job(str(job_id))

    # Update database
    job.status = JobStatus.PAUSED
    await db.commit()
    await db.refresh(job)

    return JobResponse.model_validate(job)


@router.post("/{job_id}/resume", response_model=JobResponse)
async def resume_job(
    job_id: UUID,
    db: DbSession,
    scheduler: SchedulerServiceDep,
) -> JobResponse:
    """
    Resume a paused job.
    """
    result = await db.execute(
        select(ScheduledJob).where(ScheduledJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != JobStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not paused",
        )

    # Resume in scheduler
    await scheduler.resume_job(str(job_id))

    # Update database
    job.status = JobStatus.ACTIVE
    await db.commit()
    await db.refresh(job)

    return JobResponse.model_validate(job)


@router.put("/{job_id}/trigger", response_model=JobResponse)
async def update_trigger(
    job_id: UUID,
    trigger_update: TriggerUpdate,
    db: DbSession,
    scheduler: SchedulerServiceDep,
) -> JobResponse:
    """
    Update the trigger configuration of a job.
    """
    result = await db.execute(
        select(ScheduledJob).where(ScheduledJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Update in scheduler
    updated_job = await scheduler.reschedule_job(
        str(job_id),
        trigger_type=trigger_update.trigger_type,
        trigger_config=trigger_update.trigger_config,
    )

    # Update database
    job.trigger_type = trigger_update.trigger_type
    job.trigger_config = trigger_update.trigger_config
    job.next_run_time = updated_job.next_run_time
    await db.commit()
    await db.refresh(job)

    return JobResponse.model_validate(job)
