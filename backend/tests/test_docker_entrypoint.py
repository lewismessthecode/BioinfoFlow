from __future__ import annotations

from pathlib import Path


def test_entrypoint_uses_backend_settings_for_default_bioinfoflow_home():
    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "docker-entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert "/srv/bioinfoflow" not in script
    assert "from app.config import Settings" in script
    assert "Settings(_env_file=None).bioinfoflow_home" in script
    assert "export BIOINFOFLOW_HOME=" in script
