#!/usr/bin/env python3
"""
RAG eval — Recall@k and MRR against golden queries on the cody repo.

Usage:
    python eval/run_eval.py [--api http://localhost:8000] [--repo-id 1] [--top-k 5]
"""

import argparse
import json
import sys
import time

import requests

GOLDEN: list[dict] = [
    {
        "question": "Where is _reciprocal_rank_fusion defined?",
        "expected_files": ["api/rag.py"],
    },
    {
        "question": "How are chunks embedded with Voyage AI?",
        "expected_files": ["api/ingestion/embedder.py"],
    },
    {
        "question": "What AST node types are extracted for Python?",
        "expected_files": ["api/ingestion/ast_chunker.py"],
    },
    {
        "question": "How does the sliding window chunking work?",
        "expected_files": ["api/ingestion/ast_chunker.py"],
    },
    {
        "question": "How is the database schema initialized?",
        "expected_files": ["db/init.sql"],
    },
    {
        "question": "Where is the Gemini API called?",
        "expected_files": ["api/rag.py"],
    },
    {
        "question": "How does keyword search build the tsquery?",
        "expected_files": ["api/rag.py"],
    },
    {
        "question": "How are repositories deleted?",
        "expected_files": ["api/routes/repos.py"],
    },
    {
        "question": "What languages does the AST chunker support?",
        "expected_files": ["api/ingestion/ast_chunker.py"],
    },
    {
        "question": "How does the ingest job track its progress?",
        "expected_files": ["api/routes/ingest.py"],
    },
]


def reciprocal_rank(chunks: list[dict], expected_files: list[str]) -> float:
    for rank, chunk in enumerate(chunks, start=1):
        fp = chunk.get("file_path", "")
        if any(fp.endswith(e) or e in fp for e in expected_files):
            return 1.0 / rank
    return 0.0


def recall_at_k(chunks: list[dict], expected_files: list[str]) -> bool:
    for chunk in chunks:
        fp = chunk.get("file_path", "")
        if any(fp.endswith(e) or e in fp for e in expected_files):
            return True
    return False


def run(api_base: str, repo_id: int, top_k: int) -> None:
    url = f"{api_base.rstrip('/')}/query"
    results = []

    print(f"\nEval: {len(GOLDEN)} queries | repo_id={repo_id} | top_k={top_k}\n")
    print(f"{'#':<3} {'Recall':>7} {'RR':>6}  Question")
    print("-" * 70)

    for i, item in enumerate(GOLDEN, start=1):
        t0 = time.time()
        try:
            resp = requests.post(
                url,
                json={"question": item["question"], "repo_id": repo_id, "top_k": top_k},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"{i:<3} {'ERR':>7} {'ERR':>6}  {item['question'][:55]}  [{e}]")
            results.append({"recall": 0, "rr": 0.0, "latency": time.time() - t0})
            continue

        chunks = data.get("chunks", [])
        latency = time.time() - t0
        hit = recall_at_k(chunks, item["expected_files"])
        rr = reciprocal_rank(chunks, item["expected_files"])

        mark = "✓" if hit else "✗"
        print(
            f"{i:<3} {mark} {str(hit):>5} {rr:>6.3f}  {item['question'][:55]}"
            f"  [{latency:.1f}s]"
        )
        results.append({"recall": int(hit), "rr": rr, "latency": latency})

    recall = sum(r["recall"] for r in results) / len(results)
    mrr = sum(r["rr"] for r in results) / len(results)
    avg_latency = sum(r["latency"] for r in results) / len(results)

    print("-" * 70)
    print(f"{'Recall@' + str(top_k):<12} {recall:.2%}")
    print(f"{'MRR':<12} {mrr:.3f}")
    print(f"{'Avg latency':<12} {avg_latency:.1f}s")
    print()

    failed = [GOLDEN[i] for i, r in enumerate(results) if not r["recall"]]
    if failed:
        print("Missed queries:")
        for q in failed:
            print(f"  - {q['question']}")
        print()

    if recall < 0.7:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--repo-id", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    run(args.api, args.repo_id, args.top_k)
