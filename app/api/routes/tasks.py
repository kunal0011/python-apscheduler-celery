"""
Task Routes - Immediate Task Submission Endpoints

API endpoints for submitting tasks for immediate execution and checking results.
"""

from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from celery.result import AsyncResult

from app.api.deps import DbSession, IdempotencyServiceDep
from app.schemas.task import (
    TaskSubmit,
    TaskResponse,
    TaskResultResponse,
    TaskStatus,
)
from app.core.celery.app import celery_app
from app.db.models.task_execution import TaskExecution, ExecutionStatus
from app.monitoring.metrics import (
    tasks_submitted_counter,
    idempotency_hits_counter,
)

router = APIRouter()


@router.post("/submit", response_model=TaskResponse)
async def submit_task(
    task_data: TaskSubmit,
    db: DbSession,
    idempotency_service: IdempotencyServiceDep,
) -> TaskResponse:
    """
    Submit a task for immediate execution.

    If an idempotency_key is provided, the system ensures exactly-once execution.
    Duplicate submissions with the same key will return the existing task result.
    """
    # Check idempotency if key provided
    if task_data.idempotency_key:
        existing_result = await idempotency_service.get_result(task_data.idempotency_key)
        if existing_result:
            idempotency_hits_counter.labels(task_name=task_data.task_name).inc()
            return TaskResponse(
                task_id=existing_result["task_id"],
                status=TaskStatus(existing_result["status"]),
                idempotency_key=task_data.idempotency_key,
                is_duplicate=True,
            )

        # Try to acquire idempotency lock
        acquired = await idempotency_service.acquire(
            task_data.idempotency_key,
            ttl=task_data.idempotency_ttl or 3600,
        )
        if not acquired:
            # Another request is processing this key
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task with this idempotency key is currently being processed",
            )

    try:
        # Submit to Celery
        task = celery_app.send_task(
            task_data.task_name,
            args=task_data.args or [],
            kwargs=task_data.kwargs or {},
            queue=task_data.queue or "default",
            priority=task_data.priority or 5,
        )

        # Create execution record
        execution = TaskExecution(
            celery_task_id=task.id,
            task_name=task_data.task_name,
            task_args=task_data.args or [],
            task_kwargs=task_data.kwargs or {},
            idempotency_key=task_data.idempotency_key,
            status=ExecutionStatus.PENDING,
        )
        db.add(execution)
        await db.commit()

        # Store idempotency result (task_id and pending status)
        if task_data.idempotency_key:
            await idempotency_service.set_result(
                task_data.idempotency_key,
                {"task_id": task.id, "status": "pending"},
                ttl=task_data.idempotency_ttl or 3600,
            )

        tasks_submitted_counter.labels(task_name=task_data.task_name).inc()

        return TaskResponse(
            task_id=task.id,
            status=TaskStatus.PENDING,
            idempotency_key=task_data.idempotency_key,
            is_duplicate=False,
        )

    except Exception as e:
        # Release idempotency lock on failure
        if task_data.idempotency_key:
            await idempotency_service.release(task_data.idempotency_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit task: {str(e)}",
        )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str) -> TaskResponse:
    """
    Get the current status of a task.
    """
    result = AsyncResult(task_id, app=celery_app)

    if result.state == "PENDING":
        # Task may not exist or is still in queue
        status_val = TaskStatus.PENDING
    elif result.state == "STARTED":
        status_val = TaskStatus.RUNNING
    elif result.state == "SUCCESS":
        status_val = TaskStatus.SUCCESS
    elif result.state == "FAILURE":
        status_val = TaskStatus.FAILED
    elif result.state == "REVOKED":
        status_val = TaskStatus.REVOKED
    else:
        status_val = TaskStatus.PENDING

    return TaskResponse(
        task_id=task_id,
        status=status_val,
        is_duplicate=False,
    )


@router.get("/{task_id}/result", response_model=TaskResultResponse)
async def get_task_result(task_id: str) -> TaskResultResponse:
    """
    Get the result of a completed task.
    """
    result = AsyncResult(task_id, app=celery_app)

    if not result.ready():
        return TaskResultResponse(
            task_id=task_id,
            status=TaskStatus.PENDING if result.state == "PENDING" else TaskStatus.RUNNING,
            result=None,
            error=None,
        )

    if result.successful():
        return TaskResultResponse(
            task_id=task_id,
            status=TaskStatus.SUCCESS,
            result=result.result,
            error=None,
        )
    else:
        return TaskResultResponse(
            task_id=task_id,
            status=TaskStatus.FAILED,
            result=None,
            error=str(result.result) if result.result else "Unknown error",
        )


@router.post("/{task_id}/revoke", status_code=status.HTTP_202_ACCEPTED)
async def revoke_task(
    task_id: str,
    terminate: bool = False,
) -> Dict[str, str]:
    """
    Revoke a pending or running task.

    If terminate=True, the task will be forcefully killed (SIGTERM).
    """
    celery_app.control.revoke(task_id, terminate=terminate)

    return {
        "message": f"Task {task_id} revocation requested",
        "terminate": str(terminate),
    }
