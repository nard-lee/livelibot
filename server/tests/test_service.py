"""Answer-shaping tests. Run with: python tests/test_service.py (no pytest needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat.service import NO_ANSWER, _final_sources, _looks_like_refusal

SOURCES = [{"title": "A"}, {"title": "B", "url": "https://example.com/b"}]


def test_only_cited_sources_are_returned():
    result = _final_sources("Answer [1].", SOURCES)
    assert [source["number"] for source in result] == [1]
    assert result[0]["title"] == "A"


def test_full_width_citations_work():
    result = _final_sources("Answer 【2】.", SOURCES)
    assert [source["number"] for source in result] == [2]


def test_uncited_answers_hide_sources():
    assert _final_sources("Sure, happy to help!", SOURCES) == []


def test_out_of_range_citations_are_ignored():
    assert _final_sources("See [9].", SOURCES) == []


def test_source_numbers_are_stable():
    assert _final_sources("Answer [2].", SOURCES) == [
        {"number": 2, "title": "B", "url": "https://example.com/b"}
    ]


def test_refusal_detection():
    assert _looks_like_refusal(NO_ANSWER)
    assert _looks_like_refusal("I don't have that")
    assert _looks_like_refusal("I don’t have that information")  # curly apostrophe
    assert not _looks_like_refusal("Business permits are issued by the LGU.")
    assert not _looks_like_refusal("")


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
