"""
Idempotent Task Decorator

Decorator for making Celery tasks idempotent.
"""

import functools
import logging
from typing import Any, Callable, Literal, Optional

import redis

from app.config import settings
from app.core.idempotency.keys import generate_idempotency_key

logger = logging.getLogger(__name__)


def idempotent_task(
    key_generator: Optional[Callable[..., str]] = None,
    ttl: int = 3600,
    on_duplicate: Literal["skip", "return_cached", "raise"] = "skip",
):
    """
    Decorator to make a Celery task idempotent.

    Ensures a task with the same arguments is only executed once
    within the TTL period.

    Args:
        key_generator: Custom function to generate idempotency key
        ttl: Time to live for idempotency record in seconds
        on_duplicate: Action on duplicate detection:
            - "skip": Skip execution, return None
            - "return_cached": Return cached result
            - "raise": Raise DuplicateTaskError

    Usage:
        @celery_app.task(bind=True)
        @idempotent_task(ttl=3600)
        def process_order(self, order_id: str):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get task instance if bound
            task_self = args[0] if args and hasattr(args[0], 'request') else None
            actual_args = args[1:] if task_self else args

            # Check for idempotency key in headers
            idempotency_key = None
            if task_self and hasattr(task_self.request, 'headers'):
                headers = task_self.request.headers or {}
                idempotency_key = headers.get('idempotency_key')

            # Generate key if not provided
            if not idempotency_key:
                if key_generator:
                    idempotency_key = key_generator(*actual_args, **kwargs)
                else:
                    task_name = func.__name__
                    idempotency_key = generate_idempotency_key(
                        task_name,
                        list(actual_args),
                        kwargs,
                    )

            # Connect to Redis synchronously (Celery tasks are sync)
            redis_client = redis.from_url(str(settings.redis_url))

            try:
                lock_key = f"{settings.idempotency_key_prefix}lock:{idempotency_key}"
                result_key = f"{settings.idempotency_key_prefix}{idempotency_key}"

                # Try to acquire lock
                acquired = redis_client.set(
                    lock_key,
                    "processing",
                    nx=True,
                    ex=ttl,
                )

                if not acquired:
                    # Duplicate detected
                    logger.info(f"Duplicate task detected: {idempotency_key}")

                    if on_duplicate == "skip":
                        return None
                    elif on_duplicate == "return_cached":
                        import json
                        cached = redis_client.get(result_key)
                        if cached:
                            return json.loads(cached)
                        return None
                    elif on_duplicate == "raise":
                        raise DuplicateTaskError(
                            f"Task with key {idempotency_key} is already processing"
                        )

                # Execute task
                try:
                    result = func(*args, **kwargs)

                    # Store result
                    import json
                    redis_client.set(
                        result_key,
                        json.dumps(result, default=str),
                        ex=ttl,
                    )

                    return result

                except Exception as e:
                    # Release lock on failure to allow retry
                    redis_client.delete(lock_key)
                    raise

            finally:
                redis_client.close()

        return wrapper

    return decorator


class DuplicateTaskError(Exception):
    """Raised when a duplicate task is detected and on_duplicate='raise'."""
    pass
