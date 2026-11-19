import math
import re
import unicodedata
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    # English
    "a",
    "about",
    "after",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "before",
    "being",
    "between",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "me",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "should",
    "so",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
    "would",
    "you",
    "your",
    # Tagalog
    "ako",
    "ang",
    "ay",
    "at",
    "ba",
    "dahil",
    "din",
    "ito",
    "ka",
    "kailangan",
    "kung",
    "ko",
    "kung",
    "lang",
    "mga",
    "mo",
    "na",
    "ng",
    "nito",
    "o",
    "para",
    "po",
    "sa",
    "saan",
    "si",
    "sila",
    "sya",
    "tayo",
    "yung",
}


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    tokens = []
    for token in _TOKEN_RE.findall(normalized):
        if token in _STOPWORDS:
            continue
        if len(token) == 1 and not token.isdigit():
            continue
        tokens.append(token)
    return tokens


class BM25:
    """Small Okapi BM25 implementation; documents are token lists."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.tokens = [tokenize(document) for document in documents]
        self.count = len(self.tokens)
        self.average_length = (
            sum(len(tokens) for tokens in self.tokens) / self.count if self.count else 0.0
        )
        self.frequencies = [Counter(tokens) for tokens in self.tokens]

        document_frequency: Counter[str] = Counter()
        for tokens in self.tokens:
            document_frequency.update(set(tokens))
        self.idf = {
            token: math.log(1 + (self.count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in document_frequency.items()
        }

    def scores(self, query: str) -> list[float]:
        query_tokens = tokenize(query)
        if not query_tokens or not self.count:
            return [0.0] * self.count

        scores = [0.0] * self.count
        for token in query_tokens:
            idf = self.idf.get(token)
            if idf is None:
                continue
            for index, frequency in enumerate(self.frequencies):
                term_frequency = frequency.get(token, 0)
                if not term_frequency:
                    continue
                length = len(self.tokens[index])
                denominator = term_frequency + self.k1 * (
                    1 - self.b + self.b * length / self.average_length
                )
                scores[index] += (
                    idf * term_frequency * (self.k1 + 1) / denominator
                )
        return scores


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Fuse ranked id lists: score = sum(1 / (k + rank)) across rankings."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, index in enumerate(ranking):
            fused[index] = fused.get(index, 0.0) + 1.0 / (k + rank + 1)
    return fused
