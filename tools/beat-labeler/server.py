"""The labelling page's server: static files, plus GET/PUT data/labels.json.

    python3 tools/beat-labeler/server.py      # http://127.0.0.1:8765

Localhost only; the labels are one JSON object keyed by job id, rewritten whole
on every save (atomic rename, so a crash mid-write cannot eat earlier labels).
"""
import json
import os
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
LABELS = HERE / "data" / "labels.json"


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/labels":
            return self._json(json.loads(LABELS.read_text()) if LABELS.exists() else {})
        if self.path.endswith(".mp4") and "Range" in self.headers:
            return self._range()
        return super().do_GET()

    def _range(self):
        """Byte ranges for the videos: without them the browser cannot seek, and
        seeking is the whole job of this page."""
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            return self.send_error(404)
        size = path.stat().st_size
        start_s, _, end_s = self.headers["Range"].removeprefix("bytes=").partition("-")
        start = int(start_s or 0)
        end = min(int(end_s) if end_s else size - 1, size - 1)
        if start > end:
            return self.send_error(416)
        self.send_response(206)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            self.wfile.write(f.read(end - start + 1))

    def do_PUT(self):
        if self.path != "/labels":
            return self.send_error(404)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if not isinstance(body, dict):
            return self.send_error(400)
        fd, tmp = tempfile.mkstemp(dir=LABELS.parent)
        with os.fdopen(fd, "w") as f:
            json.dump(body, f, indent=1)
        os.replace(tmp, LABELS)
        self._json({"ok": True, "n": len(body)})

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    print(f"http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(HERE))).serve_forever()
