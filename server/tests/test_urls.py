"""URL list tests. Run with: python tests/test_urls.py (no pytest needed)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from rag import urls


class _TempKnowledge:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._knowledge = config.KNOWLEDGE_DIR
        self._cache = config.URL_CACHE_DIR
        base = Path(self._tmp.name)
        config.KNOWLEDGE_DIR = base / "knowledge"
        config.URL_CACHE_DIR = base / "urls"
        config.KNOWLEDGE_DIR.mkdir()
        config.URL_CACHE_DIR.mkdir()
        return config.KNOWLEDGE_DIR

    def __exit__(self, *exc_info):
        config.KNOWLEDGE_DIR = self._knowledge
        config.URL_CACHE_DIR = self._cache
        self._tmp.cleanup()


def test_normalize_url():
    assert urls.normalize_url("example.com/page/") == "https://example.com/page"
    assert urls.normalize_url("HTTPS://Example.COM/") == "https://example.com"
    assert urls.normalize_url("http://example.com/a?b=1#frag") == "http://example.com/a?b=1"


def test_normalize_url_rejects_bad_input():
    for bad in ["", "ftp://example.com", "https://", "not a url"]:
        try:
            urls.normalize_url(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should be rejected")


def test_add_and_remove_urls_keep_comments():
    with _TempKnowledge():
        path = config.KNOWLEDGE_DIR / "urls.txt"
        path.write_text("# seed comment\nhttps://a.example.com\n", encoding="utf-8")

        urls.add_url("https://b.example.com/page/")
        assert urls.read_urls() == ["https://a.example.com", "https://b.example.com/page"]

        try:
            urls.add_url("https://b.example.com/page")
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate URL should be rejected")

        assert urls.remove_url("https://b.example.com/page/") is True
        assert urls.read_urls() == ["https://a.example.com"]
        assert "# seed comment" in path.read_text(encoding="utf-8")

        assert urls.remove_url("https://missing.example.com") is False


def test_cache_path_is_stable():
    first = urls.cache_path("https://example.com/a")
    second = urls.cache_path("https://example.com/a")
    assert first == second
    assert first.suffix == ".json"
    assert urls.cache_path("https://example.com/b") != first


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
