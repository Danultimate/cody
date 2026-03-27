import os
import time

import google.generativeai as genai
import voyageai
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SIMILARITY_THRESHOLD = 0.3


def _embed_question(question: str) -> list[float]:
    client = voyageai.Client(api_key=VOYAGE_API_KEY)
    result = client.embed([question], model="voyage-code-3", input_type="query")
    return result.embeddings[0]


async def _vector_search(question_vec: list[float], repo_id: int, top_k: int, db: AsyncSession) -> list[dict]:
    vec_str = "[" + ",".join(str(x) for x in question_vec) + "]"
    result = await db.execute(
        text(
            f"""
            SELECT
                id,
                file_path,
                chunk_type,
                name,
                start_line,
                end_line,
                content,
                1 - (embedding <=> '{vec_str}'::vector) AS similarity
            FROM chunks
            WHERE repo_id = :repo_id
            ORDER BY embedding <=> '{vec_str}'::vector
            LIMIT :top_k
            """
        ),
        {"repo_id": repo_id, "top_k": top_k},
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows if r["similarity"] >= SIMILARITY_THRESHOLD]


def _build_prompt(question: str, chunks: list[dict]) -> tuple[str, str]:
    system = (
        "You are a senior software engineer helping a developer understand a codebase. "
        "Answer questions accurately using only the provided source code chunks. "
        "Always cite the exact file path and line numbers for every claim."
    )

    context_parts = []
    for chunk in chunks:
        header = (
            f"--- {chunk['file_path']} "
            f"(lines {chunk['start_line']}-{chunk['end_line']}"
            + (f", {chunk['chunk_type']}: {chunk['name']}" if chunk.get("name") else "")
            + ") ---"
        )
        context_parts.append(f"{header}\n{chunk['content']}\n---")

    context_block = "\n\n".join(context_parts)
    user = (
        f"{context_block}\n\n"
        f"Question: {question}\n\n"
        "Provide a clear technical answer. "
        "For every claim, cite the file path and line numbers like [src/auth/middleware.js:23]."
    )

    return system, user


def _call_gemini(system: str, user: str) -> str:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=system,
    )
    response = model.generate_content(user)
    return response.text


async def query(question: str, repo_id: int, top_k: int, db: AsyncSession) -> dict:
    # Step 1: Embed question
    question_vec = _embed_question(question)

    # Step 2: Vector search
    chunks = await _vector_search(question_vec, repo_id, top_k, db)

    if not chunks:
        return {
            "answer": "No relevant code chunks found for this question in the selected repository.",
            "chunks": [],
        }

    # Step 3 & 4: Build prompt and call Gemini
    system, user = _build_prompt(question, chunks)
    answer = _call_gemini(system, user)

    # Step 5: Return
    return {"answer": answer, "chunks": chunks}
