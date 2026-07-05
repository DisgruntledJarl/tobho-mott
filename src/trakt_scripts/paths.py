"""Single source of truth for repo-relative paths.

Resolves the repo root by walking up to the directory containing pyproject.toml,
so data/ and .env are found regardless of package nesting depth or cwd.
"""

from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


REPO_ROOT = _repo_root()
DATA_DIR = REPO_ROOT / "data"
ENV_PATH = REPO_ROOT / ".env"
DEFAULT_CSV = DATA_DIR / "watch_history.csv"
