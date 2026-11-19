"""Fingerprint tests. Run with: python tests/test_fingerprint.py (no pytest needed)."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import rag.index as index
from rag import sources


def _with_dirs(base: Path):
    """Point the knowledge and URL cache dirs at ``base`` (restored by caller)."""
    saved = (config.KNOWLEDGE_DIR, config.URL_CACHE_DIR)
    config.KNOWLEDGE_DIR = base / "knowledge"
    config.URL_CACHE_DIR = base / "urls"
    config.KNOWLEDGE_DIR.mkdir(exist_ok=True)
    config.URL_CACHE_DIR.mkdir(exist_ok=True)
    return saved


def _digests(base: Path) -> dict[str, str]:
    saved = _with_dirs(base)
    try:
        return sources.source_digests()
    finally:
        config.KNOWLEDGE_DIR, config.URL_CACHE_DIR = saved


def _components(base: Path) -> dict:
    saved = _with_dirs(base)
    try:
        return index.fingerprint_components()
    finally:
        config.KNOWLEDGE_DIR, config.URL_CACHE_DIR = saved


def test_fingerprint_ignores_line_endings():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "knowledge" / "permit.md"
        path.parent.mkdir()
        path.write_bytes(b"# Permit\n\nBring forms.\n")
        lf = _digests(Path(tmp))

        path.write_bytes(b"# Permit\r\n\r\nBring forms.\r\n")
        crlf = _digests(Path(tmp))

    assert lf == crlf, "the same content must hash the same on any checkout"


def test_fingerprint_changes_with_content():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "knowledge" / "permit.md"
        path.parent.mkdir()
        path.write_text("Body one.", encoding="utf-8")
        before = _digests(Path(tmp))

        path.write_text("Body two.", encoding="utf-8")
        after = _digests(Path(tmp))

    assert before != after


def test_web_fingerprint_uses_text_not_fetch_time():
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "urls"
        cache.mkdir()
        page = cache / "abc.json"

        def write(text, title, fetched_at):
            page.write_text(
                json.dumps(
                    {
                        "url": "https://example.com/a",
                        "title": title,
                        "text": text,
                        "fetched_at": fetched_at,
                    }
                ),
                encoding="utf-8",
            )

        write("Stable body.", "First title", "2026-01-01T00:00:00+00:00")
        first = _digests(Path(tmp))

        write("Stable body.", "A different title", "2026-11-19T12:00:00+00:00")
        redated = _digests(Path(tmp))

        write("Changed body.", "A different title", "2026-11-19T12:00:00+00:00")
        changed = _digests(Path(tmp))

    assert first == redated, "title and fetched_at must not invalidate the index"
    assert redated != changed


def test_components_are_a_dict_of_settings_and_file_hashes():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "knowledge" / "permit.md"
        path.parent.mkdir()
        path.write_text("Body.", encoding="utf-8")
        components = _components(Path(tmp))

    assert components["INDEX_VERSION"] == config.INDEX_VERSION
    assert components["EMBED_MODEL"] == config.EMBED_MODEL
    assert components["RAG_CHUNK_CHARS"] == config.RAG_CHUNK_CHARS
    assert components["RAG_CHUNK_OVERLAP"] == config.RAG_CHUNK_OVERLAP
    assert any(name.endswith("permit.md") for name in components["files"])


def test_mismatch_names_exactly_which_components_differ():
    stored = {
        "INDEX_VERSION": 1,
        "EMBED_MODEL": "old-model",
        "RAG_CHUNK_CHARS": 800,
        "RAG_CHUNK_OVERLAP": 120,
        "files": {"knowledge/a.md": "aaa", "knowledge/b.md": "bbb"},
    }
    current = {
        "INDEX_VERSION": 1,
        "EMBED_MODEL": "new-model",
        "RAG_CHUNK_CHARS": 800,
        "RAG_CHUNK_OVERLAP": 120,
        "files": {"knowledge/a.md": "changed", "knowledge/c.md": "ccc"},
    }

    line = index._describe_mismatch(stored, current)

    assert "files changed: knowledge/a.md, knowledge/b.md, knowledge/c.md" in line
    assert "settings changed: EMBED_MODEL" in line
    assert "aaa" not in line and "bbb" not in line, "never log digests or contents"
    assert "missing" in index._describe_mismatch(None, current)


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
