import json
import logging

from flask import Blueprint, Response, jsonify, request, stream_with_context

import config
from chat.service import generate_reply, stream_reply
from llm import LLMConfigError

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
            f"message is too long (max {config.MAX_MESSAGE_CHARS} characters)"
        )
    return message, _parse_history(data.get("history"))


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


@chat_bp.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    try:
        message, history = _read_request(data)
    except ValueError as exc:
        return _error(str(exc))

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
def chat_stream():
    data = request.get_json(silent=True) or {}
    try:
        message, history = _read_request(data)
    except ValueError as exc:
        return _error(str(exc))

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
