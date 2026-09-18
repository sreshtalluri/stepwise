from __future__ import annotations

from uuid import uuid4
from mesh_api.config import Settings
from mesh_api.models import JobStage, JobStatus, MeshResultV1
from mesh_api.pipeline import NoPeopleFoundError, PipelineAdapters, VideoTooLongError, run_pipeline
from mesh_api.storage import ObjectStorage


class InMemoryJobStore:
    def __init__(self, settings: Settings, adapters: PipelineAdapters, storage: ObjectStorage | None = None) -> None:
        self.settings = settings
        self.adapters = adapters
        self.storage = storage
        self.statuses: dict[str, JobStatus] = {}
        self.sources: dict[str, str] = {}
        self.results: dict[str, MeshResultV1] = {}

    def create(self, source_url: str) -> JobStatus:
        job_id = str(uuid4())
        status = JobStatus(job_id=job_id, stage=JobStage.QUEUED, progress=0)
        self.statuses[job_id] = status
        self.sources[job_id] = source_url
        return status

    def get(self, job_id: str) -> JobStatus | None:
        status = self.statuses.get(job_id)
        if status and status.stage == JobStage.QUEUED:
            self._run(job_id)
        return self.statuses.get(job_id)

    def result(self, job_id: str) -> MeshResultV1 | None:
        self.get(job_id)
        return self.results.get(job_id)

    def _run(self, job_id: str) -> None:
        source_url = self.sources[job_id]
        try:
            for stage, progress in [
                (JobStage.DOWNLOADING, 10),
                (JobStage.DETECTING, 25),
                (JobStage.TRACKING, 38),
                (JobStage.MESHING, 55),
                (JobStage.SKINNING, 68),
                (JobStage.SMOOTHING, 76),
                (JobStage.ANALYZING, 86),
                (JobStage.PACKAGING, 94),
            ]:
                self.statuses[job_id] = JobStatus(job_id=job_id, stage=stage, progress=progress)
            result = run_pipeline(source_url, self.settings, self.adapters)
            if self.storage:
                self._persist_result_assets(job_id, result)
            self.results[job_id] = result
            self.statuses[job_id] = JobStatus(job_id=job_id, stage=JobStage.COMPLETE, progress=100, people_detected=len(result.people))
        except NoPeopleFoundError as exc:
            self.statuses[job_id] = JobStatus(job_id=job_id, stage=JobStage.FAILED, progress=100, error=str(exc))
        except VideoTooLongError:
            raise
        except Exception as exc:
            self.statuses[job_id] = JobStatus(job_id=job_id, stage=JobStage.FAILED, progress=100, error=str(exc))

    def _persist_result_assets(self, job_id: str, result: MeshResultV1) -> None:
        mesh_asset_urls: list[dict] = []
        for person in result.people:
            if not person.mesh_asset:
                continue
            key = f"results/{job_id}/meshes/{person.track_id}.mesh.json"
            self.storage.put_json(key, person.mesh_asset.model_dump(mode="json"))
            mesh_asset_urls.append(
                {
                    "track_id": person.track_id,
                    "url": self.storage.presign_get(key, expires_in_seconds=self.settings.result_presign_ttl_seconds),
                    "content_type": "application/json",
                }
            )
        result.assets.mesh_asset_urls = mesh_asset_urls
        result.assets.glb_url = self.storage.presign_get(f"results/{job_id}/stepwise-result.glb", expires_in_seconds=self.settings.result_presign_ttl_seconds)
        result.assets.debug_overlay_urls = [self.storage.presign_get(f"results/{job_id}/debug-overlay.mp4", expires_in_seconds=self.settings.result_presign_ttl_seconds)]
        self.storage.put_json(f"results/{job_id}/mesh-result-v1.json", result.model_dump(mode="json"))
