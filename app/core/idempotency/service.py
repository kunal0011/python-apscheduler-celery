"""
Idempotency Service

Redis-based idempotency service for exactly-once task execution.
"""

import json
from typing import Any, Optional, Dict
from datetime import datetime, timezone

import redis.asyncio as redis

from app.config import settings
from app.core.idempotency.keys import generate_idempotency_key
from app.monitoring.metrics import (
    idempotency_hits_counter,
    idempotency_misses_counter,
    idempotency_lock_acquired_counter,
)


class IdempotencyService:
    """
    Service for managing idempotency of task executions.

    Uses Redis for distributed state management with the following flow:
    1. Generate key from task name + args + optional custom key
    2. Try to acquire lock (SET NX with TTL)
    3. If acquired: execute task, store result
    4. If exists: return cached result or skip

    Supports three modes for handling duplicates:
    - skip: Silently skip execution
    - return_cached: Return the previous result
    - raise: Raise an exception
    """

    def __init__(self, redis_client: redis.Redis):
        """Initialize with Redis client."""
        self.redis = redis_client
        self.key_prefix = settings.idempotency_key_prefix

    def _make_key(self, key: str) -> str:
        """Create full Redis key with prefix."""
        return f"{self.key_prefix}{key}"

    def _lock_key(self, key: str) -> str:
        """Create lock key for a given idempotency key."""
        return f"{self.key_prefix}lock:{key}"

    async def acquire(self, key: str, ttl: int = 3600) -> bool:
        """
        Attempt to acquire idempotency lock.

        Args:
            key: Idempotency key
            ttl: Time to live in seconds

        Returns:
            True if lock acquired, False if key already exists
        """
        lock_key = self._lock_key(key)
        
        # Use SET NX to atomically acquire lock
        acquired = await self.redis.set(
            lock_key,
            json.dumps({
                "acquired_at": datetime.now(timezone.utc).isoformat(),
                "status": "processing",
            }),
            nx=True,
            ex=ttl,
        )

        if acquired:
            idempotency_lock_acquired_counter.inc()
            idempotency_misses_counter.inc()
        else:
            idempotency_hits_counter.inc()

        return bool(acquired)

    async def get_result(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached result for idempotency key.

        Args:
            key: Idempotency key

        Returns:
            Cached result dict or None if not found
        """
        result_key = self._make_key(key)
        data = await self.redis.get(result_key)
        
        if data:
            return json.loads(data)
        return None

    async def set_result(
        self,
        key: str,
        result: Dict[str, Any],
        ttl: int = 3600,
    ) -> None:
        """
        Store execution result for idempotency key.

        Args:
            key: Idempotency key
            result: Result data to cache
            ttl: Time to live in seconds
        """
        result_key = self._make_key(key)
        lock_key = self._lock_key(key)

        # Store result with metadata
        data = {
            **result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Use pipeline for atomic operations
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.set(result_key, json.dumps(data), ex=ttl)
            await pipe.delete(lock_key)  # Release lock
            await pipe.execute()

    async def release(self, key: str) -> None:
        """
        Release idempotency lock without storing result.

        Used for failure cases where execution should be retried.

        Args:
            key: Idempotency key to release
        """
        lock_key = self._lock_key(key)
        await self.redis.delete(lock_key)

    async def extend_ttl(self, key: str, additional_seconds: int) -> bool:
        """
        Extend TTL of an existing idempotency record.

        Args:
            key: Idempotency key
            additional_seconds: Seconds to add to TTL

        Returns:
            True if extended, False if key doesn't exist
        """
        result_key = self._make_key(key)
        current_ttl = await self.redis.ttl(result_key)
        
        if current_ttl > 0:
            new_ttl = current_ttl + additional_seconds
            await self.redis.expire(result_key, new_ttl)
            return True
        return False

    async def is_duplicate(self, key: str) -> bool:
        """
        Check if a key has already been processed.

        Args:
            key: Idempotency key

        Returns:
            True if duplicate, False otherwise
        """
        result_key = self._make_key(key)
        lock_key = self._lock_key(key)

        # Check both result and lock keys
        exists = await self.redis.exists(result_key, lock_key)
        return exists > 0

    async def delete(self, key: str) -> bool:
        """
        Delete idempotency record.

        Args:
            key: Idempotency key to delete

        Returns:
            True if deleted, False if not found
        """
        result_key = self._make_key(key)
        lock_key = self._lock_key(key)

        deleted = await self.redis.delete(result_key, lock_key)
        return deleted > 0
