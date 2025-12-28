"""
Application Configuration Module

Centralized configuration management using Pydantic Settings.
All configuration is loaded from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, AmqpDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Application
    app_name: str = "idempotent-scheduler"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/scheduler_db"
    )
    database_sync_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/scheduler_db"
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_lock_db: int = 1
    redis_cache_db: int = 2

    # RabbitMQ
    rabbitmq_url: AmqpDsn = Field(default="amqp://guest:guest@localhost:5672//")

    # Celery
    celery_broker_url: str = "amqp://guest:guest@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/0"
    celery_task_acks_late: bool = True
    celery_task_reject_on_worker_lost: bool = True
    celery_worker_prefetch_multiplier: int = 1

    # Scheduler
    scheduler_jobstore_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/scheduler_db"
    )
    scheduler_lock_ttl: int = 30  # seconds
    scheduler_coalesce: bool = True
    scheduler_max_instances: int = 1
    scheduler_misfire_grace_time: int = 60  # seconds

    # Idempotency
    idempotency_ttl: int = 3600  # seconds (1 hour)
    idempotency_key_prefix: str = "idem:"
    idempotency_lock_timeout: int = 30  # seconds

    # Monitoring
    prometheus_enabled: bool = True
    prometheus_port: int = 9090

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
