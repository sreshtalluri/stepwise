"""Modal app definition + FastAPI endpoints for Stepwise processing pipeline."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
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
from pipeline.services.storage import check_cache, upload_result
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


class ProcessRequest(BaseModel):
    url: str


class ProcessResponse(BaseModel):
    status: str
    result: StepwiseResult | None = None
    cached: bool = False
    error: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/process", response_model=ProcessResponse)
async def process_video(request: ProcessRequest):
    """Process a dance video and return structured movement data.

    Steps:
    1. Validate and normalize the URL
    2. Check R2 cache for existing result
    3. Download video with yt-dlp
    4. Run pose extraction, hand detection, beat detection in parallel
    5. Compute foot contacts and difficulty from poses
    6. Build StepwiseResult, upload to R2, return
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
        pass  # Cache errors should not block processing

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

    # 5. Compute derived data from poses (these are fast, run sequentially)
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

    # 7. Upload to R2 (best-effort)
    try:
        await upload_result(computed_hash, result)
    except Exception:
        pass  # Don't fail the request if caching fails

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
