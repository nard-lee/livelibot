"""Chunker tests. Run with: python tests/test_chunking.py (no pytest needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.chunking import chunk_text


def test_empty_input_returns_nothing():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunks_respect_size_limit():
    text = " ".join(f"Sentence {i} is about business permits." for i in range(80))
    chunks = chunk_text(text, max_chars=200, overlap=40)
    assert chunks
    assert max(len(chunk) for chunk in chunks) <= 200


def test_neighbouring_chunks_share_overlap():
    text = " ".join(f"Sentence {i} is about business permits." for i in range(40))
    chunks = chunk_text(text, max_chars=200, overlap=40)
    assert len(chunks) > 1
    tail = chunks[0][-20:].split(" ", 1)[-1]
    assert tail in chunks[1]


def test_bullets_keep_line_breaks():
    text = "Requirements:\nApplication forms\nBarangay clearance\nFire safety certificate"
    [chunk] = chunk_text(text, max_chars=500, overlap=0)
    assert "Application forms\nBarangay clearance" in chunk


def test_headings_become_prefix_and_sections_stay_separate():
    text = (
        "# Permit\n\n## Requirements\n\nForms are required.\n\n"
        "## Fees\n\nFees vary by city."
    )
    chunks = chunk_text(text, max_chars=300, overlap=0)
    assert chunks[0] == "Permit > Requirements\nForms are required."
    assert chunks[1] == "Permit > Fees\nFees vary by city."


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
