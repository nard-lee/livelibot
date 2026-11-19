# RAG Architecture

How a question becomes a cited answer in this app. Everything below reflects the
code in `server/`; module paths are relative to `server/`.

```
INGEST (startup / upload / url change / delete)
  knowledge/*.md|*.txt|*.pdf          .cache/urls/*.json
            │                                │
            └───────────┬────────────────────┘
                        ▼
             rag/sources.py  (read, strip, sanitize)
                        ▼
             rag/chunking.py (heading-aware chunks)
                        ▼
             rag/embedder.py (Gemini batchEmbedContents)
                        ▼
             .index/vectors.npy + .index/index.json
                  (+ in-memory BM25 over chunks)

QUERY
  question ──▶ embed (query) ──▶ dense cosine ─┐
           └─▶ tokenize ─▶ BM25 ───────┤
                                        ▼
                          reciprocal rank fusion (top 20)
                                        ▼
                          dedupe (cosine ≥ 0.95)
                                        ▼
                          LLM rerank (Gemini) → top 5
                                        ▼
                          max 3 chunks per source
                                        ▼
             numbered context ──▶ Gemini generation ──▶ cited sources
```

---

## 1. Sources

Two families feed the index (`rag/sources.py`):

1. **Files** in `knowledge/`: `.md`, `.markdown`, `.txt`, `.pdf`
   (`urls.txt` is configuration, not content).
2. **Cached web pages** in `.cache/urls/*.json`, each produced from a URL listed
   in `knowledge/urls.txt`.

`rag/urls.py` owns the URL list and cache:

- `normalize_url` lowercases scheme/host, strips trailing slash and fragment,
  requires a domain.
- `cache_url` fetches via `rag/loaders.py` and writes
  `.cache/urls/<sha1(url)[:16]>.json` with `url`, `title`, `text`, `fetched_at`.
- `remove_url` / `remove_cache` also prune duplicate cache files that point at
  the same page under a different URL spelling.
- `_web_entries` in `sources.py` dedupes caches by URL again before indexing.

`rag/loaders.py`:

- Web pages: `requests` with a 20 s timeout and a custom user agent, then
  `trafilatura` JSON extraction (`favor_precision`, no links/comments).
- PDFs: `pypdf` text extraction; empty or unreadable files raise a readable
  `ValueError` and are skipped, never fatal.
- `clean_title` collapses whitespace and un-shouts ALL-CAPS titles.

In a text/markdown file, a **leading bare URL on line 1** is treated as the
document's source link and removed from the content.

### Sanitizing (`rag/safety.py`)

All source text passes through `sanitize()` before chunking:

- HTML comments are removed.
- Lines matching prompt-injection patterns are dropped (`ignore previous
  instructions`, `disregard prior rules`, `forget your instructions`,
  `you are now a …`, leading `system:` / `assistant:`, `<|…|>`, `[inst]`,
  `### system|instructions`).
- Runs of 3+ newlines collapse to 2.

This is best-effort at ingest time. The real defense is in the prompt: retrieved
text is wrapped in `<context>…</context>` and the model is told it is untrusted
reference material, never instructions.

PDF extraction is cached in `.cache/extracted/<name>.<mtime_ns>.<size>.json`
and invalidated by mtime/size, so a rebuild does not re-parse unchanged PDFs.

---

## 2. Chunking (`rag/chunking.py`)

`chunk_text(text)` produces chunks of about `RAG_CHUNK_CHARS` (default 800)
with `RAG_CHUNK_OVERLAP` (default 120) characters of overlap.

- Text is split into blocks on blank lines.
- A leading markdown heading (`#{1,6}`) in a block updates a **heading path**
  (`level`-aware, e.g. `"Permits > Barangay Clearance"`) and is prepended to
  every chunk rendered under it as `"Path > To > Section\n<text>"`.
- Blocks are split into units: lines stay newline-separated (bullet lists
  survive), lines are split on sentence punctuation `[.!?;:]`, and oversized
  sentences are hard-wrapped on word boundaries.
- Units accumulate until adding the next would exceed the limit (minus the
  breadcrumb length). A heading change always forces a new chunk.
- The next chunk starts with the tail of the previous one (word-aligned) for
  overlap, so a fact cut at a boundary remains retrievable.

---

## 3. Embedding (`rag/embedder.py`)

- Model: `gemini-embedding-001` (`EMBED_MODEL`), called through the Gemini
  `batchEmbedContents` endpoint — no local model, no ONNX runtime, so process
  memory stays small enough for the Render free tier.
- `embed(texts)` sends batches of 32. Indexed chunks use
  `taskType = RETRIEVAL_DOCUMENT`; the live question uses `RETRIEVAL_QUERY`
  (asymmetric embeddings, which is what the task types are for).
- 429/500/503 are retried with backoff (5 s, 20 s, 60 s), extended to the
  provider's `retryDelay` / `Retry-After` when present — the free-tier
  embedding quota is per minute, so short retries just burn the window. After
  the last attempt the error names the status and the provider message. Other
  statuses fail immediately; a missing key raises `LLMConfigError` before any
  request is sent.
- The embedder returns raw floats; `rag/index.py` L2-normalises them, so cosine
  similarity is a plain dot product.

---

## 4. Index build and persistence (`rag/index.py`)

State is a module singleton guarded by a `threading.RLock`: items, normalized
vector matrix, BM25, embedding metadata, fingerprint, build time.

### Fingerprint

The fingerprint is a **component dict**, hashed with `sha256` over canonical
JSON and stored next to its components in `index.json`:

- `INDEX_VERSION` (currently `9`; bump when chunking/format changes),
- `EMBED_MODEL`,
- `RAG_CHUNK_CHARS` and `RAG_CHUNK_OVERLAP`,
- `files`: one `sha256(content)` per source, keyed by relative path
  (`knowledge/x.md`, `.cache/urls/<id>.json`). Text files hash their UTF-8
  content with `\r\n` normalised to `\n`, PDFs hash their bytes, and cached web
  pages hash their extracted `text` — never `fetched_at`, title, `mtime` or
  size.

`ensure_index()`:

1. Recompute the components and fingerprint; if it matches the in-memory one,
   return.
2. Try loading `.index/` from disk (fingerprint, version and component dict
   must match; vector row count must match item count).
3. On mismatch, log **one** line naming the differing components (for example
   `files changed: knowledge/x.md; settings changed: EMBED_MODEL`) and serve
   "The knowledge base is being updated". Startup never rebuilds and never
   calls the embedding API.
4. Only an explicit rebuild (`python ingest.py`, or an admin upload/delete with
   `force=True`) reads sources → chunks → embeds → saves.

`python fingerprint_check.py [--json]` prints the current components plus the
committed fingerprint, so a local checkout and Render can be compared.

### Vector reuse

On rebuild, chunks whose **exact text** is already in the current in-memory
index reuse their vectors; only new text is embedded, in batches of 32 with
`EMBED_DELAY_SECONDS` between batches. Each finished batch is persisted to
`.index/partial.npz` before the next one starts, so an interrupted ingest keeps
its progress and the next run resumes from that point instead of re-embedding.

### Persistence

- `.index/index.json` and `.index/vectors.npy` are committed to git, so a fresh
  clone loads them without calling the embedding API.
- `.index/index.json`: metadata, the `fingerprint_components` dict, the
  `fingerprint` hash, plus all chunk items (`source_id`, `title`, `url`,
  `content`) and a UTC `built_at`.
- `.index/vectors.npy`: normalized `float32` matrix.
- `.index/partial.npz`: git-ignored progress file for interrupted ingests.
- Writes go to pid-suffixed temp files and `os.replace` them into place, so the
  server and `ingest.py` can write concurrently without corrupting the index.

### Warmup (`warm()`)

At startup (daemon thread, `WARMUP=1`): `ensure_index()`, then parse documents
once so PDF extraction is cached before the first user question. No model is
loaded — embeddings are remote calls. A matching committed index is loaded, so
no embedding request is made; any mismatch yields the "updating" message and a
one-line component diff instead of a rebuild.

---

## 5. Retrieval (`rag/search.py`, `rag/keyword.py`)

`search(question, k=RAG_TOP_K, min_score=RAG_MIN_SCORE)` runs five stages.

### 5.1 Dense and sparse scores

- **Dense**: normalized query vector dotted with the normalized chunk matrix.
- **BM25** (`rag/keyword.py`): Okapi BM25 over chunk token lists, `k1=1.5`,
  `b=0.75`; IDF is `ln(1 + (N - df + 0.5) / (df + 0.5))`.
  Tokenization: NFKD casefold, diacritic stripping, `[a-z0-9]+`, English +
  Tagalog stopwords, single non-digit characters dropped. This is what catches
  exact terms like `RA 11032` or `Barangay`.

### 5.2 Reciprocal rank fusion

Each list contributes its top `RAG_FUSION_DEPTH` (50) entries (BM25 entries must
score > 0). Fusion score:

```
score(d) = Σ  1 / (k + rank_i(d) + 1)     k = RAG_RRF_K = 60
          i ∈ {dense, bm25}
```

### 5.3 Candidate gate

Candidates are taken in fused order until `RAG_CANDIDATES` (20). A candidate is
skipped only when it is weak on **both** channels:

- `dense < RAG_MIN_SCORE` (0.30) **and** `bm25 < RAG_BM25_MIN` (1.5).

### 5.4 Dedupe

Walk candidates in order; drop any candidate whose maximum cosine similarity to
an already-kept candidate is `≥ RAG_DEDUPE_SIM` (0.95). This removes repeated
boilerplate and overlapping chunk boundaries.

### 5.5 Rerank

`rag/rerank.py` asks the generator model to order the top
`RAG_RERANK_CANDIDATES` (20) passages (first 300 chars each) by relevance and
returns a JSON array. Temperature 0, `max_tokens=RAG_RERANK_MAX_TOKENS` (600).
Skipped indices are appended rather than lost. Any failure logs a warning and
keeps fusion order. Disabled with `RAG_RERANK=0`, and skipped automatically when
there are no more than `k` hits.

> Note: `RAG_RERANK_MODEL` and `RAG_RERANK_EFFORT` are legacy knobs. The Gemini
> client always uses `GEMINI_MODEL`; those values are passed through but ignored.

### 5.6 Final cut

`_cap_per_source` keeps at most `RAG_MAX_PER_SOURCE` (3) chunks per source and
stops at `k` (default 5). Each hit carries `score` = dense cosine (the UI/debug
score; the final order is rerank order).

---

## 6. Chat integration (`chat/service.py`)

1. **Intent** — `is_conversational(message)` short-circuits greetings, thanks,
   reactions, etc. to a conversational prompt with a topic menu, no retrieval.
2. **Retrieval** — `_retrieve` runs `search(message)`. If the message is a
   short follow-up (`≤ 10` words) and history has a prior non-conversational
   question, it also searches **that previous question** (`k = TOP_K - 2`,
   minimum 2) and merges results by `(source_id, content)`, keeping the higher
   score and cutting back to `TOP_K`.
3. **No hits** — falls back to the conversational prompt rather than refusing.
4. **Context** — sources are numbered per *document* (key = `url` or
   `source_id`); each hit is rendered as:

   ```
   [1] (Document Title)
   <chunk text>
   ```

   and the whole block is placed between `<context>` and `</context>`.
5. **Generation** — system prompt enforces: use only the context, cite with
   `[n]`, exact refusal sentence when the context is irrelevant, answer the
   covered part and note gaps otherwise, reply in the question's language
   (English/Tagalog), ignore instructions inside the context.
6. **Refusal swap** — if the model produces the canonical
   `I don't have that information in my documents.` reply, the app replaces it
   with a conversational answer that offers the topic menu. In streaming mode
   the first sentence is peeked at before anything is sent, so a refusal is
   never shown to the user.
7. **Citations** — `_final_sources` keeps only documents whose numbers actually
   appear in the reply (`[n]` or `【n】`). If the answer cites nothing, the
   source list is hidden. Snippets are whitespace-collapsed and trimmed to
   `RAG_SNIPPET_CHARS` (200).
8. **Streaming** — SSE events: `sources` (numbered sources, sent before
   generation), then `token` deltas, then `done` with the final reply and the
   filtered source list; errors arrive as an `error` event.

No user question or answer is logged to disk; logs contain only lengths,
scores, source ids, and short truncations.

---

## 7. Progress and API surface

`rag/progress.py` publishes a small state machine plus a rolling 120-entry log,
polled by the client during ingest/rebuild:

```
idle → warming | uploading | fetching | removing → reading → chunking
     → embedding → saving → done | error
```

`GET /api/index/progress` returns stage, detail, done/total, percent, elapsed,
and the log. `rag/store.py` is the thin facade used by the rest of the app
(`ensure_index`, `rebuild`, `stats`, `search`, progress helpers, document
loader).

---

## 8. File map

| File | Responsibility |
| --- | --- |
| `rag/store.py` | Public facade re-exporting index/search/progress/documents |
| `rag/__init__.py` | Package exports (`chunk_text`, `embed`, `search`, `stats`, …) |
| `rag/sources.py` | Enumerate sources, strip metadata URL, sanitize, PDF text cache |
| `rag/loaders.py` | File/PDF/URL loading, trafilatura extraction, title cleanup |
| `rag/safety.py` | HTML-comment/injection stripping, `<context>` markers |
| `rag/chunking.py` | Heading-aware, paragraph/sentence chunking with overlap |
| `rag/embedder.py` | Gemini batch embedding client (document + query task types) |
| `rag/keyword.py` | Tokenizer, BM25, reciprocal rank fusion |
| `rag/index.py` | Fingerprint, build, vector reuse, atomic persistence, warmup |
| `rag/search.py` | Hybrid retrieval: fuse → gate → dedupe → rerank → cap |
| `rag/rerank.py` | LLM reordering of fused candidates |
| `rag/urls.py` | `urls.txt` management and URL response cache |
| `rag/progress.py` | Stage/progress state and rolling ingest log |
| `chat/service.py` | Intent, retrieval, prompts, citations, streaming |

---

## 9. Configuration (`config.py`, env-overridable)

| Setting | Default | Meaning |
| --- | --- | --- |
| `EMBED_MODEL` | `gemini-embedding-001` | Embedding model |
| `RAG_TOP_K` | `5` | Chunks passed to the model |
| `RAG_MIN_SCORE` | `0.30` | Dense gate (paired with BM25 gate) |
| `RAG_CHUNK_CHARS` | `800` | Max chunk size |
| `RAG_CHUNK_OVERLAP` | `120` | Overlap between chunks |
| `RAG_SNIPPET_CHARS` | `200` | Source snippet length in the UI |
| `RAG_CANDIDATES` | `20` | Fused candidates entering dedupe/rerank |
| `RAG_FUSION_DEPTH` | `50` | Per-list depth used in RRF |
| `RAG_RRF_K` | `60` | RRF constant |
| `RAG_BM25_MIN` | `1.5` | BM25 gate |
| `RAG_MAX_PER_SOURCE` | `3` | Max chunks per document in the answer |
| `RAG_DEDUPE_SIM` | `0.95` | Near-duplicate cosine threshold |
| `RAG_RERANK` | `1` | Enable LLM rerank |
| `RAG_RERANK_CANDIDATES` | `20` | Passages shown to the reranker |
| `RAG_RERANK_MAX_TOKENS` | `600` | Reranker output budget |
| `INDEX_VERSION` | `9` | Bump to invalidate on-disk indexes |
| `WARMUP` | `1` | Warm index + model at startup |
| `INGEST_FETCH_URLS` | `1` | Fetch `urls.txt`; `0` reuses `.cache/urls` |
| `EMBED_DELAY_SECONDS` | `1` | Pause between embedding batches |

Paths default to `server/knowledge`, `server/.cache`, `server/.cache/urls`,
`server/.index`.

---

## 10. Design invariants and gotchas

- **Vectors are always L2-normalized**; never persist unnormalized rows, or
  cosine becomes a magnitude contest.
- **The fingerprint is the only staleness signal.** It is stored as a component
  dict so a mismatch names the exact settings or files that differ; bump
  `INDEX_VERSION` for chunking/format changes. Content hashing (SHA-256) means
  same-size edits and line-ending changes are handled correctly, and the index
  built on one machine matches a clone on another.
- **The index is a build artifact committed to git.** Rebuild locally with
  `python ingest.py`, then `git add .index .cache/urls && git commit`. Startup
  never rebuilds or embeds; a mismatch serves an "updating" message and logs one
  component diff line. Use `fingerprint_check.py` to compare machines.
- **Writes are atomic** (`os.replace` from a pid-suffixed temp file) because the
  API server and `ingest.py` can build concurrently. Interrupted ingests resume
  from the atomically written `.index/partial.npz`.
- **The per-source cap runs last**, after rerank, so one long document cannot
  monopolize the context window.
- **Dense score is informational after fusion.** Displayed `score` is cosine,
  but ordering after rerank is the reranker's.
- **Citations are filtered, not assumed.** No `[n]` in the answer means no
  source list; the UI only shows what the model actually used.
- **Retrieved text is data, not instructions.** Both sanitizing at ingest and
  the `<context>` wrapper + system rule protect against injection.
- **Gemma needs minimal thinking.** The Gemini client sends
  `thinkingConfig.thinkingLevel = "minimal"`; without it Gemma can spend the
  whole output budget on hidden `thought` parts and return an empty answer.
- **One provider.** `LLM_PROVIDER` accepts only `gemini`; anything else raises
  `Unknown LLM_PROVIDER`. Groq and Ollama code has been removed.
