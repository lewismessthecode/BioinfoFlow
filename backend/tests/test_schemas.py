from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.common import Meta, Pagination
from app.schemas.project import ProjectRead
from app.schemas.file import FileInfo, FileType
from app.schemas.llm import (
    LlmProviderCreate,
    LlmProviderSetupRequest,
    LlmProviderUpdate,
)


def test_meta_includes_timestamp_and_request_id():
    meta = Meta(request_id="req-1")
    assert meta.request_id == "req-1"
    assert isinstance(meta.timestamp, datetime)


def test_pagination_fields():
    pagination = Pagination(limit=10, has_more=False, total_count=0)
    assert pagination.limit == 10


def test_project_read_schema():
    payload = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Demo",
        "description": None,
        "storage_mode": "managed",
        "project_root": "asset://project",
        "is_default": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    project = ProjectRead.model_validate(payload)
    assert project.name == "Demo"


def test_file_info_schema():
    info = FileInfo(
        name="sample.txt",
        path="sample.txt",
        type=FileType.FILE,
        size_bytes=10,
        modified_at=datetime.now(timezone.utc),
    )
    assert info.type == FileType.FILE


def test_provider_schema_defaults_wire_protocol_for_compatibility() -> None:
    provider = LlmProviderCreate(name="OpenAI", kind="openai")
    setup = LlmProviderSetupRequest(template_id="openai")

    assert provider.wire_protocol == "chat_completions"
    assert setup.wire_protocol == "chat_completions"


def test_provider_schema_rejects_unknown_wire_protocol() -> None:
    with pytest.raises(ValidationError):
        LlmProviderCreate(
            name="Invalid",
            kind="openai",
            wire_protocol="guess",  # type: ignore[arg-type]
        )


def test_provider_schema_rejects_protocol_unsupported_by_kind() -> None:
    with pytest.raises(ValidationError, match="does not support"):
        LlmProviderCreate(
            name="Anthropic",
            kind="anthropic",
            wire_protocol="responses",
        )


def test_provider_update_validates_final_merged_kind_and_protocol() -> None:
    kind_change = LlmProviderUpdate(kind="anthropic")
    protocol_change = LlmProviderUpdate(wire_protocol="responses")

    with pytest.raises(ValueError, match="does not support"):
        kind_change.validate_merged_wire_protocol(
            current_kind="openai",
            current_wire_protocol="responses",
        )
    with pytest.raises(ValueError, match="does not support"):
        protocol_change.validate_merged_wire_protocol(
            current_kind="anthropic",
            current_wire_protocol="chat_completions",
        )

    assert protocol_change.validate_merged_wire_protocol(
        current_kind="openai_compatible",
        current_wire_protocol="chat_completions",
    ) == ("openai_compatible", "responses")
