"""
Idempotency Key Generation

Strategies for generating idempotency keys from task data.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


def generate_idempotency_key(
    task_name: str,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    custom_key: Optional[str] = None,
    include_timestamp: bool = False,
    time_window_seconds: Optional[int] = None,
) -> str:
    """
    Generate an idempotency key from task parameters.

    Args:
        task_name: Name of the Celery task
        args: Positional arguments
        kwargs: Keyword arguments
        custom_key: User-provided custom key (overrides auto-generation)
        include_timestamp: Include current timestamp (makes each call unique)
        time_window_seconds: Group calls within time window

    Returns:
        SHA256 hash of the task fingerprint
    """
    if custom_key:
        return custom_key

    # Build fingerprint
    fingerprint = {
        "task": task_name,
        "args": args or [],
        "kwargs": kwargs or {},
    }

    # Optionally include time window
    if time_window_seconds:
        now = datetime.utcnow()
        window = int(now.timestamp() // time_window_seconds)
        fingerprint["time_window"] = window
    elif include_timestamp:
        fingerprint["timestamp"] = datetime.utcnow().isoformat()

    # Generate hash
    fingerprint_str = json.dumps(fingerprint, sort_keys=True, default=str)
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:32]


class KeyGenerator(ABC):
    """Abstract base class for key generators."""

    @abstractmethod
    def generate(
        self,
        task_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate idempotency key."""
        pass


class TaskBasedKeyGenerator(KeyGenerator):
    """
    Generate key based on task name and arguments.

    Same arguments always produce the same key, regardless of when called.
    """

    def generate(
        self,
        task_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        return generate_idempotency_key(task_name, args, kwargs)


class TimeWindowKeyGenerator(KeyGenerator):
    """
    Generate key based on task and time window.

    Same arguments within a time window produce the same key.
    Different windows produce different keys.
    """

    def __init__(self, window_seconds: int = 60):
        """
        Initialize with time window.

        Args:
            window_seconds: Size of time window in seconds
        """
        self.window_seconds = window_seconds

    def generate(
        self,
        task_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        return generate_idempotency_key(
            task_name,
            args,
            kwargs,
            time_window_seconds=self.window_seconds,
        )


class CustomKeyGenerator(KeyGenerator):
    """
    Generate key using a user-provided function.

    Allows complete control over key generation.
    """

    def __init__(self, key_func: Callable[..., str]):
        """
        Initialize with custom key function.

        Args:
            key_func: Function that takes (task_name, args, kwargs) and returns key
        """
        self.key_func = key_func

    def generate(
        self,
        task_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.key_func(task_name, args or [], kwargs or {})


class CompositeKeyGenerator(KeyGenerator):
    """
    Generate key by combining multiple generators.

    Useful for complex idempotency requirements.
    """

    def __init__(self, *generators: KeyGenerator):
        """Initialize with multiple generators."""
        self.generators = generators

    def generate(
        self,
        task_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        keys = [g.generate(task_name, args, kwargs) for g in self.generators]
        combined = ":".join(keys)
        return hashlib.sha256(combined.encode()).hexdigest()[:32]
