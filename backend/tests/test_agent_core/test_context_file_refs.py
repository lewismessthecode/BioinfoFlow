from pathlib import Path

from app.services.agent_core import service as service_module


class _FakeFilesystemPolicy:
    def require_allowed_path(self, path, *, must_exist=True, allow_directory=False):
        target = Path(path)
        if must_exist:
            assert target.exists()
        if not allow_directory:
            assert target.is_file()
        return target


def test_generated_session_title_preserves_prompt_language():
    assert service_module._generated_session_title("新建一个 WGS 流程，包含质控和比对") == "新建一个 WGS 流程，包含质控和比对"
    assert service_module._generated_session_title("Summarize this very long workflow request with many details") == "Summarize this very long"


def test_file_ref_input_parts_expand_into_bounded_transcript_text(tmp_path, monkeypatch):
    workflow = tmp_path / "workflow.wdl"
    workflow.write_text("version 1.0\nworkflow demo {}", encoding="utf-8")
    monkeypatch.setattr(service_module, "FilesystemPolicy", lambda: _FakeFilesystemPolicy())

    parts = service_module._transcript_parts_for_turn(
        input_text="Use the attached workflow.",
        input_parts=[
            {"type": "text", "text": "Use the attached workflow."},
            {"kind": "file_ref", "path": str(workflow), "label": "workflow.wdl"},
        ],
    )

    text = "\n".join(part["text"] for part in parts)
    assert "Use the attached workflow." in text
    assert "Attached file: workflow.wdl" in text
    assert "workflow demo" in text
