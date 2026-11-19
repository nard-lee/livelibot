"""In-memory sliding-window rate limiter: 10 requests per minute per IP."""

import threading
import time

from flask import request

LIMIT = 10
WINDOW_SECONDS = 60.0

_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def retry_after() -> float | None:
    """Record a hit for the caller's IP.

    Returns None when the request is allowed, else the seconds until the
    oldest hit leaves the window.
    """
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS

    with _lock:
        if len(_hits) > 512:
            for key in [k for k, v in _hits.items() if not v or v[-1] <= cutoff]:
                del _hits[key]

        timestamps = [t for t in _hits.get(ip, ()) if t > cutoff]
        if len(timestamps) >= LIMIT:
            _hits[ip] = timestamps
            return timestamps[0] + WINDOW_SECONDS - now

        timestamps.append(now)
        _hits[ip] = timestamps
        return None
