from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.speech.errors import SpeechError


@pytest.fixture(autouse=True)
def speech_settings(monkeypatch):
    monkeypatch.setattr(settings, "asr_provider", "")
    monkeypatch.setattr(settings, "asr_base_url", "")
    monkeypatch.setattr(settings, "asr_api_key", "")
    monkeypatch.setattr(settings, "asr_model", "")
    monkeypatch.setattr(settings, "asr_language", "zh")
    monkeypatch.setattr(settings, "asr_context_terms", [])
    monkeypatch.setattr(settings, "asr_max_upload_size_bytes", 20 * 1024 * 1024)
    monkeypatch.setattr(settings, "asr_timeout_seconds", 90.0)


@pytest.mark.asyncio
async def test_speech_status_reports_disabled_without_exposing_secret(async_client):
    response = await async_client.get("/api/v1/speech/status")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "configured": False,
        "available": False,
        "provider": None,
        "model": None,
        "language": "zh",
        "message": "Speech recognition is not configured.",
    }
    assert "api_key" not in response.text.lower()


@pytest.mark.asyncio
async def test_speech_status_reports_configured_provider(async_client, monkeypatch):
    monkeypatch.setattr(settings, "asr_provider", "funasr")
    monkeypatch.setattr(settings, "asr_base_url", "http://funasr:8000")
    monkeypatch.setattr(settings, "asr_api_key", "do-not-expose")
    monkeypatch.setattr(settings, "asr_model", "fun-asr-nano")
    class Client:
        async def probe(self):
            return SimpleNamespace(available=True, message=None)
    monkeypatch.setattr("app.api.v1.speech.create_speech_client", lambda: Client())

    response = await async_client.get("/api/v1/speech/status")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "configured": True,
        "available": True,
        "provider": "funasr",
        "model": "fun-asr-nano",
        "language": "zh",
        "message": None,
    }
    assert "do-not-expose" not in response.text


@pytest.mark.asyncio
async def test_speech_status_reports_configured_but_unreachable_provider(
    async_client, monkeypatch
):
    monkeypatch.setattr(settings, "asr_provider", "whisper")
    monkeypatch.setattr(settings, "asr_base_url", "http://whisper:8000")
    monkeypatch.setattr(settings, "asr_model", "large-v3-turbo")

    class Client:
        async def probe(self):
            return SimpleNamespace(
                available=False, message="Speech provider is unavailable."
            )

    monkeypatch.setattr("app.api.v1.speech.create_speech_client", lambda: Client())

    response = await async_client.get("/api/v1/speech/status")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "configured": True,
        "available": False,
        "provider": "whisper",
        "model": "large-v3-turbo",
        "language": "zh",
        "message": "Speech provider is unavailable.",
    }


@pytest.mark.asyncio
async def test_transcription_rejects_request_when_provider_disabled(async_client):
    response = await async_client.post(
        "/api/v1/speech/transcriptions",
        files={"file": ("recording.webm", b"audio", "audio/webm")},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_transcription_rejects_oversized_audio(async_client, monkeypatch):
    monkeypatch.setattr(settings, "asr_base_url", "http://asr:8000")
    monkeypatch.setattr(settings, "asr_model", "model")
    monkeypatch.setattr(settings, "asr_max_upload_size_bytes", 4)

    response = await async_client.post(
        "/api/v1/speech/transcriptions",
        files={"file": ("recording.webm", b"12345", "audio/webm")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "invalid_audio"


@pytest.mark.asyncio
async def test_transcription_converts_once_and_returns_normalized_text(
    async_client, monkeypatch
):
    monkeypatch.setattr(settings, "asr_provider", "whisper")
    monkeypatch.setattr(settings, "asr_base_url", "http://whisper:8000")
    monkeypatch.setattr(settings, "asr_model", "large-v3-turbo")
    monkeypatch.setattr(settings, "asr_context_terms", ["FASTQ", "Nextflow"])
    normalized = []
    calls = []

    async def fake_normalize(content, *, filename):
        normalized.append((content, filename))
        return b"RIFF-wav"

    class Client:
        async def transcribe(self, audio, *, language, context_terms):
            calls.append((audio, language, context_terms))
            return SimpleNamespace(text="检查 FASTQ 文件", language="zh")

    monkeypatch.setattr("app.api.v1.speech.normalize_audio", fake_normalize)
    monkeypatch.setattr("app.api.v1.speech.create_speech_client", lambda: Client())

    response = await async_client.post(
        "/api/v1/speech/transcriptions",
        files={"file": ("recording.webm", b"webm", "audio/webm")},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"text": "检查 FASTQ 文件", "language": "zh"}
    assert normalized == [(b"webm", "recording.webm")]
    assert calls == [(b"RIFF-wav", "zh", ["FASTQ", "Nextflow"])]


@pytest.mark.asyncio
async def test_transcription_preserves_normalized_provider_error(async_client, monkeypatch):
    monkeypatch.setattr(settings, "asr_base_url", "http://asr:8000")
    monkeypatch.setattr(settings, "asr_model", "model")

    async def fake_normalize(content, *, filename):
        del content, filename
        return b"RIFF-wav"

    class Client:
        async def transcribe(self, *args, **kwargs):
            del args, kwargs
            raise SpeechError("rate_limited", "Speech provider rate limited.", 429)

    monkeypatch.setattr("app.api.v1.speech.normalize_audio", fake_normalize)
    monkeypatch.setattr("app.api.v1.speech.create_speech_client", lambda: Client())

    response = await async_client.post(
        "/api/v1/speech/transcriptions",
        files={"file": ("recording.webm", b"webm", "audio/webm")},
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
