"""HTTP client for deploy / post-release API verification."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WEB_DIR = Path(__file__).resolve().parent.parent


@dataclass
class ApiClient:
    base_url: str
    team_id: str
    session_id: str
    timeout_sec: int = 120

    def _headers(self, user_id: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-GreenNode-AgentBase-Custom-Team-Id": self.team_id,
            "X-GreenNode-AgentBase-Session-Id": self.session_id,
        }
        if user_id:
            headers["X-GreenNode-AgentBase-User-Id"] = user_id
        return headers

    def get(self, path: str) -> tuple[int, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        req = urllib.request.Request(url, method="GET")
        return self._execute(req)

    def post(self, path: str, body: dict, user_id: str | None = None) -> tuple[int, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(user_id), method="POST")
        return self._execute(req)

    def _execute(self, req: urllib.request.Request) -> tuple[int, Any]:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Request failed: {exc}") from exc

        if not raw.strip():
            return status, None
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, raw


def read_zalopay_bank_bin(config_path: Path | None = None) -> str:
    path = config_path or WEB_DIR / "config.js"
    if not path.exists():
        path = WEB_DIR / "config.example.js"
    if not path.exists():
        return os.environ.get("ZALOPAY_BIN", "971101")
    text = path.read_text(encoding="utf-8")
    match = re.search(r'bankBin:\s*"([^"]*)"', text)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return os.environ.get("ZALOPAY_BIN", "971101")


def client_from_env() -> ApiClient:
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8080").strip()
    team_id = os.environ.get("TEAM_ID", "team-api-test").strip()
    session_id = os.environ.get("SESSION_ID", f"session-api-{os.getpid()}").strip()
    timeout = int(os.environ.get("API_TEST_TIMEOUT", "120"))
    return ApiClient(base_url=base_url, team_id=team_id, session_id=session_id, timeout_sec=timeout)
