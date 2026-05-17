-- Add full-text search column for hybrid BM25 + vector retrieval.
-- Run this once on existing databases; fresh installs get it via init.sql.

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;

CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING GIN(tsv);
