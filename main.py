"""
LangGraph Platform - Main Entry Point
Starts the FastAPI server with static file serving for the visual frontend.
"""
import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.server import app as api_app

# Create the main app that wraps the API app
app = FastAPI(title="LangGraph Platform")

# Mount the API app
app.mount("/api", api_app)

# Serve static frontend files
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    async def serve_frontend():
        content = (frontend_dir / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(content=content, media_type="text/html")
else:
    @app.get("/")
    async def root():
        return {"message": "LangGraph Platform API", "docs": "/docs"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=19527,
        reload=False,
        log_level="info",
    )
