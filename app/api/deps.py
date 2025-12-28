"""
API Dependencies Module

Common dependencies used across API routes.
"""

from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.config import settings
from app.db.session import async_session_maker
from app.core.idempotency.service import IdempotencyService
from app.core.scheduler.service import scheduler_service, SchedulerService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """Get Redis connection dependency."""
    client = redis.from_url(str(settings.redis_url), decode_responses=True)
    try:
        yield client
    finally:
        await client.close()


async def get_idempotency_service(
    redis_client: Annotated[redis.Redis, Depends(get_redis)]
) -> IdempotencyService:
    """Get idempotency service dependency."""
    return IdempotencyService(redis_client)


def get_scheduler_service() -> SchedulerService:
    """Get scheduler service dependency."""
    return scheduler_service


# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[redis.Redis, Depends(get_redis)]
IdempotencyServiceDep = Annotated[IdempotencyService, Depends(get_idempotency_service)]
SchedulerServiceDep = Annotated[SchedulerService, Depends(get_scheduler_service)]
