"""Main launcher script for Duckiebot AI Navigation System."""

import os
import sys
import logging
import uvicorn
import yaml

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def load_config():
    cfg_file = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    if os.path.exists(cfg_file):
        with open(cfg_file, "r") as f:
            return yaml.safe_load(f)
    return {}

def main():
    cfg = load_config()
    dashboard_cfg = cfg.get("dashboard", {})
    host = dashboard_cfg.get("host", "0.0.0.0")
    port = int(dashboard_cfg.get("port", 8000))
    mode = cfg.get("system", {}).get("mode", "simulation").upper()

    print("=" * 65)
    print(" 🦆 DUCKIEBOT DB21J AI NATURAL-LANGUAGE NAVIGATION SYSTEM")
    print(f" Operating Mode : [{mode}]")
    print(f" Robot Target   : {cfg.get('robot', {}).get('hostname', 'entebot209.local')}")
    print(f" Web Dashboard  : http://localhost:{port}")
    print(f" API Docs       : http://localhost:{port}/docs")
    print("=" * 65)

    uvicorn.run("backend.app:app", host=host, port=port, reload=False, log_level="info")

if __name__ == "__main__":
    main()
