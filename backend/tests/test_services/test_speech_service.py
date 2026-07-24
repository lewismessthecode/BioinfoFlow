from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from app.services.speech.audio import (
    MAX_NORMALIZED_AUDIO_BYTES,
    build_ffmpeg_command,
    normalize_audio,
)
from app.services.speech.client import OpenAICompatibleSpeechClient
from app.services.speech.errors import SpeechError


def test_build_ffmpeg_command_normalizes_to_16khz_mono_wav(tmp_path):
    source = tmp_path / "recording.webm"
    target = tmp_path / "recording.wav"

    command = build_ffmpeg_command(source, target)

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-t",
        "121",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(target),
    ]


@pytest.mark.asyncio
async def test_normalize_audio_returns_wav_and_cleans_temporary_files(monkeypatch):
    seen_paths = []

    class Process:
        returncode = 0

        async def communicate(self):
            command_target = seen_paths[-1]
            command_target.write_bytes(b"RIFF-normalized")
            return b"", b""

    async def fake_subprocess(*command, **kwargs):
        del kwargs
        seen_paths.extend([Path(command[6]), Path(command[-1])])
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    result = await normalize_audio(b"webm-data", filename="recording.webm")

    assert result == b"RIFF-normalized"
    assert all(not path.exists() for path in seen_paths)


@pytest.mark.asyncio
async def test_normalize_audio_maps_ffmpeg_failure_to_invalid_audio(monkeypatch):
    class Process:
        returncode = 1

        async def communicate(self):
            return b"", b"Invalid data found"

    async def fake_subprocess(*command, **kwargs):
        del command, kwargs
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    with pytest.raises(SpeechError) as raised:
        await normalize_audio(b"not-audio", filename="recording.webm")

    assert raised.value.code == "invalid_audio"


@pytest.mark.asyncio
async def test_normalize_audio_kills_ffmpeg_after_bounded_timeout(monkeypatch):
    killed = False
    waited = False

    class Process:
        returncode = None

        async def communicate(self):
            await asyncio.Future()

        def kill(self):
            nonlocal killed
            killed = True

        async def wait(self):
            nonlocal waited
            waited = True

    async def fake_subprocess(*command, **kwargs):
        del command, kwargs
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    with pytest.raises(SpeechError) as raised:
        await normalize_audio(
            b"slow-audio", filename="recording.webm", timeout_seconds=0.001
        )

    assert raised.value.code == "invalid_audio"
    assert killed is True
    assert waited is True


@pytest.mark.asyncio
async def test_normalize_audio_rejects_decoded_audio_over_120_seconds(monkeypatch):
    class Process:
        returncode = 0

        async def communicate(self):
            Path(command_target).write_bytes(b"0" * (MAX_NORMALIZED_AUDIO_BYTES + 1))
            return b"", b""

    command_target = ""

    async def fake_subprocess(*command, **kwargs):
        nonlocal command_target
        del kwargs
        command_target = command[-1]
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    with pytest.raises(SpeechError) as raised:
        await normalize_audio(b"long-audio", filename="recording.webm")

    assert raised.value.code == "invalid_audio"


@pytest.mark.asyncio
async def test_openai_compatible_client_sends_one_normalized_request():
    async def handler(request: httpx.Request):
        assert request.url == "http://asr:8000/v1/audio/transcriptions"
        assert request.headers["Authorization"] == "Bearer secret"
        body = await request.aread()
        assert b'name="model"' in body
        assert b"fun-asr-nano" in body
        assert b'name="language"' in body
        assert b"zh" in body
        assert b'name="prompt"' in body
        assert "Nextflow, MiniWDL".encode() in body
        assert b'filename="recording.wav"' in body
        return httpx.Response(200, json={"text": "请检查这个流程", "language": "zh"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenAICompatibleSpeechClient(
            base_url="http://asr:8000",
            api_key="secret",
            model="fun-asr-nano",
            timeout_seconds=90,
            http_client=http,
        )
        result = await client.transcribe(
            b"RIFF-data",
            language="zh",
            context_terms=["Nextflow", "MiniWDL"],
        )

    assert result.text == "请检查这个流程"
    assert result.language == "zh"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "authentication_failed"),
        (404, "model_not_installed"),
        (429, "rate_limited"),
        (500, "transcription_failed"),
    ],
)
@pytest.mark.asyncio
async def test_openai_compatible_client_normalizes_http_errors(status, code):
    async def handler(request: httpx.Request):
        return httpx.Response(status, request=request, json={"error": "failed"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenAICompatibleSpeechClient(
            base_url="http://asr:8000/v1",
            api_key="",
            model="large-v3-turbo",
            http_client=http,
        )
        with pytest.raises(SpeechError) as raised:
            await client.transcribe(b"RIFF-data", language="zh")

    assert raised.value.code == code


@pytest.mark.asyncio
async def test_openai_compatible_client_normalizes_connection_failure():
    async def handler(request: httpx.Request):
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenAICompatibleSpeechClient(
            base_url="http://asr:8000",
            api_key="",
            model="large-v3-turbo",
            http_client=http,
        )
        with pytest.raises(SpeechError) as raised:
            await client.transcribe(b"RIFF-data", language="zh")

    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_openai_compatible_client_probes_model_availability():
    async def handler(request: httpx.Request):
        assert request.url == "http://asr:8000/v1/models"
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"id": "large-v3-turbo"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenAICompatibleSpeechClient(
            base_url="http://asr:8000",
            api_key="",
            model="large-v3-turbo",
            http_client=http,
        )
        probe = await client.probe()

    assert probe.available is True
    assert probe.message is None


@pytest.mark.asyncio
async def test_openai_compatible_client_probe_reports_missing_model():
    async def handler(request: httpx.Request):
        return httpx.Response(200, request=request, json={"data": [{"id": "other"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenAICompatibleSpeechClient(
            base_url="http://asr:8000",
            api_key="",
            model="large-v3-turbo",
            http_client=http,
        )
        probe = await client.probe()

    assert probe.available is False
    assert probe.message == "The configured speech model is unavailable."
