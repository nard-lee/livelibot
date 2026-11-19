import re

CONTEXT_START = "<context>"
CONTEXT_END = "</context>"

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_INJECTION_RE = re.compile(
    r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
    r"(instructions?|prompts?|rules?)"
    r"|disregard\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
    r"(instructions?|prompts?|rules?)"
    r"|forget\s+(all\s+)?(your|the)\s+(instructions?|rules|prompt)"
    r"|you\s+are\s+now\s+(a|an|the)\s"
    r"|^\s*(system|assistant)\s*:"
    r"|<\|[^>]{0,30}\|>"
    r"|\[/?inst\]"
    r"|###\s*(system|instructions)",
    re.IGNORECASE | re.MULTILINE,
)


def sanitize(text: str) -> str:
    """Strip HTML comments and prompt-injection lines from ingested text.

    Retrieved documents are data, never instructions. This is a best-effort
    filter applied at index build time; the system prompt also delimits the
    context and tells the model to treat it as reference material only.
    """
    text = _HTML_COMMENT_RE.sub(" ", text)
    lines = [line for line in text.splitlines() if not _INJECTION_RE.search(line)]
    cleaned = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)
