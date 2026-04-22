from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.common import Meta, Pagination
from app.schemas.project import ProjectRead
from app.schemas.file import FileInfo, FileType


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
