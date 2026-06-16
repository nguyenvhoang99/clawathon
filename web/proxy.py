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

from estimate_service import build_estimates
from vietqr_emv import build_vietqr_image, build_vietqr_url, should_render_locally

WEB_DIR = Path(__file__).resolve().parent
CONFIG_PATH = WEB_DIR / "config.js"
DEFAULT_PORT = 8080
DEFAULT_HOST = "0.0.0.0"

ROUTE_MAP = {
    "/api/weather": "weather",
    "/api/trip": "trip",
    "/api/bill": "bill",
}


DEFAULT_ENDPOINTS = {
    "weather": "https://endpoint-f84375b6-98f9-456c-9a9c-d38a4724ddaa.agentbase-runtime.aiplatform.vngcloud.vn",
    "trip": "https://endpoint-e1287e38-7a87-4aea-a5cf-19762fe9179c.agentbase-runtime.aiplatform.vngcloud.vn",
    "bill": "https://endpoint-5ca9ea82-4d2a-4526-be86-b731ea37355d.agentbase-runtime.aiplatform.vngcloud.vn",
}


def _parse_config_endpoints(text: str) -> dict[str, str]:
    block = re.search(r"endpoints:\s*\{([^}]+)\}", text, re.DOTALL)
    if not block:
        return {}
    return dict(re.findall(r"(\w+):\s*\"(https://[^\"]+)\"", block.group(1)))


def load_endpoints() -> dict[str, str]:
    endpoints = dict(DEFAULT_ENDPOINTS)

    for candidate in (CONFIG_PATH, WEB_DIR / "config.example.js"):
        if candidate.exists():
            endpoints.update(_parse_config_endpoints(candidate.read_text(encoding="utf-8")))

    env_keys = {
        "weather": "WEATHER_ENDPOINT_URL",
        "trip": "TRIP_ENDPOINT_URL",
        "bill": "BILL_ENDPOINT_URL",
    }
    for key, env_name in env_keys.items():
        value = os.environ.get(env_name, "").strip()
        if value:
            endpoints[key] = value

    return endpoints


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

    def do_GET(self) -> None:
        if self.path == "/health":
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path.startswith("/data/"):
            rel = self.path.lstrip("/")
            candidates = [
                WEB_DIR / rel,
                WEB_DIR.parent / "agents/trip-planner" / rel.replace("data/qr/", "data/"),
            ]
            for file_path in candidates:
                if file_path.is_file():
                    content = file_path.read_bytes()
                    content_type = "image/jpeg" if file_path.suffix.lower() in {".jpg", ".jpeg"} else "application/octet-stream"
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
        super().do_GET()

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/vietqr":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
                bank_bin = str(payload.get("bank_bin", "")).strip()
                account_no = str(payload.get("account_no", "")).strip()
                account_name = str(payload.get("account_name", account_no)).strip()
                amount_vnd = int(payload.get("amount_vnd", 0))
                transfer_content = str(payload.get("transfer_content", "Trip settle"))
                if not bank_bin or not account_no:
                    raise ValueError("bank_bin and account_no are required")
                image = build_vietqr_image(
                    bank_bin=bank_bin,
                    account_no=account_no,
                    account_name=account_name,
                    amount_vnd=amount_vnd,
                    transfer_content=transfer_content,
                )
                vietqr_url = build_vietqr_url(
                    bank_bin=bank_bin,
                    account_no=account_no,
                    account_name=account_name,
                    amount_vnd=amount_vnd,
                    transfer_content=transfer_content,
                )
                result = {
                    "payload": image.payload,
                    "vietqr_url": vietqr_url,
                    "data_url": image.data_url,
                    "local": should_render_locally(bank_bin),
                }
                data = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as exc:
                err = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err)
            return

        if path == "/api/estimates":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
                result = build_estimates(payload)
                data = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as exc:
                err = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err)
            return

        key = ROUTE_MAP.get(path)
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
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    server = HTTPServer((host, port), Handler)
    print(f"Serving {WEB_DIR} at http://{host}:{port}")
    print("Agent proxy routes:", ", ".join(ROUTE_MAP))
    print("Local routes: /api/estimates, /api/vietqr")
    if not ENDPOINTS:
        print("Warning: no endpoints loaded — copy config.example.js to config.js")
    server.serve_forever()


if __name__ == "__main__":
    main()
