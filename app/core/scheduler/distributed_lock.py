"""
Distributed Lock Manager

Redis-based distributed locking for preventing duplicate job execution.
"""

import logging
import uuid
from typing import Optional
from contextlib import asynccontextmanager

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class DistributedLockManager:
    """
    Redis-based distributed lock manager.

    Provides distributed locking to ensure only one scheduler instance
    executes a job at a time in a multi-node deployment.

    Features:
    - Unique lock holder ID per instance
    - Automatic lock expiration (TTL)
    - Lock extension for long-running operations
    - Safe release (only owner can release)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        lock_ttl: int = 30,
        lock_prefix: str = "scheduler:lock:",
    ):
        """
        Initialize lock manager.

        Args:
            redis_url: Redis connection URL
            lock_ttl: Default lock TTL in seconds
            lock_prefix: Prefix for lock keys
        """
        self.redis_url = redis_url or str(settings.redis_url)
        self.lock_ttl = lock_ttl
        self.lock_prefix = lock_prefix
        self.instance_id = str(uuid.uuid4())
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        self._redis = redis.from_url(self.redis_url, decode_responses=True)
        logger.info(f"Distributed lock manager connected (instance: {self.instance_id})")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("Distributed lock manager disconnected")

    def _make_key(self, name: str) -> str:
        """Create full lock key."""
        return f"{self.lock_prefix}{name}"

    async def acquire(
        self,
        name: str,
        ttl: Optional[int] = None,
        blocking: bool = False,
        timeout: float = 10.0,
    ) -> bool:
        """
        Acquire a distributed lock.

        Args:
            name: Lock name
            ttl: Lock TTL in seconds (uses default if not specified)
            blocking: If True, wait for lock to become available
            timeout: Maximum time to wait if blocking

        Returns:
            True if lock acquired, False otherwise
        """
        if not self._redis:
            raise RuntimeError("Lock manager not connected")

        key = self._make_key(name)
        lock_ttl = ttl or self.lock_ttl

        # Try to acquire lock
        acquired = await self._redis.set(
            key,
            self.instance_id,
            nx=True,
            ex=lock_ttl,
        )

        if acquired:
            logger.debug(f"Lock acquired: {name}")
            return True

        if not blocking:
            return False

        # Blocking acquire with timeout
        import asyncio
        import time

        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            await asyncio.sleep(0.1)
            acquired = await self._redis.set(
                key,
                self.instance_id,
                nx=True,
                ex=lock_ttl,
            )
            if acquired:
                logger.debug(f"Lock acquired after waiting: {name}")
                return True

        logger.debug(f"Failed to acquire lock: {name} (timeout)")
        return False

    async def release(self, name: str) -> bool:
        """
        Release a distributed lock.

        Only releases if this instance owns the lock.

        Args:
            name: Lock name

        Returns:
            True if released, False if not owned or not exists
        """
        if not self._redis:
            raise RuntimeError("Lock manager not connected")

        key = self._make_key(name)

        # Lua script for atomic check-and-delete
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        result = await self._redis.eval(script, 1, key, self.instance_id)

        if result:
            logger.debug(f"Lock released: {name}")
            return True
        else:
            logger.debug(f"Lock not released (not owner): {name}")
            return False

    async def extend(self, name: str, additional_ttl: Optional[int] = None) -> bool:
        """
        Extend lock TTL.

        Only extends if this instance owns the lock.

        Args:
            name: Lock name
            additional_ttl: Additional TTL in seconds

        Returns:
            True if extended, False if not owned
        """
        if not self._redis:
            raise RuntimeError("Lock manager not connected")

        key = self._make_key(name)
        ttl = additional_ttl or self.lock_ttl

        # Lua script for atomic check-and-extend
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

        result = await self._redis.eval(script, 1, key, self.instance_id, ttl)

        if result:
            logger.debug(f"Lock extended: {name}")
            return True
        return False

    async def is_locked(self, name: str) -> bool:
        """Check if a lock exists."""
        if not self._redis:
            raise RuntimeError("Lock manager not connected")

        key = self._make_key(name)
        return await self._redis.exists(key) > 0

    async def is_owner(self, name: str) -> bool:
        """Check if this instance owns the lock."""
        if not self._redis:
            raise RuntimeError("Lock manager not connected")

        key = self._make_key(name)
        owner = await self._redis.get(key)
        return owner == self.instance_id

    @asynccontextmanager
    async def lock(
        self,
        name: str,
        ttl: Optional[int] = None,
        blocking: bool = True,
        timeout: float = 10.0,
    ):
        """
        Context manager for acquiring and releasing locks.

        Usage:
            async with lock_manager.lock("my-job"):
                # Critical section
                pass

        Args:
            name: Lock name
            ttl: Lock TTL
            blocking: Wait for lock if not available
            timeout: Maximum wait time
        """
        acquired = await self.acquire(name, ttl, blocking, timeout)
        if not acquired:
            raise RuntimeError(f"Failed to acquire lock: {name}")

        try:
            yield
        finally:
            await self.release(name)
