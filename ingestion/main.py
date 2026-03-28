import os
import time
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from github_loader import clone_or_pull, walk_files, get_current_commit, get_changed_files
from ast_chunker import chunk_file
from embedder import embed_chunks
import db as database

load_dotenv()

app = typer.Typer(add_completion=False)
console = Console()


def _index_files(
    repo_path: Path,
    files_to_index: list[dict],
    voyage_key: str,
    conn,
    repo_id: int,
) -> tuple[int, int]:
    """Chunk, embed, and upsert a list of file dicts. Returns (file_count, chunk_count)."""
    all_chunks: list[dict] = []
    file_chunk_map: list[tuple[str, str, list[dict]]] = []

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


@app.command()
def ingest(
    repo: str = typer.Option(..., "--repo", help="GitHub repository URL"),
    branch: str = typer.Option("main", "--branch", help="Branch to index"),
    force: bool = typer.Option(False, "--force", help="Force full re-index even if up to date"),
) -> None:
    """Index a GitHub repository into the vector store (incremental by default)."""
    start_time = time.time()

    voyage_key = os.environ.get("VOYAGE_API_KEY", "")
    database_url = os.environ.get("DATABASE_URL", "")

    if not voyage_key:
        console.print("[red]VOYAGE_API_KEY is not set[/red]")
        raise typer.Exit(1)
    if not database_url:
        console.print("[red]DATABASE_URL is not set[/red]")
        raise typer.Exit(1)

    # 1. Clone / pull
    console.print(f"[bold cyan]Cloning/pulling[/bold cyan] {repo} @ {branch} …")
    repo_path = clone_or_pull(repo, branch)
    repo_name = repo.rstrip("/").split("/")[-1].removesuffix(".git")
    current_commit = get_current_commit(repo_path)

    console.print(f"  Local path : {repo_path}")
    console.print(f"  Commit     : {current_commit[:12]}")

    # 2. Check stored commit for incremental sync
    conn = database.get_connection(database_url)
    try:
        stored = database.get_repo_by_url(conn, repo)
        repo_id = database.upsert_repository(conn, repo, repo_name, branch, current_commit)

        if not force and stored and stored["commit_sha"] == current_commit:
            console.print("[green]Already up to date — no changes since last index.[/green]")
            return

        if not force and stored and stored["commit_sha"]:
            # 3a. Incremental: only changed files
            console.print(f"[bold cyan]Detecting changes since[/bold cyan] {stored['commit_sha'][:12]} …")
            changes = get_changed_files(repo_path, stored["commit_sha"])

            if changes.get("full_reindex"):
                console.print("[yellow]Cannot diff (history rewrite?) — falling back to full re-index.[/yellow]")
                mode = "full"
            elif not changes["modified"] and not changes["deleted"]:
                console.print("[green]No file changes detected — nothing to re-index.[/green]")
                return
            else:
                mode = "incremental"
                console.print(
                    f"  Changed: {len(changes['modified'])} modified, "
                    f"{len(changes['deleted'])} deleted"
                )
        else:
            mode = "full"

        if mode == "full":
            console.print("[bold cyan]Full index …[/bold cyan]")
            files = walk_files(repo_path)
            # Delete all existing chunks for a clean slate
            if stored:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM chunks WHERE repo_id = %s", (repo_id,))
                conn.commit()
            console.print(f"  Found {len(files)} code files")
            file_count, chunk_count = _index_files(repo_path, files, voyage_key, conn, repo_id)

        else:
            # Delete chunks for removed and modified files (will be re-added below)
            affected = changes["modified"] + changes["deleted"]
            database.delete_chunks_for_files(conn, repo_id, affected)

            # Only re-index modified files that still exist on disk
            all_files = {f["relative_path"]: f for f in walk_files(repo_path)}
            files_to_index = [
                all_files[p] for p in changes["modified"] if p in all_files
            ]
            console.print(f"[bold cyan]Re-indexing {len(files_to_index)} changed files …[/bold cyan]")
            file_count, chunk_count = _index_files(repo_path, files_to_index, voyage_key, conn, repo_id)

        database.update_repo_stats(conn, repo_id)

    finally:
        conn.close()

    elapsed = time.time() - start_time

    table = Table(title="Ingestion complete", show_header=True, header_style="bold green")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Repository", repo_name)
    table.add_row("Branch", branch)
    table.add_row("Commit", current_commit[:12])
    table.add_row("Mode", mode)
    table.add_row("Files processed", str(file_count))
    table.add_row("Chunks created", str(chunk_count))
    table.add_row("Time elapsed", f"{elapsed:.1f}s")
    console.print(table)


if __name__ == "__main__":
    app()
