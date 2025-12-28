"""
Idempotency Service Unit Tests
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.core.idempotency.service import IdempotencyService
from app.core.idempotency.keys import (
    generate_idempotency_key,
    TaskBasedKeyGenerator,
    TimeWindowKeyGenerator,
)


class TestIdempotencyKeyGeneration:
    """Tests for idempotency key generation."""

    def test_generate_key_basic(self):
        """Test basic key generation."""
        key = generate_idempotency_key("my_task", ["arg1"], {"key": "value"})
        assert key is not None
        assert len(key) == 32  # SHA256 truncated

    def test_same_args_same_key(self):
        """Test that same arguments produce same key."""
        key1 = generate_idempotency_key("task", ["a"], {"b": 1})
        key2 = generate_idempotency_key("task", ["a"], {"b": 1})
        assert key1 == key2

    def test_different_args_different_key(self):
        """Test that different arguments produce different keys."""
        key1 = generate_idempotency_key("task", ["a"], {})
        key2 = generate_idempotency_key("task", ["b"], {})
        assert key1 != key2

    def test_custom_key_override(self):
        """Test that custom key overrides generation."""
        key = generate_idempotency_key("task", ["a"], {}, custom_key="my-custom-key")
        assert key == "my-custom-key"

    def test_task_based_generator(self):
        """Test TaskBasedKeyGenerator."""
        generator = TaskBasedKeyGenerator()
        key = generator.generate("process_order", ["123"], {})
        assert key is not None
        assert len(key) == 32

    def test_time_window_generator(self):
        """Test TimeWindowKeyGenerator."""
        generator = TimeWindowKeyGenerator(window_seconds=60)
        key = generator.generate("task", [], {})
        assert key is not None


class TestIdempotencyService:
    """Tests for IdempotencyService."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = MagicMock()
        mock.set = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=0)
        mock.ttl = AsyncMock(return_value=3600)
        mock.expire = AsyncMock(return_value=True)
        mock.pipeline = MagicMock(return_value=AsyncMock())
        return mock

    @pytest.fixture
    def service(self, mock_redis):
        """Create IdempotencyService with mock Redis."""
        return IdempotencyService(mock_redis)

    @pytest.mark.asyncio
    async def test_acquire_success(self, service, mock_redis):
        """Test successful lock acquisition."""
        mock_redis.set = AsyncMock(return_value=True)
        
        result = await service.acquire("test-key", ttl=3600)
        
        assert result is True
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_already_exists(self, service, mock_redis):
        """Test acquisition when key already exists."""
        mock_redis.set = AsyncMock(return_value=False)
        
        result = await service.acquire("test-key", ttl=3600)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_result_exists(self, service, mock_redis):
        """Test getting existing result."""
        expected = {"task_id": "123", "status": "success"}
        mock_redis.get = AsyncMock(return_value=json.dumps(expected))
        
        result = await service.get_result("test-key")
        
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_result_not_exists(self, service, mock_redis):
        """Test getting non-existent result."""
        mock_redis.get = AsyncMock(return_value=None)
        
        result = await service.get_result("test-key")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_release(self, service, mock_redis):
        """Test releasing a lock."""
        await service.release("test-key")
        
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_duplicate_true(self, service, mock_redis):
        """Test duplicate detection when key exists."""
        mock_redis.exists = AsyncMock(return_value=1)
        
        result = await service.is_duplicate("test-key")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_is_duplicate_false(self, service, mock_redis):
        """Test duplicate detection when key doesn't exist."""
        mock_redis.exists = AsyncMock(return_value=0)
        
        result = await service.is_duplicate("test-key")
        
        assert result is False
