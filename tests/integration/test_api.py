"""
API Integration Tests
"""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, test_client: TestClient):
        """Test basic health check."""
        response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_liveness_check(self, test_client: TestClient):
        """Test liveness probe."""
        response = test_client.get("/health/live")
        
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


class TestJobEndpoints:
    """Tests for job management endpoints."""

    def test_list_jobs_empty(self, test_client: TestClient):
        """Test listing jobs when none exist."""
        response = test_client.get("/api/v1/jobs")
        
        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0


class TestTaskEndpoints:
    """Tests for task submission endpoints."""

    def test_get_task_status_pending(self, test_client: TestClient):
        """Test getting status of unknown task (shows as pending)."""
        response = test_client.get("/api/v1/tasks/unknown-task-id")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
