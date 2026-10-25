"""Integration tests for Backend REST API endpoints."""

import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.services.system_manager import SystemManager


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_api_health(client):
    """Test /api/health returns 200 and subsystem statuses."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "robot_connected" in data
    assert "active_state" in data


def test_api_robot_status(client):
    """Test /api/robot/status returns telemetry fields."""
    res = client.get("/api/robot/status")
    assert res.status_code == 200
    data = res.json()
    assert "battery_voltage" in data
    assert "linear_velocity" in data
    assert "hostname" in data


def test_api_vision_detections(client):
    """Test /api/vision/detections returns vision result model."""
    res = client.get("/api/vision/detections")
    assert res.status_code == 200
    data = res.json()
    assert "detections" in data
    assert "lane" in data


def test_api_create_and_control_task(client):
    """End-to-end task lifecycle: Create -> Start -> Pause -> Resume -> Stop."""
    # 1. Create task
    create_res = client.post("/api/tasks", json={"text": "Go to the laboratory"})
    assert create_res.status_code == 201
    task = create_res.json()
    task_id = task["task_id"]
    assert task["interpreted_goal"]["target"] == "laboratory"

    # 2. Start task
    start_res = client.post(f"/api/tasks/{task_id}/start")
    assert start_res.status_code == 200
    assert start_res.json()["state"] == "NAVIGATING"

    # 3. Pause task
    pause_res = client.post(f"/api/tasks/{task_id}/pause")
    assert pause_res.status_code == 200
    assert pause_res.json()["state"] == "PAUSED"

    # 4. Resume task
    resume_res = client.post(f"/api/tasks/{task_id}/resume")
    assert resume_res.status_code == 200
    assert resume_res.json()["state"] == "NAVIGATING"

    # 5. Stop task
    stop_res = client.post(f"/api/tasks/{task_id}/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["state"] == "IDLE"


def test_api_emergency_stop(client):
    """Test emergency stop endpoint instantly sets state to EMERGENCY_STOP."""
    res = client.post("/api/robot/emergency_stop")
    assert res.status_code == 200
    assert res.json()["state"] == "EMERGENCY_STOP"

    # Clear emergency stop
    clear_res = client.post("/api/robot/clear_emergency_stop")
    assert clear_res.status_code == 200
    assert clear_res.json()["state"] == "IDLE"


def test_api_logs(client):
    """Test /api/logs returns list of log entries."""
    res = client.get("/api/logs?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "timestamp" in data[0]
        assert "level" in data[0]
        assert "message" in data[0]
