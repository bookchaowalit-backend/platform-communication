"""Worker loop, standard library only.

Polling mode (default) keeps claiming and sleeps `idle_seconds` when nothing is due.
`until_empty` mode stops at the first empty claim, so a scheduled job (Railway cron)
can drain the outbox and exit, letting the database scale to zero between runs.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def drain(
    worker: Any,
    workspace: Any,
    *,
    until_empty: bool,
    max_messages: int = 500,
    idle_seconds: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    running: Callable[[], bool] = lambda: True,
) -> int:
    """Run `worker.run_one(workspace)` in a loop; return how many claims did work."""
    handled = 0
    while running():
        if until_empty and handled >= max_messages:
            break
        if worker.run_one(workspace):
            handled += 1
            continue
        if until_empty:
            break
        sleep(idle_seconds)
    return handled
