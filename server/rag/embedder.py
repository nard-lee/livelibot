"""Embed text with Gemini's embedding endpoint (no local model)."""

import logging
import time

import requests

import config
from llm import LLMConfigError

log = logging.getLogger(__name__)

BATCH_SIZE = 32
# Embedding quota is per minute, so a 429 needs a wait that outlasts the
# window. Values are fallbacks; Gemini's retryDelay is honoured when present.
RETRY_DELAYS = (5, 20, 60)
RETRY_STATUS = {429, 500, 503}
MAX_RETRY_DELAY = 120.0
ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}"
    ":batchEmbedContents"
)
MISSING_KEY = "GEMINI_API_KEY is missing in server/.env"


def _retry_delay(response, fallback: float) -> float:
    """Prefer the provider's retryDelay (e.g. '43s') over our backoff."""
    header = response.headers.get("Retry-After")
    if header:
        try:
            return min(float(header), MAX_RETRY_DELAY)
        except ValueError:
            pass
    try:
        details = response.json().get("error", {}).get("details", [])
    except ValueError:
        details = []
    for detail in details:
        delay = str(detail.get("retryDelay") or "")
        if delay.endswith("s"):
            try:
                return min(float(delay[:-1]) + 1, MAX_RETRY_DELAY)
            except ValueError:
                pass
    return fallback


def _post(batch: list[str], task: str) -> list[list[float]]:
    if not config.GEMINI_API_KEY:
        raise LLMConfigError(MISSING_KEY)

    payload = {
        "requests": [
            {
                "model": f"models/{config.EMBED_MODEL}",
                "content": {"parts": [{"text": text}]},
                "taskType": task,
            }
            for text in batch
        ]
    }
    url = ENDPOINT.format(model=config.EMBED_MODEL)

    status, detail, delay = 0, "", 0.0
    for attempt in range(len(RETRY_DELAYS) + 1):
        if attempt:
            time.sleep(delay)
        response = requests.post(
            url,
            headers={"x-goog-api-key": config.GEMINI_API_KEY},
            json=payload,
            timeout=(10, 60),
        )
        if response.status_code == 200:
            break
        if response.status_code not in RETRY_STATUS:
            detail = response.text[:200]
            status = response.status_code
            response.close()
            raise RuntimeError(f"embedding failed: {status} {detail}")

        status = response.status_code
        detail = response.text[:200]
        delay = _retry_delay(
            response, RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
        )
        log.warning(
            "embedding attempt %d/%d: status %d, retrying in %.0fs",
            attempt + 1,
            len(RETRY_DELAYS) + 1,
            status,
            delay,
        )
        response.close()
    else:
        raise RuntimeError(f"embedding failed: {status} {detail}")

    try:
        embeddings = response.json()["embeddings"]
        return [list(map(float, item["values"])) for item in embeddings]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("embedding failed: unexpected response") from exc


def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        vectors.extend(_post(texts[start : start + BATCH_SIZE], task))
    return vectors
