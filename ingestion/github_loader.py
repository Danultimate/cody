from pathlib import Path
import git
from typing import Optional

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".php", ".go", ".rs", ".java", ".rb",
    ".c", ".cpp", ".h", ".cs", ".md",
}

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "__pycache__",
    "dist", "build", ".next", ".nuxt", ".venv",
    "venv", "env", ".tox", "coverage",
}

MAX_FILE_SIZE = 500 * 1024  # 500 KB


def clone_or_pull(repo_url: str, branch: str = "main", cache_dir: str = "/tmp/repos") -> Path:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    repo_path = cache_path / repo_name

    if repo_path.exists():
        repo = git.Repo(repo_path)
        origin = repo.remotes.origin
        origin.fetch()
        repo.git.checkout(branch)
        origin.pull(branch)
    else:
        git.Repo.clone_from(repo_url, repo_path, branch=branch, depth=None)

    return repo_path


def get_current_commit(repo_path: Path) -> str:
    return git.Repo(repo_path).head.commit.hexsha


def get_changed_files(repo_path: Path, since_commit: str) -> dict:
    """Return files changed between since_commit and HEAD.

    Returns {'modified': [paths], 'deleted': [paths]}
    where 'modified' covers added, modified, and renamed files.
    """
    repo = git.Repo(repo_path)
    try:
        diff_output = repo.git.diff("--name-status", since_commit, "HEAD")
    except git.GitCommandError:
        # since_commit not found (e.g. force-pushed) — signal full re-index
        return {"modified": [], "deleted": [], "full_reindex": True}

    modified, deleted = [], []
    for line in diff_output.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0][0]  # D=deleted, M=modified, A=added, R=renamed, C=copied
        path = parts[-1]      # last field is always the destination path
        if status == "D":
            deleted.append(path)
        else:
            modified.append(path)
    return {"modified": modified, "deleted": deleted, "full_reindex": False}


def _is_binary(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def _ext_to_language(ext: str) -> str:
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".php": "php",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".cs": "c_sharp",
        ".md": "markdown",
    }
    return mapping.get(ext, "unknown")


def walk_files(repo_path: Path) -> list[dict]:
    results = []

    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue

        # Skip blacklisted dirs anywhere in path
        parts = set(file_path.relative_to(repo_path).parts[:-1])
        if parts & SKIP_DIRS:
            continue

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        size = file_path.stat().st_size
        if size > MAX_FILE_SIZE or size == 0:
            continue

        if _is_binary(file_path):
            continue

        relative_path = str(file_path.relative_to(repo_path))
        results.append({
            "path": file_path,
            "relative_path": relative_path,
            "language": _ext_to_language(ext),
            "size_bytes": size,
        })

    return results
