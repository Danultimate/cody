import os
import re

import requests
import voyageai
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# Reranker handles quality filtering — this is just a noise floor
SIMILARITY_THRESHOLD = 0.2
MAX_CONTEXT_TOKENS = 6000
RERANK_MODEL = "rerank-2"


def _embed_question(question: str) -> list[float]:
    client = voyageai.Client(api_key=VOYAGE_API_KEY)
    result = client.embed([question], model="voyage-code-3", input_type="query")
    return result.embeddings[0]


async def _vector_search(
    question_vec: list[float], repo_id: int, top_k: int, db: AsyncSession
) -> list[dict]:
    vec_str = "[" + ",".join(str(x) for x in question_vec) + "]"
    # Higher ef_search trades a little latency for better HNSW recall
    await db.execute(text("SET LOCAL hnsw.ef_search = 100"))
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
                token_count,
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


def _build_tsquery(question: str) -> str | None:
    # Extract alphanumeric tokens and join with OR so any matching term scores.
    # plainto_tsquery AND semantics would require "where","is","defined" to all
    # appear in code — they won't. OR lets ts_rank sort by how many tokens match.
    tokens = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return " | ".join(tokens) if tokens else None


async def _keyword_search(
    question: str, repo_id: int, top_k: int, db: AsyncSession
) -> list[dict]:
    tsquery = _build_tsquery(question)
    if not tsquery:
        return []
    try:
        result = await db.execute(
            text(
                """
                SELECT
                    id,
                    file_path,
                    chunk_type,
                    name,
                    start_line,
                    end_line,
                    content,
                    token_count,
                    ts_rank(tsv, to_tsquery('simple', :tsquery)) AS bm25_rank
                FROM chunks
                WHERE repo_id = :repo_id
                  AND tsv @@ to_tsquery('simple', :tsquery)
                ORDER BY bm25_rank DESC
                LIMIT :top_k
                """
            ),
            {"repo_id": repo_id, "tsquery": tsquery, "top_k": top_k},
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _reciprocal_rank_fusion(
    vector_chunks: list[dict], keyword_chunks: list[dict], k: int = 60
) -> list[dict]:
    scores: dict[int, float] = {}
    all_chunks: dict[int, dict] = {}

    for rank, chunk in enumerate(vector_chunks):
        cid = chunk["id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (rank + 1 + k)
        all_chunks[cid] = chunk  # vector version carries the similarity field

    for rank, chunk in enumerate(keyword_chunks):
        cid = chunk["id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (rank + 1 + k)
        if cid not in all_chunks:
            all_chunks[cid] = {**chunk, "similarity": 0.0}  # keyword-only: no cosine score

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [all_chunks[cid] for cid in sorted_ids]


def _rerank(question: str, candidates: list[dict], top_k: int) -> list[dict]:
    if not candidates:
        return candidates
    url = "https://api.voyageai.com/v1/rerank"
    payload = {
        "query": question,
        "documents": [c["content"] for c in candidates],
        "model": RERANK_MODEL,
        "top_k": min(top_k, len(candidates)),
    }
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return [candidates[item["index"]] for item in resp.json()["data"]]
    except Exception:
        return candidates[:top_k]


def _build_prompt(question: str, chunks: list[dict]) -> tuple[str, str]:
    system = (
        "You are a senior software engineer helping a developer understand a codebase. "
        "Answer questions accurately using only the provided source code chunks. "
        "When asked what a project or application IS, base your answer on README.md, "
        "top-level docs, or package manifests — not on configuration variable names, "
        "default values, database names, or hostnames that happen to share the project name. "
        "Always cite the exact file path and line numbers for every claim."
    )

    context_parts = []
    total_tokens = 0
    for chunk in chunks:
        chunk_tokens = chunk.get("token_count") or 0
        if total_tokens + chunk_tokens > MAX_CONTEXT_TOKENS:
            break
        header = (
            f"--- {chunk['file_path']} "
            f"(lines {chunk['start_line']}-{chunk['end_line']}"
            + (f", {chunk['chunk_type']}: {chunk['name']}" if chunk.get("name") else "")
            + ") ---"
        )
        context_parts.append(f"{header}\n{chunk['content']}\n---")
        total_tokens += chunk_tokens

    context_block = "\n\n".join(context_parts)
    user = (
        f"{context_block}\n\n"
        f"Question: {question}\n\n"
        "Provide a clear technical answer. "
        "For every claim, cite the file path and line numbers like [src/auth/middleware.js:23]."
    )

    return system, user


def _call_gemini(system: str, user: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models"
        f"/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def query(question: str, repo_id: int, top_k: int, db: AsyncSession) -> dict:
    retrieval_k = top_k * 3

    # Step 1: Embed question
    question_vec = _embed_question(question)

    # Step 2: Hybrid retrieval — vector and keyword run sequentially (shared session)
    vector_chunks = await _vector_search(question_vec, repo_id, retrieval_k, db)
    keyword_chunks = await _keyword_search(question, repo_id, retrieval_k, db)

    # Step 3: Merge candidates with Reciprocal Rank Fusion
    candidates = _reciprocal_rank_fusion(vector_chunks, keyword_chunks)

    if not candidates:
        return {
            "answer": "No relevant code chunks found for this question in the selected repository.",
            "chunks": [],
        }

    # Step 4: Rerank to top_k (falls back to RRF order if Voyage rerank API fails)
    # For meta questions about the project, surface README/docs chunks first so
    # the reranker sees them — config file hits for the same word would otherwise
    # push them out of the candidate window.
    meta_keywords = {"what is", "what's", "what are", "describe", "overview", "explain"}
    q_lower = question.lower()
    if any(kw in q_lower for kw in meta_keywords):
        readme_chunks = [c for c in candidates if "readme" in c["file_path"].lower()]
        other_chunks = [c for c in candidates if "readme" not in c["file_path"].lower()]
        candidates = readme_chunks + other_chunks

    chunks = _rerank(question, candidates, top_k)

    # Step 5: Build prompt with token budget and call Gemini
    system, user = _build_prompt(question, chunks)
    answer = _call_gemini(system, user)

    return {"answer": answer, "chunks": chunks}
