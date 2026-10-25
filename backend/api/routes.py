"""Backend REST API routes."""

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional

from backend.schemas.api_models import (
    TaskCreateRequest,
    TaskResponse,
    HealthResponse,
    LogMessage,
    ControlCommandRequest
)
from backend.services.system_manager import SystemManager
from computer_vision.schemas import VisionFrameResult
from robot_interface.base import RobotTelemetry

router = APIRouter(prefix="/api", tags=["Duckiebot AI Navigation API"])


@router.get("/health", response_model=HealthResponse)
def get_health():
    """Health check endpoint: returns status of robot, camera, LLM, and navigation."""
    mgr = SystemManager.get_instance()
    telemetry = mgr.get_telemetry()
    mode = mgr.config.get("system", {}).get("mode", "simulation")

    return HealthResponse(
        status="ok",
        mode=mode,
        robot_connected=telemetry.connected,
        camera_connected=telemetry.camera_connected,
        llm_cloud_ready=mgr.intent_parser.client.is_cloud_ready(),
        active_state=mgr.state_machine.current_state,
        version="1.0.0"
    )


@router.get("/robot/status", response_model=RobotTelemetry)
def get_robot_status():
    """Returns complete telemetry, diagnostics, and sensor readings from Duckiebot."""
    mgr = SystemManager.get_instance()
    return mgr.get_telemetry()


@router.get("/camera/status")
def get_camera_status():
    """Returns camera resolution, FPS, and connection state."""
    mgr = SystemManager.get_instance()
    telemetry = mgr.get_telemetry()
    return {
        "camera_connected": telemetry.camera_connected,
        "fps": telemetry.camera_fps,
        "resolution": "640x480",
        "mode": telemetry.mode
    }


@router.get("/camera/stream")
def get_camera_stream():
    """Live MJPEG video stream with real-time bounding boxes, lane overlays, and HUD."""
    mgr = SystemManager.get_instance()
    return StreamingResponse(
        mgr.generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/camera/snapshot")
def get_camera_snapshot():
    """Returns a single annotated JPEG frame snapshot."""
    mgr = SystemManager.get_instance()
    if not mgr.latest_annotated_jpeg:
        raise HTTPException(status_code=503, detail="Camera frame not ready yet")
    return Response(content=mgr.latest_annotated_jpeg, media_type="image/jpeg")


@router.get("/vision/detections", response_model=VisionFrameResult)
def get_vision_detections():
    """Returns current computer vision detections, lane tracking, and obstacle status."""
    mgr = SystemManager.get_instance()
    return mgr.get_latest_vision_result()


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_navigation_task(req: TaskCreateRequest):
    """Submit a natural-language navigation request (e.g., 'Go to the laboratory').
    
    Parses intent with LLM, validates target against landmark database, and plans task.
    """
    mgr = SystemManager.get_instance()
    task = mgr.create_task(req.text)
    return task


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    """Retrieve details and progress of a navigation task."""
    mgr = SystemManager.get_instance()
    task = mgr.tasks_history.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    # Update latest navigation state
    task.navigation_state = mgr.state_machine.current_state
    return task


@router.post("/tasks/{task_id}/start")
def start_task(task_id: str):
    """Confirm and begin autonomous movement for the planned task."""
    mgr = SystemManager.get_instance()
    if not mgr.active_task or mgr.active_task.task_id != task_id:
        raise HTTPException(status_code=404, detail="Task is not active or has already ended.")

    success = mgr.start_active_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start task from current state ({mgr.state_machine.current_state.value})."
        )
    return {"status": "started", "task_id": task_id, "state": mgr.state_machine.current_state.value}


@router.post("/tasks/{task_id}/pause")
def pause_task(task_id: str):
    """Pause navigation task."""
    mgr = SystemManager.get_instance()
    success = mgr.pause_active_task()
    if not success:
        raise HTTPException(status_code=400, detail="Cannot pause task.")
    return {"status": "paused", "task_id": task_id, "state": mgr.state_machine.current_state.value}


@router.post("/tasks/{task_id}/resume")
def resume_task(task_id: str):
    """Resume paused navigation task."""
    mgr = SystemManager.get_instance()
    success = mgr.resume_active_task()
    if not success:
        raise HTTPException(status_code=400, detail="Cannot resume task.")
    return {"status": "resumed", "task_id": task_id, "state": mgr.state_machine.current_state.value}


@router.post("/tasks/{task_id}/stop")
def stop_task(task_id: str):
    """Stop active navigation task."""
    mgr = SystemManager.get_instance()
    success = mgr.stop_active_task("Task cancelled by user.")
    return {"status": "stopped", "task_id": task_id, "state": mgr.state_machine.current_state.value}


@router.post("/robot/emergency_stop")
def trigger_emergency_stop():
    """IMMEDIATE SAFETY STOP: Cuts motor power and commands zero velocity."""
    mgr = SystemManager.get_instance()
    mgr.emergency_stop()
    return {"status": "emergency_stop_engaged", "state": mgr.state_machine.current_state.value}


@router.post("/robot/clear_emergency_stop")
def clear_emergency_stop():
    """Reset emergency stop interlock."""
    mgr = SystemManager.get_instance()
    mgr.clear_emergency_stop()
    return {"status": "emergency_stop_cleared", "state": mgr.state_machine.current_state.value}


@router.get("/logs", response_model=List[LogMessage])
def get_logs(limit: int = 50):
    """Retrieve recent navigation, vision, and system log events."""
    mgr = SystemManager.get_instance()
    return mgr.get_recent_logs(limit=limit)
