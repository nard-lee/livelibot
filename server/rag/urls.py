import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import config
from rag.loaders import load_url

log = logging.getLogger(__name__)


def urls_file() -> Path:
    return config.KNOWLEDGE_DIR / "urls.txt"


def _key(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{scheme}://{netloc}{path}"


def normalize_url(raw: str) -> str:
    """Validate and normalise a URL for storage in knowledge/urls.txt."""
    value = (raw or "").strip()
    if not value:
        raise ValueError("url is required")
    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("url must start with http:// or https://")
    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError("url must include a domain")

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            parsed.query,
            "",
        )
    )


def read_urls() -> list[str]:
    path = urls_file()
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _raw_lines() -> list[str]:
    path = urls_file()
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _write_lines(lines: list[str]) -> None:
    path = urls_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def add_url(url: str) -> None:
    """Append a URL to urls.txt, keeping existing comments and lines."""
    url = normalize_url(url)
    if any(_key(existing) == _key(url) for existing in read_urls()):
        raise ValueError("that URL is already in the list")
    lines = _raw_lines()
    lines.append(url)
    _write_lines(lines)


def remove_url(url: str) -> bool:
    """Remove a URL from urls.txt (comments stay); returns whether it existed."""
    url = normalize_url(url)
    lines = _raw_lines()
    remaining = [
        line
        for line in lines
        if not (
            line.strip()
            and not line.strip().startswith("#")
            and _key(line.strip()) == _key(url)
        )
    ]
    if len(remaining) == len(lines):
        return False
    _write_lines(remaining)
    return True


def cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return config.URL_CACHE_DIR / f"{digest}.json"


def _url_key(url: str) -> str:
    return url.rstrip("/").lower()


def _prune_duplicate_caches(url: str) -> None:
    """Remove cache files for the same page stored under a different URL form."""
    if not config.URL_CACHE_DIR.exists():
        return
    keep = cache_path(url)
    key = _url_key(url)
    for path in config.URL_CACHE_DIR.glob("*.json"):
        if path == keep:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        existing = payload.get("url") or ""
        if existing and _url_key(existing) == key:
            path.unlink(missing_ok=True)


def cache_url(url: str) -> dict:
    """Fetch a URL and store its extracted text in the URL cache."""
    title, text = load_url(url)
    payload = {
        "url": url,
        "title": title,
        "text": text,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    config.URL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(url).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    _prune_duplicate_caches(url)
    return payload


def remove_cache(url: str) -> None:
    key = _url_key(url)
    if not config.URL_CACHE_DIR.exists():
        return
    for path in config.URL_CACHE_DIR.glob("*.json"):
        if path == cache_path(url):
            path.unlink(missing_ok=True)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        existing = payload.get("url") or ""
        if existing and _url_key(existing) == key:
            path.unlink(missing_ok=True)


def cached_urls() -> dict[str, dict]:
    """Map cached URL -> payload for every cached page."""
    result: dict[str, dict] = {}
    if not config.URL_CACHE_DIR.exists():
        return result
    for path in config.URL_CACHE_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        url = payload.get("url")
        if url:
            result[url] = payload
    return result
