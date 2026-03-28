import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter()


@router.get("/repos")
async def list_repos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            """
            SELECT id, name, url, branch, chunk_count, file_count, indexed_at, updated_at
            FROM repositories
            ORDER BY indexed_at DESC
            """
        )
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.delete("/repos/{repo_id}")
async def delete_repo(repo_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id FROM repositories WHERE id = :id"),
        {"id": repo_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Repo not found")
    # CASCADE in schema handles deleting chunks
    await db.execute(text("DELETE FROM repositories WHERE id = :id"), {"id": repo_id})
    await db.commit()
    return {"ok": True}


@router.post("/repos/{repo_id}/resync")
async def resync_repo(repo_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT url, branch FROM repositories WHERE id = :id"),
        {"id": repo_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Repo not found")

    from routes.ingest import _jobs, _run_ingest

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "repo_url": row["url"],
        "branch": row["branch"],
        "log": "",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    asyncio.create_task(_run_ingest(job_id, row["url"], row["branch"], force=False))
    return {"job_id": job_id}
