"""The owner's tool for quarantined lessons. Read docs/legal/abuse-report-runbook.md first.

    python3 quarantine.py list
    python3 quarantine.py export <clip_id> --out <dir>     # for the CyberTipline report
    python3 quarantine.py purge <clip_id> --i-understand-this-destroys-evidence
        [--adult-ncii-lawyer-cleared-early-purge]            # adults only; see the runbook

A lesson reported as sexual content involving a minor, or intimate images
shared without consent, is not deleted: retention.quarantine_clip moves its
bytes to the `stepwise-quarantine` Volume, which no API route and no page
reads. This script is the only way in. It runs on the owner's machine with a
Modal token; it prints ids, times and hashes, never file contents.

`list` and `export` change nothing but the manifest's export log. `purge`
deletes one lesson's quarantined files and manifest, and refuses before its
`preserve_until` date (one year, REPORT Act) -- if law enforcement asked for
longer, do not purge. The blocklist entry stays after a purge: it is hashes,
not the video, and it keeps the same video from being uploaded again.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import retention  # noqa: E402


def _day(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t))


def manifests(qvol) -> list[dict]:
    out = []
    for e in qvol.listdir("/", recursive=True):
        path = "/" + e.path.lstrip("/")
        if path.endswith("/manifest.json") and path.count("/") == 2:
            doc = retention.read_json(qvol, path)
            if doc:
                out.append(doc)
    return sorted(out, key=lambda m: m.get("quarantined_at", 0))


def list_items(qvol) -> list[dict]:
    rows = manifests(qvol)
    for m in rows:
        print(f"{m['clip_id']}  quarantined {_day(m['quarantined_at'])}  "
              f"preserve until {_day(m['preserve_until'])}  {m.get('relationship')}  "
              f"{len(m['files'])} files  exported {len(m.get('exports', []))}x")
    if not rows:
        print("nothing quarantined")
    return rows


def export_item(qvol, clip_id: str, out_dir: str) -> Path:
    """Every quarantined file of one lesson, plus its manifest, into `out_dir/<clip_id>/`.
    Each file's sha256 is re-checked against the manifest; the export is logged."""
    import hashlib
    import json
    m = retention.read_json(qvol, retention.manifest_path(clip_id))
    if not m:
        raise SystemExit(f"{clip_id} is not quarantined")
    dest = Path(out_dir) / clip_id
    for f in m["files"]:
        data = retention.read_bytes(qvol, f["path"])
        if data is None or hashlib.sha256(data).hexdigest() != f["sha256"]:
            raise SystemExit(f"{f['path']} is missing or does not match its sha256 -- stop and investigate")
        target = dest / f["path"].lstrip("/").removeprefix(f"{clip_id}/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    m.setdefault("exports", []).append(time.time())
    retention.write_json(qvol, retention.manifest_path(clip_id), m)
    (dest / "manifest.json").write_text(json.dumps(m, indent=2))
    print(f"exported {len(m['files'])} files (sha256-checked) to {dest}")
    return dest


def purge_item(qvol, clip_id: str, confirmed: bool, now: float | None = None,
               early: bool = False) -> list[str]:
    """`early` is for intimate images of adults only, once a lawyer has said no
    preservation duty applies (runbook section 4). Never for anything involving a minor."""
    m = retention.read_json(qvol, retention.manifest_path(clip_id))
    if not m:
        raise SystemExit(f"{clip_id} is not quarantined")
    if not confirmed:
        raise SystemExit("purge destroys preserved evidence; pass --i-understand-this-destroys-evidence")
    if not early and (now or time.time()) < m["preserve_until"]:
        raise SystemExit(f"{clip_id} must be preserved until {_day(m['preserve_until'])}; not purged")
    gone = []
    for path in [f["path"] for f in m["files"]] + [retention.manifest_path(clip_id)]:
        if retention.remove_if_present(qvol, path):
            gone.append(path)
    try:
        qvol.remove_file(f"/{clip_id}", recursive=True)  # the now-empty directory
    except Exception:  # noqa: BLE001 -- nothing left in it either way
        pass
    print(f"purged {clip_id}: {len(gone)} files. The tombstone and blocklist entry stay.")
    return gone


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    ex = sub.add_parser("export")
    ex.add_argument("clip_id")
    ex.add_argument("--out", required=True)
    pu = sub.add_parser("purge")
    pu.add_argument("clip_id")
    pu.add_argument("--i-understand-this-destroys-evidence", dest="confirmed", action="store_true")
    pu.add_argument("--adult-ncii-lawyer-cleared-early-purge", dest="early", action="store_true",
                    help="adults only, lawyer-cleared: purge before preserve_until (runbook section 4)")
    args = ap.parse_args()
    qvol = retention.quarantine_volume()
    if args.cmd == "list":
        list_items(qvol)
    elif args.cmd == "export":
        export_item(qvol, args.clip_id, args.out)
    else:
        purge_item(qvol, args.clip_id, args.confirmed, early=args.early)


if __name__ == "__main__":
    main()
