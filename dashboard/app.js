/**
 * Duckiebot AI Navigation Dashboard Controller
 */

let activeTaskId = null;
let currentNavigationState = "IDLE";
let pollInterval = null;

document.addEventListener("DOMContentLoaded", () => {
  console.log("Duckiebot Dashboard initialized.");
  fetchHealth();
  fetchRobotStatus();
  fetchVisionDetections();
  fetchLogs();

  // Periodic poll loops
  setInterval(fetchHealth, 1000);
  setInterval(fetchRobotStatus, 500);
  setInterval(fetchVisionDetections, 600);
  setInterval(fetchLogs, 1500);
});

// Helper for quick prompt chips
function setPrompt(text) {
  const input = document.getElementById("promptInput");
  input.value = text;
  input.focus();
}

// 1. Submit Natural Language Prompt
async function submitPrompt() {
  const input = document.getElementById("promptInput");
  const text = input.value.trim();
  if (!text) return;

  const btn = document.getElementById("submitPromptBtn");
  btn.disabled = true;
  btn.textContent = "Interpreting...";

  try {
    const res = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });

    if (!res.ok) {
      const err = await res.json();
      showAlert(err.detail || "Failed to create task");
      return;
    }

    const task = await res.json();
    activeTaskId = task.task_id;
    updateGoalDisplay(task);

  } catch (err) {
    showAlert("Network error connecting to backend: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Interpret & Plan";
  }
}

// Update Active Goal UI
function updateGoalDisplay(task) {
  document.getElementById("activeTaskId").textContent = task.task_id;
  const goal = task.interpreted_goal;

  if (goal) {
    document.getElementById("goalIntent").textContent = goal.intent;
    document.getElementById("goalTarget").textContent = goal.target || "N/A";
    document.getElementById("goalIndicator").textContent = goal.visual_indicator || "-";

    const clarifEl = document.getElementById("goalClarification");
    if (goal.requires_clarification) {
      clarifEl.textContent = goal.clarification_message || "Clarification required";
      clarifEl.className = "prop-val text-warning";
      showAlert("Notice: " + (goal.clarification_message || "Ambiguous request"));
    } else {
      clarifEl.textContent = "Validated against landmark database";
      clarifEl.className = "prop-val muted";
    }
  }

  // Update button availability
  updateControlButtons(task.navigation_state);
}

// 2. Control Actions
async function startNavigation() {
  if (!activeTaskId) return;
  try {
    const res = await fetch(`/api/tasks/${activeTaskId}/start`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json();
      showAlert(err.detail || "Cannot start navigation");
    }
  } catch (err) {
    showAlert(err.message);
  }
}

async function pauseNavigation() {
  if (!activeTaskId) return;
  try {
    await fetch(`/api/tasks/${activeTaskId}/pause`, { method: "POST" });
  } catch (err) {
    showAlert(err.message);
  }
}

async function resumeNavigation() {
  if (!activeTaskId) return;
  try {
    await fetch(`/api/tasks/${activeTaskId}/resume`, { method: "POST" });
  } catch (err) {
    showAlert(err.message);
  }
}

async function stopNavigation() {
  if (!activeTaskId) return;
  try {
    await fetch(`/api/tasks/${activeTaskId}/stop`, { method: "POST" });
  } catch (err) {
    showAlert(err.message);
  }
}

async function triggerEStop() {
  try {
    await fetch("/api/robot/emergency_stop", { method: "POST" });
    showAlert("EMERGENCY STOP ACTIVATED! Motors halted.");
  } catch (err) {
    showAlert(err.message);
  }
}

async function clearEStop() {
  try {
    await fetch("/api/robot/clear_emergency_stop", { method: "POST" });
    closeAlert();
  } catch (err) {
    showAlert(err.message);
  }
}

// 3. Health & Telemetry Fetching
async function fetchHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return;
    const data = await res.json();

    // Mode badge
    const modeBadge = document.getElementById("modeBadge");
    modeBadge.textContent = data.mode.toUpperCase();
    modeBadge.className = "status-pill " + (data.mode === "hardware" ? "mode-hw" : "mode-sim");

    // Robot & Camera Indicators
    const rInd = document.getElementById("robotIndicator");
    rInd.className = "dot " + (data.robot_connected ? "dot-green" : "dot-red");

    const cInd = document.getElementById("cameraIndicator");
    cInd.className = "dot " + (data.camera_connected ? "dot-green" : "dot-red");
    document.getElementById("cameraText").textContent = data.camera_connected ? "Camera Active" : "Camera Lost";

    // LLM Indicator
    const llmInd = document.getElementById("llmIndicator");
    llmInd.className = "dot " + (data.llm_cloud_ready ? "dot-green" : "dot-yellow");
    document.getElementById("llmText").textContent = data.llm_cloud_ready ? "Cloud LLM" : "Mock/Heuristic";

    // Navigation state badge
    updateStateBadge(data.active_state);

  } catch (err) {
    console.debug("Health fetch error:", err);
  }
}

function updateStateBadge(state) {
  currentNavigationState = state;
  const badge = document.getElementById("stateBadge");
  badge.textContent = state;

  badge.className = "status-pill ";
  if (state === "NAVIGATING") badge.classList.add("state-navigating");
  else if (state === "BLOCKED") badge.classList.add("state-blocked");
  else if (state === "GOAL_REACHED") badge.classList.add("state-reached");
  else badge.classList.add("state-idle");

  // Show/Hide E-Stop reset button
  const clearBtn = document.getElementById("clearEStopBtn");
  if (state === "EMERGENCY_STOP") {
    clearBtn.style.display = "inline-flex";
  } else {
    clearBtn.style.display = "none";
  }

  updateControlButtons(state);
}

function updateControlButtons(state) {
  const startBtn = document.getElementById("startNavBtn");
  const pauseBtn = document.getElementById("pauseNavBtn");
  const resumeBtn = document.getElementById("resumeNavBtn");
  const stopBtn = document.getElementById("stopNavBtn");

  if (!activeTaskId) {
    startBtn.disabled = true;
    pauseBtn.disabled = true;
    resumeBtn.disabled = true;
    stopBtn.disabled = true;
    return;
  }

  if (state === "PLANNING") {
    startBtn.disabled = false;
    pauseBtn.disabled = true;
    resumeBtn.disabled = true;
    stopBtn.disabled = false;
  } else if (state === "NAVIGATING") {
    startBtn.disabled = true;
    pauseBtn.disabled = false;
    resumeBtn.disabled = true;
    stopBtn.disabled = false;
  } else if (state === "PAUSED" || state === "BLOCKED") {
    startBtn.disabled = true;
    pauseBtn.disabled = true;
    resumeBtn.disabled = false;
    stopBtn.disabled = false;
  } else {
    startBtn.disabled = true;
    pauseBtn.disabled = true;
    resumeBtn.disabled = true;
    stopBtn.disabled = true;
  }
}

async function fetchRobotStatus() {
  try {
    const res = await fetch("/api/robot/status");
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("batteryPct").textContent = `${data.battery_percentage}%`;
    document.getElementById("batteryVolt").textContent = `(${data.battery_voltage}V)`;
    document.getElementById("streamFps").textContent = `${data.camera_fps.toFixed(1)} FPS`;

    document.getElementById("metricSpeedV").textContent = `${data.linear_velocity.toFixed(2)} m/s`;
    document.getElementById("metricOmega").textContent = `${data.angular_velocity.toFixed(2)} rad/s`;
    document.getElementById("metricToF").textContent = data.tof_distance_m ? `${data.tof_distance_m.toFixed(2)} m` : "N/A";
    document.getElementById("metricTicks").textContent = `L: ${data.left_wheel_ticks} | R: ${data.right_wheel_ticks}`;
  } catch (err) {
    console.debug("Telemetry fetch error:", err);
  }
}

async function fetchVisionDetections() {
  try {
    const res = await fetch("/api/vision/detections");
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("detCount").textContent = data.detections ? data.detections.length : 0;
    document.getElementById("streamLatency").textContent = `${data.latency_ms.toFixed(0)}ms latency`;

    // Lane
    const laneText = document.getElementById("laneStatusText");
    if (data.lane && data.lane.detected) {
      laneText.textContent = `Offset: ${(data.lane.center_offset_normalized * 100).toFixed(0)}%`;
      laneText.style.color = "#34d399";
    } else {
      laneText.textContent = "Lost / None";
      laneText.style.color = "#94a3b8";
    }

    // Objects
    const container = document.getElementById("objectsList");
    if (!data.detections || data.detections.length === 0) {
      container.innerHTML = `<p class="muted-text">No objects currently in field of view.</p>`;
      return;
    }

    container.innerHTML = data.detections.map(det => `
      <div class="obj-row ${det.is_obstacle ? 'obj-obstacle' : ''}">
        <div class="obj-label">
          <span>${det.is_obstacle ? '⚠️' : '📍'}</span>
          <span>${det.label.toUpperCase()}</span>
          ${det.color ? `<span class="muted-text">(${det.color})</span>` : ''}
        </div>
        <div>
          <span>Confidence: <strong>${(det.confidence * 100).toFixed(0)}%</strong></span>
          ${det.estimated_distance_m ? ` • <span>Dist: <strong>${det.estimated_distance_m}m</strong></span>` : ''}
        </div>
      </div>
    `).join("");

  } catch (err) {
    console.debug("Vision detections error:", err);
  }
}

async function fetchLogs() {
  try {
    const res = await fetch("/api/logs?limit=40");
    if (!res.ok) return;
    const logs = await res.json();

    const consoleEl = document.getElementById("logsConsole");
    consoleEl.innerHTML = logs.map(l => {
      const timeStr = new Date(l.timestamp * 1000).toLocaleTimeString();
      return `
        <div class="log-entry">
          <span class="log-time">[${timeStr}]</span>
          <span class="log-level level-${l.level}">${l.level}</span>
          <span class="log-msg">${escapeHtml(l.message)}</span>
        </div>
      `;
    }).join("");

    consoleEl.scrollTop = consoleEl.scrollHeight;
  } catch (err) {
    console.debug("Logs fetch error:", err);
  }
}

function reloadStream() {
  const img = document.getElementById("cameraStream");
  img.src = `/api/camera/stream?t=${Date.now()}`;
}

function handleStreamError(img) {
  // If MJPEG stream disconnects or is unavailable, retry snapshot
  img.src = `/api/camera/snapshot?t=${Date.now()}`;
}

function showAlert(msg) {
  const banner = document.getElementById("alertBanner");
  document.getElementById("alertMessage").textContent = msg;
  banner.style.display = "flex";
}

function closeAlert() {
  document.getElementById("alertBanner").style.display = "none";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
