from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from app.services.speech.errors import SpeechError

MAX_AUDIO_SECONDS = 120
_CONVERSION_SECONDS = MAX_AUDIO_SECONDS + 1
MAX_NORMALIZED_AUDIO_BYTES = MAX_AUDIO_SECONDS * 16_000 * 2 + 4096


def build_ffmpeg_command(source: Path, target: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-t",
        str(_CONVERSION_SECONDS),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(target),
    ]


async def normalize_audio(
    content: bytes, *, filename: str, timeout_seconds: float = 30.0
) -> bytes:
    suffix = Path(filename).suffix.lower() or ".audio"
    with tempfile.TemporaryDirectory(prefix="bioinfoflow-asr-") as directory:
        source = Path(directory) / f"input{suffix}"
        target = Path(directory) / "normalized.wav"
        source.write_bytes(content)
        try:
            process = await asyncio.create_subprocess_exec(
                *build_ffmpeg_command(source, target),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise SpeechError(
                "provider_unavailable",
                "Audio conversion is unavailable on this server.",
                503,
            ) from exc
        try:
            await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise SpeechError(
                "invalid_audio",
                "The recording took too long to decode.",
                422,
            ) from exc
        if process.returncode != 0 or not target.exists():
            raise SpeechError(
                "invalid_audio",
                "The recording could not be decoded.",
                422,
            )
        if target.stat().st_size > MAX_NORMALIZED_AUDIO_BYTES:
            raise SpeechError(
                "invalid_audio",
                f"Recordings cannot exceed {MAX_AUDIO_SECONDS} seconds.",
                422,
            )
        return target.read_bytes()
