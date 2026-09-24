"""Fetch evaluation clips into the Modal Volume.

The manifest (clips.yaml) is versioned. The videos are not — they are large
binaries and other people's work. They live in the Modal Volume "stepwise-eval"
so every GPU run reads the same bytes without re-downloading.

    python evaluation/fetch.py --list           # what is in the manifest
    python evaluation/fetch.py --status         # what is actually in the Volume
    python evaluation/fetch.py solo-03          # fetch one clip
    python evaluation/fetch.py --all            # fetch everything with a URL

Downloading happens locally via yt-dlp, then uploads to the Volume. Local
because platform rate-limiting and bot checks are far worse from datacenter IPs.

RIGHTS: this downloads for private pipeline testing only. Anything destined for
a public demo needs explicit permission recorded in the manifest's `rights:`
field. Do not put an `untested` clip on a public page.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

MANIFEST = pathlib.Path(__file__).parent / "clips.yaml"
VOLUME = "stepwise-eval"
LOCAL_CACHE = pathlib.Path.home() / ".stepwise-clips"


def load_manifest() -> list[dict]:
    try:
        import yaml
    except ImportError:
        sys.exit("pip install pyyaml")
    data = yaml.safe_load(MANIFEST.read_text())
    return data.get("clips", [])


def have_tool(name: str) -> bool:
    return subprocess.run(["which", name], capture_output=True).returncode == 0


def cmd_list(clips: list[dict]) -> None:
    ready = sum(1 for c in clips if c.get("url"))
    print(f"{len(clips)} clips in manifest, {ready} with a URL\n")
    for c in clips:
        mark = "OK " if c.get("url") else "-- "
        tests = ",".join(c.get("tests") or [])
        print(f"{mark}{c['id']:<22} {tests:<38} rights={c.get('rights')}")
    if ready < len(clips):
        print(f"\n{len(clips) - ready} clips still need a URL. Edit {MANIFEST.name}.")


def cmd_status() -> None:
    """What is actually in the Volume right now."""
    r = subprocess.run(
        ["modal", "volume", "ls", VOLUME],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        if "not found" in (r.stderr or "").lower():
            print(f"Volume '{VOLUME}' does not exist yet. It is created on first upload.")
        else:
            print(r.stderr.strip())
        return
    print(r.stdout)


def fetch_one(clip: dict) -> bool:
    cid, url = clip["id"], clip.get("url")
    if not url:
        print(f"skip {cid}: no URL in manifest")
        return False

    LOCAL_CACHE.mkdir(exist_ok=True)
    out = LOCAL_CACHE / f"{cid}.mp4"

    if out.exists():
        print(f"have {cid} locally ({out.stat().st_size / 1e6:.1f} MB)")
    else:
        if not have_tool("yt-dlp"):
            sys.exit("yt-dlp not installed:  uv tool install yt-dlp")
        print(f"downloading {cid} ...")
        # Same selection as services/motion-api/ingest.py download(): H.264,
        # short side <= 1080 (so vertical clips keep their 1080x1920 stream).
        r = subprocess.run(
            [
                "yt-dlp",
                "-f", "bv*+ba/b", "-S", "vcodec:h264,res:1080",
                "--merge-output-format", "mp4",
                "-o", str(out),
                url,
            ]
        )
        if r.returncode != 0 or not out.exists():
            print(f"FAILED to download {cid}")
            return False

    print(f"uploading {cid} to volume {VOLUME} ...")
    r = subprocess.run(
        ["modal", "volume", "put", VOLUME, str(out), f"/{cid}.mp4", "--force"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(f"upload failed: {r.stderr.strip()[:300]}")
        return False
    print(f"done {cid}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ids", nargs="*", help="clip ids to fetch")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    clips = load_manifest()
    by_id = {c["id"]: c for c in clips}

    if args.list:
        return cmd_list(clips)
    if args.status:
        return cmd_status()

    targets = clips if args.all else [by_id[i] for i in args.ids if i in by_id]
    missing = [i for i in args.ids if i not in by_id]
    for m in missing:
        print(f"unknown clip id: {m}")
    if not targets:
        ap.print_help()
        return

    ok = sum(fetch_one(c) for c in targets)
    print(f"\n{ok}/{len(targets)} fetched")


if __name__ == "__main__":
    main()
