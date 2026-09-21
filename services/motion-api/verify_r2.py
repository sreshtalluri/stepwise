"""Prove R2 delivery actually does the thing it was chosen for: HTTP 206.

The whole argument for moving assets off Modal Volumes is that a `<video>`
element's `Range:` request must come back as a partial response, not a 200 with
the entire file (storage.py's docstring, infrastructure.md decision 3). That is
a claim about a live service, so measure it rather than trust it.

    python3 verify_r2.py                 # uses ~/.stepwise-secrets/r2.env
    R2_ENDPOINT_URL=... python3 verify_r2.py   # or an already-populated env

Writes one 16 KB object under `diagnostic/`, range-reads it, checks the bytes
are the right bytes, then deletes it. Costs two Class A operations. Exits
non-zero and says which credential is missing if it cannot run.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

DEFAULT_ENV_FILE = Path.home() / ".stepwise-secrets" / "r2.env"


def load_env_file(path: Path = DEFAULT_ENV_FILE) -> int:
    """Populate os.environ from a KEY=value file, without overwriting anything
    already set. Deliberately not python-dotenv: this is six lines and adding a
    dependency to read six lines is how requirement files get long."""
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and not os.environ.get(k):
            os.environ[k] = v
            n += 1
    return n


def main() -> int:
    load_env_file()

    import storage

    if not storage.enabled():
        print(f"R2 not configured -- missing: {', '.join(storage.missing_env())}")
        print(f"Put them in {DEFAULT_ENV_FILE} or the environment.")
        return 2

    storage._self_check()

    key = "diagnostic/range-probe.bin"
    data = bytes(range(256)) * 64  # 16,384 bytes, every byte value, so a wrong
    #                                offset produces wrong bytes rather than
    #                                accidentally-equal ones.
    storage.put_bytes(key, data, "application/octet-stream")
    try:
        url = storage.url_for(key)
        mode = "custom domain" if os.environ.get("R2_PUBLIC_BASE_URL") else "presigned"
        print(f"url mode: {mode}")

        req = urllib.request.Request(url, headers={"Range": "bytes=100-199"})
        with urllib.request.urlopen(req) as r:
            body = r.read()
            print(f"  status         {r.status}")
            print(f"  Content-Range  {r.headers.get('Content-Range')}")
            print(f"  Accept-Ranges  {r.headers.get('Accept-Ranges')}")
            print(f"  Cache-Control  {r.headers.get('Cache-Control')}")
            print(f"  bytes returned {len(body)}")
            assert r.status == 206, f"expected HTTP 206, got {r.status} -- range requests are NOT working"
            assert body == data[100:200], "206 returned the wrong bytes"

        with urllib.request.urlopen(url) as r:
            full = r.read()
            assert r.status == 200 and len(full) == len(data), "full GET is broken"
            print(f"  full GET       {r.status}, {len(full)} bytes")
    finally:
        storage.delete(key)

    print("R2 delivery verified: real HTTP 206 partial responses, correct bytes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
