"""RAG pipeline facade.

The implementation is split by responsibility so each file stays readable:

- ``rag.progress``  live indexing stage + human-readable log
- ``rag.sources``   read knowledge files and cached web pages into documents
- ``rag.index``     chunk, embed, persist, load and rebuild the vector index
- ``rag.search``    hybrid retrieval (dense + BM25 + rerank)

Use ``from rag import search, stats, rebuild, warm`` or import from here.
"""

from rag.index import UPDATING_MESSAGE, ensure_index, rebuild, stats, unavailable, warm
from rag.progress import begin, log_event, progress
from rag.search import search
from rag.sources import load_documents as _documents

__all__ = [
    "UPDATING_MESSAGE",
    "begin",
    "ensure_index",
    "log_event",
    "progress",
    "rebuild",
    "search",
    "stats",
    "unavailable",
    "warm",
    "_documents",
]
