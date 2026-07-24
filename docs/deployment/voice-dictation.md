# Voice dictation deployment

Bioinfoflow records audio in the browser, converts it once to 16 kHz mono WAV,
and calls an OpenAI-compatible `POST /v1/audio/transcriptions` endpoint. The
same service must expose `GET /v1/models` and list the configured model so the
composer can distinguish configuration from actual readiness. The
backend does not load ASR models and never falls back to a cloud service unless
you explicitly configure a cloud URL.

## Choose one runtime

For Chinese on a Linux GPU, use Fun-ASR-Nano-2512:

```env
ASR_PROVIDER=funasr
ASR_BASE_URL=http://asr-funasr:8000
ASR_MODEL=FunAudioLLM/Fun-ASR-Nano-2512
ASR_DEVICE=cuda
```

```bash
docker compose --profile voice-funasr up -d --build asr-funasr backend frontend
docker compose ps
docker compose logs -f asr-funasr
```

For macOS, a general CPU host, or broader multilingual dictation, use
faster-whisper:

```env
ASR_PROVIDER=whisper
ASR_BASE_URL=http://asr-whisper:8000
ASR_MODEL=large-v3-turbo
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
```

```bash
docker compose --profile voice-whisper up -d --build asr-whisper backend frontend
docker compose ps
docker compose logs -f asr-whisper
```

Do not enable both profiles unless you are deliberately comparing models. Model
files are cached under `BIOINFOFLOW_HOME/models/asr/`; the first start downloads
and warms the selected model and can take several minutes.

## Cloud or another compatible server

Point the same settings at any service implementing the OpenAI audio
transcription and model-list contracts:

```env
ASR_PROVIDER=openai
ASR_BASE_URL=https://api.openai.com
ASR_MODEL=gpt-4o-mini-transcribe
ASR_API_KEY=replace-me
ASR_LANGUAGE=zh
```

Restart the backend after changing ASR settings. Confirm discovery without
exposing the key:

```bash
curl -s http://localhost:8000/api/v1/speech/status
```

The sidecars have no host ports; only the Bioinfoflow backend can reach them on
the Compose network. Audio and transcripts stay in request memory and are not
persisted or logged.
