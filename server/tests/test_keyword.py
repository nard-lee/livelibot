"""Keyword retrieval tests. Run with: python tests/test_keyword.py (no pytest needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.keyword import BM25, reciprocal_rank_fusion, tokenize


def test_tokenize_drops_stopwords_and_accents():
    assert tokenize("What are the requirements, mga requirements?") == [
        "requirements",
        "requirements",
    ]
    assert tokenize("Barangay Clearance") == ["barangay", "clearance"]


def test_bm25_ranks_exact_keyword_documents():
    documents = [
        "The Bureau of Internal Revenue handles BIR registration.",
        "Barangay clearance is required before a business permit.",
        "Fees vary by city.",
    ]
    scores = BM25(documents).scores("BIR registration")
    assert scores.index(max(scores)) == 0
    assert scores[0] > scores[2]


def test_bm25_returns_zero_without_shared_terms():
    scores = BM25(["business permit", "barangay clearance"]).scores("sourdough bread")
    assert scores == [0.0, 0.0]


def test_reciprocal_rank_fusion_prefers_agreement():
    fused = reciprocal_rank_fusion([[1, 2, 3], [2, 1, 4]], k=60)
    assert fused[1] > fused[3]
    assert fused[2] > fused[3]
    assert 4 in fused


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
