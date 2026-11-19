import io
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
import trafilatura

USER_AGENT = "Mozilla/5.0 (compatible; knowledge-ingest/1.0)"
TIMEOUT = 20


def clean_title(title: str) -> str:
    """Normalise page titles: collapse whitespace and un-shout ALL CAPS titles."""
    title = " ".join(title.split())
    if not title or not title.isupper():
        return title
    return " ".join(
        word if word.isdigit() else word.capitalize() for word in title.split(" ")
    )


def pretty_url_title(url: str) -> str:
    """Human-readable fallback title from a URL, e.g. a PDF file name."""
    stem = Path(urlparse(url).path).stem
    if not stem:
        return url
    return re.sub(r"[-_]+", " ", stem).strip() or url


def extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ValueError("PDF support requires pypdf") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        raise ValueError(f"could not read PDF: {exc}") from exc

    text = "\n\n".join(page for page in pages if page).strip()
    if not text:
        raise ValueError("no extractable text in PDF")
    return text


def load_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return extract_pdf(path.read_bytes())
    return path.read_text(encoding="utf-8")


def load_url(url: str) -> tuple[str, str]:
    """Fetch a URL and return (title, extracted_text).

    Raises ValueError with a readable reason when the page cannot be used, so
    callers can report and skip it instead of crashing the ingest.
    """
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"could not download {url}: {exc}") from exc

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return pretty_url_title(url), extract_pdf(response.content)

    # Pass raw bytes: requests guesses Latin-1 for text/* without a charset,
    # which turns UTF-8 like ’ into "â€™". trafilatura detects the encoding.
    extracted = trafilatura.extract(
        response.content,
        url=url,
        output_format="json",
        with_metadata=True,
        include_links=False,
        include_comments=False,
        favor_precision=True,
    )
    if not extracted:
        raise ValueError(f"no readable text at {url}")

    try:
        data = json.loads(extracted)
    except json.JSONDecodeError as exc:
        raise ValueError(f"unreadable extraction for {url}") from exc

    text = (data.get("text") or "").strip()
    if not text:
        raise ValueError(f"no readable text at {url}")

    title = clean_title(data.get("title") or "") or url
    return title, text
