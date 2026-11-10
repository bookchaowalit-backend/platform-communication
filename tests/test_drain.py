"""Worker loop: `--until-empty` drains due messages then exits (cron mode); default keeps polling."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

# Loaded by path: the module is standard library only, so this runs in the offline CI job too.
_PATH = Path(__file__).resolve().parents[1] / "src" / "platform_communication" / "_drain.py"
_spec = importlib.util.spec_from_file_location("platform_communication_drain_under_test", _PATH)
assert _spec is not None and _spec.loader is not None
_drain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_drain)


class FakeWorker:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def run_one(self, workspace):
        self.calls.append(workspace)
        return self.results.pop(0) if self.results else False


class DrainTest(unittest.TestCase):
    def test_until_empty_stops_at_first_empty_claim(self):
        worker = FakeWorker([True, True, False, True])
        sleeps: list[float] = []
        n = _drain.drain(worker, "ws", until_empty=True, sleep=sleeps.append)
        self.assertEqual(n, 2)
        self.assertEqual(len(worker.calls), 3)
        self.assertEqual(sleeps, [])

    def test_until_empty_on_empty_outbox_makes_one_claim(self):
        worker = FakeWorker([])
        self.assertEqual(_drain.drain(worker, "ws", until_empty=True, sleep=lambda s: None), 0)
        self.assertEqual(len(worker.calls), 1)

    def test_until_empty_is_bounded_by_max_messages(self):
        worker = FakeWorker([True] * 10)
        n = _drain.drain(worker, "ws", until_empty=True, max_messages=3, sleep=lambda s: None)
        self.assertEqual(n, 3)
        self.assertEqual(len(worker.calls), 3)

    def test_polling_mode_sleeps_when_empty_and_stops_on_signal(self):
        worker = FakeWorker([True, False, False])
        sleeps: list[float] = []
        state = {"left": 3}

        def running():
            state["left"] -= 1
            return state["left"] >= 0

        n = _drain.drain(worker, "ws", until_empty=False, sleep=sleeps.append, running=running)
        self.assertEqual(n, 1)
        self.assertEqual(sleeps, [0.5, 0.5])

    def test_until_empty_stops_on_signal(self):
        worker = FakeWorker([True] * 5)
        n = _drain.drain(worker, "ws", until_empty=True, sleep=lambda s: None, running=lambda: False)
        self.assertEqual(n, 0)
        self.assertEqual(worker.calls, [])


if __name__ == "__main__":
    unittest.main()
