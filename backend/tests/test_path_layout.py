from __future__ import annotations

import pytest

from app.config import settings
from app.path_layout import (
    agent_attachment_root,
    agent_attachments_root,
    agent_session_attachments_root,
)


def test_agent_attachment_paths_are_session_scoped(tmp_path, monkeypatch) -> None:
    home = tmp_path / "bioinfoflow-home"
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))

    root = home / "state" / "agent_core" / "attachments"
    assert agent_attachments_root() == root
    assert agent_session_attachments_root("session-1") == root / "session-1"
    assert agent_attachment_root("session-1", "attachment-1") == (
        root / "session-1" / "attachment-1"
    )


@pytest.mark.parametrize(
    "unsafe_name",
    ["../escape", "/absolute", "nested/path", "", ".", ".."],
)
def test_agent_attachment_paths_reject_unsafe_ids(unsafe_name: str) -> None:
    with pytest.raises(ValueError):
        agent_session_attachments_root(unsafe_name)
