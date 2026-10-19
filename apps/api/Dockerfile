# syntax=docker/dockerfile:1
#
# One image, two commands: the API (`uvicorn app.main:app`) and the worker
# (`python -m app.workers`). Railway sets the command per service, so the image
# carries both dependency sets and neither process is privileged over the other.
#
# Build context is this directory (`apps/api`), which is also the Railway root
# directory. The web app is not built here; Vercel builds it.

FROM python:3.12-slim

# uv from the official image: `uv sync` resolves the same lock file the
# developers use, and it is faster than pip in a layer that runs on every deploy.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# libsndfile1 is what `soundfile` links against; audio cannot be decoded without
# it. ffmpeg is the fallback decoder for containers libsndfile cannot open.
# No build toolchain: every dependency ships a manylinux wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies before source, so editing a route rebuilds one small layer.
# `--no-dev` drops pytest/ruff; `--group worker` adds librosa, soundfile and
# pretty-midi, which the API service installs but never imports.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --group worker

COPY app ./app

# Non-root. The process writes only to /tmp (decoded audio while analysing).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Railway injects PORT. The worker service overrides this command with
# `python -m app.workers`; nothing here is worker-specific.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
