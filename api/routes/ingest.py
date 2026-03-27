import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

# job store: { job_id: { status, repo, branch, log, started_at, finished_at } }
_jobs: dict[str, dict] = {}

router = APIRouter()


class IngestRequest(BaseModel):
    repo_url: str
    branch: str = "main"


@router.post("/ingest")
async def start_ingest(body: IngestRequest):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "repo_url": body.repo_url,
        "branch": body.branch,
        "log": "",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    asyncio.create_task(_run_ingest(job_id, body.repo_url, body.branch))
    return {"job_id": job_id}


@router.get("/ingest/{job_id}")
async def get_ingest_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/ingest")
async def list_ingest_jobs():
    return list(_jobs.values())


async def _run_ingest(job_id: str, repo_url: str, branch: str):
    _jobs[job_id]["status"] = "running"

    def _sync():
        # Add ingestion dir to path so imports work
        ingestion_dir = os.path.join(os.path.dirname(__file__), "..", "ingestion")
        if ingestion_dir not in sys.path:
            sys.path.insert(0, ingestion_dir)

        from github_loader import clone_or_pull, walk_files
        from ast_chunker import chunk_file
        from embedder import embed_chunks
        import db as ingestion_db
        import git as gitlib

        voyage_key = os.environ.get("VOYAGE_API_KEY", "")
        # Convert asyncpg URL to psycopg2-compatible URL
        db_url = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

        lines = []

        def log(msg: str):
            lines.append(msg)
            _jobs[job_id]["log"] = "\n".join(lines)

        try:
            log(f"Cloning/pulling {repo_url} @ {branch}…")
            repo_path = clone_or_pull(repo_url, branch)
            repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
            git_repo = gitlib.Repo(repo_path)
            commit_sha = git_repo.head.commit.hexsha
            log(f"Commit: {commit_sha[:12]}")

            log("Walking files…")
            files = walk_files(repo_path)
            log(f"Found {len(files)} code files")

            log("Chunking…")
            all_chunks = []
            file_chunk_map = []
            for file_info in files:
                try:
                    content = file_info["path"].read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                chunks = chunk_file(file_info["path"], file_info["language"], content)
                if chunks:
                    file_chunk_map.append((file_info["relative_path"], file_info["language"], chunks))
                    all_chunks.extend(chunks)
            log(f"Total chunks: {len(all_chunks)}")

            if not all_chunks:
                log("No chunks produced.")
                return {"files": 0, "chunks": 0}

            log(f"Embedding {len(all_chunks)} chunks…")
            embeddings = embed_chunks(all_chunks, voyage_key)
            total_tokens = sum(c["token_count"] for c in all_chunks)

            log("Writing to database…")
            conn = ingestion_db.get_connection(db_url)
            try:
                repo_id = ingestion_db.upsert_repository(conn, repo_url, repo_name, branch, commit_sha)
                emb_offset = 0
                for rel_path, language, chunks in file_chunk_map:
                    n = len(chunks)
                    ingestion_db.upsert_chunks(conn, repo_id, rel_path, language, chunks, embeddings[emb_offset:emb_offset + n])
                    emb_offset += n
                ingestion_db.update_repo_stats(conn, repo_id)
            finally:
                conn.close()

            log(f"Done. {len(file_chunk_map)} files, {len(all_chunks)} chunks, {total_tokens:,} tokens.")
            return {"files": len(file_chunk_map), "chunks": len(all_chunks)}

        except Exception as e:
            raise RuntimeError(str(e))

    try:
        result = await asyncio.to_thread(_sync)
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["result"] = result
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["log"] += f"\nERROR: {e}"
    finally:
        _jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
