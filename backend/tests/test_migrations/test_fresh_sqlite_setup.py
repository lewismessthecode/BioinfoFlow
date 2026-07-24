from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_upgrade_creates_fresh_sqlite_parent_directory(tmp_path: Path) -> None:
    home = tmp_path / "fresh-bioinfoflow-home"
    env = os.environ.copy()
    env["BIOINFOFLOW_HOME"] = str(home)
    env.pop("DATABASE_URL", None)

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (home / "state" / "bioinfoflow.db").is_file()
