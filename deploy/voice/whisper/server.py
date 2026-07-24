from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from faster_whisper import WhisperModel

app = FastAPI(title="Bioinfoflow faster-whisper adapter")
model_name = os.environ.get("ASR_MODEL", "large-v3-turbo")
model = WhisperModel(
    model_name,
    device=os.environ.get("ASR_DEVICE", "cpu"),
    compute_type=os.environ.get("ASR_COMPUTE_TYPE", "int8"),
)
inference_lock = asyncio.Lock()


def _transcribe_file(path: str, language: str, prompt: str) -> tuple[str, str]:
    segments, info = model.transcribe(
        path,
        language=language or None,
        initial_prompt=prompt or None,
        vad_filter=True,
    )
    text = "".join(segment.text for segment in segments).strip()
    return text, info.language or language


@app.get("/health")
async def health():
    return {"status": "ready", "model": model_name}


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": model_name, "object": "model"}]}


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model_requested: str = Form(alias="model"),
    language: str = Form(default="zh"),
    prompt: str = Form(default=""),
    response_format: str = Form(default="json"),
):
    del response_format
    if model_requested != model_name:
        raise HTTPException(status_code=404, detail="model not installed")
    suffix = Path(file.filename or "recording.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix) as audio:
        audio.write(await file.read())
        audio.flush()
        async with inference_lock:
            text, detected_language = await asyncio.to_thread(
                _transcribe_file, audio.name, language, prompt
            )
    return {"text": text, "language": detected_language}
