"""Cron worker heartbeat, standard library only.

Posts `{"ok", "failed", "handled"}` (counts only, never recipients or bodies) to
HEARTBEAT_URL with HEARTBEAT_TOKEN as a bearer token. Off unless both are set.
A monitoring failure never fails the delivery run.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

JOB = "communication-worker"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: it would carry the bearer token to another URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect).open


def send(
    ok: bool,
    handled: int,
    *,
    env: Mapping[str, str] = os.environ,
    opener: Callable[..., Any] = _OPENER,
) -> bool:
    """Return True when the heartbeat was posted."""
    url = env.get("HEARTBEAT_URL", "").strip()
    token = env.get("HEARTBEAT_TOKEN", "").strip()
    if not url or not token or not url.startswith("https://"):
        return False
    payload = {"ok": ok, "failed": [] if ok else [JOB], "handled": handled}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": f"{JOB}/1"},
    )
    try:
        opener(request, timeout=10)
    except Exception:  # noqa: BLE001 - monitoring must not fail the run
        return False
    return True
