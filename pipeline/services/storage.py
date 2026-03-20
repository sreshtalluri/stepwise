"""Cloudflare R2 storage (S3-compatible) for caching processing results."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from pipeline.models.schema import StepwiseResult


class StorageError(Exception):
    """Raised when R2 operations fail."""


# Default TTL: 30 days
CACHE_TTL_DAYS = 30

# R2 bucket name
BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "stepwise-results")


def _get_r2_client():
    """Create boto3 S3 client configured for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("R2_ENDPOINT_URL"),
        aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def _result_key(url_hash: str) -> str:
    """Build the R2 object key for a result."""
    return f"{url_hash}/v1.0.json"


async def check_cache(url_hash: str) -> StepwiseResult | None:
    """Check if a cached result exists in R2 for this URL hash.

    Returns the cached StepwiseResult if found and not expired, else None.
    """
    try:
        client = _get_r2_client()
        key = _result_key(url_hash)

        response = client.get_object(Bucket=BUCKET_NAME, Key=key)
        data = json.loads(response["Body"].read())

        result = StepwiseResult.model_validate(data)

        # Check TTL
        processed_at = result.processed_at
        if processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - processed_at
        if age > timedelta(days=CACHE_TTL_DAYS):
            return None

        return result

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("NoSuchKey", "404"):
            return None
        raise StorageError(f"R2 cache check failed: {e}") from e
    except Exception:
        # Cache miss on any error — don't block processing
        return None


async def upload_result(url_hash: str, result: StepwiseResult) -> str:
    """Upload a StepwiseResult to R2.

    Args:
        url_hash: SHA-256 hash of the canonical URL.
        result: The processing result to cache.

    Returns:
        The R2 object key.

    Raises:
        StorageError: If upload fails.
    """
    try:
        client = _get_r2_client()
        key = _result_key(url_hash)

        client.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=result.model_dump_json(indent=2),
            ContentType="application/json",
        )

        return key

    except Exception as e:
        raise StorageError(f"Failed to upload result to R2: {e}") from e


def _video_key(url_hash: str) -> str:
    """Build the R2 object key for a video file."""
    return f"{url_hash}/video.mp4"


async def upload_video(url_hash: str, video_path: str) -> str:
    """Upload a video file to R2.

    Args:
        url_hash: SHA-256 hash of the canonical URL.
        video_path: Local path to the video file.

    Returns:
        The R2 object key.

    Raises:
        StorageError: If upload fails.
    """
    try:
        client = _get_r2_client()
        key = _video_key(url_hash)

        with open(video_path, "rb") as f:
            client.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=f,
                ContentType="video/mp4",
            )

        return key

    except Exception as e:
        raise StorageError(f"Failed to upload video to R2: {e}") from e


async def get_video_signed_url(url_hash: str, expires_in: int = 86400) -> str:
    """Generate a pre-signed URL for a video file (24h expiry by default)."""
    try:
        client = _get_r2_client()
        key = _video_key(url_hash)

        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=expires_in,
        )
        return url

    except Exception as e:
        raise StorageError(f"Failed to generate video signed URL: {e}") from e


async def get_signed_url(url_hash: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed URL for downloading a result.

    Args:
        url_hash: SHA-256 hash of the canonical URL.
        expires_in: URL expiration time in seconds (default 1 hour).

    Returns:
        Pre-signed URL string.
    """
    try:
        client = _get_r2_client()
        key = _result_key(url_hash)

        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=expires_in,
        )
        return url

    except Exception as e:
        raise StorageError(f"Failed to generate signed URL: {e}") from e
