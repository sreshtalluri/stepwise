"""Modal app definition + FastAPI endpoints for Stepwise processing pipeline."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline.models.schema import StepwiseResult
from pipeline.services.beat_detector import detect_beats
from pipeline.services.difficulty import compute_difficulty
from pipeline.services.downloader import (
    DownloadError,
    VideoTooLongError,
    download_video,
)
from pipeline.services.foot_contact import compute_foot_contacts
from pipeline.services.hand_detector import detect_hands
from pipeline.services.pose_extractor import extract_poses
from pipeline.services.storage import check_cache, get_signed_url, upload_result
from pipeline.utils.url_normalizer import (
    InvalidURLError,
    UnsupportedPlatformError,
    extract_video_id,
    url_hash,
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Stepwise Processing Pipeline",
    description="Extract 3D pose, hand gestures, foot contacts, beats, and difficulty from dance videos.",
    version="1.0.0",
)

# CORS middleware — allow frontend (localhost:3000) to call the pipeline
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    url: str


class ProcessResponse(BaseModel):
    status: str
    result: StepwiseResult | None = None
    cached: bool = False
    error: str | None = None


class AsyncProcessResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    status: str  # "processing" | "complete" | "error"
    step: str | None = None
    result_url: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}


async def _run_pipeline(job_id: str, url: str) -> None:
    """Run the full processing pipeline in the background, updating job status."""
    job = _jobs[job_id]

    try:
        # 1. Validate URL
        job["step"] = "Downloading video..."
        try:
            platform, video_id = extract_video_id(url)
            computed_hash = url_hash(url)
        except (InvalidURLError, UnsupportedPlatformError) as e:
            job["status"] = "error"
            job["error"] = str(e)
            return

        # 2. Check cache
        try:
            cached = await check_cache(computed_hash)
            if cached is not None:
                signed_url = await get_signed_url(computed_hash)
                job["status"] = "complete"
                job["result_url"] = signed_url
                return
        except Exception:
            pass  # Cache errors should not block processing

        # 3. Download video
        try:
            video_info = await download_video(url)
        except VideoTooLongError as e:
            job["status"] = "error"
            job["error"] = str(e)
            return
        except DownloadError as e:
            job["status"] = "error"
            job["error"] = str(e)
            return

        # 4. Run independent steps in parallel
        job["step"] = "Extracting poses..."

        poses_task = extract_poses(
            video_info.video_path, video_info.total_frames, video_info.fps
        )
        hands_task = detect_hands(
            video_info.video_path, video_info.total_frames, video_info.fps
        )
        beats_task = detect_beats(
            video_info.audio_path, video_info.duration_seconds
        )

        poses, hand_states, beats = await asyncio.gather(
            poses_task, hands_task, beats_task
        )

        job["step"] = "Detecting beats..."

        # 5. Compute derived data from poses
        job["step"] = "Almost ready..."
        foot_contacts = compute_foot_contacts(poses, video_info.fps)
        difficulty = compute_difficulty(poses, video_info.fps)

        # 6. Build result
        result = StepwiseResult(
            version="1.0",
            video_id=video_info.video_id,
            url_hash=computed_hash,
            source_url=url,
            duration_seconds=video_info.duration_seconds,
            fps=video_info.fps,
            total_frames=video_info.total_frames,
            body_poses=poses,
            hand_states=hand_states,
            foot_contacts=foot_contacts,
            beats=beats,
            difficulty=difficulty,
            processed_at=datetime.now(timezone.utc),
        )

        # 7. Upload to R2
        try:
            await upload_result(computed_hash, result)
            signed_url = await get_signed_url(computed_hash)
            job["result_url"] = signed_url
        except Exception:
            # If upload fails, we can't provide a URL
            job["status"] = "error"
            job["error"] = "Failed to upload result"
            return

        job["status"] = "complete"

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/process", response_model=AsyncProcessResponse)
async def process_video(request: ProcessRequest):
    """Accept a video URL, start processing in the background, return a job ID."""
    url = request.url

    # Basic URL validation
    try:
        extract_video_id(url)
    except (InvalidURLError, UnsupportedPlatformError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "processing",
        "step": "Downloading video...",
        "result_url": None,
        "error": None,
    }

    # Start processing in the background
    asyncio.create_task(_run_pipeline(job_id, url))

    return AsyncProcessResponse(job_id=job_id)


@app.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Check the status of a processing job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    return JobStatusResponse(
        status=job["status"],
        step=job.get("step"),
        result_url=job.get("result_url"),
        error=job.get("error"),
    )


@app.post("/process/sync", response_model=ProcessResponse)
async def process_video_sync(request: ProcessRequest):
    """Process a dance video synchronously and return structured movement data.

    This is the original synchronous endpoint, kept for backwards compatibility.
    """
    url = request.url

    # 1. Validate URL
    try:
        platform, video_id = extract_video_id(url)
        computed_hash = url_hash(url)
    except InvalidURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnsupportedPlatformError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Check cache
    try:
        cached = await check_cache(computed_hash)
        if cached is not None:
            return ProcessResponse(status="ok", result=cached, cached=True)
    except Exception:
        pass

    # 3. Download video
    try:
        video_info = await download_video(url)
    except VideoTooLongError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DownloadError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # 4. Run independent steps in parallel
    poses_task = extract_poses(
        video_info.video_path, video_info.total_frames, video_info.fps
    )
    hands_task = detect_hands(
        video_info.video_path, video_info.total_frames, video_info.fps
    )
    beats_task = detect_beats(
        video_info.audio_path, video_info.duration_seconds
    )

    poses, hand_states, beats = await asyncio.gather(
        poses_task, hands_task, beats_task
    )

    # 5. Compute derived data
    foot_contacts = compute_foot_contacts(poses, video_info.fps)
    difficulty = compute_difficulty(poses, video_info.fps)

    # 6. Build result
    result = StepwiseResult(
        version="1.0",
        video_id=video_info.video_id,
        url_hash=computed_hash,
        source_url=url,
        duration_seconds=video_info.duration_seconds,
        fps=video_info.fps,
        total_frames=video_info.total_frames,
        body_poses=poses,
        hand_states=hand_states,
        foot_contacts=foot_contacts,
        beats=beats,
        difficulty=difficulty,
        processed_at=datetime.now(timezone.utc),
    )

    # 7. Upload to R2
    try:
        await upload_result(computed_hash, result)
    except Exception:
        pass

    return ProcessResponse(status="ok", result=result, cached=False)


# ---------------------------------------------------------------------------
# Modal app (commented out for local dev — uncomment for deployment)
# ---------------------------------------------------------------------------
# import modal
#
# modal_app = modal.App("stepwise-pipeline")
#
# modal_image = modal.Image.debian_slim().pip_install_from_requirements(
#     "requirements.txt"
# )
#
# @modal_app.function(
#     image=modal_image,
#     gpu="T4",
#     timeout=300,
# )
# @modal.asgi_app()
# def fastapi_app():
#     return app
