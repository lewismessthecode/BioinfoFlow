from __future__ import annotations

from sqlalchemy import inspect

import app.models
from app.models.agent_harness import (
    AgentHarnessArtifact,
    AgentHarnessAttachment,
    AgentHarnessEntry,
    AgentHarnessRun,
    AgentHarnessSession,
)
from app.models.agent_token import AgentToken
from app.models.base import Base


def test_harness_models_are_the_canonical_main_metadata_tables() -> None:
    expected = {
        "agent_sessions": AgentHarnessSession,
        "agent_runs": AgentHarnessRun,
        "agent_entries": AgentHarnessEntry,
        "agent_attachments": AgentHarnessAttachment,
        "agent_artifacts": AgentHarnessArtifact,
        "agent_tokens": AgentToken,
    }

    for table_name, model in expected.items():
        assert model.metadata is Base.metadata
        assert Base.metadata.tables[table_name] is model.__table__

    assert app.models.AgentSession is AgentHarnessSession
    assert app.models.AgentRun is AgentHarnessRun
    assert app.models.AgentEntry is AgentHarnessEntry
    assert app.models.AgentAttachment is AgentHarnessAttachment
    assert app.models.AgentArtifact is AgentHarnessArtifact


def test_main_metadata_declares_real_harness_foreign_keys() -> None:
    expected = {
        ("agent_runs", "session_id"): ("agent_sessions.id", "CASCADE"),
        ("agent_entries", "session_id"): ("agent_sessions.id", "CASCADE"),
        ("agent_entries", "run_id"): ("agent_runs.id", "SET NULL"),
        ("agent_attachments", "session_id"): ("agent_sessions.id", "CASCADE"),
        ("agent_artifacts", "session_id"): ("agent_sessions.id", "CASCADE"),
        ("agent_artifacts", "run_id"): ("agent_runs.id", "SET NULL"),
        ("agent_tokens", "workspace_id"): ("workspaces.id", "CASCADE"),
        ("agent_tokens", "session_id"): ("agent_sessions.id", "CASCADE"),
        ("agent_tokens", "run_id"): ("agent_runs.id", "CASCADE"),
    }

    for (table_name, column_name), (target, ondelete) in expected.items():
        foreign_keys = Base.metadata.tables[table_name].c[column_name].foreign_keys
        assert {(fk.target_fullname, fk.ondelete) for fk in foreign_keys} == {
            (target, ondelete)
        }

    assert inspect(AgentToken).local_table is Base.metadata.tables["agent_tokens"]
