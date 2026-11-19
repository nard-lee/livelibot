"""Live indexing progress shared by the UI and the ingest log.

The indexer publishes a small state machine plus a rolling human-readable log.
The client polls ``GET /api/index/progress`` while a rebuild runs.

Stages: idle -> warming/uploading/fetching/removing -> reading -> chunking ->
embedding -> saving -> done (or error).
"""

import threading
import time
from collections import deque

_LOCK = threading.Lock()
_STATE: dict = {
    "stage": "idle",
    "detail": "",
    "done": 0,
    "total": 0,
    "started": 0.0,
    "finished": 0.0,
}
_LOG: deque[dict] = deque(maxlen=120)


def set_progress(stage: str, detail: str = "", done: int = 0, total: int = 0) -> None:
    """Publish the current stage and (optionally) a progress counter."""
    now = time.time()
    with _LOCK:
        previous = _STATE["stage"]

        # A new run starts when we leave a finished/idle stage.
        if stage == "idle":
            started = 0.0
        elif stage in {"done", "error"}:
            started = _STATE["started"] or now
        elif previous in {"idle", "done", "error"}:
            started = now
        else:
            started = _STATE["started"] or now

        if stage == "idle" or previous in {"idle", "done", "error"}:
            _LOG.clear()

        if detail and (not _LOG or _LOG[-1]["message"] != detail):
            _LOG.append(
                {
                    "stage": stage,
                    "message": detail,
                    "elapsed": round(max(now - started, 0.0), 2),
                }
            )

        _STATE.update(
            stage=stage,
            detail=detail,
            done=done,
            total=total,
            started=started,
            finished=now if stage in {"done", "error", "idle"} else 0.0,
        )


def begin(stage: str, detail: str = "") -> None:
    """Start a run for work that happens before a rebuild (upload, fetch, delete)."""
    set_progress(stage, detail)


def log_event(message: str) -> None:
    """Append a detail line to the log without changing the stage."""
    now = time.time()
    with _LOCK:
        started = _STATE["started"] or now
        _LOG.append(
            {
                "stage": _STATE["stage"],
                "message": message,
                "elapsed": round(max(now - started, 0.0), 2),
            }
        )


def progress() -> dict:
    """Snapshot for the HTTP endpoint (state + log + derived elapsed/percent)."""
    with _LOCK:
        state = dict(_STATE)
        log = list(_LOG)

    if state["started"]:
        end = (
            state["finished"]
            if state["stage"] in {"done", "error"} and state["finished"]
            else time.time()
        )
        elapsed = round(max(end - state["started"], 0.0), 1)
    else:
        elapsed = 0.0

    percent = (
        round(100.0 * state["done"] / state["total"], 1)
        if state["total"]
        else None
    )
    return {**state, "log": log, "elapsed": elapsed, "percent": percent}
