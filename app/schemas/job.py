"""
Job Schemas

Pydantic schemas for job-related API requests and responses.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class TriggerType(str, Enum):
    """Job trigger types."""
    CRON = "cron"
    INTERVAL = "interval"
    DATE = "date"


class JobStatus(str, Enum):
    """Job status values."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class JobBase(BaseModel):
    """Base schema for job data."""
    name: str = Field(..., min_length=1, max_length=255, description="Unique job name")
    description: Optional[str] = Field(None, max_length=1000, description="Job description")
    task_name: str = Field(..., min_length=1, max_length=255, description="Celery task to execute")
    task_args: Optional[List[Any]] = Field(default_factory=list, description="Task positional arguments")
    task_kwargs: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Task keyword arguments")
    queue: str = Field(default="default", description="Celery queue name")


class JobCreate(JobBase):
    """Schema for creating a new job."""
    trigger_type: TriggerType = Field(..., description="Type of trigger (cron, interval, date)")
    trigger_config: Dict[str, Any] = Field(
        ...,
        description="Trigger configuration",
        examples=[
            {"seconds": 60},  # interval
            {"hour": 9, "minute": 0, "day_of_week": "mon-fri"},  # cron
            {"run_date": "2024-12-31T23:59:59"},  # date
        ]
    )
    idempotency_key: Optional[str] = Field(
        None,
        max_length=255,
        description="Custom idempotency key pattern"
    )
    idempotency_ttl: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Idempotency TTL in seconds"
    )
    max_instances: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Maximum concurrent instances"
    )
    coalesce: bool = Field(
        default=True,
        description="Combine missed executions into one"
    )
    misfire_grace_time: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="Grace time for misfired jobs in seconds"
    )


class JobUpdate(BaseModel):
    """Schema for updating a job."""
    description: Optional[str] = Field(None, max_length=1000)
    task_args: Optional[List[Any]] = None
    task_kwargs: Optional[Dict[str, Any]] = None
    queue: Optional[str] = Field(None, max_length=100)
    idempotency_key: Optional[str] = Field(None, max_length=255)
    max_instances: Optional[int] = Field(None, ge=1, le=10)
    coalesce: Optional[bool] = None


class TriggerUpdate(BaseModel):
    """Schema for updating job trigger."""
    trigger_type: TriggerType = Field(..., description="Type of trigger")
    trigger_config: Dict[str, Any] = Field(..., description="Trigger configuration")


class JobResponse(BaseModel):
    """Schema for job response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    trigger_type: str
    trigger_config: Dict[str, Any]
    task_name: str
    task_args: List[Any]
    task_kwargs: Dict[str, Any]
    queue: str
    idempotency_key: Optional[str] = None
    idempotency_ttl: int
    max_instances: int
    coalesce: bool
    status: str
    next_run_time: Optional[datetime] = None
    last_run_time: Optional[datetime] = None
    run_count: int
    error_count: int
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    """Schema for paginated job list."""
    jobs: List[JobResponse]
    total: int
    limit: int
    offset: int
