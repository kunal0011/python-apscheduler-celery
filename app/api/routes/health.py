"""
Health Check Routes

Endpoints for health, liveness, and readiness probes.
"""

from typing import Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as redis

from app.api.deps import get_db, get_redis
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    Returns application status and version.
    """
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> Dict[str, Any]:
    """
    Readiness probe - checks all dependencies are available.
    Used by Kubernetes to determine if the pod can receive traffic.
    """
    checks: Dict[str, Dict[str, Any]] = {}
    overall_status = "ready"

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "latency_ms": 0}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}
        overall_status = "not_ready"

    # Check Redis
    try:
        await redis_client.ping()
        checks["redis"] = {"status": "ok", "latency_ms": 0}
    except Exception as e:
        checks["redis"] = {"status": "error", "error": str(e)}
        overall_status = "not_ready"

    return {
        "status": overall_status,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/live")
async def liveness_check() -> Dict[str, str]:
    """
    Liveness probe - basic check that the service is running.
    Used by Kubernetes to determine if the pod should be restarted.
    """
    return {"status": "alive"}
