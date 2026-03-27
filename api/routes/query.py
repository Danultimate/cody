import time
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
import rag

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    repo_id: int
    top_k: int = 8


@router.post("/query")
async def query_endpoint(body: QueryRequest, db: AsyncSession = Depends(get_db)):
    start = time.monotonic()
    result = await rag.query(body.question, body.repo_id, body.top_k, db)
    latency_ms = int((time.monotonic() - start) * 1000)
    result["latency_ms"] = latency_ms

    # Log the query
    await db.execute(
        text(
            """
            INSERT INTO query_log (repo_id, question, answer, top_chunks, latency_ms)
            VALUES (:repo_id, :question, :answer, :top_chunks, :latency_ms)
            """
        ),
        {
            "repo_id": body.repo_id,
            "question": body.question,
            "answer": result["answer"],
            "top_chunks": json.dumps([
                {k: v for k, v in c.items() if k != "content"}
                for c in result["chunks"]
            ]),
            "latency_ms": latency_ms,
        },
    )
    await db.commit()

    return result
