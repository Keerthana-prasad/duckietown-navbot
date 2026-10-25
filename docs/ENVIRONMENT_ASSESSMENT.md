# Environment Assessment: Duckiebot DB21J (Ente Release)

## 1. Executive Summary

This assessment audits the hardware and software configuration of the Duckiebot DB21J (`entebot209`), running the official Duckietown **Ente** software image on an NVIDIA Jetson Nano 4GB.

The system is configured to support a hybrid architecture:
1. **Simulation / Mock Mode (Default)**: Complete software pipeline (CV, LLM intent parsing, state machine, safety supervision, and web dashboard) runs independently of physical hardware on laptop or PC.
2. **Hardware Mode**: Connects directly over Wi-Fi (mDNS `entebot209.local`) using standard Duckietown Ente ROS topics via WebSocket (`rosbridge:9090`) or HTTP REST/streaming interfaces.

---

## 2. Hardware Profile

| Component | Specification | Operational Status |
| :--- | :--- | :--- |
| **Compute Board** | NVIDIA Jetson Nano 4GB | **Verified** (Booted & Discoverable) |
| **SoC / CPU** | Quad-core ARM® Cortex®-A57 @ 1.43 GHz | **Verified** |
| **GPU** | 128-core NVIDIA Maxwell™ architecture | Available for TensorRT / PyTorch |
| **RAM** | 4 GB 64-bit LPDDR4 (25.6 GB/s) | Monitored; memory-conscious CV required |
| **Storage** | 64 GB MicroSD Card (DB21J Ente Fast Way) | **Verified** (Etcher flash complete) |
| **Chassis / Model** | Duckiebot DB21J (Differential drive) | **Verified** |
| **Wi-Fi Interface** | Realtek 802.11ac USB NIC | **Verified** (Hotspot: `duckietown`) |
| **Onboard Display** | Small I2C / SPI status screen | **Verified** (Illuminated on boot) |
| **Battery System** | Standard Duckietown LiPo power pack | **Verified** (Top power button on) |

---

## 3. Software & Middleware Environment

| Layer | Environment on Robot | Role in this Project |
| :--- | :--- | :--- |
| **OS on Robot** | Ubuntu 18.04 LTS (JetPack 4.6) | Host OS hosting Duckietown Docker containers |
| **Container Engine** | Docker CE | Manages `dt-core`, `dt-duckiebot-interface` |
| **ROS Release** | **ROS 1 Noetic** (Standard Ente) | Inter-process messaging on robot |
| **Duckietown Shell** | `dts` (installed on workstation) | Fleet management & diagnostic discovery |
| **Discovered Hostname** | `entebot209` | mDNS address: `entebot209.local` |
| **Fleet Status** | **Ready** | Confirmed by `dts fleet discover` |

---

## 4. Hardware Interface Verification Matrix

| Interface / Topic | Protocol | Verified on Hardware? | Fallback / Mock Behavior |
| :--- | :--- | :--- | :--- |
| **mDNS Fleet Discovery** | Avahi / Bonjour | **YES** (`Ready`) | N/A |
| **SSH Terminal** | SSH (port 22) | *Pending User Verification* | Standard diagnostic procedures |
| **Web Dashboard** | HTTP (port 80) | *Pending User Verification* | Diagnostic probe script provided |
| **Camera Streaming** | HTTP (port 8085) / ROS topic | *Pending User Verification* | High-fidelity synthetic road frames |
| **Camera Topic** | `/{name}/camera_node/image/compressed` | *Pending User Verification* | Decodes JPEG from WebSocket or fallback |
| **Car Control Topic** | `/{name}/car_cmd_switch_node/cmd` | *Pending User Verification* | Speed-clamped Twist2D generator |
| **Emergency Stop** | `/{name}/wheels_driver_node/emergency_stop` | *Pending User Verification* | Zero-velocity publisher & watchdog |
| **ToF Range Sensor** | `/{name}/front_center_tof_driver_node/range` | *Pending User Verification* | Visual proximity detection fallback |
| **Wheel Encoders** | `/{name}/*_wheel_encoder_node/tick` | *Pending User Verification* | Simulated encoder odometry |

---

## 5. Jetson Nano 4GB Resource Constraints

1. **RAM Management**: 4GB total unified memory must be shared between the OS, Docker containers, camera pipeline, and neural networks.
   - Large LLMs (e.g. 7B/13B parameters) **cannot** run directly on the Jetson Nano. This project utilizes a cloud-based LLM API (Google Gemini / OpenAI) with local heuristic fallback.
   - The CV pipeline is configured to use lightweight models (YOLOv8n / YOLOv11n or classical OpenCV HSV lane filters) consuming < 450 MB RAM.
2. **Motor Safety Interlock**: Physical wheel movement is **disabled by default** (`safety.enable_hardware_movement: false`). The user must explicitly enable hardware movement after initial elevated-wheel checks.
