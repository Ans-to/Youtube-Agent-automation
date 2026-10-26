#!/usr/bin/env python3
"""Serve the delivery folder, with byte ranges so a long film can be scrubbed.

``python3 -m http.server`` answers a request for a 500 MB MP4 with the whole
file and ignores ``Range``, so the player cannot jump to a chapter and some
browsers refuse to play at all. This answers ``Range`` with ``206 Partial
Content`` and streams in chunks, so the server is not holding a film in memory
for every viewer.

    python3 serve_delivery.py --root /home/user/build/site --port 8099 --bind 0.0.0.0
"""
from __future__ import annotations

import argparse
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

CHUNK = 256 * 1024
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
TYPES = {".vtt": "text/vtt; charset=utf-8", ".srt": "text/plain; charset=utf-8",
         ".md": "text/plain; charset=utf-8", ".json": "application/json; charset=utf-8"}


def build_handler(root: Path):
    root = root.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "delivery/1.0"
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - fixed by the base class
            self._serve(body=True)

        def do_HEAD(self) -> None:  # noqa: N802 - fixed by the base class
            self._serve(body=False)

        def _target(self) -> Path | None:
            path = unquote(urlparse(self.path).path)
            if path == "/":
                path = "/index.html"
            candidate = (root / path.lstrip("/")).resolve()
            if candidate != root and not str(candidate).startswith(str(root) + "/"):
                return None
            if candidate.is_dir():
                candidate = candidate / "index.html"
            return candidate

        def _serve(self, *, body: bool) -> None:
            target = self._target()
            if target is None or not target.is_file():
                self.send_error(404, "not here")
                return
            size = target.stat().st_size
            ctype = TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] \
                or "application/octet-stream"
            start, end, status = 0, size - 1, 200
            header = self.headers.get("Range")
            if header:
                match = RANGE.match(header.strip())
                if not match:
                    self.send_error(416, "only single byte ranges are supported")
                    return
                first, last = match.groups()
                if first == "" and last == "":
                    self.send_error(416, "empty range")
                    return
                if first == "":
                    start = max(0, size - int(last))
                else:
                    start = int(first)
                    end = int(last) if last else size - 1
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = 206

            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Access-Control-Allow-Origin", "*")
            if target.suffix in {".html", ".json"}:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not body:
                return
            with target.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    block = handle.read(min(CHUNK, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)

        def log_message(self, fmt: str, *args) -> None:
            print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="folder to serve")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f"no such folder: {root}")
        return 2
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((args.bind, args.port), build_handler(root))
    server.daemon_threads = True
    print(f"serving {root.resolve()} on http://{args.bind}:{args.port} (byte ranges on)",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
