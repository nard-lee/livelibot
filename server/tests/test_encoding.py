"""Encoding tests. Run with: python tests/test_encoding.py (no pytest needed)."""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import rag.index as index
import rag.urls as urls
from llm.client import _decode_line, _gemini_text
from rag.sources import _web_document

TEXT = "Mayor’s permit costs ₱30."


def test_utf8_sse_payload_round_trips():
    raw = (
        'data: {"candidates":[{"content":{"parts":[{"text":"' + TEXT + '"}]}}]}'
    ).encode("utf-8")
    assert _gemini_text(json.loads(_decode_line(raw)[5:].strip())) == TEXT


def test_page_cache_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        saved = config.URL_CACHE_DIR
        original = urls.load_url
        config.URL_CACHE_DIR = Path(tmp)
        urls.load_url = lambda url: ("Permit Guide", TEXT)
        try:
            payload = urls.cache_url("https://example.com/permit")
            [path] = Path(tmp).glob("*.json")
            document = _web_document(path)
        finally:
            urls.load_url = original
            config.URL_CACHE_DIR = saved

    assert "₱30" in payload["text"] and "Mayor’s" in payload["text"]
    assert document["text"] == TEXT


def test_index_round_trips():
    items = [
        {
            "source_id": "permit.md",
            "title": "Permit Guide",
            "url": None,
            "content": TEXT,
        }
    ]
    vectors = np.asarray([[1.0, 0.0]], dtype=np.float32)

    with tempfile.TemporaryDirectory() as tmp:
        saved_dir = config.INDEX_DIR
        saved_paths = (index.INDEX_PATH, index.VECTORS_PATH)
        config.INDEX_DIR = Path(tmp)
        index.INDEX_PATH = Path(tmp) / "index.json"
        index.VECTORS_PATH = Path(tmp) / "vectors.npy"
        try:
            index._save_to_disk("encoding-test", {}, items, vectors)
            assert index._load_from_disk("encoding-test", {})
            loaded, _ = index.get_index()
        finally:
            config.INDEX_DIR = saved_dir
            index.INDEX_PATH, index.VECTORS_PATH = saved_paths
            index._set_index([], None, None)

    assert loaded[0]["content"] == TEXT


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
