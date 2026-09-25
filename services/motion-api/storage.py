"""Where a lesson's delivered bytes live: Cloudflare R2, over S3's API.

**This is a bug fix before it is a cost decision** (docs/research/infrastructure.md
decision 3). `api.py::_volume_read_bytes` reads a whole object into memory with
`volume.read_file_into_fileobj()` and returns one `Response`. A `<video>`
element asking for `Range: bytes=...` gets a **200 with the entire body**, so a
learner scrubbing their own clip -- DESIGN.md §7c's core interaction, "speed,
mirror and loop already working" -- downloads every byte before the first seek
resolves. R2 speaks S3, and an S3 GET honours `Range`. That is the fix; zero
egress fees are a bonus, not the argument.

**What moves and what does not.** Video, GLBs and the materialised
`MotionResult` move here: browsers fetch them. The `.npz` and the model weights
stay on Modal Volumes -- pipeline-internal, never touched by a browser, and the
Volumes already work.

**The contract does not change.** An `asset_id` is opaque and immutable and is
*never* a signed or expiring URL (motion-result.schema.json's `AnimationRef`
comment is explicit). This module maps `asset_id -> key`; `GET /assets/{id}`
stays the separate resolution step and answers with a 302. The id in the
stored document is the same string it always was.

**Two URL modes, chosen by configuration, never by code:**

  * `R2_PUBLIC_BASE_URL` set -> a plain immutable `https://assets.example/<key>`.
    That is the custom domain decision 3 wants: real Cloudflare edge caching,
    `Cache-Control: immutable`, no signature, no expiry. **Not available yet** --
    it needs a domain and Workers Paid, neither of which exists today.
  * unset -> a **presigned GET**, valid `PRESIGN_TTL_S`. Correct right now (the
    bucket is private and there is no domain), gives genuine HTTP 206 range
    responses, and simply misses the edge cache. Swapping to the first mode is
    one environment variable on the `stepwise-r2` Modal Secret and no code change.

Serving video from an R2 origin sits against Cloudflare's CDN content
restriction for customers without Paid Services (infrastructure.md §3, licence
scrutiny). The mitigation recorded there is to be an unambiguous paid Developer
Platform customer -- Workers Paid, $5/mo -- which the frontend needs anyway.
Do not run this on the free plan to save $5.

Degrades to nothing rather than to a crash: with no R2 credentials configured
`enabled()` is False and every caller keeps its old Volume path. That is what
makes this deployable before the swap is finished, and revertible after.
"""
from __future__ import annotations

import os
from typing import Optional

# How long a presigned GET stays valid. Long enough that a learner can open a
# lesson, wander off and come back before the <video> element's next range
# request 403s; short enough that a leaked URL is not a permanent one. Only
# used in the no-custom-domain mode -- with R2_PUBLIC_BASE_URL set there is no
# signature and no expiry at all.
PRESIGN_TTL_S = 6 * 3600

# Delivered bytes are immutable: a video is keyed by its clip_id, and a GLB or
# a MotionResult is keyed by a hash of its own bytes (`versioned_name`), so a
# re-export writes NEW keys instead of rewriting old ones. That is what makes a
# one-year `immutable` safe. It was not before: GLBs were `{clip}_track{n}.glb`,
# and a re-processed lesson (job_a10682..., 2026-09-24) keeps its stale bytes
# in any cache keyed on that name -- for a year, once assets have a stable
# public URL (R2_PUBLIC_BASE_URL).
CACHE_CONTROL = "public, max-age=31536000, immutable"
# The one object that IS rewritten: `motion-result/{clip}.json.gz`, the
# "latest" copy api.py reads and heads (its metadata names the current
# version). No browser is ever sent to it; it says no-cache to any cache anyway.
MUTABLE_CACHE_CONTROL = "no-cache"

_ENV = ("R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")

_client = None


def enabled() -> bool:
    """True when every credential this module needs is present.

    Checked per call, not cached at import: Modal injects Secrets into the
    container environment, and a module imported before that happened would
    otherwise decide "no R2" permanently.
    """
    return all(os.environ.get(k) for k in _ENV)


def missing_env() -> list[str]:
    """Which of the four are absent -- for /health, so a 2am reader is told
    *which* credential is missing rather than 'storage not configured'."""
    return [k for k in _ENV if not os.environ.get(k)]


def bucket() -> str:
    return os.environ["R2_BUCKET_NAME"]


def client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=os.environ["R2_ENDPOINT_URL"],
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            # R2 ignores the region but botocore insists on one, and R2's
            # documented value is "auto". s3v4 is required: R2 rejects the
            # older signature versions outright.
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
    return _client


# --- asset_id <-> key ------------------------------------------------------
#
# Prefixes exist so a delete can be a prefix sweep and so a Cloudflare cache
# purge can be scoped (infrastructure.md §9 D7: deleting the origin object does
# not delete the edge copy -- a "deleted" video still served from an edge cache
# is a broken privacy promise, not a caching bug).

def video_key(clip_id: str) -> str:
    return f"video/{clip_id}.mp4"


def glb_key(glb_name: str) -> str:
    """`glb_name` is `{clip_id}_track{n}.{version}.glb` (or, for a lesson
    exported before versioning, `{clip_id}_track{n}.glb`), per
    modal_app.export_clip_gltf."""
    return f"glb/{glb_name}"


def motion_result_key(clip_id: str, version: Optional[str] = None) -> str:
    """No version: the "latest" copy (see MUTABLE_CACHE_CONTROL). With one: the
    immutable object a browser is redirected to."""
    return f"motion-result/{clip_id}.{version}.json.gz" if version else f"motion-result/{clip_id}.json.gz"


def content_version(data: bytes) -> str:
    """12 hex chars of sha256: identical bytes, identical name; any change, a
    new name. 48 bits is plenty -- it only has to tell apart the handful of
    exports one lesson will ever have."""
    import hashlib
    return hashlib.sha256(data).hexdigest()[:12]


def versioned_name(name: str, data: bytes) -> str:
    """`abc_track1.glb` + its bytes -> `abc_track1.3f2a9c01b7de.glb`."""
    stem, ext = name.rsplit(".", 1)
    return f"{stem}.{content_version(data)}.{ext}"


def key_for_asset(asset_id: str) -> Optional[str]:
    """The R2 key an `asset_id` from a MotionResult document resolves to.

    Mirrors api.py's `GET /assets/{asset_id}` dispatch exactly; if the two ever
    disagree the endpoint silently serves a 404 for an object that is there.
    """
    if asset_id.startswith("video:"):
        return video_key(asset_id[len("video:"):])
    if asset_id.endswith(".glb"):
        return glb_key(asset_id)
    return None


def clip_id_for_asset(asset_id: str) -> Optional[str]:
    """Which lesson an asset belongs to -- the tombstone check needs this
    before handing out any URL at all."""
    if asset_id.startswith("video:"):
        return asset_id[len("video:"):]
    if asset_id.endswith(".glb"):
        return asset_id.rsplit("_track", 1)[0]
    return None


def clip_prefixes(clip_id: str) -> list[str]:
    """Every R2 key of one lesson starts with one of these, every version of
    every GLB and MotionResult included -- which is why deletion lists by
    prefix instead of deriving names. `{clip}.` / `{clip}_track` cannot match
    another lesson: clip ids are fixed-length hex."""
    return [f"video/{clip_id}.", f"motion-result/{clip_id}.", f"glb/{clip_id}_track"]


def list_keys(prefix: str) -> list[str]:
    keys = []
    for page in client().get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", [])]
    return keys


def clip_keys(clip_id: str) -> list[str]:
    """Every R2 key belonging to one lesson, as it is right now. The removal
    path deletes exactly this list, so it lives next to the writers rather than
    being re-derived by whoever is deleting -- same reason
    retention.clip_artifact_paths exists."""
    return [k for p in clip_prefixes(clip_id) for k in list_keys(p)]


def prune_versions(clip_id: str, keep: set) -> list[str]:
    """Delete this lesson's GLB and MotionResult objects that are not in
    `keep` -- the versions a re-export superseded. Never the video. Returns the
    keys deleted."""
    old = [k for p in clip_prefixes(clip_id)[1:] for k in list_keys(p) if k not in keep]
    for k in old:
        client().delete_object(Bucket=bucket(), Key=k)
    return old


# --- reads and writes ------------------------------------------------------

def put_bytes(key: str, data: bytes, content_type: str,
              content_encoding: Optional[str] = None) -> str:
    extra = {"ContentType": content_type, "CacheControl": CACHE_CONTROL}
    if content_encoding:
        extra["ContentEncoding"] = content_encoding
    client().put_object(Bucket=bucket(), Key=key, Body=data, **extra)
    return key


def put_file(key: str, path: str, content_type: str,
             content_encoding: Optional[str] = None,
             metadata: Optional[dict] = None,
             cache_control: str = CACHE_CONTROL) -> str:
    """Streaming upload, for the objects big enough that reading them into
    memory is the thing this module exists to stop doing."""
    extra = {"ContentType": content_type, "CacheControl": cache_control}
    if content_encoding:
        extra["ContentEncoding"] = content_encoding
    if metadata:
        extra["Metadata"] = metadata
    client().upload_file(path, bucket(), key, ExtraArgs=extra)
    return key


def exists(key: str) -> bool:
    from botocore.exceptions import ClientError
    try:
        client().head_object(Bucket=bucket(), Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "403"):
            return False
        raise


def delete(key: str) -> bool:
    """True if the object was there. R2's DELETE is idempotent and does not
    distinguish, so this heads first -- the removal endpoint reports what it
    actually deleted rather than claiming, and DESIGN.md §7h's honesty rule
    covers promises about data at least as much as it covers copy."""
    present = exists(key)
    client().delete_object(Bucket=bucket(), Key=key)
    return present


def url_for(key: str) -> str:
    """The URL `GET /assets/{id}` redirects to. See the module docstring for
    why there are two modes and which one is live today."""
    base = os.environ.get("R2_PUBLIC_BASE_URL")
    if base:
        return f"{base.rstrip('/')}/{key}"
    return client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket(), "Key": key},
        ExpiresIn=PRESIGN_TTL_S,
    )


def _self_check() -> None:
    """The smallest thing that fails if the id<->key mapping breaks."""
    assert key_for_asset("video:abc") == "video/abc.mp4"
    assert key_for_asset("abc_track1.glb") == "glb/abc_track1.glb"
    assert key_for_asset("nonsense") is None
    assert clip_id_for_asset("video:abc") == "abc"
    assert clip_id_for_asset("abc_track12.glb") == "abc"
    assert clip_id_for_asset("abc_track12.3f2a9c01b7de.glb") == "abc"
    assert key_for_asset("abc_track1.3f2a9c01b7de.glb") == "glb/abc_track1.3f2a9c01b7de.glb"
    v = versioned_name("abc_track1.glb", b"x")
    assert v == versioned_name("abc_track1.glb", b"x") != versioned_name("abc_track1.glb", b"y")
    assert v.startswith("abc_track1.") and v.endswith(".glb") and len(v) == len("abc_track1.glb") + 13
    assert motion_result_key("abc", "v1") == "motion-result/abc.v1.json.gz"
    print("storage: id<->key mapping ok")


if __name__ == "__main__":
    _self_check()
