"""End-to-end check against a deployed API: upload, poll, result, stream.

    python3 e2e_check.py https://... /path/to/clip.mp4

Every claim in docs/DEPLOYMENT.md about the live service comes from running
this, not from reasoning about the code. It costs one real GPU reconstruction
(~$0.03 for an 8-second clip, ~$0.08 for a 20-second one) and takes two to
three minutes, so it is a deliberate act, not a health check -- `GET /health`
is the cheap one.

What it asserts, in the order a learner would hit it:

  1. `POST /clips` dispatches and returns a job_id immediately.
  2. `GET /jobs/{id}` serves a valid job-status.schema.json document on every
     poll -- validated against the contract, not eyeballed, because the point
     of decision 4 is that this document does not change when its storage does.
  3. `GET /jobs/{id}/result` serves a schema-valid MotionResult.
  4. `GET /assets/{id}` **redirects** and the redirect target answers a
     `Range:` request with **HTTP 206** and the right bytes. This is the one
     that used to be impossible: the old byte proxy returned 200 with the whole
     file and video scrubbing could not work.
"""
from __future__ import annotations

import json
import sys
import time
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "motion-contract" / "python"))


def _req(url: str, **kw) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, **kw)
    # The API answers only the Worker once STEPWISE_ORIGIN_KEY is set in Modal;
    # export the same value (~/.stepwise-secrets/origin.env) to call it direct.
    if os.environ.get("STEPWISE_ORIGIN_KEY"):
        req.add_header("x-stepwise-origin-key", os.environ["STEPWISE_ORIGIN_KEY"])
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _multipart(path: Path) -> tuple[bytes, str]:
    boundary = "----stepwise-e2e-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def main(base: str, clip: Path) -> int:
    base = base.rstrip("/")
    from motion_contract import validate  # noqa: PLC0415

    t0 = time.time()
    status, _, body = _req(f"{base}/health")
    print(f"GET  /health                {status}  {time.time() - t0:.2f}s  {body.decode()}")
    assert status == 200

    payload, ctype = _multipart(clip)
    t0 = time.time()
    status, _, body = _req(f"{base}/clips", data=payload,
                           headers={"Content-Type": ctype}, method="POST")
    upload_s = time.time() - t0
    print(f"POST /clips                 {status}  {upload_s:.2f}s  {body.decode()}")
    assert status == 200, body
    disp = json.loads(body)
    job_id, clip_id = disp["job_id"], disp["clip_id"]
    if disp.get("deduplicated"):
        print("  (deduplicated -- no GPU run; the poll below reports the existing lesson)")

    t0, last, polls = time.time(), None, 0
    while time.time() - t0 < 900:
        status, _, body = _req(f"{base}/jobs/{job_id}")
        assert status == 200, body
        doc = json.loads(body)
        polls += 1
        # Validated every single poll, not once at the end: a storage swap that
        # produced a valid terminal document and an invalid intermediate one
        # would break ProcessingScreen.tsx and pass a lazier check.
        v = validate.validate_job_status(doc)
        assert v.valid, f"job-status document is not contract-valid: {v.errors}"
        if (doc["state"], doc["stage_message"]) != last:
            print(f"  {time.time() - t0:6.1f}s  {doc['state']:<10} "
                  f"progress={doc['progress']}  {doc['stage_message']}")
            last = (doc["state"], doc["stage_message"])
        if doc["state"] in ("succeeded", "failed"):
            break
        time.sleep(2.0)
    job_s = time.time() - t0
    print(f"GET  /jobs/{{id}}              {polls} polls, {job_s:.1f}s to terminal, "
          f"every one schema-valid")
    if doc["state"] != "succeeded":
        print(f"job did not succeed: {doc}")
        return 1

    t0 = time.time()
    status, _, body = _req(f"{base}/jobs/{job_id}/result")
    result_s = time.time() - t0
    assert status == 200, body
    result = json.loads(body)
    v = validate.validate_motion_result(result)
    assert v.valid, f"MotionResult is not contract-valid: {v.errors}"
    print(f"GET  /jobs/{{id}}/result       {status}  {result_s:.2f}s  "
          f"{len(body)} bytes, schema-valid, {len(result['persons'])} person(s)")

    asset_ids = [result["source_video"]["asset_id"]]
    asset_ids += [p["animation"]["glb_asset_id"] for p in result["persons"]
                  if p.get("animation")]

    ok = True
    for asset_id in asset_ids:
        url = f"{base}/assets/{urllib.parse.quote(asset_id)}"
        # Do NOT follow the redirect: the 302 itself is the thing under test.
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(urllib.request.Request(url, method="GET"))
            redirect_status, location = 200, None
        except urllib.error.HTTPError as e:
            redirect_status, location = e.code, e.headers.get("Location")
        print(f"GET  /assets/{asset_id[:38]:<38} {redirect_status}"
              f"{'  -> ' + location.split('?')[0] if location else '  (byte proxy, no range support)'}")
        if redirect_status != 302:
            ok = False
            continue
        status, headers, chunk = _req(location, headers={"Range": "bytes=0-1023"})
        print(f"       Range: bytes=0-1023  ->  {status}  "
              f"Content-Range={headers.get('Content-Range')}  {len(chunk)} bytes  "
              f"Cache-Control={headers.get('Cache-Control')}")
        if status != 206 or len(chunk) != 1024:
            ok = False

    print()
    print(f"clip_id {clip_id}   job_id {job_id}")
    print("PASS" if ok else "FAIL: at least one asset did not serve a 206 range response")
    return 0 if ok else 1


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):  # noqa: ANN002, ANN003
        return None


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
