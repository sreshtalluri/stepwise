from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote
from uuid import uuid4

from mesh_api.config import Settings


class StorageConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PresignedPut:
    upload_url: str
    object_key: str
    headers: dict[str, str]
    expires_in_seconds: int

    @property
    def upload_ref(self) -> str:
        return f"storage://{self.object_key}"


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None: ...

    def put_json(self, key: str, payload: dict[str, Any]) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def presign_put(self, key: str, *, content_type: str, expires_in_seconds: int) -> PresignedPut: ...

    def presign_get(self, key: str, *, expires_in_seconds: int) -> str: ...


def safe_filename(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1].strip().lower()
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-._")
    return stem or "uploaded-video.mp4"


def storage_ref_to_key(upload_ref: str) -> str:
    if not upload_ref.startswith("storage://"):
        raise ValueError("storage reference must start with storage://")
    key = upload_ref.removeprefix("storage://").lstrip("/")
    if not key:
        raise ValueError("storage reference is missing an object key")
    return key


def upload_object_key(filename: str) -> str:
    return f"uploads/{uuid4()}/{safe_filename(filename)}"


class InMemoryObjectStorage:
    """Small deterministic object store for tests and local mock runs."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        self.objects[key] = data
        self.content_types[key] = content_type

    def put_json(self, key: str, payload: dict[str, Any]) -> None:
        self.put_bytes(key, json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"), content_type="application/json")

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def presign_put(self, key: str, *, content_type: str, expires_in_seconds: int) -> PresignedPut:
        return PresignedPut(
            upload_url=f"memory://signed-put/{quote(key)}",
            object_key=key,
            headers={"Content-Type": content_type},
            expires_in_seconds=expires_in_seconds,
        )

    def presign_get(self, key: str, *, expires_in_seconds: int) -> str:
        return f"memory://signed-get/{quote(key)}?expires={expires_in_seconds}"


class S3ObjectStorage:
    """S3-compatible storage adapter used for Cloudflare R2."""

    def __init__(self, settings: Settings) -> None:
        if not all([settings.s3_endpoint_url, settings.s3_bucket, settings.s3_access_key_id, settings.s3_secret_access_key]):
            raise StorageConfigurationError("S3/R2 storage requires S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and S3_SECRET_ACCESS_KEY.")
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover - only hit in production config without extras
            raise StorageConfigurationError("S3/R2 storage requires installing the optional boto3 dependency.") from exc

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def put_json(self, key: str, payload: dict[str, Any]) -> None:
        self.put_bytes(key, json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"), content_type="application/json")

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def presign_put(self, key: str, *, content_type: str, expires_in_seconds: int) -> PresignedPut:
        upload_url = self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in_seconds,
        )
        return PresignedPut(upload_url=upload_url, object_key=key, headers={"Content-Type": content_type}, expires_in_seconds=expires_in_seconds)

    def presign_get(self, key: str, *, expires_in_seconds: int) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in_seconds,
        )


def create_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend.lower() in {"s3", "r2", "cloudflare-r2"}:
        return S3ObjectStorage(settings)
    return InMemoryObjectStorage()
