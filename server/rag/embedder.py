"""Embed text with Gemini's embedding endpoint (no local model)."""

import logging
import time

import requests

import config
from llm import LLMConfigError

log = logging.getLogger(__name__)

BATCH_SIZE = 32
RETRY_DELAYS = (5, 15)
RETRY_STATUS = {429, 500, 503}
ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}"
    ":batchEmbedContents"
)
MISSING_KEY = "GEMINI_API_KEY is missing in server/.env"


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

    response = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        if attempt:
            time.sleep(RETRY_DELAYS[attempt - 1])
        response = requests.post(
            url,
            headers={"x-goog-api-key": config.GEMINI_API_KEY},
            json=payload,
            timeout=(10, 60),
        )
        if response.status_code == 200:
            break
        if response.status_code in RETRY_STATUS:
            response.close()
            continue
        detail = response.text[:200]
        status = response.status_code
        response.close()
        raise RuntimeError(f"embedding failed: {status} {detail}")
    else:
        raise RuntimeError("embedding failed: model busy")

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
