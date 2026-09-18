from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from mesh_api.adapters.mock import MockMeshRecoverer, MockPersonDetector, MockPersonTracker, MockVideoIngestor
from mesh_api.config import Settings
from mesh_api.jobs import InMemoryJobStore
from mesh_api.models import JobCreate, JobStatus, UploadPresignCreate, UploadPresignResponse
from mesh_api.pipeline import PipelineAdapters, VideoTooLongError
from mesh_api.storage import create_storage, storage_ref_to_key, upload_object_key


def create_app(settings: Settings | None = None, scenario: str = "two_person_crossing", mesh_unavailable: bool = False) -> FastAPI:
    settings = settings or Settings()
    ingestor = MockVideoIngestor()
    detector = MockPersonDetector(scenario=scenario)
    tracker = MockPersonTracker()
    mesh = MockMeshRecoverer(available=not mesh_unavailable)
    adapters = PipelineAdapters(ingestor=ingestor, detector=detector, tracker=tracker, mesh_recoverer=mesh)
    storage = create_storage(settings)
    store = InMemoryJobStore(settings=settings, adapters=adapters, storage=storage)
    app = FastAPI(title="Stepwise Mesh API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "mesh-api"}

    @app.get("/v1/models")
    def models() -> dict:
        return {
            "defaults": {"max_video_seconds": settings.max_video_seconds, "target_mesh_fps": settings.target_mesh_fps},
            "storage": {"backend": settings.storage_backend, "direct_uploads": True},
            "ingestors": [ingestor.descriptor.model_dump()],
            "detectors": [detector.descriptor.model_dump()],
            "trackers": [tracker.descriptor.model_dump()],
            "mesh_recoverers": [mesh.descriptor.model_dump() | {"enabled": mesh.available}],
            "license_flags": [flag.model_dump() for flag in ingestor.license_flags + detector.license_flags + tracker.license_flags + mesh.license_flags],
        }

    @app.post("/v1/uploads/presign", response_model=UploadPresignResponse)
    def presign_upload(payload: UploadPresignCreate) -> UploadPresignResponse:
        key = upload_object_key(payload.filename)
        presigned = storage.presign_put(key, content_type=payload.content_type, expires_in_seconds=settings.upload_presign_ttl_seconds)
        return UploadPresignResponse(
            upload_url=presigned.upload_url,
            upload_ref=presigned.upload_ref,
            object_key=presigned.object_key,
            headers=presigned.headers,
            expires_in_seconds=presigned.expires_in_seconds,
        )

    @app.post("/v1/jobs", response_model=JobStatus)
    def create_job(payload: JobCreate) -> JobStatus:
        if not mesh.available:
            raise HTTPException(status_code=503, detail="Mesh adapter unavailable: enable a MeshRecoverer adapter before starting jobs.")
        source_url = payload.source_url or payload.upload_ref
        if not source_url:
            raise HTTPException(status_code=422, detail="source_url or upload_ref is required")
        if payload.upload_ref:
            storage_ref_to_key(payload.upload_ref)
        probe = ingestor.probe(source_url)
        if probe.duration_seconds > settings.max_video_seconds:
            raise HTTPException(status_code=400, detail=f"Video is too long ({probe.duration_seconds:.0f}s). Max is {settings.max_video_seconds}s.")
        return store.create(source_url)


    @app.post("/v1/jobs/upload", response_model=JobStatus)
    async def create_job_from_uploaded_video(request: Request) -> JobStatus:
        if not mesh.available:
            raise HTTPException(status_code=503, detail="Mesh adapter unavailable: enable a MeshRecoverer adapter before starting jobs.")
        body = await request.body()
        if not body:
            raise HTTPException(status_code=422, detail="raw video bytes are required")
        filename = request.headers.get("x-filename", "uploaded-video.mp4").replace("/", "_")
        content_type = request.headers.get("content-type", "application/octet-stream")
        if not (content_type.startswith("video/") or content_type == "application/octet-stream"):
            raise HTTPException(status_code=415, detail="upload must be video bytes")
        object_key = upload_object_key(filename)
        storage.put_bytes(object_key, body, content_type=content_type)
        upload_ref = f"storage://{object_key}"
        probe = ingestor.probe(upload_ref)
        if probe.duration_seconds > settings.max_video_seconds:
            raise HTTPException(status_code=400, detail=f"Video is too long ({probe.duration_seconds:.0f}s). Max is {settings.max_video_seconds}s.")
        return store.create(upload_ref)

    @app.get("/v1/jobs/{job_id}", response_model=JobStatus)
    def get_job(job_id: str) -> JobStatus:
        try:
            status = store.get(job_id)
        except VideoTooLongError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not status:
            raise HTTPException(status_code=404, detail="job not found")
        return status

    @app.get("/v1/jobs/{job_id}/result")
    def get_result(job_id: str) -> dict:
        result = store.result(job_id)
        if not result:
            status = store.statuses.get(job_id)
            if status and status.error:
                raise HTTPException(status_code=409, detail=status.error)
            raise HTTPException(status_code=404, detail="result not found")
        return result.model_dump(mode="json")

    app.state.job_store = store
    app.state.object_storage = storage
    return app


app = create_app()
