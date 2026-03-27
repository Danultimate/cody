CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS repositories (
    id          SERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    branch      TEXT NOT NULL DEFAULT 'main',
    commit_sha  TEXT,
    chunk_count INTEGER DEFAULT 0,
    file_count  INTEGER DEFAULT 0,
    indexed_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    repo_id     INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_path   TEXT NOT NULL,
    language    TEXT,
    chunk_type  TEXT,        -- 'function' | 'class' | 'method' | 'window'
    name        TEXT,        -- symbol name if AST-extracted
    start_line  INTEGER,
    end_line    INTEGER,
    content     TEXT NOT NULL,
    token_count INTEGER,
    embedding   vector(1024),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS chunks_repo_id_idx ON chunks (repo_id);
CREATE INDEX IF NOT EXISTS chunks_repo_file_idx ON chunks (repo_id, file_path);

CREATE TABLE IF NOT EXISTS query_log (
    id              SERIAL PRIMARY KEY,
    repo_id         INTEGER REFERENCES repositories(id),
    question        TEXT NOT NULL,
    answer          TEXT,
    top_chunks      JSONB,
    latency_ms      INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Keep updated_at current on repositories
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER repositories_updated_at
    BEFORE UPDATE ON repositories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
