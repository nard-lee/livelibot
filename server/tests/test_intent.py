"""Intent tests. Run with: python tests/test_intent.py (no pytest needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat.intent import is_conversational


def test_greetings_and_acknowledgements():
    for message in ["hey", "Hi!", "hello there", "Good morning", "kamusta", "thanks", "Salamat po", "ok"]:
        assert is_conversational(message), message


def test_capability_questions():
    for message in [
        "what can you do",
        "how can you help?",
        "who are you",
        "what topics do you cover",
        "ano ang kaya mong gawin",
    ]:
        assert is_conversational(message), message


def test_vague_requests():
    for message in ["give me info", "info", "details", "tell me more"]:
        assert is_conversational(message), message


def test_short_reactions_are_conversational():
    for message in [
        "what?",
        "huh",
        "?",
        "uhm",
        "uhmn",
        "hmm",
        "umm",
        "ano?",
        "ha?",
        "sorry?",
        "what do you mean",
        "I don't get it",
        "hindi ko gets",
    ]:
        assert is_conversational(message), message


def test_real_questions_are_not_conversational():
    for message in [
        "What are the requirements for a business permit?",
        "How much is the Kabuhayan Starter Kit?",
        "Ano ang mga serbisyo ng Negosyo Center?",
        "What can I do if my permit application is delayed?",
        "Give me the BIR registration steps",
        "What is a Business One-Stop Shop?",
        "Ano ang BOSS?",
    ]:
        assert not is_conversational(message), message


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
