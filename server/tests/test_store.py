"""Document parsing tests. Run with: python tests/test_store.py (no pytest needed)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import rag.store as store


class _TempKnowledge:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._knowledge = config.KNOWLEDGE_DIR
        self._urls = config.URL_CACHE_DIR
        base = Path(self._tmp.name)
        config.KNOWLEDGE_DIR = base / "knowledge"
        config.URL_CACHE_DIR = base / "urls"
        config.KNOWLEDGE_DIR.mkdir()
        config.URL_CACHE_DIR.mkdir()
        return config.KNOWLEDGE_DIR

    def __exit__(self, *exc_info):
        config.KNOWLEDGE_DIR = self._knowledge
        config.URL_CACHE_DIR = self._urls
        self._tmp.cleanup()


def test_leading_url_becomes_source_link():
    with _TempKnowledge() as knowledge:
        (knowledge / "permit.md").write_text(
            "https://example.com/permit\n\n# Permit Guide\n\nBring application forms.",
            encoding="utf-8",
        )
        [document] = store._documents()
        assert document["url"] == "https://example.com/permit"
        assert document["title"] == "Permit Guide"
        assert "example.com" not in document["text"]


def test_markdown_title_falls_back_to_filename():
    with _TempKnowledge() as knowledge:
        (knowledge / "boi_business_permit.md").write_text("Body only.", encoding="utf-8")
        [document] = store._documents()
        assert document["title"] == "BOI Business Permit"
        assert document["url"] is None


def test_url_cache_is_indexed_and_cleaned():
    with _TempKnowledge() as knowledge:
        del knowledge  # cache dir is configured separately
        (config.URL_CACHE_DIR / "abc.json").write_text(
            '{"url": "https://example.com/a", "title": "REPUBLIC ACT NO. 11032", "text": "Body."}',
            encoding="utf-8",
        )
        [document] = store._documents()
        assert document["url"] == "https://example.com/a"
        assert document["title"] == "Republic Act No. 11032"


def test_urls_file_is_not_a_document():
    with _TempKnowledge() as knowledge:
        (knowledge / "urls.txt").write_text("https://example.com\n", encoding="utf-8")
        assert store._documents() == []


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
