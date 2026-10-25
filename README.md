# Duckiebot DB21J AI Natural-Language Navigation System

An autonomous, modular software system for the **Duckiebot DB21J** running on an **NVIDIA Jetson Nano 4GB** with the **Duckietown Ente** software release.

The system combines **Computer Vision** (YOLOv11/YOLOv8 & classical Duckietown lane/obstacle detection), **Cloud LLM Natural-Language Understanding** (Gemini / OpenAI), a **deterministic navigation state machine**, and an interactive **Web Mission Control Dashboard**.

---

## 🌟 Key Features

1. **Module 1 — Robot Hardware Abstraction Layer**:
   - Integrates with standard Duckietown Ente ROS 1 Noetic topics via WebSocket (`rosbridge:9090`) and HTTP video streaming (`:8085`).
   - Supports safe `Twist2DStamped` velocity commands (`/{robot_name}/car_cmd_switch_node/cmd`).
   - Includes a high-fidelity **Mock Interface** that generates synthetic road scenes, odometry, and ToF range readings for offline testing.

2. **Module 2 — Computer Vision Pipeline**:
   - Object & landmark detection for dynamic targets (duckies, bottles, boxes, cups, traffic lights).
   - Duckietown road lane detection (HSV thresholding for yellow dashed center lines and white solid outer borders).
   - Multi-layer obstacle detection combining 2D bounding box geometry, driving corridor filtering, and hardware ToF range sensor fusion.
   - Live annotated frame rendering with bounding boxes, lane lines, crosshairs, and telemetry HUD.

3. **Module 3 — LLM Destination Interpreter**:
   - Translates human natural-language commands (e.g., *"Go to the laboratory"*, *"Find the red object near the entrance"*, *"Stop when you reach the target"*) into strictly validated JSON schemas (`InterpretedGoal`).
   - Supports cloud LLM APIs (Google Gemini, OpenAI) with a robust deterministic heuristic fallback for offline development.
   - Validates requests against a verified landmark catalog; rejects ambiguous or unsupported commands (e.g. flight, jumping, manipulation) with clear explanations.

4. **Module 4 — Navigation & Safety**:
   - Explicit state machine: `IDLE -> VALIDATING_REQUEST -> PLANNING -> NAVIGATING -> GOAL_REACHED`, plus `PAUSED`, `BLOCKED`, `ERROR`, and `EMERGENCY_STOP`.
   - Hard safety speed caps (max linear velocity 0.22 m/s, max angular velocity 2.2 rad/s).
   - Autonomous emergency stop on camera loss, obstacle detection, or heartbeat timeout.
   - Physical movement requires explicit user action to start.

5. **Module 5 — Mission Control Web Dashboard**:
   - Live camera stream with visual HUD annotations.
   - Real-time robot telemetry (speed, battery voltage, ToF range, wheel odometry).
   - Natural language mission planner input with quick-prompt chips.
   - Action controls: Start Navigation, Pause, Resume, Stop, and instant Emergency Stop.
   - Live detection table and scrolling system event logs.

---

## 📁 Project Architecture

```text
duckiebot/
├── backend/
│   ├── app.py                 # FastAPI application & static mounting
│   ├── api/
│   │   └── routes.py          # REST endpoints (/api/health, /api/tasks, /api/camera/stream)
│   ├── schemas/
│   │   └── api_models.py      # Request/response Pydantic schemas
│   └── services/
│       └── system_manager.py  # Central singleton coordinating robot, vision, LLM, and navigation
├── robot_interface/
│   ├── base.py                # Abstract BaseRobotInterface & RobotTelemetry
│   ├── mock.py                # Simulated Duckiebot road frame generator & odometry
│   ├── duckiebot_ros.py       # Physical Duckiebot DB21J ROS/WebSocket driver
│   └── factory.py             # Interface factory (simulation vs hardware)
├── computer_vision/
│   ├── detector.py            # YOLO & simulated object detector
│   ├── lane_detector.py       # Yellow center / white border lane tracker
│   ├── obstacle_detector.py   # Corridor collision & ToF sensor fusion
│   ├── visualization.py       # HUD and bounding box frame annotator
│   └── pipeline.py            # Unified vision processing pipeline
├── llm/
│   ├── client.py              # Cloud API client (Gemini/OpenAI) + heuristic fallback
│   ├── schemas.py             # InterpretedGoal Pydantic schema
│   ├── prompts.py             # System prompt templates & landmark catalog
│   └── intent_parser.py       # High-level query validator
├── navigation/
│   ├── state_machine.py       # NavigationStateMachine & state transitions
│   ├── safety.py              # Speed limits, watchdog, and collision supervisor
│   └── planner.py             # Goal tracking, lane centering, and visual servoing
├── dashboard/
│   ├── index.html             # Web Mission Control dashboard UI
│   ├── styles.css             # Modern dark-mode styling
│   └── app.js                 # Dashboard controller & status polling
├── config/
│   ├── config.yaml            # Master configuration file
│   └── .env.example           # Secrets template (GEMINI_API_KEY)
├── scripts/
│   ├── run_system.py          # Dashboard & backend launcher
│   └── test_duckiebot.py      # Network & hardware diagnostic probe
├── docs/
│   ├── ENVIRONMENT_ASSESSMENT.md # Audit of Duckiebot Ente environment
│   ├── HARDWARE_CHECKLIST.md     # Sequential verification checklist
│   └── DEPLOYMENT_GUIDE.md       # Staged deployment guide
├── tests/                     # 23 automated unit & integration tests
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start Guide

### 1. Installation

Clone or open the repository and install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Run Automated Tests

Verify that all subsystems (LLM parser, CV pipeline, state machine, safety, and REST APIs) are passing:

```bash
python -m pytest tests/ -v
```

Expected result:
```text
============================= 23 passed in 3.84s ==============================
```

### 3. Launch Mission Dashboard (Simulation Mode)

Launch the backend server and web dashboard:

```bash
python scripts/run_system.py
```

Open your browser to:
- **Web Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 💬 Natural Language Prompt Examples

Try entering these commands in the Mission Control prompt input:

| Natural Language Instruction | Interpreted Intent | Target / Action |
| :--- | :--- | :--- |
| `"Go to the laboratory"` | `navigate_to_landmark` | Targets `laboratory` (visual: `bottle`) |
| `"Find the red object near the entrance"` | `search_for_object` | Searches for visual `red object` |
| `"Follow the lane"` | `follow_lane` | Activates Duckietown lane centering |
| `"Stop when you reach the target"` | `stop` | Halts robot motion |
| `"Fly to the moon"` | `unsupported` | Rejected: Ground robot explanation provided |
| `"Go somewhere quickly"` | `ambiguous` | Asks for clarification from known landmarks |

---

## 🤖 Transitioning to Hardware (`entebot209.local`)

1. Ensure the Duckiebot is powered on and connected to your Wi-Fi hotspot (`duckietown / quackquack`).
2. Run the hardware probe:
   ```bash
   python scripts/test_duckiebot.py
   ```
3. Set your Cloud LLM API key (optional, heuristic fallback works offline):
   ```bash
   export GEMINI_API_KEY="your_api_key_here"
   ```
4. Edit `config/config.yaml`:
   ```yaml
   system:
     mode: "hardware"
   robot:
     hostname: "entebot209.local"
   safety:
     enable_hardware_movement: true
   ```
5. Follow the [Hardware Checklist](docs/HARDWARE_CHECKLIST.md) to conduct initial tests with wheels lifted before autonomous floor runs.

---

## 🛡️ Safety Guarantees

- **Hardware Movement Disabled by Default**: Motors will not turn until `safety.enable_hardware_movement` is explicitly enabled.
- **Heartbeat Watchdog**: If the camera stream disconnects or the control loop stops for > 1.0s, the robot halts automatically.
- **Independent E-Stop**: The red **EMERGENCY STOP** button directly commands zero velocity and cuts drive commands independent of the LLM.
- **Speed Clamping**: Commanded speeds are strictly capped at 0.22 m/s linear velocity and 2.2 rad/s angular velocity.
