# Voice Dictation Design

**Date:** 2026-07-24

## Goal

Add Chinese-first speech-to-text dictation to the Agent composer. The user clicks
the microphone, records up to 120 seconds, stops recording, waits for
transcription, and receives editable text at the current caret. Dictation never
sends a message automatically.

## First-principles boundary

The product needs text, not an audio conversation. Therefore v1 contains only:

1. browser audio capture and a small level indicator;
2. one backend upload and normalization boundary;
3. one OpenAI-compatible transcription client;
4. insertion of the returned text into the existing composer.

It deliberately excludes realtime streaming, TTS, client VAD, silence detection,
continuous listening, playback, microphone selection, and automatic fallback.
Those features add state and failure modes without improving the core dictation
job.

## Architecture

```text
MediaRecorder (WebM/Opus or browser fallback)
  -> POST /api/v1/speech/transcriptions
  -> ffmpeg: 16 kHz mono WAV
  -> POST {ASR_BASE_URL}/v1/audio/transcriptions
  -> normalized { text, language? }
  -> insert at composer selection
```

Bioinfoflow never imports or loads an ASR model. Fun-ASR, faster-whisper, and a
cloud vendor are deployment profiles behind the same HTTP contract. Only the
selected local service should be installed and started.

## Backend contract

- `GET /api/v1/speech/status` probes the provider's OpenAI-compatible
  `GET /v1/models` endpoint and distinguishes configured from actually ready,
  without exposing secrets.
- `POST /api/v1/speech/transcriptions` accepts one multipart audio file, rejects
  files over 20 MiB, normalizes it once with ffmpeg, and calls the configured
  OpenAI-compatible endpoint with a 90-second timeout.
- Default language is `zh`. Domain terms are represented as one context list and
  converted to a prompt at the provider boundary.
- Audio bytes and transcript text are neither persisted nor logged.
- Errors are normalized to: `provider_unavailable`, `model_not_installed`,
  `invalid_audio`, `transcription_failed`, `authentication_failed`, and
  `rate_limited`.

Configuration:

```env
ASR_PROVIDER=funasr
ASR_BASE_URL=http://funasr:8000
ASR_MODEL=fun-asr-nano
ASR_LANGUAGE=zh
ASR_API_KEY=
```

An empty `ASR_BASE_URL` disables dictation. There is no implicit cloud fallback.

## Frontend behavior

- The microphone button sits immediately left of send.
- Unsupported browsers or disabled backend configuration keep the control
  visible but disabled with an accessible explanation.
- Idle click requests microphone permission and begins recording.
- Recording shows a stop-square, elapsed time, and five understated RMS bars.
- Stop uploads the blob and shows a transcription state.
- Success inserts text at the captured caret (append fallback), restores focus,
  and leaves the draft editable.
- Failure preserves the draft, shows an inline status and toast, and returns to
  idle.
- `Escape` cancels and discards the current recording.
- Send is disabled while recording or transcribing. A running agent does not
  prevent dictation for the next turn.

## Deployment

Docker Compose exposes opt-in voice profiles for a persistent Fun-ASR service and
a persistent faster-whisper service. Sidecars remain internal to the Compose
network and store model caches below `BIOINFOFLOW_HOME/models/asr/`. Operators
select one profile and point the backend at it; Bioinfoflow does not download
both models.

## Security and observability

- Treat audio and transcript as ephemeral request data.
- Do not include API keys, audio, prompts, or transcript content in logs.
- Safe metrics are provider, model, input MIME type, duration when known,
  latency, output character count, and normalized error code.
- Cloud transmission happens only when the operator explicitly configures a
  cloud base URL.
