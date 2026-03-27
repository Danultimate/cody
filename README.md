# Codebase Intelligence Engine

A RAG-powered developer tool that indexes GitHub repositories and answers natural language questions about codebases with cited file paths.

## Stack

| Layer | Technology |
|---|---|
| Embeddings | Voyage AI `voyage-code-3` (1024-dim) |
| Vector store | pgvector on Postgres 16 |
| Answer synthesis | Anthropic Claude claude-sonnet-4-6 |
| Chunking | Tree-sitter AST-aware |
| API | Python 3.12 + FastAPI |
| Frontend | React 18 + Vite |
| Orchestration | Docker Compose |

## Quick start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY and VOYAGE_API_KEY

# 2. Start the database, API, and frontend
docker compose up db api frontend

# 3. Index a repository (runs as a one-shot CLI container)
docker compose --profile ingest run ingestion --repo https://github.com/org/repo

# Optional: specify a branch
docker compose --profile ingest run ingestion --repo https://github.com/org/repo --branch develop

# 4. Open the UI
open http://localhost:5173
```

## How it works

### Ingestion pipeline

1. **Clone / pull** — GitPython clones the repo to `/tmp/repos/<name>` (idempotent: `git pull` on subsequent runs).
2. **Walk files** — skips `.git`, `node_modules`, `vendor`, `__pycache__`, `dist`, `build`, `.next`, binaries, files > 500 KB.
3. **AST chunking** — Tree-sitter extracts functions, classes, and methods. Files with no AST hits fall back to 60-line sliding windows with 10-line overlap. Chunks < 5 lines are dropped; chunks > 150 lines are split into 100-line sub-chunks with 15-line overlap.
4. **Embed** — Voyage AI `voyage-code-3` in batches of 128 with a 1 s inter-batch sleep.
5. **Upsert** — clean re-index per file: delete existing chunks then bulk insert with embeddings. The HNSW index (created by `db/init.sql`) handles approximate nearest-neighbour search.

### Query API (`POST /query`)

1. Embed the question with `voyage-code-3` (`input_type="query"`).
2. Cosine similarity search via pgvector's `<=>` operator; return top-8 chunks with similarity > 0.3.
3. Build a context block of retrieved chunks with file paths and line numbers.
4. Call Claude claude-sonnet-4-6 with a system prompt that instructs it to cite every claim.
5. Return `{ answer, chunks, latency_ms }`.

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/repos` | List all indexed repositories |
| `POST` | `/query` | Ask a question; body: `{ question, repo_id, top_k? }` |

## Project structure

```
codebase-intel/
├── docker-compose.yml
├── .env.example
├── db/
│   └── init.sql            pgvector schema
├── ingestion/
│   ├── main.py             Typer CLI entry point
│   ├── github_loader.py    Clone/pull + file walker
│   ├── ast_chunker.py      Tree-sitter chunking
│   ├── embedder.py         Voyage AI batched embedding
│   └── db.py               psycopg2 upsert helpers
├── api/
│   ├── main.py             FastAPI app + CORS
│   ├── db.py               Async SQLAlchemy engine
│   ├── rag.py              Embed → search → Claude pipeline
│   └── routes/
│       ├── repos.py        GET /repos
│       └── query.py        POST /query
└── frontend/
    └── src/
        ├── App.jsx
        └── components/
            ├── QueryPanel.jsx
            ├── AnswerPanel.jsx
            └── RepoTree.jsx
```

## Environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `VOYAGE_API_KEY` | Voyage AI API key |
| `POSTGRES_USER` | Postgres username (default: `cody`) |
| `POSTGRES_PASSWORD` | Postgres password (default: `cody`) |
| `POSTGRES_DB` | Postgres database name (default: `cody`) |
