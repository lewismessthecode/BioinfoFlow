"""Path Contract v3 migration.

Rewrites DB-stored absolute paths from an old platform root
(e.g. `/root/bioinfoflow/data`) to the new canonical root
(e.g. `/srv/bioinfoflow`).

Affected storage:
    - run.config (JSON blob with many path fields)
    - run.samplesheet_path
    - project.external_root_path
    - audit_log.details (JSON)

Usage::

    # Dry run (default):
    uv run python -m scripts.migrate_path_contract_v3 \
        --old-home /root/bioinfoflow/data \
        --new-home /srv/bioinfoflow

    # Apply for real:
    uv run python -m scripts.migrate_path_contract_v3 \
        --old-home /root/bioinfoflow/data \
        --new-home /srv/bioinfoflow \
        --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.database import async_session_maker, init_db
from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.run import Run


def _rewrite(value: Any, old: str, new: str) -> tuple[Any, int]:
    """Return (rewritten, n_changes). Operates recursively on dict/list/str."""
    if isinstance(value, dict):
        changed = 0
        result = {}
        for k, v in value.items():
            new_v, sub_changes = _rewrite(v, old, new)
            result[k] = new_v
            changed += sub_changes
        return result, changed
    if isinstance(value, list):
        changed = 0
        result_list = []
        for item in value:
            new_item, sub_changes = _rewrite(item, old, new)
            result_list.append(new_item)
            changed += sub_changes
        return result_list, changed
    if isinstance(value, str) and value.startswith(old):
        return new + value[len(old) :], 1
    return value, 0


def _verify_path(value: Any, warn: list[str]) -> None:
    if isinstance(value, dict):
        for v in value.values():
            _verify_path(v, warn)
    elif isinstance(value, list):
        for item in value:
            _verify_path(item, warn)
    elif isinstance(value, str) and os.path.isabs(value) and "/" in value:
        # Heuristic: only check paths that look like real filesystem paths
        # with common bioinformatics extensions or /srv/bioinfoflow prefix.
        looks_like_path = value.startswith("/srv/bioinfoflow/") or value.endswith(
            (".wdl", ".nf", ".fq.gz", ".fastq.gz", ".tsv", ".csv", ".json", ".list")
        )
        if looks_like_path and not Path(value).exists():
            warn.append(value)


async def run_migration(old_home: str, new_home: str, *, apply: bool) -> int:
    old = old_home.rstrip("/")
    new = new_home.rstrip("/")
    if not old or not new:
        print("ERROR: --old-home and --new-home must be non-empty", file=sys.stderr)
        return 2
    if old == new:
        print("old-home and new-home are the same; nothing to migrate.")
        return 0

    await init_db()

    total_changes = 0
    missing_paths: list[str] = []

    async with async_session_maker() as session:
        # --- Runs ---
        result = await session.execute(select(Run))
        for run in result.scalars().all():
            local_changes = 0

            new_config, n = _rewrite(run.config or {}, old, new)
            if n:
                print(f"run {run.run_id}: config — {n} path(s)")
                local_changes += n
                if apply:
                    run.config = new_config
                _verify_path(new_config, missing_paths)

            if run.samplesheet_path and run.samplesheet_path.startswith(old):
                new_ss = new + run.samplesheet_path[len(old) :]
                print(f"run {run.run_id}: samplesheet_path -> {new_ss}")
                local_changes += 1
                if apply:
                    run.samplesheet_path = new_ss
                if not Path(new_ss).exists():
                    missing_paths.append(new_ss)

            total_changes += local_changes

        # --- Projects ---
        result = await session.execute(select(Project))
        for project in result.scalars().all():
            if project.external_root_path and project.external_root_path.startswith(old):
                new_p = new + project.external_root_path[len(old) :]
                print(f"project {project.id}: external_root_path -> {new_p}")
                total_changes += 1
                if apply:
                    project.external_root_path = new_p
                if not Path(new_p).exists():
                    missing_paths.append(new_p)

        # --- Audit logs ---
        result = await session.execute(select(AuditLog))
        for entry in result.scalars().all():
            new_details, n = _rewrite(entry.details or {}, old, new)
            if n:
                print(f"audit_log {entry.id}: details — {n} path(s)")
                total_changes += n
                if apply:
                    entry.details = new_details

        if apply:
            await session.commit()
            print(f"\nCOMMITTED {total_changes} path rewrite(s).")
        else:
            print(f"\nDRY RUN: would rewrite {total_changes} path(s). Pass --apply to commit.")

    if missing_paths:
        print(f"\nWARNING: {len(missing_paths)} rewritten path(s) do not exist on disk:")
        for p in missing_paths[:20]:
            print(f"  missing: {p}")
        if len(missing_paths) > 20:
            print(f"  … and {len(missing_paths) - 20} more")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-home", required=True, help="Old absolute platform root")
    parser.add_argument("--new-home", required=True, help="New absolute platform root")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes (default is dry-run)",
    )
    args = parser.parse_args()
    return asyncio.run(
        run_migration(args.old_home, args.new_home, apply=args.apply)
    )


if __name__ == "__main__":
    sys.exit(main())
