from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.config import settings
from app.services.speech.audio import normalize_audio
from app.services.speech.client import OpenAICompatibleSpeechClient
from app.services.speech.errors import SpeechError
from app.utils.logging import get_logger
from app.utils.responses import error_response, success_response

router = APIRouter(prefix="/speech", tags=["speech"])
logger = get_logger(__name__)


def create_speech_client() -> OpenAICompatibleSpeechClient:
    return OpenAICompatibleSpeechClient(
        base_url=settings.asr_base_url,
        api_key=settings.asr_api_key,
        model=settings.asr_model,
        timeout_seconds=settings.asr_timeout_seconds,
    )


@router.get("/status")
async def speech_status(
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    del user
    configured = bool(settings.asr_base_url.strip() and settings.asr_model.strip())
    probe = await create_speech_client().probe() if configured else None
    available = bool(probe and probe.available)
    return success_response(
        {
            "configured": configured,
            "available": available,
            "provider": settings.asr_provider or None,
            "model": settings.asr_model or None,
            "language": settings.asr_language,
            "message": (
                probe.message
                if probe
                else "Speech recognition is not configured."
            ),
        },
        request=request,
    )


@router.post("/transcriptions")
async def transcribe_speech(
    request: Request,
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
):
    del user
    if not settings.asr_base_url.strip() or not settings.asr_model.strip():
        return _speech_error_response(
            request,
            SpeechError(
                "provider_unavailable", "Speech recognition is not configured.", 503
            ),
        )
    content_type = (file.content_type or "").lower()
    if content_type and not (
        content_type.startswith("audio/") or content_type == "application/octet-stream"
    ):
        return _speech_error_response(
            request, SpeechError("invalid_audio", "Unsupported audio type.", 422)
        )
    content = await file.read(settings.asr_max_upload_size_bytes + 1)
    if not content or len(content) > settings.asr_max_upload_size_bytes:
        status_code = 413 if content else 422
        return _speech_error_response(
            request,
            SpeechError("invalid_audio", "The recording is empty or too large.", status_code),
        )

    started = perf_counter()
    try:
        wav = await normalize_audio(content, filename=file.filename or "recording.audio")
        transcript = await create_speech_client().transcribe(
            wav,
            language=settings.asr_language,
            context_terms=settings.asr_context_terms,
        )
    except SpeechError as exc:
        logger.warning(
            "speech.transcription.failed",
            provider=settings.asr_provider or "compatible",
            model=settings.asr_model,
            mime_type=content_type or "unknown",
            latency_ms=round((perf_counter() - started) * 1000),
            error_code=exc.code,
        )
        return _speech_error_response(request, exc)

    logger.info(
        "speech.transcription.complete",
        provider=settings.asr_provider or "compatible",
        model=settings.asr_model,
        mime_type=content_type or "unknown",
        latency_ms=round((perf_counter() - started) * 1000),
        character_count=len(transcript.text),
    )
    return success_response(
        {"text": transcript.text, "language": transcript.language}, request=request
    )


def _speech_error_response(request: Request, error: SpeechError):
    return error_response(
        code=error.code,
        message=error.message,
        status_code=error.status_code,
        request=request,
    )
