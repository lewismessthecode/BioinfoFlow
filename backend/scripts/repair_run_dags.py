from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import async_session_maker
from app.services.run_service import RunService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair persisted DAG node statuses for historical runs."
    )
    parser.add_argument(
        "--run-id",
        action="append",
        dest="run_ids",
        help="Specific run_id to repair. Repeatable.",
    )
    parser.add_argument(
        "--project-id",
        help="Limit bulk repair to a single project.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview repair results without writing changes.",
    )
    return parser


async def _main() -> int:
    args = _build_parser().parse_args()
    async with async_session_maker() as session:
        service = RunService(session)
        result = await service.repair_run_dags(
            run_ids=args.run_ids,
            project_id=args.project_id,
            dry_run=args.dry_run,
        )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
