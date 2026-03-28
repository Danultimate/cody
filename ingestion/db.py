import psycopg2
from psycopg2.extras import execute_values


def get_connection(database_url: str):
    return psycopg2.connect(database_url)


def get_repo_by_url(conn, url: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, commit_sha FROM repositories WHERE url = %s",
            (url,),
        )
        row = cur.fetchone()
    if row:
        return {"id": row[0], "commit_sha": row[1]}
    return None


def delete_chunks_for_files(conn, repo_id: int, file_paths: list[str]) -> None:
    if not file_paths:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM chunks WHERE repo_id = %s AND file_path = ANY(%s)",
            (repo_id, file_paths),
        )
    conn.commit()


def upsert_repository(conn, url: str, name: str, branch: str, commit_sha: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO repositories (url, name, branch, commit_sha, indexed_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (url) DO UPDATE
                SET name       = EXCLUDED.name,
                    branch     = EXCLUDED.branch,
                    commit_sha = EXCLUDED.commit_sha,
                    indexed_at = NOW()
            RETURNING id
            """,
            (url, name, branch, commit_sha),
        )
        repo_id = cur.fetchone()[0]
    conn.commit()
    return repo_id


def upsert_chunks(
    conn,
    repo_id: int,
    file_path: str,
    language: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    with conn.cursor() as cur:
        # Clean re-index: remove existing chunks for this file
        cur.execute(
            "DELETE FROM chunks WHERE repo_id = %s AND file_path = %s",
            (repo_id, file_path),
        )

        if not chunks:
            conn.commit()
            return

        rows = [
            (
                repo_id,
                file_path,
                language,
                chunk["chunk_type"],
                chunk.get("name") or None,
                chunk["start_line"],
                chunk["end_line"],
                chunk["content"],
                chunk["token_count"],
                embeddings[i],
            )
            for i, chunk in enumerate(chunks)
        ]

        execute_values(
            cur,
            """
            INSERT INTO chunks
                (repo_id, file_path, language, chunk_type, name,
                 start_line, end_line, content, token_count, embedding)
            VALUES %s
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)",
        )
    conn.commit()


def update_repo_stats(conn, repo_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE repositories
            SET
                chunk_count = (SELECT COUNT(*) FROM chunks WHERE repo_id = %s),
                file_count  = (SELECT COUNT(DISTINCT file_path) FROM chunks WHERE repo_id = %s)
            WHERE id = %s
            """,
            (repo_id, repo_id, repo_id),
        )
    conn.commit()
