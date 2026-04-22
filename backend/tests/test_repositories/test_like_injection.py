"""Tests for SQL LIKE wildcard escaping in BaseRepository._apply_search."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.repositories.workflow_repo import WorkflowRepository


@pytest.mark.asyncio
async def test_search_escapes_percent_wildcard(db_session):
    """A literal '%' in search must not act as a LIKE wildcard."""
    repo = WorkflowRepository(db_session)

    # Create workflows: one with a literal %, one without
    wf_percent = Workflow(
        name=f"my%workflow-{uuid4().hex[:8]}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )
    wf_normal = Workflow(
        name=f"normal-workflow-{uuid4().hex[:8]}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )
    db_session.add_all([wf_percent, wf_normal])
    await db_session.commit()

    # Searching for "%" should only match the workflow with a literal %
    results, _ = await repo.list(search="my%work")
    names = [w.name for w in results]
    assert wf_percent.name in names
    assert wf_normal.name not in names


@pytest.mark.asyncio
async def test_search_escapes_underscore_wildcard(db_session):
    """A literal '_' in search must not act as a single-char LIKE wildcard."""
    repo = WorkflowRepository(db_session)

    tag = uuid4().hex[:8]
    # Create two workflows: one with underscore, one with a different char in that position
    wf_underscore = Workflow(
        name=f"wf_test-{tag}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )
    wf_dash = Workflow(
        name=f"wfXtest-{tag}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )
    db_session.add_all([wf_underscore, wf_dash])
    await db_session.commit()

    # Searching for "wf_test" with literal underscore should only match the underscore variant
    results, _ = await repo.list(search=f"wf_test-{tag}")
    names = [w.name for w in results]
    assert wf_underscore.name in names
    assert wf_dash.name not in names


@pytest.mark.asyncio
async def test_search_normal_text_still_works(db_session):
    """Normal search text without special chars should still work."""
    repo = WorkflowRepository(db_session)

    tag = uuid4().hex[:8]
    wf = Workflow(
        name=f"viralrecon-{tag}",
        source=WorkflowSource.NFCORE,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )
    db_session.add(wf)
    await db_session.commit()

    results, _ = await repo.list(search=f"viralrecon-{tag}")
    assert any(w.name == wf.name for w in results)
