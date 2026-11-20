# LiveliBot

LiveliBot answers questions about Philippine business permits, taxes, and
livelihood programs using only the documents in its knowledge library, citing
the sources it used.

- `client/` — React + Vite chat UI: one page, streamed answers, collapsible sources.
- `server/` — Flask API with a local RAG pipeline: fastembed embeddings, hybrid
  retrieval (dense + BM25), Gemma through Google's Gemini API, SSE streaming.

## Requirements

- Python 3.10+ (tested on 3.10.11) — server packages are pinned in
  `server/requirements.txt`: Flask, fastembed, numpy, pypdf, python-dotenv,
  requests, trafilatura.
- Node.js 20+ and pnpm (the client uses `pnpm-lock.yaml`; `npm install` also
  works) — React 19, Vite, Tailwind, react-router, ky, radix-ui.
- A Google Gemini API key: used for answers and reranking. Embeddings run
  locally, no key needed for those.
- Internet on the first ingest: the fastembed profile downloads a ~90 MB MiniLM
  ONNX model into `server/.cache/models` (kept out of `%TEMP%`, which gets wiped).

## Run

### 1. Server setup

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # then set GEMINI_API_KEY
```

`.env` is gitignored and only `server/config.py` reads it.

### 2. Add knowledge

A fresh checkout has an empty library (`server/knowledge/`). Add sources in
either way, then build the index:

- copy `.md`, `.txt`, or `.pdf` files into `server/knowledge/`, or
- add web pages from the client's **Library** page (or append to
  `server/knowledge/urls.txt`).

```powershell
python ingest.py               # fetch URL sources, then embed everything
python ingest.py --local-only  # reuse cached pages, no network fetch
```

Indexing prints progress; embeddings are local (roughly 80 chunks/s). Delete
`server/.index/` to force a cold rebuild.

### 3. Run the API

```powershell
python app.py   # http://127.0.0.1:5001
```

Health check: `GET /api/health`. Startup loads the index and model in a
background thread; the first question waits for warmup.

### 4. Run the UI

In a separate terminal:

```powershell
cd client
pnpm install          # or npm install
pnpm dev              # http://localhost:5173, proxies /api to 127.0.0.1:5001
pnpm dev --port 5199  # if 5173 is already taken
```

`pnpm build` produces `client/dist` for static hosting. The Flask server in
this setup does not serve it; the Vite dev server is the normal way to run the
UI locally.

## Configuration

Copy `server/.env.example` to `server/.env`. The most used variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | Required for answers and reranking. |
| `GEMINI_MODEL` | `gemma-4-26b-a4b-it` | Gemini model id. |
| `PORT` | `5001` | Flask port (the Vite proxy expects 5001). |
| `CLIENT_ORIGIN` | `*` | `Access-Control-Allow-Origin` for direct API calls. |
| `DEBUG` | `0` | `1` enables Flask debug; the reloader leaks processes on Windows. |
| `EMBED_MODEL` | multilingual MiniLM | fastembed model name. |
| `RAG_RERANK` | `1` | LLM rerank of candidates (`0` to disable). |

Full table, API routes, and the pipeline internals: [server/README.md](server/README.md).

## Tests

No pytest dependency; run the scripts directly:

```powershell
cd server
.\.venv\Scripts\python.exe tests\test_store.py
.\.venv\Scripts\python.exe tests\test_keyword.py
.\.venv\Scripts\python.exe tests\test_chunking.py
.\.venv\Scripts\python.exe tests\test_safety.py
.\.venv\Scripts\python.exe tests\test_intent.py
```

## Troubleshooting

- **"not in my documents" for everything** — the index is empty or stale: add
  sources and run `python ingest.py`.
- **Port already in use** — another app owns 5001 or 5173. Stop it, change
  `PORT` in `.env`, or run the client on another port; the proxy target stays
  5001.
- **`ImportError: lxml.html.clean`** — lxml 6 moved that module out; run
  `pip install lxml_html_clean`.
- **429 or "model busy" from Gemini** — the free tier is per minute; wait and
  retry, or disable reranking with `RAG_RERANK=0`.
