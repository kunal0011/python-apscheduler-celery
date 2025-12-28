"""
Scheduled Job Model

Database model for storing scheduled job configurations.
"""

import enum
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import String, Enum, Boolean, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class JobStatus(str, enum.Enum):
    """Status of a scheduled job."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class TriggerType(str, enum.Enum):
    """Types of job triggers."""
    CRON = "cron"
    INTERVAL = "interval"
    DATE = "date"


class ScheduledJob(Base):
    """
    Scheduled Job Model.

    Represents a job that is scheduled to run at specified intervals or times.
    Jobs are executed by Celery workers and tracked via APScheduler.
    """

    __tablename__ = "scheduled_jobs"

    # Job identification
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Trigger configuration
    trigger_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TriggerType.INTERVAL.value,
    )
    trigger_config: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Task configuration
    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_args: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)
    task_kwargs: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    queue: Mapped[str] = mapped_column(String(100), nullable=False, default="default")

    # Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    idempotency_ttl: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)

    # Execution control
    max_instances: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    coalesce: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    misfire_grace_time: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # Scheduling state
    next_run_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=JobStatus.ACTIVE.value,
        index=True,
    )

    # Relationships
    executions: Mapped[List["TaskExecution"]] = relationship(
        "TaskExecution",
        back_populates="job",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ScheduledJob(id={self.id}, name={self.name}, status={self.status})>"
