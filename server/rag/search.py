"""Hybrid retrieval.

1. Dense cosine scores from the chunk embeddings.
2. BM25 keyword scores (good for exact terms like "RA 11032" or "Barangay").
3. Fuse both rankings with reciprocal rank fusion (RRF).
4. Drop near-duplicate chunks, rerank the survivors, and cap chunks per source.
"""

import logging

import numpy as np

import config
from rag.embedder import embed
from rag.index import ensure_index, get_bm25, get_index
from rag.keyword import reciprocal_rank_fusion
from rag.rerank import rerank

log = logging.getLogger(__name__)


def _query_vector(question: str) -> np.ndarray | None:
    vector = np.asarray(embed([question], task="RETRIEVAL_QUERY")[0], dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        return None
    return vector / norm


def _candidates(dense: np.ndarray, sparse: np.ndarray, min_score: float) -> list[int]:
    """Fuse dense + BM25 rankings and keep the best candidates above the gate."""
    depth = min(len(dense), config.RAG_FUSION_DEPTH)
    dense_order = [int(index) for index in np.argsort(-dense)[:depth]]
    sparse_order = [
        int(index) for index in np.argsort(-sparse)[:depth] if float(sparse[index]) > 0
    ]

    fused = reciprocal_rank_fusion([dense_order, sparse_order], k=config.RAG_RRF_K)
    if not fused:
        return []

    candidates: list[int] = []
    for index, _ in sorted(fused.items(), key=lambda item: item[1], reverse=True):
        index = int(index)
        weak_dense = float(dense[index]) < min_score
        weak_bm25 = float(sparse[index]) < config.RAG_BM25_MIN
        if weak_dense and weak_bm25:
            continue
        candidates.append(index)
        if len(candidates) >= config.RAG_CANDIDATES:
            break
    return candidates


def _dedupe(candidates: list[int], vectors: np.ndarray) -> list[int]:
    """Drop candidates whose embedding is nearly identical to one already kept."""
    kept: list[int] = []
    for index in candidates:
        if kept and float(np.max(vectors[kept] @ vectors[index])) >= config.RAG_DEDUPE_SIM:
            continue
        kept.append(index)
    return kept


def _cap_per_source(hits: list[dict], k: int) -> list[dict]:
    capped: list[dict] = []
    per_source: dict[str, int] = {}
    for hit in hits:
        if per_source.get(hit["source_id"], 0) >= config.RAG_MAX_PER_SOURCE:
            continue
        per_source[hit["source_id"]] = per_source.get(hit["source_id"], 0) + 1
        capped.append(hit)
        if len(capped) >= k:
            break
    return capped


def search(
    question: str, k: int | None = None, min_score: float | None = None
) -> list[dict]:
    """Return the best chunks for ``question`` (see module docstring)."""
    question = (question or "").strip()
    if not question:
        return []

    k = k or config.RAG_TOP_K
    min_score = config.RAG_MIN_SCORE if min_score is None else min_score

    ensure_index()
    items, vectors = get_index()
    if vectors is None or not items:
        return []

    query = _query_vector(question)
    if query is None:
        return []

    dense = np.asarray(vectors @ query, dtype=np.float32)
    bm25 = get_bm25()
    sparse = (
        np.asarray(bm25.scores(question), dtype=np.float32)
        if bm25
        else np.zeros(len(items))
    )

    candidates = _candidates(dense, sparse, min_score)
    if not candidates:
        return []

    hits = [
        {**items[index], "score": round(float(dense[index]), 4)}
        for index in _dedupe(candidates, vectors)
    ]
    hits = rerank(question, hits, k)
    return _cap_per_source(hits, k)
