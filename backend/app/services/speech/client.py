from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.services.speech.errors import SpeechError


@dataclass(frozen=True)
class SpeechTranscript:
    text: str
    language: str | None = None


@dataclass(frozen=True)
class SpeechProbe:
    available: bool
    message: str | None = None


class OpenAICompatibleSpeechClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 90.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = _transcription_endpoint(base_url)
        self.models_endpoint = _models_endpoint(base_url)
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    async def probe(self) -> SpeechProbe:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(min(self.timeout_seconds, 5.0), connect=3.0)
        )
        try:
            response = await client.get(self.models_endpoint, headers=headers)
            if response.status_code in {401, 403}:
                return SpeechProbe(False, "Speech provider authentication failed.")
            if response.status_code >= 400:
                return SpeechProbe(False, "Speech provider is unavailable.")
            payload = response.json()
            model_ids = {
                str(item.get("id"))
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            }
            if self.model not in model_ids:
                return SpeechProbe(
                    False, "The configured speech model is unavailable."
                )
            return SpeechProbe(True)
        except (httpx.RequestError, ValueError, TypeError):
            return SpeechProbe(False, "Speech provider is unavailable.")
        finally:
            if owns_client:
                await client.aclose()

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str,
        context_terms: list[str] | None = None,
    ) -> SpeechTranscript:
        fields = {"model": self.model, "language": language, "response_format": "json"}
        if context_terms:
            fields["prompt"] = ", ".join(context_terms)
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds, connect=5.0)
        )
        try:
            response = await client.post(
                self.endpoint,
                data=fields,
                files={"file": ("recording.wav", audio, "audio/wav")},
                headers=headers,
            )
            if response.status_code >= 400:
                raise _http_error(response.status_code)
            payload = response.json()
            text = str(payload.get("text") or "").strip()
            if not text:
                raise SpeechError(
                    "transcription_failed",
                    "The speech provider returned an empty transcript.",
                    502,
                )
            language_value = payload.get("language")
            return SpeechTranscript(
                text=text,
                language=str(language_value) if language_value else None,
            )
        except SpeechError:
            raise
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise SpeechError(
                "provider_unavailable",
                "The speech provider is unavailable.",
                503,
            ) from exc
        except (httpx.RequestError, ValueError, TypeError) as exc:
            raise SpeechError(
                "transcription_failed",
                "Speech transcription failed.",
                502,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()


def _transcription_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/audio/transcriptions"
    return f"{normalized}/v1/audio/transcriptions"


def _models_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/models"
    return f"{normalized}/v1/models"


def _http_error(status_code: int) -> SpeechError:
    if status_code in {401, 403}:
        return SpeechError(
            "authentication_failed", "Speech provider authentication failed.", 401
        )
    if status_code == 404:
        return SpeechError(
            "model_not_installed", "The configured speech model is unavailable.", 503
        )
    if status_code == 429:
        return SpeechError("rate_limited", "Speech provider rate limited.", 429)
    if status_code in {400, 415, 422}:
        return SpeechError("invalid_audio", "The speech provider rejected the audio.", 422)
    return SpeechError("transcription_failed", "Speech transcription failed.", 502)
