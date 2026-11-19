import logging

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

import config
import rag.store as store
from rag import rebuild, stats
from rag.loaders import extract_pdf
from rag.urls import (
    add_url,
    cache_url,
    cached_urls,
    normalize_url,
    read_urls,
    remove_cache,
    remove_url,
)

log = logging.getLogger(__name__)

documents_bp = Blueprint("documents", __name__)


@documents_bp.before_request
def block_writes_when_public():
    """Hide every mutating route unless ADMIN_ENABLED is on."""
    if config.ADMIN_ENABLED or request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    return jsonify({"error": "not found"}), 404


TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
PDF_SUFFIXES = {".pdf"}
ALLOWED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES


def _path_for(name: str):
    """Resolve a knowledge file name, rejecting traversal and unknown types."""
    safe = secure_filename(name)
    if not safe or safe == "urls.txt":
        return None
    path = (config.KNOWLEDGE_DIR / safe).resolve()
    if path.parent != config.KNOWLEDGE_DIR.resolve():
        return None
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        return None
    return path


def _validate_payload(filename: str, payload: bytes) -> None:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if not payload.strip():
        raise ValueError("file is empty")
    if suffix == "pdf":
        extract_pdf(payload)
        return

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("file must be UTF-8 text or a PDF") from exc
    if not text.strip():
        raise ValueError("file has no text")


def _document_info(name: str, index: dict) -> dict:
    detail = next(
        (item for item in index.get("details", []) if item["source"] == name),
        {"title": name, "chunks": 0},
    )
    return {"name": name, "title": detail.get("title", name), "chunks": detail.get("chunks", 0)}


def _url_info(url: str, index: dict, cached: dict[str, dict]) -> dict:
    detail = next(
        (item for item in index.get("details", []) if item["source"] == url), None
    )
    payload = cached.get(url) or {}
    return {
        "url": url,
        "title": (detail or {}).get("title") or payload.get("title") or url,
        "chunks": (detail or {}).get("chunks", 0),
        "cached": bool(payload),
    }


@documents_bp.get("/documents")
def list_documents():
    paths = []
    if config.KNOWLEDGE_DIR.exists():
        paths = [
            path
            for path in sorted(config.KNOWLEDGE_DIR.iterdir())
            if path.is_file()
            and path.suffix.lower() in ALLOWED_SUFFIXES
            and path.name != "urls.txt"
        ]

    index = stats()
    documents = []
    for path in paths:
        info = _document_info(path.name, index)
        stat = path.stat()
        info.update({"bytes": stat.st_size, "modified_at": stat.st_mtime})
        documents.append(info)

    cached = cached_urls()
    urls = [_url_info(url, index, cached) for url in read_urls()]

    return jsonify(
        {
            "documents": documents,
            "urls": urls,
            "index": index,
            "max_upload_bytes": config.MAX_UPLOAD_BYTES,
        }
    )


@documents_bp.get("/index/progress")
def index_progress():
    return jsonify(store.progress())


@documents_bp.post("/documents")
def upload_document():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "file is required"}), 400

    path = _path_for(file.filename)
    if path is None:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
        return jsonify({"error": f"unsupported file type (allowed: {allowed})"}), 400

    store.begin("uploading", f"Reading {path.name}")

    payload = file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(payload) > config.MAX_UPLOAD_BYTES:
        return (
            jsonify(
                {
                    "error": "file is too large",
                    "max_bytes": config.MAX_UPLOAD_BYTES,
                }
            ),
            413,
        )

    try:
        _validate_payload(path.name, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    config.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)

    try:
        index = rebuild()
    except Exception:
        log.exception("index rebuild failed after upload")
        path.unlink(missing_ok=True)
        return jsonify({"error": "index rebuild failed, upload rolled back"}), 500

    return jsonify({"document": _document_info(path.name, index), "index": index}), 201


@documents_bp.delete("/documents/<path:name>")
def delete_document(name: str):
    path = _path_for(name)
    if path is None:
        return jsonify({"error": "unknown document"}), 400
    if not path.exists():
        return jsonify({"error": "document not found"}), 404

    path.unlink()
    store.begin("removing", path.name)
    try:
        index = rebuild()
    except Exception:
        log.exception("index rebuild failed after delete")
        return jsonify({"error": "index rebuild failed"}), 500

    return jsonify({"deleted": path.name, "index": index})


@documents_bp.post("/documents/urls")
def add_url_document():
    data = request.get_json(silent=True) or {}
    try:
        url = normalize_url(str(data.get("url") or ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        add_url(url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    warning = None
    store.begin("fetching", url)
    try:
        payload = cache_url(url)
        store.log_event(f"  fetched {len(payload['text']):,} chars")
    except ValueError as exc:
        warning = str(exc)
        log.warning("could not fetch %s: %s", url, exc)

    try:
        index = rebuild()
    except Exception:
        log.exception("index rebuild failed after adding URL")
        return jsonify({"error": "index rebuild failed"}), 500

    return (
        jsonify(
            {
                "source": _url_info(url, index, cached_urls()),
                "warning": warning,
                "index": index,
            }
        ),
        201,
    )


@documents_bp.post("/documents/urls/refresh")
def refresh_url_document():
    data = request.get_json(silent=True) or {}
    try:
        url = normalize_url(str(data.get("url") or ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    known = set()
    for existing in read_urls():
        try:
            known.add(normalize_url(existing))
        except ValueError:
            continue
    if url not in known:
        return jsonify({"error": "URL is not in the list"}), 404

    warning = None
    store.begin("fetching", url)
    try:
        payload = cache_url(url)
        store.log_event(f"  fetched {len(payload['text']):,} chars")
    except ValueError as exc:
        warning = str(exc)
        log.warning("could not fetch %s: %s", url, exc)

    try:
        index = rebuild()
    except Exception:
        log.exception("index rebuild failed after refreshing URL")
        return jsonify({"error": "index rebuild failed"}), 500

    return jsonify(
        {
            "source": _url_info(url, index, cached_urls()),
            "warning": warning,
            "index": index,
        }
    )


@documents_bp.delete("/documents/urls")
def delete_url_document():
    data = request.get_json(silent=True) or {}
    try:
        url = normalize_url(str(data.get("url") or ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    removed = remove_url(url)
    remove_cache(url)
    if not removed:
        return jsonify({"error": "URL not found"}), 404

    store.begin("removing", url)
    try:
        index = rebuild()
    except Exception:
        log.exception("index rebuild failed after removing URL")
        return jsonify({"error": "index rebuild failed"}), 500

    return jsonify({"deleted": url, "index": index})
