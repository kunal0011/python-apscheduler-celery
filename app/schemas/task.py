"""
Task Schemas

Pydantic schemas for task-related API requests and responses.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    REVOKED = "revoked"
    RETRYING = "retrying"


class TaskSubmit(BaseModel):
    """Schema for submitting a task for immediate execution."""
    task_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the Celery task to execute"
    )
    args: Optional[List[Any]] = Field(
        default_factory=list,
        description="Positional arguments for the task"
    )
    kwargs: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Keyword arguments for the task"
    )
    queue: Optional[str] = Field(
        default="default",
        max_length=100,
        description="Celery queue to submit to"
    )
    priority: Optional[int] = Field(
        default=5,
        ge=0,
        le=9,
        description="Task priority (0-9, higher is more urgent)"
    )
    idempotency_key: Optional[str] = Field(
        None,
        max_length=255,
        description="Idempotency key to ensure exactly-once execution"
    )
    idempotency_ttl: Optional[int] = Field(
        default=3600,
        ge=60,
        le=86400,
        description="TTL for idempotency key in seconds"
    )
    countdown: Optional[int] = Field(
        None,
        ge=0,
        le=86400,
        description="Delay execution by this many seconds"
    )
    eta: Optional[datetime] = Field(
        None,
        description="Execute task at this specific time"
    )


class TaskResponse(BaseModel):
    """Schema for task submission response."""
    task_id: str = Field(..., description="Celery task ID")
    status: TaskStatus = Field(..., description="Current task status")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key if provided")
    is_duplicate: bool = Field(
        default=False,
        description="Whether this was a duplicate submission"
    )


class TaskResultResponse(BaseModel):
    """Schema for task result response."""
    task_id: str = Field(..., description="Celery task ID")
    status: TaskStatus = Field(..., description="Task status")
    result: Optional[Any] = Field(None, description="Task result if completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[datetime] = Field(None, description="When task started")
    completed_at: Optional[datetime] = Field(None, description="When task completed")
    duration_seconds: Optional[float] = Field(None, description="Execution duration")


class TaskStatusResponse(BaseModel):
    """Schema for batch task status check."""
    tasks: Dict[str, TaskStatus] = Field(
        ...,
        description="Map of task_id to status"
    )
