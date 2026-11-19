import re

_GREETINGS = re.compile(
    r"^\s*(hi|hey|hello|yo|sup|good\s+(morning|afternoon|evening)|"
    r"kamusta|kumusta|musta)\b",
    re.IGNORECASE,
)
_CLOSINGS = re.compile(
    r"^\s*(thanks|thank\s+you|ty|salamat|ok(ay)?|sige|got\s+it|noted|nice|great|"
    r"bye|goodbye|see\s+you)\b",
    re.IGNORECASE,
)
_META = re.compile(
    r"\b(what|how)\s+can\s+you\s+(do|help)\b"
    r"|\bwhat\s+(do\s+you\s+do|are\s+you|topics?\s+do\s+you\s+(cover|know))\b"
    r"|\bwho\s+are\s+you\b|\bwhat\s+are\s+you\b"
    r"|\b(your|the)\s+(capabilities|features|topics)\b"
    r"|\bano\s+(ang\s+)?(kaya|pwede)\s+mong\s+gawin\b",
    re.IGNORECASE,
)
_VAGUE = re.compile(
    r"^\s*(info|information|details|help)\s*[?!.]*\s*$"
    r"|^\s*(give|send)\s+me\s+(some\s+)?(info|information|details)\b"
    r"|^\s*tell\s+me\s+(something|more)\b"
    r"|^\s*(more|and\??)\s*$",
    re.IGNORECASE,
)
_CLARIFICATIONS = re.compile(
    # Bare reactions: "what?", "huh", "?", "ano?", "ha?", "uhm", "sorry?"
    r"^\s*(what|huh|uh+m*n*|hm+|um+|eh+|ha|ano|sorry)\s*[?!.,]*\s*$"
    r"|^\s*\?+\s*$"
    r"|^\s*(what|huh)\s+do\s+you\s+mean\b"
    r"|^\s*(i\s+don'?t|i\s+do\s+not)\s+(get|understand)\b"
    r"|^\s*(hindi|di)\s+ko\s+(gets|maintindihan|naintindihan)\b",
    re.IGNORECASE,
)


def is_conversational(message: str) -> bool:
    """True for greetings, thanks, capability questions, vague requests, and
    short reactions like 'what?' that should get a conversational answer
    instead of the "not in my documents" refusal."""
    text = (message or "").strip()
    if not text or len(text.split()) > 12:
        return False
    return bool(
        _GREETINGS.match(text)
        or _CLOSINGS.match(text)
        or _META.search(text)
        or _VAGUE.match(text)
        or _CLARIFICATIONS.match(text)
    )
