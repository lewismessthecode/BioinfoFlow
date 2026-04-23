from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger(__name__)

# run_id must be a simple slug. Any path separators, nul bytes, or
# parent-directory markers are rejected so a corrupted DB row cannot
# steer shutil.rmtree at an arbitrary directory.
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(slots=True)
class CleanupPolicy:
    keep_on_success: bool = True
    keep_on_failure: bool = True
    max_age_days: int = 7


class WorkDirCleaner:
    def __init__(self, policy: CleanupPolicy | None = None) -> None:
        self.policy = policy or CleanupPolicy()

    async def cleanup_run(
        self,
        run_id: str,
        *,
        workspace_path: str | Path,
        status: str,
        engine: str,
        runtime: dict | None = None,
    ) -> dict[str, list[str]]:
        if not self._should_cleanup(status):
            return {"deleted": []}
        return await self.manual_cleanup(
            run_id,
            workspace_path=workspace_path,
            engine=engine,
            runtime=runtime,
        )

    async def manual_cleanup(
        self,
        run_id: str,
        *,
        workspace_path: str | Path,
        engine: str,
        runtime: dict | None = None,
    ) -> dict[str, list[str]]:
        if not _SAFE_RUN_ID_RE.fullmatch(run_id):
            logger.error("scheduler.cleanup.invalid_run_id", run_id=run_id)
            return {"deleted": []}
        workspace_root = Path(workspace_path).resolve()
        runs_root = (workspace_root / "runs").resolve()
        deleted: list[str] = []
        for path in self._candidate_paths(
            run_id,
            workspace_path=workspace_root,
            engine=engine,
            runtime=runtime or {},
        ):
            if not path.exists():
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(runs_root)
            except ValueError:
                logger.error(
                    "scheduler.cleanup.escapes_workspace",
                    run_id=run_id,
                    path=str(resolved),
                    runs_root=str(runs_root),
                )
                continue
            shutil.rmtree(resolved)
            deleted.append(str(resolved))
        return {"deleted": deleted}

    def _should_cleanup(self, status: str) -> bool:
        normalized = str(status).strip().lower()
        if normalized == "completed":
            return not self.policy.keep_on_success
        if normalized in {"failed", "cancelled"}:
            return not self.policy.keep_on_failure
        return False

    def _candidate_paths(
        self,
        run_id: str,
        *,
        workspace_path: Path,
        engine: str,
        runtime: dict,
    ) -> list[Path]:
        del runtime
        del engine
        return [workspace_path / "runs" / run_id]

    def _resolve_path(self, workspace_path: Path, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else workspace_path / path

    def _unique_paths(self, paths: list[Path]) -> list[Path]:
        seen: dict[str, Path] = {}
        for path in paths:
            key = str(path.resolve(strict=False))
            if key not in seen:
                seen[key] = path
        return list(seen.values())
