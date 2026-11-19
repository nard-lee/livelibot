import re

import config

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_SENTENCE_RE = re.compile(r"(?<=[.!?;:])\s+")


def _units(block: str, max_chars: int) -> list[tuple[str, str]]:
    """Split a block into (text, separator-before) units.

    Lines inside a block stay separated by newlines so bullet lists survive
    chunking; sentences inside a line are separated by spaces. Oversized
    sentences are hard-wrapped on word boundaries.
    """
    units: list[tuple[str, str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        separator = "\n" if units else ""
        for sentence in _SENTENCE_RE.split(line):
            sentence = sentence.strip()
            while len(sentence) > max_chars:
                cut = sentence.rfind(" ", 0, max_chars)
                if cut <= 0:
                    cut = max_chars
                units.append((sentence[:cut].strip(), separator))
                separator = " "
                sentence = sentence[cut:].strip()
            if sentence:
                units.append((sentence, separator))
                separator = " "
    return units


def _tail(text: str, overlap: int) -> str:
    """Return up to `overlap` trailing characters, aligned to a word boundary."""
    if overlap <= 0:
        return ""
    tail = text[-overlap:]
    cut = tail.find(" ")
    if 0 <= cut < len(tail) - 1:
        tail = tail[cut + 1:]
    return tail.strip()


def _render(text: str, heading_path: list[str]) -> str:
    prefix = " > ".join(heading_path)
    return f"{prefix}\n{text}" if prefix else text


def chunk_text(
    text: str, *, max_chars: int | None = None, overlap: int | None = None
) -> list[str]:
    """Chunk text on paragraph and sentence boundaries, keeping headings as context.

    Chunks stay under `max_chars`, overlap by roughly `overlap` characters so a
    fact split across a boundary is still retrievable, and keep list/line breaks
    so the retrieved context stays readable for the model.
    """
    max_chars = max_chars or config.RAG_CHUNK_CHARS
    overlap = overlap or config.RAG_CHUNK_OVERLAP
    if not text or not text.strip():
        return []

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.replace("\r\n", "\n"))]
    units: list[tuple[str, str, list[str]]] = []
    heading_path: list[str] = []

    for block in blocks:
        if not block:
            continue

        lines = block.splitlines()
        heading = _HEADING_RE.match(lines[0].strip())
        if heading:
            level = len(heading.group(1))
            heading_path = heading_path[: level - 1] + [heading.group(2).strip()]
            block = "\n".join(lines[1:]).strip()
            if not block:
                continue

        for position, (unit, separator) in enumerate(_units(block, max_chars)):
            if position == 0 and units:
                # Keep paragraph breaks when blocks are glued back together.
                separator = "\n"
            units.append((unit, separator, list(heading_path)))

    chunks: list[str] = []
    current = ""
    current_path: list[str] = []

    for unit, separator, path in units:
        if not current:
            current = unit
            current_path = path
            continue

        if path != current_path:
            # A new heading means a new section: don't blur them in one chunk.
            chunks.append(_render(current, current_path))
            current = unit
            current_path = path
            continue

        candidate = f"{current}{separator or ' '}{unit}"
        limit = max_chars
        if path:
            limit = max(max_chars - len(" > ".join(path)) - 1, 1)
        if len(candidate) <= limit:
            current = candidate
            continue

        chunks.append(_render(current, current_path))
        tail = _tail(current, overlap)
        current = f"{tail}\n{unit}" if tail else unit
        current_path = path

    if current:
        chunks.append(_render(current, current_path))

    return chunks
