"""Modal deployment for the Stepwise processing pipeline.

Deploys the FastAPI app on a T4 GPU with all dependencies.
Uses MediaPipe Pose Landmarker for 3D body pose estimation.

Deploy (from project root):
    modal deploy pipeline/modal_app.py

Test locally:
    modal serve pipeline/modal_app.py
"""

from __future__ import annotations

from pathlib import Path

import modal

app = modal.App("stepwise-pipeline")

# Path to the pipeline package (parent of this file)
PIPELINE_DIR = Path(__file__).parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1-mesa-glx", "libglib2.0-0", "wget")
    .pip_install(
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pydantic>=2.5.0",
        "yt-dlp>=2023.11.16",
        "librosa>=0.10.1",
        "mediapipe>=0.10.8",
        "numpy>=1.24.0",
        "boto3>=1.29.0",
        "httpx>=0.25.0",
        "opencv-python-headless>=4.8.0",
    )
    .run_commands(
        # Download MediaPipe Pose Landmarker model (heavy variant for best accuracy)
        "mkdir -p /models/mediapipe",
        "wget -q -O /models/mediapipe/pose_landmarker_heavy.task "
        "'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task'",
    )
    .env({"PYTHONPATH": "/root"})
    .add_local_dir(
        local_path=str(PIPELINE_DIR),
        remote_path="/root/pipeline",
    )
)


@app.function(
    image=image,
    gpu="T4",
    timeout=600,
    secrets=[modal.Secret.from_name("stepwise-r2")],
)
@modal.asgi_app()
def fastapi_app():
    import os
    os.environ.setdefault("USE_REAL_POSE", "true")
    from pipeline.app import app as _app
    return _app
