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
import time
from datetime import datetime, timezone

import numpy as np

import config
from rag.chunking import chunk_text
from rag.embedder import BATCH_SIZE, embed
from rag.keyword import BM25
from rag.progress import log_event, set_progress
from rag.sources import load_documents, source_files

log = logging.getLogger(__name__)

INDEX_PATH = config.INDEX_DIR / "index.json"
VECTORS_PATH = config.INDEX_DIR / "vectors.npy"

UPDATING_MESSAGE = "The knowledge base is being updated. Please try again shortly."

_LOCK = threading.RLock()
_items: list[dict] = []
_vectors: np.ndarray | None = None
_bm25: BM25 | None = None
_meta: dict | None = None
_fingerprint: str | None = None
_built_at: str | None = None
_unavailable: str | None = None


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
        "updating": _unavailable is not None,
    }


def unavailable() -> str | None:
    """Reason the index cannot answer yet, or None when it is ready."""
    ensure_index()
    return _unavailable


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


def _text_key(text: str) -> str:
    """Stable key for a chunk in the partial-embedding cache."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _partial_path():
    # Resolved per call so tests and INDEX_DIR overrides take effect.
    return config.INDEX_DIR / "partial.npz"


def _load_partial() -> dict[str, np.ndarray]:
    """Vectors saved by an interrupted ingest, keyed by chunk hash."""
    try:
        with np.load(_partial_path(), allow_pickle=False) as data:
            meta = json.loads(str(data["meta"]))
            keys = [str(key) for key in data["keys"]]
            vectors = data["vectors"]
    except Exception:
        # Missing or unreadable progress file: start this run from scratch.
        return {}

    if meta != _embedding_meta() or vectors.ndim != 2 or vectors.shape[0] != len(keys):
        return {}
    return {
        key: np.asarray(vectors[index], dtype=np.float32)
        for index, key in enumerate(keys)
    }


def _save_partial(vectors: dict[str, np.ndarray]) -> None:
    """Persist finished batches atomically so a rerun can continue."""
    if not vectors:
        return
    try:
        config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
        keys = sorted(vectors)
        rows = np.asarray([vectors[key] for key in keys], dtype=np.float32)
        tmp = config.INDEX_DIR / f"partial.{os.getpid()}.tmp.npz"
        np.savez(
            tmp,
            meta=np.array(json.dumps(_embedding_meta(), sort_keys=True)),
            keys=np.array(keys, dtype=str),
            vectors=rows,
        )
        os.replace(tmp, _partial_path())
    except OSError as exc:
        log.warning("could not save partial embeddings: %s", exc)


def _drop_partial() -> None:
    try:
        _partial_path().unlink(missing_ok=True)
    except OSError:
        pass


def _embed_missing(texts: list[str]) -> dict[str, np.ndarray]:
    """Embed only chunks that are not already in the index (batched + logged).

    Each batch is persisted before the next one starts, so an interrupted run
    keeps every finished batch and the next run resumes instead of re-embedding.
    """
    fresh: dict[str, np.ndarray] = {}
    recovered = _load_partial()
    pending: list[str] = []
    for text in texts:
        vector = recovered.get(_text_key(text))
        if vector is None:
            pending.append(text)
        else:
            fresh[text] = vector

    if fresh:
        log.info("resumed %d chunk(s) from partial embeddings", len(fresh))

    total = len(texts)
    done = len(fresh)
    set_progress("embedding", f"Embedding {done}/{total} new chunk(s)", done, total)

    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        for text, vector in zip(batch, embed(batch)):
            vector = np.asarray(vector, dtype=np.float32)
            fresh[text] = vector
            recovered[_text_key(text)] = vector
        _save_partial(recovered)

        done += len(batch)
        set_progress(
            "embedding",
            f"Embedding {done}/{total} new chunk(s)",
            done,
            total,
        )
        if start + len(batch) < len(pending) and config.EMBED_DELAY_SECONDS > 0:
            time.sleep(config.EMBED_DELAY_SECONDS)

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
        _drop_partial()
    except OSError as exc:
        log.warning("could not persist index: %s", exc)


# ------------------------------------------------------------------ lifecycle

def _rebuild(fingerprint: str) -> None:
    global _fingerprint, _unavailable

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
        _unavailable = None
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
    """Load a valid on-disk index or rebuild from sources when stale.

    In production a stale index is never rebuilt at startup: rebuilding costs
    embedding quota and can fail on a deploy. The app serves UPDATING_MESSAGE
    until the committed index matches again.
    """
    global _fingerprint, _unavailable

    with _LOCK:
        fingerprint = _compute_fingerprint()
        if not force and fingerprint == _fingerprint:
            return
        if not force and _load_from_disk(fingerprint):
            _fingerprint = fingerprint
            _unavailable = None
            set_progress("idle")
            return
        if not force and config.PRODUCTION:
            _fingerprint = fingerprint
            _unavailable = UPDATING_MESSAGE
            log.error(
                "committed index does not match the sources; serving "
                "'knowledge base is being updated' instead of rebuilding"
            )
            set_progress("idle")
            return
        _unavailable = None
        log.info("building index: no valid on-disk index")
        _rebuild(fingerprint)


def rebuild() -> dict:
    """Force a rebuild (uploads, deletes, ingest) and return fresh stats."""
    ensure_index(force=True)
    return stats()


def warm() -> None:
    """Load the index before the first question."""
    set_progress("warming", "Loading index")
    ensure_index()

    if _unavailable:
        set_progress("idle")
        return

    # Parse documents once so PDF extraction is cached for later rebuilds.
    try:
        load_documents()
    except Exception:
        log.warning("document warmup failed", exc_info=True)

    set_progress("idle")
    log.info("warmup complete: %d chunks, %s", len(_items), config.EMBED_MODEL)
