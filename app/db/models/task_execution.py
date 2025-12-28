"""
Task Execution Model

Database model for tracking individual task executions.
"""

import enum
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

from sqlalchemy import String, Integer, DateTime, JSON, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ExecutionStatus(str, enum.Enum):
    """Status of a task execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    REVOKED = "revoked"
    RETRYING = "retrying"


class TaskExecution(Base):
    """
    Task Execution Model.

    Tracks individual executions of scheduled jobs or submitted tasks.
    Provides an audit trail of all task runs.
    """

    __tablename__ = "task_executions"

    # Job reference (nullable for immediate task submissions)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Celery task reference
    celery_task_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    # Task details
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

    # Execution timing
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Execution result
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ExecutionStatus.PENDING.value,
        index=True,
    )
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retry information
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Worker information
    worker_hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    worker_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationship
    job: Mapped[Optional["ScheduledJob"]] = relationship(
        "ScheduledJob",
        back_populates="executions",
    )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def __repr__(self) -> str:
        return f"<TaskExecution(id={self.id}, task={self.task_name}, status={self.status})>"
