"""FastAPI application entrypoint for Duckiebot AI Navigation System."""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.api.routes import router
from backend.services.system_manager import SystemManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("duckiebot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for FastAPI."""
    logger.info("Initializing Duckiebot Application...")
    # Initialize singleton system manager
    SystemManager.get_instance()
    yield
    logger.info("Shutting down Duckiebot Application...")
    SystemManager.get_instance().shutdown()


app = FastAPI(
    title="Duckiebot AI Natural-Language Navigation System",
    description="DB21J Jetson Nano 4GB Computer Vision & Cloud LLM Navigation Stack",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local development and cross-origin dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# Mount dashboard static files
dashboard_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))
if os.path.exists(dashboard_path):
    app.mount("/static", StaticFiles(directory=dashboard_path), name="static")

    @app.get("/")
    def serve_dashboard():
        """Serve dashboard single page app."""
        index_file = os.path.join(dashboard_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Duckiebot backend is online. Dashboard index.html not found."}
