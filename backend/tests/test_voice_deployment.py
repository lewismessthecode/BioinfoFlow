from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_voice_sidecars_are_opt_in_and_share_one_openai_compatible_contract():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    funasr = compose["services"]["asr-funasr"]
    whisper = compose["services"]["asr-whisper"]
    assert funasr["profiles"] == ["voice-funasr"]
    assert whisper["profiles"] == ["voice-whisper"]
    assert "ports" not in funasr
    assert "ports" not in whisper
    assert funasr["gpus"] == "all"
    assert funasr["healthcheck"]["test"][-1].endswith("/health")
    assert whisper["healthcheck"]["test"][-1].endswith("/health")


def test_backend_receives_only_explicit_asr_configuration():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["backend"]["environment"]

    assert environment["ASR_BASE_URL"] == "${ASR_BASE_URL:-}"
    assert environment["ASR_MODEL"] == "${ASR_MODEL:-}"
    assert environment["ASR_API_KEY"] == "${ASR_API_KEY:-}"


def test_backend_image_contains_the_single_audio_converter():
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    package_block = dockerfile.split("apt-get install -y --no-install-recommends", 1)[1]
    package_block = package_block.split("&&", 1)[0]
    assert "ffmpeg" in package_block.split()


def test_sidecar_inference_runs_off_the_healthcheck_event_loop():
    for runtime in ("funasr", "whisper"):
        source = (ROOT / "deploy" / "voice" / runtime / "server.py").read_text(
            encoding="utf-8"
        )
        assert "asyncio.Lock()" in source
        assert "await asyncio.to_thread(" in source
