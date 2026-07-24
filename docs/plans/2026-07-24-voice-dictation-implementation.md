# Voice Dictation Implementation Plan

**Goal:** Deliver private-by-default Chinese voice dictation in the Agent
composer through one OpenAI-compatible ASR boundary.

**Method:** Strict TDD. Every behavior starts with a focused failing test, then
the smallest implementation that makes it pass, followed by refactoring while
green. Full suites run after focused cycles.

## 1. Backend configuration and status contract

**Files:** `backend/app/config.py`, `backend/app/schemas/speech.py`,
`backend/app/api/v1/speech.py`, `backend/app/api/v1/router.py`, and focused tests.

1. Add failing config tests for disabled defaults and explicit provider values.
2. Add minimal ASR settings: provider, base URL, API key, model, language,
   context terms, upload limit, and timeout.
3. Add failing API tests for disabled and configured status responses.
4. Implement the authenticated status endpoint without secret exposure.

## 2. Backend audio normalization and provider client

**Files:** `backend/app/services/speech/` and focused service tests.

1. Test ffmpeg command construction, successful conversion, invalid audio, and
   temporary-file cleanup.
2. Implement a single async converter producing 16 kHz mono WAV.
3. Test multipart request fields, authorization header, default language,
   context prompt, response parsing, timeout/network failures, and HTTP error
   normalization.
4. Implement one OpenAI-compatible HTTP client. Do not create provider-specific
   classes until incompatible behavior actually exists.

## 3. Backend transcription endpoint

**Files:** `backend/app/api/v1/speech.py` and API tests.

1. Test disabled provider, empty/oversized/unsupported uploads, successful
   transcription, and every normalized provider error.
2. Implement bounded upload reading, one conversion, one provider call, safe
   structured logging, and response schemas.

## 4. Frontend API boundary

**Files:** `frontend/lib/speech.ts` and unit tests.

1. Test status decoding, multipart upload, response decoding, and normalized
   API failures.
2. Implement small typed functions using the existing authenticated request
   layer.

## 5. Recorder state machine

**Files:** `frontend/hooks/use-voice-dictation.ts` and hook tests.

1. Test unsupported browser, permission failure, MIME fallback, recording,
   elapsed time, 120-second stop, RMS levels, cancel/discard, upload success,
   upload failure, and resource cleanup.
2. Implement MediaRecorder plus Web Audio analyser with explicit states:
   `idle`, `recording`, `transcribing`, and `error`.
3. Keep audio in memory only and stop tracks/audio contexts on every terminal
   path and unmount.

## 6. Composer integration and UI

**Files:** `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`, a
small voice control component if extraction improves readability, composer
tests, and both locale JSON files.

1. Test disabled discovery, start/stop interaction, recording/transcribing
   labels, send disabling, Escape cancellation, error preservation, no
   auto-submit, and caret insertion with focus restoration.
2. Implement the microphone immediately left of send using existing button,
   icon, spacing, focus, and semantic color conventions.
3. Keep animation functional and restrained; honor reduced motion.
4. Add matching English and Simplified Chinese copy.

## 7. Optional local runtimes and documentation

**Files:** Compose configuration, `.env.example`, and focused deployment docs.

1. Add contract tests or static assertions for opt-in voice profiles and cache
   mounts where practical.
2. Define independent Fun-ASR and faster-whisper services. Neither starts in the
   default stack.
3. Document exact selection, health check, warm-up, cache, GPU/CPU, and cloud
   configuration commands. State clearly that users run only one local model.

## 8. Verification and review

1. Run focused tests during every red/green cycle.
2. Run backend `pytest` and `ruff check .`.
3. Run frontend `lint`, `test`, `lint:i18n`, and `lint:dead-code`.
4. Run `git diff --check` and inspect the complete diff for leaked secrets,
   transcript logging, accidental auto-send, and unrelated changes.
5. Request an independent code review; fix all critical and important findings
   and repeat affected verification.
6. Fetch and rebase onto current `origin/main`, then repeat proportional tests.
7. Commit with a Conventional Commit message, push the branch, and open a ready
   PR whose body includes architecture, deployment, privacy, and verification.
