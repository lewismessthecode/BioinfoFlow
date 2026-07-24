from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from funasr import AutoModel

app = FastAPI(title="Bioinfoflow Fun-ASR adapter")
model_name = os.environ.get("ASR_MODEL", "FunAudioLLM/Fun-ASR-Nano-2512")
model = AutoModel(model=model_name, device=os.environ.get("ASR_DEVICE", "cpu"))
inference_lock = asyncio.Lock()


def _transcribe_file(path: str, language: str, prompt: str) -> str:
    result = model.generate(
        input=path,
        cache={},
        language=language,
        hotword=prompt or None,
    )
    return "".join(str(item.get("text") or "") for item in result).strip()


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
    if model_requested not in {model_name, "fun-asr-nano"}:
        raise HTTPException(status_code=404, detail="model not installed")
    suffix = Path(file.filename or "recording.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix) as audio:
        audio.write(await file.read())
        audio.flush()
        async with inference_lock:
            text = await asyncio.to_thread(
                _transcribe_file, audio.name, language, prompt
            )
    return {"text": text, "language": language}
