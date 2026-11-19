import json
import logging
import re

import config
from llm import complete

log = logging.getLogger(__name__)

MAX_PASSAGE_CHARS = 300
_NUMBER_RE = re.compile(r"\d+")
_ARRAY_RE = re.compile(r"\[[^\]]*\]")

SYSTEM = (
    "You rank search results for a retrieval system. "
    "Given a question and numbered passages, order every passage from most to "
    "least relevant. Return a JSON array containing each passage number exactly "
    "once, for example [3, 1, 2]."
)


def _parse_order(raw: str, count: int) -> list[int]:
    match = _ARRAY_RE.search(raw)
    if not match:
        return []
    try:
        numbers = json.loads(match.group(0))
    except json.JSONDecodeError:
        numbers = [int(value) for value in _NUMBER_RE.findall(match.group(0))]

    order: list[int] = []
    for number in numbers:
        if isinstance(number, int) and 1 <= number <= count and number not in order:
            order.append(number)
    return order


def rerank(question: str, hits: list[dict], k: int | None = None) -> list[dict]:
    """Reorder the top candidates with the generator model, then take the best k."""
    k = k or config.RAG_TOP_K
    if not config.RAG_RERANK or len(hits) <= k:
        return hits[:k]

    candidates = hits[: config.RAG_RERANK_CANDIDATES]
    listing = "\n\n".join(
        f"[{index}] {' '.join(hit['content'].split())[:MAX_PASSAGE_CHARS]}"
        for index, hit in enumerate(candidates, start=1)
    )
    prompt = f"Question:\n{question}\n\nPassages:\n{listing}"

    try:
        raw = complete(
            [{"role": "user", "content": prompt}],
            system=SYSTEM,
            temperature=0.0,
            max_tokens=config.RAG_RERANK_MAX_TOKENS,
            model=config.RAG_RERANK_MODEL,
            reasoning_effort=config.RAG_RERANK_EFFORT or None,
        )
        order = _parse_order(raw, len(candidates))
    except Exception:
        log.warning("rerank failed, keeping fusion order", exc_info=True)
        return hits[:k]

    if not order:
        return hits[:k]

    ranked = [candidates[number - 1] for number in order]
    # Keep any candidates the model skipped at the end instead of losing them.
    ranked.extend(candidate for candidate in candidates if candidate not in ranked)
    return ranked[:k]
