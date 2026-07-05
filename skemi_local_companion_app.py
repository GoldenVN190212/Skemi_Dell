from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
import os

import skemi_local_computer_backend

app = FastAPI(title="Skemi Local Companion", version="0.2.0")
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "SKEMI_COMPANION_ALLOWED_ORIGINS",
        "http://127.0.0.1:8010,http://localhost:8010",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
skemi_local_computer_backend.register(app)


@app.get("/")
async def root():
    return {
        "success": True,
        "name": "Skemi Local Companion",
        "status_url": "/api/local-computer/status",
        "kill_switch": "Ctrl+Alt+Shift+K",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
