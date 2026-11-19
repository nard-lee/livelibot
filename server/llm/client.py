import json
import logging
import time
from typing import Iterator

import requests

import config

log = logging.getLogger(__name__)

MAX_TOKENS = 2000
MISSING_KEY = "GEMINI_API_KEY is missing in server/.env"
BUSY = "The model is busy, try again."
RETRY_DELAYS = (5, 10, 15)
RETRY_STATUS = {429, 500, 503}

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}"

GEMINI_THINKING_LEVEL = "minimal"


class LLMConfigError(RuntimeError):
    """Provider configuration cannot serve requests."""


class MissingKeyError(LLMConfigError):
    """The selected provider has no usable API key."""


class UnknownProviderError(LLMConfigError):
    """LLM_PROVIDER is not one of the supported values."""


def provider() -> str:
    name = (config.LLM_PROVIDER or "gemini").strip().lower()
    if name != "gemini":
        raise UnknownProviderError("Unknown LLM_PROVIDER")
    return name


def describe() -> dict:
    """Safe-to-expose backend info for /api/health; never includes the key."""
    provider()
    return {
        "provider": "gemini",
        "model": config.GEMINI_MODEL,
        "key_loaded": bool(config.GEMINI_API_KEY),
    }


# --- Gemini / Gemma ---------------------------------------------------------


def _gemini_contents(messages: list[dict], system: str | None) -> list[dict]:
    contents: list[dict] = []
    for message in messages:
        role = "model" if message.get("role") == "assistant" else "user"
        text = str(message.get("content") or "")
        if not text:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n\n" + text
            continue
        contents.append({"role": role, "parts": [{"text": text}]})

    # Gemini conversations must open with a user turn.
    while contents and contents[0]["role"] != "user":
        contents.pop(0)

    if system:
        if contents:
            contents[0]["parts"][0]["text"] = (
                f"{system}\n\n{contents[0]['parts'][0]['text']}"
            )
        else:
            contents.append({"role": "user", "parts": [{"text": system}]})
    return contents


def _gemini_payload(
    messages: list[dict],
    system: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> dict:
    return {
        "contents": _gemini_contents(messages, system),
        "generationConfig": {
            "temperature": config.TEMPERATURE if temperature is None else temperature,
            "maxOutputTokens": max_tokens or MAX_TOKENS,
            "thinkingConfig": {"thinkingLevel": GEMINI_THINKING_LEVEL},
        },
    }


def _gemini_post(payload: dict, stream: bool):
    """POST to generateContent, retrying 429/500/503. Returns None when busy."""
    if not config.GEMINI_API_KEY:
        raise MissingKeyError(MISSING_KEY)

    method = "streamGenerateContent" if stream else "generateContent"
    url = GEMINI_URL.format(model=config.GEMINI_MODEL, method=method)

    for attempt in range(len(RETRY_DELAYS) + 1):
        if attempt:
            time.sleep(RETRY_DELAYS[attempt - 1])
        response = requests.post(
            url,
            headers={"x-goog-api-key": config.GEMINI_API_KEY},
            json=payload,
            params={"alt": "sse"} if stream else None,
            stream=stream,
            timeout=(10, 180),
        )
        if response.status_code == 200:
            return response
        response.close()
        if response.status_code in RETRY_STATUS:
            continue
        raise RuntimeError(f"Gemini request failed with HTTP {response.status_code}")

    log.warning("gemini still unavailable after %d tries", len(RETRY_DELAYS) + 1)
    return None


def _decode_line(line: bytes | str) -> str:
    """SSE payloads are UTF-8; requests' default Latin-1 decode mangles them."""
    return line.decode("utf-8") if isinstance(line, bytes) else line


def _gemini_text(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(
        part.get("text", "")
        for part in parts
        if part.get("text") and not part.get("thought")
    )


def _gemini_complete(
    messages: list[dict],
    system: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> str:
    response = _gemini_post(
        _gemini_payload(messages, system, temperature, max_tokens), stream=False
    )
    if response is None:
        return BUSY
    try:
        data = json.loads(response.content.decode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("Gemini returned an invalid response") from exc
    return _gemini_text(data)


def _gemini_stream(
    messages: list[dict],
    system: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> Iterator[str]:
    response = _gemini_post(
        _gemini_payload(messages, system, temperature, max_tokens), stream=True
    )
    if response is None:
        yield BUSY
        return
    try:
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = _decode_line(raw_line)
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                data = json.loads(chunk)
            except ValueError:
                continue
            text = _gemini_text(data)
            if text:
                yield text
    finally:
        response.close()


# --- Public API -------------------------------------------------------------


def complete(
    messages: list[dict],
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    # Validates LLM_PROVIDER before spending a request.
    provider()
    return _gemini_complete(messages, system, temperature, max_tokens)


def stream(
    messages: list[dict],
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> Iterator[str]:
    provider()
    yield from _gemini_stream(messages, system, temperature, max_tokens)
