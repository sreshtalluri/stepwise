"""Modal app definition + FastAPI endpoints for Stepwise processing pipeline."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline.models.schema import StepwiseResult, StepwiseResultV2
from pipeline.services.beat_detector import detect_beats
from pipeline.services.difficulty import compute_body_part_difficulty, compute_difficulty
from pipeline.services.smplx_extractor import extract_smplx
from pipeline.services.downloader import (
    DownloadError,
    VideoTooLongError,
    download_video,
)
from pipeline.services.foot_contact import compute_foot_contacts
from pipeline.services.hand_detector import detect_hands
from pipeline.services.pose_extractor import extract_poses
from pipeline.services.storage import check_cache, get_signed_url, get_video_signed_url, upload_result, upload_video
from pipeline.utils.url_normalizer import (
    InvalidURLError,
    UnsupportedPlatformError,
    extract_video_id,
    is_tiktok_shortlink,
    resolve_shortlink,
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

# CORS middleware — allow frontend (localhost:3000 + Modal deployment) to call the pipeline
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://localhost:3000",
    ],
    allow_origin_regex=r"https://.*--stepwise-pipeline.*\.modal\.run",
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
    video_url: str | None = None


class AsyncProcessResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    status: str  # "processing" | "skeleton_ready" | "upgrading" | "mannequin_ready" | "complete" | "error"
    step: str | None = None
    result_url: str | None = None
    skeleton_result_url: str | None = None
    mannequin_result_url: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}


async def _run_pipeline(job_id: str, url: str) -> None:
    """Run the progressive enhancement pipeline.

    Pass 1 (fast): MediaPipe -> skeleton data -> upload v1 -> status: skeleton_ready
    Pass 2 (slow): SMPL-X -> mannequin data -> upload v2 -> status: mannequin_ready
    """
    job = _jobs[job_id]

    try:
        # 0. Resolve short links
        if is_tiktok_shortlink(url):
            try:
                url = await resolve_shortlink(url)
            except InvalidURLError as e:
                job["status"] = "error"
                job["error"] = str(e)
                return

        # 1. Validate URL
        job["step"] = "Downloading video..."
        try:
            platform, video_id = extract_video_id(url)
            computed_hash = url_hash(url)
        except (InvalidURLError, UnsupportedPlatformError) as e:
            job["status"] = "error"
            job["error"] = str(e)
            return

        # 2. Check cache (v2 first, fall back to v1)
        try:
            cached = await check_cache(computed_hash)
            if cached is not None:
                signed_url = await get_signed_url(computed_hash)
                job["status"] = "complete"
                job["result_url"] = signed_url
                job["skeleton_result_url"] = signed_url
                return
        except Exception:
            pass

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

        # =====================================================================
        # PASS 1: MediaPipe fast pass -> skeleton (v1)
        # =====================================================================
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

        foot_contacts = compute_foot_contacts(poses, video_info.fps)
        difficulty = compute_difficulty(poses, video_info.fps)

        result_v1 = StepwiseResult(
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

        # Upload v1 skeleton result
        try:
            await upload_result(computed_hash, result_v1)
            skeleton_url = await get_signed_url(computed_hash)
            job["skeleton_result_url"] = skeleton_url
            job["result_url"] = skeleton_url
        except Exception:
            job["status"] = "error"
            job["error"] = "Failed to upload skeleton result"
            return

        # Upload video to R2
        try:
            await upload_video(computed_hash, str(video_info.video_path))
        except Exception:
            pass  # Video upload failure shouldn't block

        job["status"] = "skeleton_ready"
        job["step"] = "Enhancing with SMPL-X..."

        # =====================================================================
        # PASS 2: SMPL-X full pass -> mannequin (v2)
        # =====================================================================
        try:
            smplx_result = await extract_smplx(
                video_info.video_path,
                video_info.total_frames,
                video_info.fps,
            )

            job["status"] = "upgrading"
            job["step"] = "Analyzing movement detail..."

            body_part_diff = compute_body_part_difficulty(poses, video_info.fps)

            result_v2 = StepwiseResultV2(
                version="2.0",
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
                person_count=smplx_result.person_count,
                person_poses=smplx_result.person_poses,
                body_part_difficulty=body_part_diff,
                processed_at=datetime.now(timezone.utc),
            )

            # Upload v2 with a different R2 key so v1 is preserved
            from pipeline.services.storage import _get_r2_client, BUCKET_NAME
            v2_key = f"{computed_hash}/v2.0.json"
            client = _get_r2_client()
            client.put_object(
                Bucket=BUCKET_NAME,
                Key=v2_key,
                Body=result_v2.model_dump_json(indent=2),
                ContentType="application/json",
            )
            mannequin_url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": v2_key},
                ExpiresIn=3600,
            )
            job["mannequin_result_url"] = mannequin_url
            job["result_url"] = mannequin_url
            job["status"] = "mannequin_ready"

        except NotImplementedError:
            # Real SMPL-X not available yet — stay on skeleton
            job["status"] = "skeleton_ready"
        except Exception:
            # SMPL-X failed — stay on skeleton, which is already available
            job["status"] = "skeleton_ready"

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

    # Resolve TikTok short links (tiktok.com/t/*, vm.tiktok.com/*)
    if is_tiktok_shortlink(url):
        try:
            url = await resolve_shortlink(url)
        except InvalidURLError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Basic URL validation
    try:
        extract_video_id(url)
    except (InvalidURLError, UnsupportedPlatformError) as e:
        if str(e).startswith("SHORTLINK:"):
            raise HTTPException(status_code=400, detail="Could not resolve TikTok short link")
        raise HTTPException(status_code=400, detail=str(e))

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "processing",
        "step": "Downloading video...",
        "result_url": None,
        "skeleton_result_url": None,
        "mannequin_result_url": None,
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
        skeleton_result_url=job.get("skeleton_result_url"),
        mannequin_result_url=job.get("mannequin_result_url"),
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
            # Try to get the video URL from R2 too
            cached_video_url = None
            try:
                cached_video_url = await get_video_signed_url(computed_hash)
            except Exception:
                pass
            return ProcessResponse(status="ok", result=cached, cached=True, video_url=cached_video_url)
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

    # 7. Upload result + video to R2
    video_signed_url = None
    try:
        await upload_result(computed_hash, result)
        await upload_video(computed_hash, str(video_info.video_path))
        video_signed_url = await get_video_signed_url(computed_hash)
    except Exception:
        # Fall back to direct CDN URL if R2 upload fails
        video_signed_url = video_info.direct_video_url

    return ProcessResponse(
        status="ok",
        result=result,
        cached=False,
        video_url=video_signed_url,
    )


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
