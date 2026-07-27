# Voice dictation deployment

The speech model is separate from the Bioinfoflow application. Bioinfoflow
records audio in the browser, converts it once to 16 kHz mono WAV, and calls an
OpenAI-compatible ASR service over HTTP. Fun-ASR or faster-whisper runs in its
own container and can be started, stopped, upgraded, or replaced without
changing the recorder or composer code.

```text
Browser MediaRecorder
        ↓
Bioinfoflow backend
  - authenticates the user
  - enforces upload, duration, and timeout limits
  - converts once to 16 kHz mono WAV
        ↓
OpenAI-compatible ASR endpoint
  - Fun-ASR sidecar
  - faster-whisper sidecar
  - explicit cloud or private endpoint
        ↓
Editable text inserted at the composer caret
```

The ASR service must expose `GET /v1/models` and
`POST /v1/audio/transcriptions`. The backend does not load ASR models and never
falls back to a cloud service unless you explicitly configure a cloud URL.

The built-in sidecars currently belong to the source-build `docker-compose.yml`.
The one-line localhost installer does not bundle them.

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

On Apple Silicon, Docker runs faster-whisper inside a Linux ARM64 VM. The
included image supports ARM64 and CPU `int8`, but it cannot use Metal or the
Apple Neural Engine. For a 16 GB Mac, use `ASR_MODEL=small` for the first real
deployment or `ASR_MODEL=tiny` for a smoke test; move to `large-v3-turbo` when
the extra accuracy is worth the larger download and slower CPU inference.

Optional Hugging Face authentication and network settings are passed through
when configured in `.env`:

```env
HF_TOKEN=<optional-read-token>
# HF_HUB_DISABLE_XET=1
# HTTPS_PROXY=http://host.docker.internal:7890
# HTTP_PROXY=http://host.docker.internal:7890
```

Bioinfoflow does not hard-code a third-party Hugging Face mirror. If a custom
endpoint is required, set `HF_ENDPOINT` explicitly for your deployment.

```bash
docker compose --profile voice-whisper up -d --build asr-whisper backend frontend
docker compose ps
docker compose logs -f asr-whisper
```

Do not enable both profiles unless you are deliberately comparing models. Model
files are cached under `BIOINFOFLOW_HOME/models/asr/`; the first start downloads
and warms the selected model and can take several minutes.

## Verify the local connection

The sidecars publish no host port. Check them through the Compose network:

```bash
docker compose ps
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://asr-funasr:8000/health').read().decode())"
# Replace asr-funasr with asr-whisper when using faster-whisper.
```

After changing `.env`, recreate the backend rather than using
`docker compose restart backend`, because restart does not load new environment
values. Sign in and refresh the Agent page; the microphone becomes available
after the backend confirms that `/v1/models` lists the configured model.

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

Recreate the backend after changing ASR settings:

```bash
docker compose up -d --build --force-recreate backend frontend
```

The sidecars have no host ports; only the Bioinfoflow backend can reach them on
the Compose network. Audio may use short-lived temporary files during format
conversion and inference; those files are removed when the request completes.
Bioinfoflow does not persist audio or transcripts in its databases and does not
log their content.

## Troubleshooting

If the microphone is disabled, check:

1. `ASR_BASE_URL` and `ASR_MODEL` are not empty.
2. The configured model ID exactly matches an entry returned by `/v1/models`.
3. The selected sidecar is healthy in `docker compose ps`.
4. The backend was recreated after `.env` changed.
5. The browser has microphone permission and the page uses localhost or HTTPS.

Inspect metadata-only application logs and the selected model log:

```bash
docker compose logs --tail=100 backend
docker compose logs --tail=100 asr-funasr
# or: docker compose logs --tail=100 asr-whisper
```

If Fun-ASR repeatedly exits during `uvicorn server:app`, inspect the first
import exception rather than changing the restart policy. The included image
installs matching `torch` and `torchaudio` versions required by FunASR. Rebuild
without reusing an older image, then verify the runtime imports before waiting
for the model download:

```bash
docker compose --profile voice-funasr build --no-cache asr-funasr
docker compose --profile voice-funasr run --rm --no-deps --entrypoint python asr-funasr -c "import torch, torchaudio, funasr; print(torch.__version__)"
docker compose --profile voice-funasr up -d asr-funasr backend frontend
docker compose ps
docker compose logs --tail=100 asr-funasr
```
