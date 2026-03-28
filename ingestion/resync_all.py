"""
Resync all indexed repositories incrementally.

Only re-embeds files that changed since the last index — repos with no new
commits are skipped entirely, incurring zero Voyage AI cost.

Run manually:
    docker compose --profile cron run resync

Or schedule via cron (runs at 02:00 daily):
    0 2 * * * docker compose --profile cron run --rm resync
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

# Add ingestion dir to path so local imports work
sys.path.insert(0, str(Path(__file__).parent))

from github_loader import clone_or_pull, walk_files, get_current_commit, get_changed_files
from ast_chunker import chunk_file
from embedder import embed_chunks
import db as database

console = Console()

# Seconds to wait between repos to avoid Voyage AI rate limits
INTER_REPO_DELAY = 2


def _index_files(repo_path, files_to_index, voyage_key, conn, repo_id) -> tuple[int, int]:
    all_chunks = []
    file_chunk_map = []

    for file_info in files_to_index:
        try:
            content = file_info["path"].read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunks = chunk_file(file_info["path"], file_info["language"], content)
        if chunks:
            file_chunk_map.append((file_info["relative_path"], file_info["language"], chunks))
            all_chunks.extend(chunks)

    if not all_chunks:
        return 0, 0

    embeddings = embed_chunks(all_chunks, voyage_key)

    emb_offset = 0
    for rel_path, language, chunks in file_chunk_map:
        n = len(chunks)
        database.upsert_chunks(conn, repo_id, rel_path, language, chunks, embeddings[emb_offset:emb_offset + n])
        emb_offset += n

    return len(file_chunk_map), len(all_chunks)


def resync_repo(repo_url: str, branch: str, voyage_key: str, database_url: str) -> dict:
    """Incrementally resync one repo. Returns a result summary dict."""
    result = {"repo": repo_url, "mode": "skip", "files": 0, "chunks": 0, "error": None}

    try:
        repo_path = clone_or_pull(repo_url, branch)
        current_commit = get_current_commit(repo_path)
        repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")

        conn = database.get_connection(database_url)
        try:
            stored = database.get_repo_by_url(conn, repo_url)
            repo_id = database.upsert_repository(conn, repo_url, repo_name, branch, current_commit)

            if stored and stored["commit_sha"] == current_commit:
                # Nothing changed
                return result

            if stored and stored["commit_sha"]:
                changes = get_changed_files(repo_path, stored["commit_sha"])
                if changes.get("full_reindex"):
                    mode = "full"
                elif not changes["modified"] and not changes["deleted"]:
                    return result
                else:
                    mode = "incremental"
            else:
                mode = "full"

            if mode == "full":
                if stored:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM chunks WHERE repo_id = %s", (repo_id,))
                    conn.commit()
                files_to_index = walk_files(repo_path)
            else:
                affected = changes["modified"] + changes["deleted"]
                database.delete_chunks_for_files(conn, repo_id, affected)
                all_files = {f["relative_path"]: f for f in walk_files(repo_path)}
                files_to_index = [all_files[p] for p in changes["modified"] if p in all_files]

            file_count, chunk_count = _index_files(repo_path, files_to_index, voyage_key, conn, repo_id)
            database.update_repo_stats(conn, repo_id)

            result.update({"mode": mode, "files": file_count, "chunks": chunk_count})

        finally:
            conn.close()

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    voyage_key = os.environ.get("VOYAGE_API_KEY", "")
    database_url = os.environ.get("DATABASE_URL", "")

    if not voyage_key:
        console.print("[red]VOYAGE_API_KEY is not set[/red]")
        sys.exit(1)
    if not database_url:
        console.print("[red]DATABASE_URL is not set[/red]")
        sys.exit(1)

    # Fetch all repos, most recently queried first (prioritise active repos)
    conn = database.get_connection(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT url, branch FROM repositories ORDER BY updated_at DESC NULLS LAST")
            repos = cur.fetchall()
    finally:
        conn.close()

    if not repos:
        console.print("[yellow]No repositories indexed yet.[/yellow]")
        return

    console.print(f"[bold cyan]Resyncing {len(repos)} repositories…[/bold cyan]")
    start = time.time()
    results = []

    for i, (url, branch) in enumerate(repos, 1):
        console.print(f"[{i}/{len(repos)}] {url}")
        r = resync_repo(url, branch, voyage_key, database_url)
        results.append(r)
        if r["error"]:
            console.print(f"  [red]ERROR: {r['error']}[/red]")
        else:
            console.print(f"  [{r['mode']}] {r['files']} files, {r['chunks']} chunks")
        if i < len(repos):
            time.sleep(INTER_REPO_DELAY)

    elapsed = time.time() - start

    table = Table(title=f"Resync complete ({elapsed:.0f}s)", show_header=True, header_style="bold green")
    table.add_column("Repository", style="cyan")
    table.add_column("Mode", justify="center")
    table.add_column("Files", justify="right")
    table.add_column("Chunks", justify="right")
    table.add_column("Status")
    for r in results:
        name = r["repo"].rstrip("/").split("/")[-1]
        status = "[red]ERROR[/red]" if r["error"] else "[green]OK[/green]"
        table.add_row(name, r["mode"], str(r["files"]), str(r["chunks"]), status)
    console.print(table)


if __name__ == "__main__":
    main()
