import os
import time
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from github_loader import clone_or_pull, walk_files
from ast_chunker import chunk_file
from embedder import embed_chunks
import db as database

load_dotenv()

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def ingest(
    repo: str = typer.Option(..., "--repo", help="GitHub repository URL"),
    branch: str = typer.Option("main", "--branch", help="Branch to index"),
) -> None:
    """Index a GitHub repository into the vector store."""
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

    import git as gitlib
    git_repo = gitlib.Repo(repo_path)
    commit_sha = git_repo.head.commit.hexsha

    console.print(f"  Local path : {repo_path}")
    console.print(f"  Commit     : {commit_sha[:12]}")

    # 2. Walk files
    console.print("[bold cyan]Walking files …[/bold cyan]")
    files = walk_files(repo_path)
    console.print(f"  Found {len(files)} code files")

    # 3. Chunk all files
    console.print("[bold cyan]Chunking (AST-aware) …[/bold cyan]")
    all_chunks: list[dict] = []
    file_chunk_map: list[tuple[str, str, list[dict]]] = []

    for file_info in files:
        try:
            content = file_info["path"].read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        chunks = chunk_file(file_info["path"], file_info["language"], content)
        if chunks:
            file_chunk_map.append((file_info["relative_path"], file_info["language"], chunks))
            all_chunks.extend(chunks)

    console.print(f"  Total chunks: {len(all_chunks)}")

    if not all_chunks:
        console.print("[yellow]No chunks produced — nothing to index.[/yellow]")
        raise typer.Exit(0)

    # 4. Embed
    console.print(f"[bold cyan]Embedding {len(all_chunks)} chunks (batch=128) …[/bold cyan]")
    embeddings = embed_chunks(all_chunks, voyage_key)
    total_tokens = sum(c["token_count"] for c in all_chunks)

    # 5. Upsert to DB
    console.print("[bold cyan]Writing to database …[/bold cyan]")
    conn = database.get_connection(database_url)
    try:
        repo_id = database.upsert_repository(conn, repo, repo_name, branch, commit_sha)

        # Distribute embeddings back to per-file chunks
        emb_offset = 0
        for rel_path, language, chunks in file_chunk_map:
            n = len(chunks)
            file_embeddings = embeddings[emb_offset : emb_offset + n]
            database.upsert_chunks(conn, repo_id, rel_path, language, chunks, file_embeddings)
            emb_offset += n

        database.update_repo_stats(conn, repo_id)
    finally:
        conn.close()

    elapsed = time.time() - start_time

    # 6. Summary
    table = Table(title="Ingestion complete", show_header=True, header_style="bold green")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Repository", repo_name)
    table.add_row("Branch", branch)
    table.add_row("Commit", commit_sha[:12])
    table.add_row("Files processed", str(len(file_chunk_map)))
    table.add_row("Chunks created", str(len(all_chunks)))
    table.add_row("Total tokens", f"{total_tokens:,}")
    table.add_row("Time elapsed", f"{elapsed:.1f}s")
    console.print(table)


if __name__ == "__main__":
    app()
