import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR") or BASE_DIR / "knowledge")
CACHE_DIR = Path(os.getenv("CACHE_DIR") or BASE_DIR / ".cache")
URL_CACHE_DIR = CACHE_DIR / "urls"
INDEX_DIR = Path(os.getenv("INDEX_DIR") or BASE_DIR / ".index")

FIELD_NAME = os.getenv("FIELD_NAME", "general topics")
PORT = int(os.getenv("PORT", "5001"))

# Public hosting: the API is read-only unless admin routes are explicitly enabled.
ADMIN_ENABLED = os.getenv("ADMIN_ENABLED", "0").lower() in {"1", "true", "yes"}

# Only this origin may call the API cross-origin; empty means same-origin only.
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "").strip()

PERSONA = os.getenv("PERSONA", "").strip()
AUDIENCE = os.getenv("AUDIENCE", "").strip()
TONE = os.getenv("TONE", "").strip()
EXTRA_RULES = os.getenv("EXTRA_RULES", "").strip()

TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
HISTORY_MESSAGES = int(os.getenv("HISTORY_MESSAGES", "6"))

# LLM provider: "gemini" (Gemma via Google's native API) is the only supported
# value. Only this module reads the environment.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-26b-a4b-it").strip()

# Retrieval
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.30"))
RAG_CHUNK_CHARS = int(os.getenv("RAG_CHUNK_CHARS", "800"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
RAG_SNIPPET_CHARS = int(os.getenv("RAG_SNIPPET_CHARS", "200"))
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "500"))

# Hybrid retrieval: dense embeddings fused with BM25 through reciprocal rank fusion.
RAG_CANDIDATES = int(os.getenv("RAG_CANDIDATES", "20"))
RAG_FUSION_DEPTH = int(os.getenv("RAG_FUSION_DEPTH", "50"))
RAG_RRF_K = int(os.getenv("RAG_RRF_K", "60"))
RAG_BM25_MIN = float(os.getenv("RAG_BM25_MIN", "1.5"))
RAG_MAX_PER_SOURCE = int(os.getenv("RAG_MAX_PER_SOURCE", "3"))
RAG_DEDUPE_SIM = float(os.getenv("RAG_DEDUPE_SIM", "0.95"))

# Optional LLM rerank of the fused candidates before the final cut.
RAG_RERANK = os.getenv("RAG_RERANK", "1").lower() in {"1", "true", "yes"}
RAG_RERANK_CANDIDATES = int(os.getenv("RAG_RERANK_CANDIDATES", "20"))
RAG_RERANK_MAX_TOKENS = int(os.getenv("RAG_RERANK_MAX_TOKENS", "600"))
RAG_RERANK_MODEL = os.getenv("RAG_RERANK_MODEL", "openai/gpt-oss-20b")
RAG_RERANK_EFFORT = os.getenv("RAG_RERANK_EFFORT", "low").strip()

# Startup warmup and uploads.
WARMUP = os.getenv("WARMUP", "1").lower() in {"1", "true", "yes"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

# Ingestion: fetch knowledge/urls.txt by default; production builds reuse the
# committed .cache/urls pages so a flaky site cannot break a deploy.
INGEST_FETCH_URLS = os.getenv("INGEST_FETCH_URLS", "1").lower() in {"1", "true", "yes"}
# Pause between embedding batches so the per-minute quota is not exhausted.
EMBED_DELAY_SECONDS = float(os.getenv("EMBED_DELAY_SECONDS", "1"))

# Startup never rebuilds the index: it loads the committed one or serves an
# "updating" message. Rebuild explicitly with `python ingest.py`.

# Bump whenever the on-disk index format or chunking output changes, so stale
# indexes are rebuilt instead of silently reused.
INDEX_VERSION = 9
