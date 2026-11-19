"""Build, persist and load the vector index.

Flow:
    ensure_index() -> fingerprint check -> load .index/ from disk, or
    read sources -> chunk -> embed (reusing unchanged vectors) -> save.

The index state is a module-level singleton guarded by a lock. Chunk vectors
are normalised, so search can use a plain dot product.
"""

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone

import numpy as np

import config
from rag.chunking import chunk_text
from rag.embedder import embed
from rag.keyword import BM25
from rag.progress import log_event, set_progress
from rag.sources import load_documents, source_files

log = logging.getLogger(__name__)

INDEX_PATH = config.INDEX_DIR / "index.json"
VECTORS_PATH = config.INDEX_DIR / "vectors.npy"

_LOCK = threading.RLock()
_items: list[dict] = []
_vectors: np.ndarray | None = None
_bm25: BM25 | None = None
_meta: dict | None = None
_fingerprint: str | None = None
_built_at: str | None = None


# ---------------------------------------------------------------- public state

def get_index() -> tuple[list[dict], np.ndarray | None]:
    return _items, _vectors


def get_bm25() -> BM25 | None:
    return _bm25


def stats() -> dict:
    ensure_index()
    sources = sorted({item["source_id"] for item in _items})
    per_source: dict[str, dict] = {}
    for item in _items:
        entry = per_source.setdefault(
            item["source_id"],
            {"source": item["source_id"], "title": item["title"], "chunks": 0},
        )
        entry["chunks"] += 1

    return {
        "chunks": len(_items),
        "documents": len(sources),
        "details": [per_source[source] for source in sources],
        "model": config.EMBED_MODEL,
        "dimensions": int(_vectors.shape[1]) if _vectors is not None else 0,
        "built_at": _built_at,
        "rerank": config.RAG_RERANK,
        "bm25": _bm25 is not None,
    }


# ------------------------------------------------------------------ building

def _embedding_meta() -> dict:
    """Settings that must match for old vectors to be reusable."""
    return {
        "version": config.INDEX_VERSION,
        "model": config.EMBED_MODEL,
        "chunk": [config.RAG_CHUNK_CHARS, config.RAG_CHUNK_OVERLAP],
    }


def _normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _reusable_vectors() -> dict[str, np.ndarray]:
    """chunk text -> vector, only when the embedding settings are unchanged."""
    if _vectors is None or _meta != _embedding_meta():
        return {}
    return {item["content"]: _vectors[index] for index, item in enumerate(_items)}


def _chunk_documents(documents: list[dict]) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    texts: list[str] = []
    total = len(documents)

    for position, document in enumerate(documents, start=1):
        set_progress(
            "chunking",
            f"Chunking {document['id'][:60]} ({position}/{total})",
            position - 1,
            total,
        )
        chunks = chunk_text(document["text"])
        for chunk in chunks:
            items.append(
                {
                    "source_id": document["id"],
                    "title": document["title"],
                    "url": document["url"],
                    "content": chunk,
                }
            )
            texts.append(chunk)
        log_event(f"  {len(chunks)} chunk(s)")

    return items, texts


def _embed_missing(texts: list[str]) -> dict[str, np.ndarray]:
    """Embed only chunks that are not already in the index (batched + logged)."""
    fresh: dict[str, np.ndarray] = {}
    batch_size = 32
    embedded = 0
    set_progress("embedding", f"Embedding 0/{len(texts)} new chunk(s)", 0, len(texts))

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        for text, vector in zip(batch, embed(batch)):
            fresh[text] = np.asarray(vector, dtype=np.float32)
        embedded += len(batch)
        set_progress(
            "embedding",
            f"Embedding {embedded}/{len(texts)} new chunk(s)",
            embedded,
            len(texts),
        )

    return fresh


def _build(documents: list[dict]) -> tuple[list[dict], np.ndarray | None]:
    items, texts = _chunk_documents(documents)
    if not texts:
        return [], None

    known = _reusable_vectors()
    missing = list(dict.fromkeys(text for text in texts if text not in known))
    reused = len(texts) - len(missing)

    if missing:
        fresh = _embed_missing(missing)
    else:
        set_progress(
            "embedding",
            f"Reused {reused} cached chunk(s), nothing new to embed",
            reused,
            reused,
        )
        fresh = {}

    rows = [known[text] if text in known else fresh[text] for text in texts]
    vectors = _normalise(np.asarray(rows, dtype=np.float32))

    log.info(
        "embedded %d new chunk(s), reused %d unchanged chunk(s)",
        len(missing),
        reused,
    )
    return items, vectors


def _set_index(
    items: list[dict],
    vectors: np.ndarray | None,
    built_at: str | None,
    meta: dict | None = None,
) -> None:
    global _items, _vectors, _bm25, _meta, _built_at
    _items = items
    _vectors = vectors
    _bm25 = BM25([item["content"] for item in items]) if items else None
    _built_at = built_at
    _meta = meta or _embedding_meta()


# --------------------------------------------------------------- persistence

def _compute_fingerprint() -> str:
    payload = json.dumps(
        {
            "version": config.INDEX_VERSION,
            "model": config.EMBED_MODEL,
            "chunk": [config.RAG_CHUNK_CHARS, config.RAG_CHUNK_OVERLAP],
            "files": source_files(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_from_disk(fingerprint: str) -> bool:
    try:
        meta = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    if meta.get("fingerprint") != fingerprint or meta.get("version") != config.INDEX_VERSION:
        return False

    items = meta.get("items") or []
    if not items:
        return False

    try:
        vectors = np.load(VECTORS_PATH)
    except (OSError, ValueError) as exc:
        log.warning("could not read cached vectors: %s", exc)
        return False

    if vectors.ndim != 2 or vectors.shape[0] != len(items):
        return False

    _set_index(
        items,
        _normalise(vectors.astype(np.float32, copy=False)),
        meta.get("built_at"),
    )
    log.info("loaded index from disk: %d chunks", len(items))
    return True


def _save_to_disk(fingerprint: str, items: list[dict], vectors: np.ndarray) -> None:
    try:
        config.INDEX_DIR.mkdir(parents=True, exist_ok=True)

        # Unique temp names: the server and `ingest.py` may write concurrently.
        tmp_vectors = config.INDEX_DIR / f"vectors.{os.getpid()}.tmp.npy"
        np.save(tmp_vectors, vectors)
        os.replace(tmp_vectors, VECTORS_PATH)

        meta = {
            "version": config.INDEX_VERSION,
            "fingerprint": fingerprint,
            "model": config.EMBED_MODEL,
            "chunk_chars": config.RAG_CHUNK_CHARS,
            "chunk_overlap": config.RAG_CHUNK_OVERLAP,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": items,
        }
        tmp_meta = config.INDEX_DIR / f"index.{os.getpid()}.tmp.json"
        tmp_meta.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_meta, INDEX_PATH)
    except OSError as exc:
        log.warning("could not persist index: %s", exc)


# ------------------------------------------------------------------ lifecycle

def _rebuild(fingerprint: str) -> None:
    global _fingerprint

    try:
        set_progress("reading", "Reading sources")
        documents = load_documents()

        set_progress(
            "chunking",
            f"Chunking {len(documents)} document(s)",
            0,
            len(documents),
        )
        items, vectors = _build(documents)

        if vectors is not None:
            set_progress(
                "saving",
                f"Saving {len(items)} chunk(s) to disk",
                len(items),
                len(items),
            )
            _save_to_disk(fingerprint, items, vectors)

        _set_index(
            items,
            vectors,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        _fingerprint = fingerprint
        set_progress(
            "done",
            f"Index ready: {len(items)} chunk(s) from {len(documents)} document(s)",
            len(items),
            len(items),
        )
        log.info("built index: %d chunks from %d files", len(items), len(source_files()))
    except Exception as exc:
        set_progress("error", f"{type(exc).__name__}: {exc}")
        raise


def ensure_index(force: bool = False) -> None:
    """Load a valid on-disk index or rebuild from sources when stale."""
    global _fingerprint

    with _LOCK:
        fingerprint = _compute_fingerprint()
        if not force and fingerprint == _fingerprint:
            return
        if not force and _load_from_disk(fingerprint):
            _fingerprint = fingerprint
            set_progress("idle")
            return
        _rebuild(fingerprint)


def rebuild() -> dict:
    """Force a rebuild (uploads, deletes, ingest) and return fresh stats."""
    ensure_index(force=True)
    return stats()


def warm() -> None:
    """Load the index before the first question."""
    set_progress("warming", "Loading index")
    ensure_index()

    # Parse documents once so PDF extraction is cached for later rebuilds.
    try:
        load_documents()
    except Exception:
        log.warning("document warmup failed", exc_info=True)

    set_progress("idle")
    log.info("warmup complete: %d chunks, %s", len(_items), config.EMBED_MODEL)
