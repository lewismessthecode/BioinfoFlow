"""Tests for FileService — listing, reading, writing, scanning, path safety."""

from __future__ import annotations

from pathlib import Path

import pytest

import app.models  # noqa: F401
from app.models.project import Project
from app.services.file_service import FileService, _detect_file_type, _parse_fastq


# ---------------------------------------------------------------------------
# Pure function unit tests (no DB)
# ---------------------------------------------------------------------------


class TestDetectFileType:
    EXTENSIONS = {
        "fastq": [".fastq", ".fq", ".fastq.gz", ".fq.gz"],
        "bam": [".bam"],
        "vcf": [".vcf", ".vcf.gz"],
    }

    def test_fastq_gz(self):
        assert _detect_file_type(Path("sample_R1.fastq.gz"), self.EXTENSIONS) == "fastq"

    def test_bam(self):
        assert _detect_file_type(Path("aligned.bam"), self.EXTENSIONS) == "bam"

    def test_vcf_gz(self):
        assert _detect_file_type(Path("variants.vcf.gz"), self.EXTENSIONS) == "vcf"

    def test_unknown_extension(self):
        assert _detect_file_type(Path("readme.txt"), self.EXTENSIONS) is None

    def test_case_insensitive(self):
        assert _detect_file_type(Path("SAMPLE.FASTQ.GZ"), self.EXTENSIONS) == "fastq"


class TestParseFastq:
    def test_paired_r1(self):
        sample, read = _parse_fastq("sample1_R1.fastq.gz")
        assert sample == "sample1"
        assert read == "1"

    def test_paired_r2(self):
        sample, read = _parse_fastq("sample1_R2.fq.gz")
        assert sample == "sample1"
        assert read == "2"

    def test_single_end(self):
        sample, read = _parse_fastq("single_sample.fastq")
        assert sample == "single_sample"
        assert read is None

    def test_numbered_suffix(self):
        sample, read = _parse_fastq("sample_1.fastq.gz")
        assert sample == "sample"
        assert read == "1"

    def test_lane_suffix(self):
        sample, read = _parse_fastq("sample_R1_001.fastq.gz")
        assert sample == "sample"
        assert read == "1"


# ---------------------------------------------------------------------------
# FileService integration tests (require DB + filesystem)
# ---------------------------------------------------------------------------


async def _create_project(db_session, workspace: Path) -> str:
    project = Project(
        name="file-test-project",
        storage_mode="external", external_root_path=str(workspace),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return str(project.id)


@pytest.mark.asyncio
async def test_list_files_empty_dir(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.list_files(project_id=project_id)
    assert result.path == "."
    assert result.files == []


@pytest.mark.asyncio
async def test_list_files_with_contents(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "file1.txt").write_text("hello")
    (workspace / "subdir").mkdir()

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.list_files(project_id=project_id)
    names = {f.name for f in result.files}
    assert "file1.txt" in names
    assert "subdir" in names


@pytest.mark.asyncio
async def test_list_files_with_pattern(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "data.csv").write_text("a,b")
    (workspace / "readme.md").write_text("# hi")

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.list_files(project_id=project_id, pattern="*.csv")
    assert len(result.files) == 1
    assert result.files[0].name == "data.csv"


@pytest.mark.asyncio
async def test_read_file(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test.txt").write_text("line1\nline2\nline3\n")

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.read_file(project_id=project_id, path="test.txt")
    assert "line1" in result.content
    assert result.total_lines == 3


@pytest.mark.asyncio
async def test_read_file_with_offset(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    lines = "\n".join(f"line{i}" for i in range(10)) + "\n"
    (workspace / "big.txt").write_text(lines)

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.read_file(
        project_id=project_id, path="big.txt", lines=3, offset=5
    )
    assert result.total_lines == 10
    assert result.truncated is True
    assert "line5" in result.content


@pytest.mark.asyncio
async def test_write_file(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.write_file(
        project_id=project_id, path="new.txt", content="hello world"
    )
    assert result["path"] == "new.txt"
    assert (workspace / "new.txt").read_text() == "hello world"


@pytest.mark.asyncio
async def test_write_file_creates_subdirs(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    await service.write_file(
        project_id=project_id, path="sub/dir/file.txt", content="nested"
    )
    assert (workspace / "sub" / "dir" / "file.txt").read_text() == "nested"


@pytest.mark.asyncio
async def test_delete_path_file(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "delete_me.txt"
    target.write_text("bye")

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.delete_path(project_id=project_id, path="delete_me.txt")
    assert result["path"] == "delete_me.txt"
    assert not target.exists()


@pytest.mark.asyncio
async def test_delete_path_rejects_root(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    with pytest.raises(PermissionError, match="cannot delete workspace root"):
        await service.delete_path(project_id=project_id, path=".")


@pytest.mark.asyncio
async def test_safe_path_rejects_traversal(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    with pytest.raises(PermissionError, match="path escapes workspace"):
        await service.list_files(project_id=project_id, path="../../etc")


@pytest.mark.asyncio
async def test_write_upload(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.write_upload(
        project_id=project_id,
        path=None,
        filename="upload.csv",
        content=b"a,b\n1,2",
    )
    assert result["path"] == "upload.csv"
    assert (workspace / "upload.csv").read_bytes() == b"a,b\n1,2"


@pytest.mark.asyncio
async def test_write_upload_rejects_duplicate(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "exists.csv").write_text("old")

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    with pytest.raises(FileExistsError):
        await service.write_upload(
            project_id=project_id,
            path=None,
            filename="exists.csv",
            content=b"new",
        )


@pytest.mark.asyncio
async def test_scan_directory_finds_fastq(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample1_R1.fastq.gz").write_bytes(b"fake")
    (workspace / "sample1_R2.fastq.gz").write_bytes(b"fake")

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.scan_directory(
        project_id=project_id, file_types=["fastq"]
    )
    assert result.total_samples == 1
    assert result.detected_samples[0].sample_id == "sample1"
    assert len(result.detected_samples[0].files) == 2
    assert result.file_format == "paired-end"
    assert result.compression == "gzip"


@pytest.mark.asyncio
async def test_scan_directory_empty(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    result = await service.scan_directory(project_id=project_id)
    assert result.total_samples == 0
    assert result.detected_samples == []


@pytest.mark.asyncio
async def test_resolve_path(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "data").mkdir()

    project_id = await _create_project(db_session, workspace)
    service = FileService(db_session)

    target, root = await service.resolve_path(project_id=project_id, path="data")
    assert target == workspace / "data"
    assert root == workspace


@pytest.mark.asyncio
async def test_project_not_found(db_session):
    from uuid import uuid4

    service = FileService(db_session)
    with pytest.raises(FileNotFoundError, match="project not found"):
        await service.list_files(project_id=str(uuid4()))
