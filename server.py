"""Local backend for the web UI: serves web/wasm and runs the pipeline on uploads.

The UI stays a static page (GitHub Pages works as before); when this server is
running on 127.0.0.1 the page detects it and offers transcription.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pipeline


WEB_DIR = Path(__file__).resolve().parent / "web" / "wasm"
PAGES_ORIGIN = "https://nullwiz.github.io"
MAX_UPLOAD = 4 * 1024**3
# ponytail: one job at a time; add a queue if several people share one backend
JOB_LOCK = threading.Lock()


def origin_allowed(origin: str | None) -> bool:
    """No Origin (curl, same-origin GET) is fine; otherwise Pages or localhost."""
    if not origin:
        return True
    return origin == PAGES_ORIGIN or urlparse(origin).hostname in (
        "localhost",
        "127.0.0.1",
    )


def parse_options(query: str) -> dict[str, Any]:
    """Validate the UI's query string into pipeline.main kwargs."""
    q = {k: v[0] for k, v in parse_qs(query).items()}
    opts: dict[str, Any] = {
        "language": q.get("language") or None,
        "separate": q.get("separate", "1") != "0",
    }
    if q.get("num_speakers"):
        n = int(q["num_speakers"])
        if not 1 <= n <= 8:
            raise ValueError("num_speakers must be 1-8")
        opts["num_speakers"] = n
    suffix = Path(q.get("filename", "")).suffix.lower()
    opts["suffix"] = suffix if suffix[1:].isalnum() and len(suffix) <= 6 else ""
    return opts


class Handler(SimpleHTTPRequestHandler):
    device: str | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204 if origin_allowed(self.headers.get("Origin")) else 403)
        self.end_headers()

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/health":
            self.send_json(
                200,
                {
                    "ok": True,
                    "busy": JOB_LOCK.locked(),
                    "model": pipeline.DEFAULT_MODEL,
                },
            )
        else:
            super().do_GET()

    def do_POST(self) -> None:
        url = urlparse(self.path)
        if url.path != "/api/transcribe":
            return self.send_json(404, {"error": "not found"})
        if not origin_allowed(self.headers.get("Origin")):
            return self.send_json(403, {"error": "origin not allowed"})
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_UPLOAD:
            return self.send_json(413, {"error": "empty or too large upload"})
        try:
            opts = parse_options(url.query)
        except ValueError as e:
            return self.send_json(400, {"error": str(e)})
        if not JOB_LOCK.acquire(blocking=False):
            return self.send_json(409, {"error": "busy with another file"})

        work = tempfile.mkdtemp(prefix="audiopipe-")
        try:
            src = os.path.join(work, "input" + opts.pop("suffix"))
            with open(src, "wb") as f:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(remaining, 1 << 20))
                    if not chunk:
                        raise ConnectionError("upload interrupted")
                    f.write(chunk)
                    remaining -= len(chunk)
            out = pipeline.main(
                src, device=self.device, output_dir=os.path.join(work, "out"), **opts
            )
            with open(out, encoding="utf-8") as f:
                self.send_json(200, json.load(f))
        except Exception as e:
            self.send_json(500, {"error": str(e)})
        finally:
            JOB_LOCK.release()
            shutil.rmtree(work, ignore_errors=True)


def cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the AudioPipe web UI locally")
    parser.add_argument("--port", "-p", type=int, default=8737)
    parser.add_argument("--device", "-d", choices=["cpu", "cuda", "mps"])
    parser.add_argument(
        "--offline", action="store_true", help="Never touch the network"
    )
    args = parser.parse_args(argv)

    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    pipeline.setup_logging(os.path.join(tempfile.gettempdir(), "audiopipe.log"))
    Handler.device = args.device
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"🌐 AudioPipe UI on http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    print(f"   {PAGES_ORIGIN}/audiopipe/ will also find this backend")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
