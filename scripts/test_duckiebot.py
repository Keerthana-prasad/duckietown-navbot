"""Duckiebot Hardware Connection & Diagnostics Tester."""

import socket
import sys
import os
import requests

ROBOT_HOST = os.getenv("ROBOT_HOSTNAME", "entebot209.local")
PORTS_TO_CHECK = {
    80: "Duckietown Web Dashboard (HTTP)",
    8085: "Duckietown Video Streaming (HTTP)",
    9090: "ROSBridge WebSocket (ws://)",
    22: "SSH Terminal (duckie@...)"
}

def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False

def main():
    print("=" * 60)
    print(f"🔍 DUCKIEBOT HARDWARE INTERFACE DIAGNOSTIC")
    print(f"Target: {ROBOT_HOST}")
    print("=" * 60)

    # 1. DNS Resolution check
    try:
        ip = socket.gethostbyname(ROBOT_HOST)
        print(f"✅ Hostname Resolution: {ROBOT_HOST} -> {ip}")
    except Exception as e:
        print(f"❌ Hostname Resolution Failed for {ROBOT_HOST}: {e}")
        print("   (Ensure Duckiebot is powered on and laptop is on the same hotspot/Wi-Fi)")
        ip = None

    if not ip:
        print("\nSkipping port checks since hostname could not be resolved.")
        print("Note: In simulation mode, the system runs with full mock capabilities without hardware.")
        return

    # 2. Port connectivity checks
    print("\nProbing standard Duckietown service ports:")
    for port, service_desc in PORTS_TO_CHECK.items():
        is_open = check_tcp_port(ROBOT_HOST, port)
        status_icon = "✅ OPEN  " if is_open else "❌ CLOSED"
        print(f"  {status_icon} Port {port:5d} : {service_desc}")

    # 3. HTTP Dashboard check
    try:
        resp = requests.get(f"http://{ROBOT_HOST}", timeout=2.0)
        print(f"\n✅ Duckietown Dashboard reachable (HTTP {resp.status_code})")
    except Exception as e:
        print(f"\n⚠️  Duckietown Dashboard HTTP check: {e}")

if __name__ == "__main__":
    main()
