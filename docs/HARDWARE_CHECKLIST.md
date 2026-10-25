# Duckiebot DB21J Hardware Integration Checklist

Follow these sequential steps to verify each hardware interface on `entebot209` without risking physical runaway or equipment damage.

---

## Phase 1: Network & Basic Discovery

- [ ] **Step 1.1: Network Alignment**
  - Verify that the laptop/workstation and `entebot209` are connected to the same Wi-Fi hotspot (`duckietown / quackquack`).
- [ ] **Step 1.2: Fleet Discover Verification**
  - Run on workstation:
    ```bash
    dts fleet discover
    ```
  - Confirm output shows:
    ```text
    entebot209 | jetson_nano | duckiebot | DB21J | Ready | entebot209.local
    ```
- [ ] **Step 1.3: Hostname Ping**
  - Run:
    ```bash
    ping entebot209.local
    ```
  - Confirm IP reply (e.g. `192.168.x.x`).

---

## Phase 2: Remote Access & Port Diagnostics

- [ ] **Step 2.1: Run Hardware Diagnostic Script**
  - Run the diagnostic tester included in this repository:
    ```bash
    python scripts/test_duckiebot.py
    ```
  - Verify accessibility of Port 80 (Dashboard), Port 9090 (ROSBridge), and Port 22 (SSH).
- [ ] **Step 2.2: SSH Access Test**
  - Open terminal:
    ```bash
    ssh duckie@entebot209.local
    ```
  - Password: `quackquack`
  - Confirm login prompt appears and verify Jetson Nano status:
    ```bash
    tegrastats
    docker ps
    ```

---

## Phase 3: Camera & Sensor Verification

- [ ] **Step 3.1: Duckietown Web Dashboard Check**
  - Open a browser to: `http://entebot209.local`
  - Check the camera preview widget to confirm the camera lens cap is removed and focus is sharp.
- [ ] **Step 3.2: ROS Camera Topic Verification**
  - Via SSH or docker container:
    ```bash
    rostopic list | grep camera
    rostopic hz /entebot209/camera_node/image/compressed
    ```
  - Expected rate: ~15 to 30 Hz.
- [ ] **Step 3.3: ToF Sensor Check (if DB21J ToF mounted)**
  - Run:
    ```bash
    rostopic echo /entebot209/front_center_tof_driver_node/range
    ```
  - Place your hand in front of the sensor (10 cm to 50 cm) and confirm range value changes.

---

## Phase 4: Controlled Motor Safety Testing (Elevated Wheels)

> [!CAUTION]
> Never place the robot on the floor for first motor tests. Elevate the chassis on a stand or block so the wheels rotate freely in the air.

- [ ] **Step 4.1: Elevate the Robot**
  - Place a small box or stand underneath the chassis so both rubber wheels are lifted 2 cm off the desk.
- [ ] **Step 4.2: Enable Hardware Mode in Configuration**
  - Edit `config/config.yaml`:
    ```yaml
    system:
      mode: "hardware"
    safety:
      enable_hardware_movement: true
    ```
- [ ] **Step 4.3: Launch Dashboard & Test Emergency Stop**
  - Launch system:
    ```bash
    python scripts/run_system.py
    ```
  - Open `http://localhost:8000`.
  - Click the red **EMERGENCY STOP** button. Confirm state transitions to `EMERGENCY_STOP`.
- [ ] **Step 4.4: Low-Speed Forward Test**
  - Enter prompt: `"Follow the lane"` or `"Go to the laboratory"`.
  - Click **Start Navigation**.
  - Observe elevated wheels: both wheels should rotate smoothly forward at low speed (< 0.22 m/s).
  - Click **Stop Navigation**: confirm wheels halt immediately.

---

## Phase 5: Controlled Ground Test

- [ ] **Step 5.1: Clear Flat Arena**
  - Place robot inside a clean, enclosed Duckietown road loop or clear floor area free of stairs and drop-offs.
- [ ] **Step 5.2: Autonomous Mission Execution**
  - From the dashboard, enter: `"Go to the laboratory"`.
  - Observe the robot following the yellow center line and stopping safely when near the target landmark.
