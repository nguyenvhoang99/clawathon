#!/usr/bin/env python3
"""Local dev server: static files + CORS proxy to AgentBase runtimes."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
CONFIG_PATH = WEB_DIR / "config.js"
DEFAULT_PORT = 3000

ROUTE_MAP = {
    "/api/weather": "weather",
    "/api/trip": "trip",
    "/api/bill": "bill",
}


def load_endpoints() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        example = WEB_DIR / "config.example.js"
        text = example.read_text(encoding="utf-8") if example.exists() else ""
    else:
        text = CONFIG_PATH.read_text(encoding="utf-8")

    block = re.search(r"endpoints:\s*\{([^}]+)\}", text, re.DOTALL)
    if not block:
        return {}
    urls = dict(re.findall(r"(\w+):\s*\"(https://[^\"]+)\"", block.group(1)))
    return urls


ENDPOINTS = load_endpoints()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_POST(self) -> None:
        key = ROUTE_MAP.get(self.path)
        if not key:
            self.send_error(404, "Not found")
            return
        target = ENDPOINTS.get(key)
        if not target:
            self.send_error(503, f"Endpoint not configured for {key}")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"

        headers = {"Content-Type": "application/json"}
        for name in (
            "X-GreenNode-AgentBase-Custom-Team-Id",
            "X-GreenNode-AgentBase-Session-Id",
            "X-GreenNode-AgentBase-User-Id",
        ):
            value = self.headers.get(name)
            if value:
                headers[name] = value

        url = f"{target.rstrip('/')}/invocations"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload or json.dumps({"error": str(exc)}).encode())
        except Exception as exc:
            self.send_error(502, str(exc))


def main() -> None:
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving {WEB_DIR} at http://127.0.0.1:{port}")
    print("Agent proxy routes:", ", ".join(ROUTE_MAP))
    if not ENDPOINTS:
        print("Warning: no endpoints loaded — copy config.example.js to config.js")
    server.serve_forever()


if __name__ == "__main__":
    main()
