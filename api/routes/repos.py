from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter()


@router.get("/repos")
async def list_repos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            """
            SELECT id, name, url, branch, chunk_count, file_count, indexed_at
            FROM repositories
            ORDER BY indexed_at DESC
            """
        )
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]
