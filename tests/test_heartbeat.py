"""Cron worker heartbeat: counts only, off unless HEARTBEAT_URL + HEARTBEAT_TOKEN, never raises."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

# Loaded by path: the module is standard library only, so this runs in the offline CI job too.
_PATH = Path(__file__).resolve().parents[1] / "src" / "platform_communication" / "_heartbeat.py"
_spec = importlib.util.spec_from_file_location("platform_communication_heartbeat_under_test", _PATH)
assert _spec is not None and _spec.loader is not None
_hb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hb)

URL = "https://monitor.example/heartbeat/communication-worker"


class Recorder:
    def __init__(self, fail: bool = False):
        self.requests: list[Any] = []
        self.fail = fail

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.fail:
            raise OSError("down")
        return None


class HeartbeatTest(unittest.TestCase):
    def test_off_without_url_or_token(self):
        rec = Recorder()
        for env in ({}, {"HEARTBEAT_URL": URL}, {"HEARTBEAT_TOKEN": "t"}):
            self.assertFalse(_hb.send(True, 1, env=env, opener=rec))
        self.assertEqual(rec.requests, [])

    def test_posts_counts_only_with_bearer(self):
        rec = Recorder()
        env = {"HEARTBEAT_URL": URL, "HEARTBEAT_TOKEN": "secret-token"}
        self.assertTrue(_hb.send(True, 3, env=env, opener=rec))
        request, timeout = rec.requests[0]
        self.assertEqual(request.full_url, URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertEqual(json.loads(request.data), {"ok": True, "failed": [], "handled": 3})
        self.assertLessEqual(timeout, 15)

    def test_failure_names_the_job(self):
        rec = Recorder()
        _hb.send(False, 0, env={"HEARTBEAT_URL": URL, "HEARTBEAT_TOKEN": "t"}, opener=rec)
        self.assertEqual(json.loads(rec.requests[0][0].data), {"ok": False, "failed": ["communication-worker"], "handled": 0})

    def test_rejects_non_https_url(self):
        rec = Recorder()
        self.assertFalse(_hb.send(True, 1, env={"HEARTBEAT_URL": "http://monitor.example/x", "HEARTBEAT_TOKEN": "t"}, opener=rec))
        self.assertEqual(rec.requests, [])

    def test_default_opener_refuses_redirects(self):
        # A redirect must not carry the bearer token to another URL.
        handler = _hb._NoRedirect()
        req = _hb.urllib.request.Request(URL, headers={"Authorization": "Bearer t"})
        self.assertIsNone(handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/"))

    def test_network_error_is_swallowed(self):
        rec = Recorder(fail=True)
        self.assertFalse(_hb.send(True, 1, env={"HEARTBEAT_URL": URL, "HEARTBEAT_TOKEN": "t"}, opener=rec))


if __name__ == "__main__":
    unittest.main()
