"""Delivered artifacts live in R2; working storage stays on Modal Volumes.

Why this exists (docs/research/infrastructure.md, decision 3). `api.py` used to
serve every asset by reading the whole object off a Volume into memory and
returning one `Response`. That has no HTTP range support, so a `<video>`
element asking for `Range: bytes=...` gets a 200 and the entire body: the
learner scrubbing their own clip -- the core interaction in `DESIGN.md` §7c --
downloads the whole file before the first seek resolves. That is a product
defect today, not a scaling problem later. R2 answers real 206s, charges $0
egress, and takes those bytes off the API container's concurrency budget.

What moves and what does not. Video, GLBs and the materialised `MotionResult`
are *delivered* to browsers, so they move here. The `.npz` is pipeline-internal
working storage that no browser ever touches, so it stays on the Volume.

**The contract constraint this must not break.** `motion-result.schema.json`
says an `asset_id` is an opaque, immutable id and is *never* a signed or
expiring URL stored in the document. So nothing in here changes what an
asset_id is -- `video:{clip_id}` and `{clip_id}_track{n}.glb` are exactly what
they were. Only the *resolution* of that id, at render time, in
`GET /assets/{asset_id}`, changes: it now redirects instead of proxying.

Keys are prefixed one-per-lesson (`lessons/{clip_id}/...`) so a takedown is a
single prefix delete and, once a CDN is in front, a single prefix purge.

Configuration is four env vars -- `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` -- from the `stepwise-r2` Modal
Secret in deployment, or `~/.stepwise-secrets/r2.env` on a laptop. If they are
absent `enabled()` is False and every caller falls back to the Volume
byte-proxy it used before. Additive, and reversible by unsetting one variable.
"""
from __future__ import annotations

import functools
import os

# One year, immutable: an asset_id names one immutable object, so a byte that
# has been fetched never needs refetching. Set at PUT time, on the object, so
# it is already correct the day a custom domain and CDN appear in front.
CACHE_CONTROL = "public, max-age=31536000, immutable"

# How long a presigned URL stays valid. Only used until R2_PUBLIC_BASE_URL is
# set; see url_for(). A day is long enough that a lesson left open overnight
# still plays, and short enough that a leaked URL is not forever.
PRESIGN_TTL_S = 86400


def _env(name: str) -> str:
    # .strip() is not decoration: the real r2.env on this machine has trailing
    # whitespace on R2_ENDPOINT_URL, which boto3 turns into an unroutable host.
    return os.environ.get(name, "").strip()


def enabled() -> bool:
    return bool(_env("R2_ENDPOINT_URL") and _env("R2_ACCESS_KEY_ID")
                and _env("R2_SECRET_ACCESS_KEY") and _env("R2_BUCKET_NAME"))


def bucket() -> str:
    return _env("R2_BUCKET_NAME")


@functools.lru_cache(maxsize=1)
def client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=_env("R2_ENDPOINT_URL"),
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


# --- keys -------------------------------------------------------------------
#
# One prefix per lesson. `delete_lesson` relies on it, and so does a future
# cache purge: "delete everything about this lesson" must be one operation, or
# it will eventually be a partial one.

def lesson_prefix(clip_id: str) -> str:
    return f"lessons/{clip_id}/"


def key_for(clip_id: str, asset_id: str) -> str:
    """The R2 key backing one opaque asset_id.

    `video:{clip_id}` -> `lessons/{clip_id}/source.mp4`
    `{clip_id}_track{n}.glb` -> `lessons/{clip_id}/{clip_id}_track{n}.glb`
    """
    if asset_id.startswith("video:"):
        return f"{lesson_prefix(clip_id)}source.mp4"
    return f"{lesson_prefix(clip_id)}{asset_id}"


def motion_result_key(clip_id: str) -> str:
    return f"{lesson_prefix(clip_id)}motion-result.json.gz"


# --- read / write -----------------------------------------------------------

def exists(key: str) -> bool:
    from botocore.exceptions import ClientError
    try:
        client().head_object(Bucket=bucket(), Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def put(key: str, data: bytes, content_type: str, content_encoding: str | None = None) -> None:
    kwargs = {"Bucket": bucket(), "Key": key, "Body": data,
              "ContentType": content_type, "CacheControl": CACHE_CONTROL}
    if content_encoding:
        kwargs["ContentEncoding"] = content_encoding
    client().put_object(**kwargs)


def url_for(key: str) -> str:
    """The URL a browser should fetch this object from.

    Two modes, one env var. With `R2_PUBLIC_BASE_URL` set (a custom domain on
    the bucket, e.g. `https://assets.example.com`) this returns a stable,
    cacheable, CDN-frontable URL -- which is what makes CACHE_CONTROL above
    mean anything, because a browser caches by URL.

    Without it, a presigned URL against the R2 S3 endpoint. That serves real
    206s today (verified), but its signature changes per request, so browser
    caching is defeated and every loop of the lesson is a fresh fetch. That is
    the honest cost of not yet owning a domain, and it is why the swap is one
    environment variable and not a code change.
    """
    base = _env("R2_PUBLIC_BASE_URL")
    if base:
        return f"{base.rstrip('/')}/{key}"
    return client().generate_presigned_url(
        "get_object", Params={"Bucket": bucket(), "Key": key}, ExpiresIn=PRESIGN_TTL_S)


def ensure(key: str, content_type: str, load: "callable", content_encoding: str | None = None) -> str:
    """Return a URL for `key`, copying the bytes in from the Volume if absent.

    ponytail: read-through, so the FIRST fetch of each asset pays one Volume
    read plus one R2 write and the rest are pure redirects. Deliberate --
    it means lessons reconstructed before R2 existed migrate themselves on
    demand, with no backfill job and no change to the pinned CV/glTF images
    (which the decision record warns against touching). Upgrade path when the
    first-fetch latency matters: have `export_clip_gltf` write straight to R2
    at export time, and this function becomes a plain `url_for`.
    """
    if not exists(key):
        data = load()
        if data is None:
            return ""
        put(key, data, content_type, content_encoding)
    return url_for(key)


def delete_lesson(clip_id: str) -> list[str]:
    """Delete every R2 object belonging to one lesson. Returns the keys removed.

    Used by the takedown path and the retention sweeper. Deleting by prefix
    rather than by a known list of names on purpose: the GLB names depend on
    ByteTrack's track ids, so a name-based delete can silently miss a dancer,
    and a removal that leaves one dancer's motion fetchable is not a removal.

    **Not finished the day R2_PUBLIC_BASE_URL is set.** With a CDN in front,
    deleting the origin object does not evict the edge copy, so a "deleted"
    video keeps being served from cache -- a broken privacy promise, not a
    caching bug (docs/research/infrastructure.md §9, D7). The lesson prefix
    above is what makes the fix one call; it needs a Cloudflare API token,
    which does not exist yet. Tracked in docs/DEPLOYMENT.md.
    """
    c, b = client(), bucket()
    keys: list[str] = []
    token = None
    while True:
        kw = {"Bucket": b, "Prefix": lesson_prefix(clip_id)}
        if token:
            kw["ContinuationToken"] = token
        page = c.list_objects_v2(**kw)
        keys += [o["Key"] for o in page.get("Contents", [])]
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    for i in range(0, len(keys), 1000):  # delete_objects caps at 1000 per call
        c.delete_objects(Bucket=b, Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]]})
    return keys
