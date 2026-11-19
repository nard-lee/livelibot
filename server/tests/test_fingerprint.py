"""Fingerprint tests. Run with: python tests/test_fingerprint.py (no pytest needed)."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from rag import sources


def _fingerprint(base: Path) -> list[list]:
    """source_files() with the knowledge and URL cache pointed at ``base``."""
    saved = (config.KNOWLEDGE_DIR, config.URL_CACHE_DIR)
    config.KNOWLEDGE_DIR = base / "knowledge"
    config.URL_CACHE_DIR = base / "urls"
    config.KNOWLEDGE_DIR.mkdir(exist_ok=True)
    config.URL_CACHE_DIR.mkdir(exist_ok=True)
    try:
        return sources.source_files()
    finally:
        config.KNOWLEDGE_DIR, config.URL_CACHE_DIR = saved


def test_fingerprint_ignores_line_endings():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "knowledge" / "permit.md"
        path.parent.mkdir()
        path.write_bytes(b"# Permit\n\nBring forms.\n")
        lf = _fingerprint(Path(tmp))

        path.write_bytes(b"# Permit\r\n\r\nBring forms.\r\n")
        crlf = _fingerprint(Path(tmp))

    assert lf == crlf, "the same content must hash the same on any checkout"


def test_fingerprint_changes_with_content():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "knowledge" / "permit.md"
        path.parent.mkdir()
        path.write_text("Body one.", encoding="utf-8")
        before = _fingerprint(Path(tmp))

        path.write_text("Body two.", encoding="utf-8")
        after = _fingerprint(Path(tmp))

    assert before != after


def test_web_fingerprint_uses_text_not_fetch_time():
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "urls"
        cache.mkdir()
        page = cache / "abc.json"
        page.write_text(
            json.dumps(
                {
                    "url": "https://example.com/a",
                    "title": "First title",
                    "text": "Stable body.",
                    "fetched_at": "2026-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        first = _fingerprint(Path(tmp))

        page.write_text(
            json.dumps(
                {
                    "url": "https://example.com/a",
                    "title": "A different title",
                    "text": "Stable body.",
                    "fetched_at": "2026-11-19T12:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        redated = _fingerprint(Path(tmp))

        page.write_text(
            json.dumps(
                {
                    "url": "https://example.com/a",
                    "title": "A different title",
                    "text": "Changed body.",
                    "fetched_at": "2026-11-19T12:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        changed = _fingerprint(Path(tmp))

    assert first == redated, "title and fetched_at must not invalidate the index"
    assert redated != changed


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
            except AssertionError:
                failures += 1
                print(f"FAIL {name}")
            else:
                print(f"ok   {name}")
    raise SystemExit(1 if failures else 0)
