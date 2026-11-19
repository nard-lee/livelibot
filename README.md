# LiveliBot

LiveliBot answers questions about Philippine business permits, taxes, and
livelihood programs using only the documents in its knowledge library, citing
the sources it used.

- `client/` — React + Vite chat UI: one page, streamed answers, collapsible
  sources.
- `server/` — Flask API with a local RAG pipeline: hybrid retrieval (dense +
  BM25), Gemma through Google's Gemini API, SSE streaming.

## Run it

```powershell
# API
cd server
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # then set GEMINI_API_KEY
python ingest.py
python app.py             # http://127.0.0.1:5001

# UI (separate terminal)
cd client
pnpm install
pnpm dev --port 5199      # proxies /api to port 5001
```

After changing the knowledge base, rebuild and commit the index so deploys never
call the embedding API:

```powershell
cd server
python ingest.py
git add .index .cache/urls
git commit -m "Rebuild knowledge index"
```

Server details and API routes: [server/README.md](server/README.md).
