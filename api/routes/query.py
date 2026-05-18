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
    session_id: str = ""


@router.post("/query")
async def query_endpoint(body: QueryRequest, db: AsyncSession = Depends(get_db)):
    from limiter import check_question_limit, record_question
    from fastapi import HTTPException

    if body.session_id:
        remaining = await check_question_limit(body.session_id)
        if remaining <= 0:
            raise HTTPException(
                status_code=429,
                detail="You've used all 5 questions for this session. Index a new repo to continue.",
            )

    start = time.monotonic()
    result = await rag.query(body.question, body.repo_id, body.top_k, db)
    latency_ms = int((time.monotonic() - start) * 1000)
    result["latency_ms"] = latency_ms

    questions_remaining = await record_question(body.session_id)
    result["questions_remaining"] = questions_remaining

    try:
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
    except Exception:
        await db.rollback()

    return result
