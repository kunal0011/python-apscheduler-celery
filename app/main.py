"""
FastAPI Application Entry Point

Main application module that configures and starts the FastAPI server.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.config import settings
from app.api.routes import scheduler, tasks, health
from app.db.session import init_db, close_db
from app.core.scheduler.service import scheduler_service
from app.monitoring.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    setup_logging()
    await init_db()
    await scheduler_service.start()
    
    yield
    
    # Shutdown
    await scheduler_service.shutdown()
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Production-grade idempotent task scheduler with APScheduler and Celery",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount Prometheus metrics
    if settings.prometheus_enabled:
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(
        scheduler.router,
        prefix=f"{settings.api_v1_prefix}/jobs",
        tags=["Jobs"],
    )
    app.include_router(
        tasks.router,
        prefix=f"{settings.api_v1_prefix}/tasks",
        tags=["Tasks"],
    )

    return app


# Application instance
app = create_app()
