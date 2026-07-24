# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=0 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=0

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

# ── System dependencies ──────────────────────────────────────
# default-jre-headless (~200MB) is required for Nextflow.
# git is required by uv when installing git+URL deps (e.g. hermes-agent).
ARG APT_MIRROR=
RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}/debian|g; s|http://deb.debian.org/debian-security|${APT_MIRROR}/debian-security|g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      btop \
      bubblewrap \
      curl \
      default-jre-headless \
      ffmpeg \
      git \
      procps && \
    rm -rf /var/lib/apt/lists/*

# ── Install Nextflow ──────────────────────────────────────────
RUN curl -fsSL https://get.nextflow.io | bash && \
    mv nextflow /usr/local/bin/ && \
    chmod +x /usr/local/bin/nextflow

# ── Install uv ────────────────────────────────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# ── Dependency layer (expensive, stable) ─────────────────────
# Only `pyproject.toml` + `uv.lock` affect this layer. Code changes below
# do NOT invalidate it, so `uv sync` only re-runs when deps actually change.
# `--no-install-project` skips installing the local `app` package here; we
# do that in the cheap app layer below.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ── App code layer (cheap, frequently-invalidated) ────────────
COPY app app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Strip source: compile app/ to .pyc, drop .py ─────────────
# Goal: images shipped to customers should not contain readable source.
# `-b` writes .pyc next to the original .py (not under __pycache__/), so the
# standard import machinery finds them without path changes. `.pyc` is
# reversible with decompile3/pycdc — this is a speedbump, not encryption.
# alembic/ is left as .py (see plan: Alembic revision loader needs source).
RUN python -m compileall -b -q app && \
    find app -type f -name "*.py" -delete && \
    find app -type d -name "__pycache__" -exec rm -rf {} +

# ── Support files (rarely change) ────────────────────────────
COPY alembic alembic
COPY alembic.ini .
COPY scripts scripts

# ── Entrypoint ────────────────────────────────────────────────
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
# Production mode: no --reload, no --workers (SQLite single-writer)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
