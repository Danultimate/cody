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
    force: bool = False  # set True to force full re-index


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
    asyncio.create_task(_run_ingest(job_id, body.repo_url, body.branch, body.force))
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


async def _run_ingest(job_id: str, repo_url: str, branch: str, force: bool = False):
    _jobs[job_id]["status"] = "running"

    def _sync():
        ingestion_dir = os.path.join(os.path.dirname(__file__), "..", "ingestion")
        if ingestion_dir not in sys.path:
            sys.path.insert(0, ingestion_dir)

        import importlib.util

        def _load(name, filename):
            spec = importlib.util.spec_from_file_location(name, os.path.join(ingestion_dir, filename))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        gh_loader    = _load("github_loader", "github_loader.py")
        ast_chunker  = _load("ast_chunker",   "ast_chunker.py")
        embedder     = _load("embedder",       "embedder.py")
        ingestion_db = _load("ingestion_db",   "db.py")

        clone_or_pull      = gh_loader.clone_or_pull
        walk_files         = gh_loader.walk_files
        get_current_commit = gh_loader.get_current_commit
        get_changed_files  = gh_loader.get_changed_files
        chunk_file         = ast_chunker.chunk_file
        embed_chunks       = embedder.embed_chunks

        voyage_key = os.environ.get("VOYAGE_API_KEY", "")
        db_url = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

        lines = []

        def log(msg: str):
            lines.append(msg)
            _jobs[job_id]["log"] = "\n".join(lines)

        try:
            log(f"Cloning/pulling {repo_url} @ {branch}…")
            repo_path = clone_or_pull(repo_url, branch)
            repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
            current_commit = get_current_commit(repo_path)
            log(f"Commit: {current_commit[:12]}")

            conn = ingestion_db.get_connection(db_url)
            try:
                stored = ingestion_db.get_repo_by_url(conn, repo_url)
                repo_id = ingestion_db.upsert_repository(conn, repo_url, repo_name, branch, current_commit)

                if not force and stored and stored["commit_sha"] == current_commit:
                    log("Already up to date — no changes since last index.")
                    return {"files": 0, "chunks": 0, "mode": "skip"}

                if not force and stored and stored["commit_sha"]:
                    log(f"Detecting changes since {stored['commit_sha'][:12]}…")
                    changes = get_changed_files(repo_path, stored["commit_sha"])

                    if changes.get("full_reindex"):
                        log("Cannot diff (history rewrite?) — falling back to full re-index.")
                        mode = "full"
                    elif not changes["modified"] and not changes["deleted"]:
                        log("No file changes detected — nothing to re-index.")
                        return {"files": 0, "chunks": 0, "mode": "skip"}
                    else:
                        mode = "incremental"
                        log(f"Changed: {len(changes['modified'])} modified, {len(changes['deleted'])} deleted")
                else:
                    mode = "full"

                all_chunks = []
                file_chunk_map = []

                if mode == "full":
                    log("Full index…")
                    if stored:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM chunks WHERE repo_id = %s", (repo_id,))
                        conn.commit()
                    files_to_index = walk_files(repo_path)
                    log(f"Found {len(files_to_index)} code files")
                else:
                    affected = changes["modified"] + changes["deleted"]
                    ingestion_db.delete_chunks_for_files(conn, repo_id, affected)
                    all_files = {f["relative_path"]: f for f in walk_files(repo_path)}
                    files_to_index = [all_files[p] for p in changes["modified"] if p in all_files]
                    log(f"Re-indexing {len(files_to_index)} changed files…")

                for file_info in files_to_index:
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
                    ingestion_db.update_repo_stats(conn, repo_id)
                    log("No chunks produced.")
                    return {"files": 0, "chunks": 0, "mode": mode}

                log(f"Embedding {len(all_chunks)} chunks…")
                embeddings = embed_chunks(all_chunks, voyage_key)
                total_tokens = sum(c["token_count"] for c in all_chunks)

                log("Writing to database…")
                emb_offset = 0
                for rel_path, language, chunks in file_chunk_map:
                    n = len(chunks)
                    ingestion_db.upsert_chunks(conn, repo_id, rel_path, language, chunks, embeddings[emb_offset:emb_offset + n])
                    emb_offset += n

                ingestion_db.update_repo_stats(conn, repo_id)
                log(f"Done [{mode}]. {len(file_chunk_map)} files, {len(all_chunks)} chunks, {total_tokens:,} tokens.")
                return {"files": len(file_chunk_map), "chunks": len(all_chunks), "mode": mode}

            finally:
                conn.close()

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
