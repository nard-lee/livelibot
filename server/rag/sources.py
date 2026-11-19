"""Read every source document into plain text.

Sources are:
1. Files in ``knowledge/`` (``.md``, ``.txt``, ``.pdf``).
2. Cached web pages fetched from ``knowledge/urls.txt`` into ``.cache/urls/``.

A leading bare URL in a markdown file is treated as metadata (the source link)
and removed from the text. All text is sanitised before it reaches the indexer.
"""

import json
import logging
import re
from pathlib import Path

import config
from rag.loaders import clean_title, load_file, pretty_url_title
from rag.progress import log_event, set_progress
from rag.safety import sanitize

log = logging.getLogger(__name__)

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
KNOWLEDGE_SUFFIXES = TEXT_SUFFIXES | {".pdf"}

_TEXT_CACHE_DIR = config.CACHE_DIR / "extracted"

_ACRONYMS = {
    "bir", "boi", "dole", "dswd", "dti", "lgu", "ncr", "ph", "ra", "sec", "sme", "smes",
}


def _pretty(stem: str) -> str:
    words = [word for word in re.split(r"[_\s]+", stem) if word]
    return " ".join(
        word.upper() if word.lower() in _ACRONYMS else word[:1].upper() + word[1:].lower()
        for word in words
    ) or stem


def _title_for(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith("# "):
            return line.strip()[2:].strip()
    return _pretty(fallback)


def _read_document_text(path: Path) -> str:
    """Read a file, caching expensive PDF extraction by (mtime, size)."""
    if path.suffix.lower() != ".pdf":
        return load_file(path)

    try:
        stat = path.stat()
    except OSError:
        return load_file(path)

    cache_file = _TEXT_CACHE_DIR / f"{path.name}.{stat.st_mtime_ns}.{stat.st_size}.json"
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(cached.get("text"), str):
            return cached["text"]
    except (OSError, json.JSONDecodeError):
        pass

    text = load_file(path)
    try:
        _TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
        for stale in _TEXT_CACHE_DIR.glob(f"{path.name}.*.json"):
            if stale != cache_file:
                stale.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not cache extracted text for %s: %s", path.name, exc)
    return text


def _file_document(path: Path) -> dict | None:
    try:
        text = _read_document_text(path)
    except (OSError, ValueError) as exc:
        log.warning("skipping unreadable knowledge file %s: %s", path.name, exc)
        return None

    url = None
    if path.suffix.lower() in TEXT_SUFFIXES:
        lines = text.splitlines()
        if lines and re.fullmatch(r"https?://\S+", lines[0].strip()):
            url = lines[0].strip()
            text = "\n".join(lines[1:]).lstrip()

    text = sanitize(text)
    if not text:
        return None

    log_event(f"  parsed {len(text):,} chars")
    return {
        "id": path.name,
        "title": _title_for(text, path.stem),
        "url": url,
        "text": text,
    }


def _web_document(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("skipping unreadable URL cache %s: %s", path.name, exc)
        return None

    text = sanitize((data.get("text") or "").strip())
    url = data.get("url") or ""
    if not text:
        return None

    title = clean_title((data.get("title") or "").strip())
    if not title or title == url or title.startswith(("http://", "https://")):
        title = pretty_url_title(url) if url else path.stem

    log_event(f"  {title[:60]} ({len(text):,} chars)")
    return {"id": url or path.stem, "title": title, "url": url or None, "text": text}


def _web_entries() -> list[Path]:
    """Cache files, one per page even if the same URL was cached twice."""
    if not config.URL_CACHE_DIR.exists():
        return []

    paths: list[Path] = []
    seen: set[str] = set()
    for path in sorted(config.URL_CACHE_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            paths.append(path)
            continue

        url = (payload.get("url") or "").strip()
        key = (url.rstrip("/") if url else path.stem).lower()
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _entries() -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    if config.KNOWLEDGE_DIR.exists():
        for path in sorted(config.KNOWLEDGE_DIR.glob("*")):
            if path.suffix.lower() in KNOWLEDGE_SUFFIXES and path.name != "urls.txt":
                entries.append(("file", path))
    for path in _web_entries():
        entries.append(("web", path))
    return entries


def load_documents() -> list[dict]:
    """Return ``[{id, title, url, text}]`` for every configured source."""
    entries = _entries()
    total = len(entries)
    documents: list[dict] = []

    for position, (kind, path) in enumerate(entries, start=1):
        if kind == "file":
            set_progress("reading", f"Reading {position}/{total}: {path.name}", position - 1, total)
            document = _file_document(path)
        else:
            set_progress("reading", f"Reading web page {position}/{total}", position - 1, total)
            document = _web_document(path)

        if document is not None:
            documents.append(document)

    set_progress("reading", f"Read {len(documents)} document(s)", total, total)
    return documents


def source_files() -> list[list]:
    """File fingerprints (name, size, mtime) used to invalidate the index."""
    files: list[list] = []
    for root, suffixes in (
        (config.KNOWLEDGE_DIR, KNOWLEDGE_SUFFIXES),
        (config.URL_CACHE_DIR, {".json"}),
    ):
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if path.name == "urls.txt":
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append([f"{root.name}/{path.name}", stat.st_size, stat.st_mtime_ns])
    return files
