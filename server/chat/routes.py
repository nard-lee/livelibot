import json
import logging
import math
from functools import wraps

from flask import Blueprint, Response, jsonify, request, stream_with_context

import config
import rag.store as store
from chat.service import generate_reply, stream_reply
from llm import LLMConfigError
from utils.ratelimit import retry_after

log = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


def _parse_history(raw) -> list[dict]:
    """Accept a JSON string (FormData) or a list of {role, content} objects."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []

    return [
        {"role": item["role"], "content": str(item["content"])}
        for item in raw
        if isinstance(item, dict)
        and item.get("role") in ("user", "assistant")
        and item.get("content")
    ]


def _read_request(data: dict) -> tuple[str, list[dict]]:
    message = str(data.get("message") or "").strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > config.MAX_MESSAGE_CHARS:
        raise ValueError(
            "That question is a bit long — please keep it under "
            f"{config.MAX_MESSAGE_CHARS} characters so I can focus on what matters."
        )
    return message, _parse_history(data.get("history"))


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def rate_limited(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        wait = retry_after()
        if wait is None:
            return view(*args, **kwargs)

        response = jsonify(
            {
                "error": (
                    "You're asking questions a bit quickly — "
                    "please wait a minute and try again."
                )
            }
        )
        response.status_code = 429
        response.headers["Retry-After"] = str(max(1, math.ceil(wait)))
        return response

    return wrapper


@chat_bp.post("/chat")
@rate_limited
def chat():
    data = request.get_json(silent=True) or {}
    try:
        message, history = _read_request(data)
    except ValueError as exc:
        return _error(str(exc))

    reason = store.unavailable()
    if reason:
        return _error(reason, 503)

    try:
        reply, sources = generate_reply(message, history)
    except LLMConfigError as exc:
        log.error("%s", exc)
        return _error(str(exc), 503)
    except Exception:
        log.exception("chat generation failed")
        return _error("The assistant is unavailable right now. Please try again.", 502)

    return jsonify({"reply": reply, "sources": sources})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@chat_bp.post("/chat/stream")
@rate_limited
def chat_stream():
    data = request.get_json(silent=True) or {}
    try:
        message, history = _read_request(data)
    except ValueError as exc:
        return _error(str(exc))

    reason = store.unavailable()
    if reason:
        return _error(reason, 503)

    def generate():
        try:
            for event in stream_reply(message, history):
                yield _sse(event["event"], event["data"])
        except Exception:
            log.exception("stream failed before completion")
            yield _sse(
                "error",
                {"error": "The assistant is unavailable right now. Please try again."},
            )

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
