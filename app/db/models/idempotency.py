"""
Idempotency Record Model

Database model for persistent idempotency tracking (backup to Redis).
"""

from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import String, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdempotencyRecord(Base):
    """
    Idempotency Record Model.

    Provides persistent storage for idempotency keys as a backup to Redis.
    Used for recovery scenarios and long-term auditing.
    """

    __tablename__ = "idempotency_records"

    # Idempotency key (unique identifier)
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    # Associated task
    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Request fingerprint (hash of args/kwargs)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Execution result
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Metadata
    client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    request_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<IdempotencyRecord(key={self.key}, task={self.task_name}, status={self.status})>"
