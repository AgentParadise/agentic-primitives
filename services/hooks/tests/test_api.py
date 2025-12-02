"""Tests for API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hooks_backend.main import app
from hooks_backend.storage.jsonl import JSONLStorage


@pytest.fixture
def test_storage(tmp_path: Path) -> JSONLStorage:
    """Create a test JSONL storage."""
    return JSONLStorage(path=tmp_path / "events.jsonl")


@pytest.fixture
def client(test_storage: JSONLStorage) -> TestClient:
    """Create a test client with JSONL storage."""
    # Override the storage in the app
    app.state.storage = test_storage
    app.state.start_time = datetime.now(UTC).timestamp()
    app.state.metrics = {
        "events_received_total": 0,
        "events_stored_total": 0,
        "storage_errors_total": 0,
    }
    return TestClient(app)


class TestEventsEndpoint:
    """Tests for /events endpoint."""

    def test_receive_single_event(self, client: TestClient) -> None:
        """Test receiving a single event."""
        event = {
            "event_type": "session_started",
            "session_id": "session-123",
            "data": {"model": "claude-sonnet"},
        }

        response = client.post("/events", json=event)

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
        assert data["message"] == "Events accepted"

    def test_receive_event_with_all_fields(self, client: TestClient) -> None:
        """Test receiving event with all optional fields."""
        event = {
            "event_type": "tool_execution_started",
            "session_id": "session-123",
            "event_id": "event-456",
            "workflow_id": "workflow-789",
            "phase_id": "phase-1",
            "milestone_id": "milestone-1",
            "data": {"tool_name": "Write"},
            "timestamp": "2025-12-01T10:30:00Z",
        }

        response = client.post("/events", json=event)

        assert response.status_code == 202
        assert response.json()["accepted"] == 1

    def test_receive_event_minimal(self, client: TestClient) -> None:
        """Test receiving event with minimal fields."""
        event = {
            "event_type": "session_started",
            "session_id": "session-123",
        }

        response = client.post("/events", json=event)

        assert response.status_code == 202

    def test_receive_event_missing_required(self, client: TestClient) -> None:
        """Test error on missing required fields."""
        event = {
            "event_type": "session_started",
            # Missing session_id
        }

        response = client.post("/events", json=event)

        assert response.status_code == 422  # Validation error


class TestBatchEndpoint:
    """Tests for /events/batch endpoint."""

    def test_receive_batch(self, client: TestClient) -> None:
        """Test receiving a batch of events."""
        events = [
            {"event_type": "session_started", "session_id": "session-1"},
            {"event_type": "tool_execution_started", "session_id": "session-1"},
            {"event_type": "tool_execution_completed", "session_id": "session-1"},
        ]

        response = client.post("/events/batch", json=events)

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 3

    def test_receive_empty_batch(self, client: TestClient) -> None:
        """Test receiving empty batch."""
        response = client.post("/events/batch", json=[])

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 0
        assert "No events" in data["message"]

    def test_receive_large_batch(self, client: TestClient) -> None:
        """Test receiving a large batch of events."""
        events = [
            {"event_type": "session_started", "session_id": f"session-{i}"} for i in range(100)
        ]

        response = client.post("/events/batch", json=events)

        assert response.status_code == 202
        assert response.json()["accepted"] == 100


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """Test health check returns healthy."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["storage"] == "jsonl"
        assert "version" in data


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    def test_get_metrics(self, client: TestClient) -> None:
        """Test getting metrics."""
        response = client.get("/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "events_received_total" in data
        assert "events_stored_total" in data
        assert "storage_errors_total" in data
        assert "uptime_seconds" in data

    def test_metrics_update_on_events(self, client: TestClient) -> None:
        """Test metrics update when events are received."""
        # Get initial metrics
        initial = client.get("/metrics").json()

        # Send events
        client.post("/events", json={"event_type": "test", "session_id": "s1"})
        client.post(
            "/events/batch",
            json=[
                {"event_type": "test", "session_id": "s2"},
                {"event_type": "test", "session_id": "s3"},
            ],
        )

        # Check updated metrics
        updated = client.get("/metrics").json()

        assert updated["events_received_total"] == initial["events_received_total"] + 3
        assert updated["events_stored_total"] == initial["events_stored_total"] + 3

    def test_prometheus_metrics(self, client: TestClient) -> None:
        """Test Prometheus format metrics."""
        response = client.get("/metrics/prometheus")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        text = response.text
        assert "hooks_events_received_total" in text
        assert "hooks_events_stored_total" in text
        assert "hooks_storage_errors_total" in text
        assert "hooks_uptime_seconds" in text
