from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_SQLITE_DB = BACKEND_DIR / "adops_signal.db"


def configure_backend_runtime() -> None:
    """Make the existing backend package importable for MCP tool execution."""
    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    os.environ.setdefault("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_DB}")

