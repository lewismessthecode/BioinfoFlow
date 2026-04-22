#!/usr/bin/env python
"""Re-validate all local workflows and update their schema_json.

This script:
1. Reads all local workflows from the database
2. Re-validates each workflow using the WorkflowValidator
3. Updates schema_json with the extracted dependencies and other info

Usage:
    cd backend
    uv run python scripts/revalidate_workflows.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import async_session_maker
from app.models.workflow import Workflow, WorkflowSource
from app.path_layout import workflow_entrypoint_path
from app.services.workflow_validator import WorkflowValidator


async def revalidate_workflows() -> None:
    """Re-validate all local workflows and update their schema_json."""
    validator = WorkflowValidator()
    updated_count = 0
    error_count = 0

    async with async_session_maker() as session:
        # Get all local workflows
        stmt = select(Workflow).where(Workflow.source == WorkflowSource.LOCAL.value)
        result = await session.execute(stmt)
        workflows = result.scalars().all()

        print(f"Found {len(workflows)} local workflows to re-validate\n")

        for workflow in workflows:
            print(f"Processing: {workflow.name} (v{workflow.version})")
            print(f"  Engine: {workflow.engine}")
            print(f"  Source ref: {workflow.source_ref}")

            if not workflow.entrypoint_relpath:
                print("  ❌ Skipping: No local bundle entrypoint\n")
                error_count += 1
                continue

            source_path = workflow_entrypoint_path(workflow)
            if not source_path.exists():
                print(f"  ❌ Skipping: File not found: {source_path}\n")
                error_count += 1
                continue

            try:
                content = source_path.read_text()
            except Exception as e:
                print(f"  ❌ Error reading file: {e}\n")
                error_count += 1
                continue

            # Re-validate
            try:
                validation_result = validator.validate(
                    content=content,
                    engine=workflow.engine,
                    file_name=source_path.name,
                )
            except Exception as e:
                print(f"  ❌ Validation error: {e}\n")
                error_count += 1
                continue

            if not validation_result.valid:
                error_msgs = "; ".join(e.message for e in validation_result.errors)
                print(f"  ⚠️  Validation failed: {error_msgs}\n")
                error_count += 1
                continue

            # Update schema_json
            new_schema = validation_result.to_schema_json()
            old_deps_count = (
                len(workflow.schema_json.get("dependencies", []))
                if workflow.schema_json
                else 0
            )
            new_deps_count = len(new_schema.get("dependencies", []))

            workflow.schema_json = new_schema
            updated_count += 1

            print("  ✅ Updated schema_json:")
            print(f"     - Tasks: {len(new_schema.get('tasks', []))}")
            print(f"     - Dependencies: {old_deps_count} → {new_deps_count}")
            print(f"     - Inputs: {len(new_schema.get('inputs', []))}")
            print()

        await session.commit()

    print("=" * 50)
    print("Re-validation complete!")
    print(f"  ✅ Updated: {updated_count}")
    print(f"  ❌ Errors: {error_count}")


if __name__ == "__main__":
    asyncio.run(revalidate_workflows())
