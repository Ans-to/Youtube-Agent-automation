#!/usr/bin/env python3
"""Tiny sanitized health endpoint for the Render test-only service."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

STATUS_FILE = Path(__file__).resolve().with_name("ci-test-status.json")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health", "/status"):
            self.send_response(404)
            self.end_headers()
            return

        try:
            status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            status = {"status": "unavailable"}

        healthy = status.get("status") == "passed"
        body = (
            b'{"status":"ok","service":"test-only","agent_tasks_enabled":false}\n'
            if healthy else b'{"status":"not_ready"}\n'
        )
        self.send_response(200 if healthy else 503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        # Do not echo request paths, query strings, or user-supplied values.
        print("health endpoint request", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print("Test-only health endpoint started; task execution is disabled.", flush=True)
    server.serve_forever()
