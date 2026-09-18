from __future__ import annotations

import os

from pydantic import BaseModel, Field


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    max_video_seconds: int = Field(default_factory=lambda: _env_int("MAX_VIDEO_SECONDS", 120), ge=1)
    target_mesh_fps: int = Field(default_factory=lambda: _env_int("TARGET_MESH_FPS", 24), ge=1)

    # Storage is S3-compatible so the same adapter works for Cloudflare R2 in
    # production and an in-memory fake in local tests.
    storage_backend: str = Field(default_factory=lambda: _env("STORAGE_BACKEND", "memory") or "memory")
    s3_endpoint_url: str | None = Field(default_factory=lambda: _env("S3_ENDPOINT_URL"))
    s3_region: str = Field(default_factory=lambda: _env("S3_REGION", "auto") or "auto")
    s3_bucket: str | None = Field(default_factory=lambda: _env("S3_BUCKET"))
    s3_access_key_id: str | None = Field(default_factory=lambda: _env("S3_ACCESS_KEY_ID"))
    s3_secret_access_key: str | None = Field(default_factory=lambda: _env("S3_SECRET_ACCESS_KEY"))
    upload_presign_ttl_seconds: int = Field(default_factory=lambda: _env_int("UPLOAD_PRESIGN_TTL_SECONDS", 900), ge=60)
    result_presign_ttl_seconds: int = Field(default_factory=lambda: _env_int("RESULT_PRESIGN_TTL_SECONDS", 3600), ge=60)

    database_url: str | None = Field(default_factory=lambda: _env("DATABASE_URL"))
    modal_gpu_worker_url: str | None = Field(default_factory=lambda: _env("MODAL_GPU_WORKER_URL"))
    modal_gpu_worker_token: str | None = Field(default_factory=lambda: _env("MODAL_GPU_WORKER_TOKEN"))
    cors_origins: list[str] = Field(default_factory=lambda: _env_list("CORS_ORIGINS", ["http://localhost:3000"]))
