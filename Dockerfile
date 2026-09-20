# Two stages, so the runtime image carries no Node and no build tooling.
#
# The UI is compiled first and its output copied into the Python image, which is
# also how the app expects to be served: `app/main.py` mounts `web/dist` if it
# exists and falls back to an API-only mode if it does not. One container, one
# port, no reverse proxy to explain.

# --- stage 1: build the supervision UI -------------------------------------
FROM node:22-alpine AS ui

WORKDIR /ui
# Copy manifests alone first so `npm ci` is cached until a dependency actually
# changes — editing a component should not reinstall React.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build


# --- stage 2: the application ----------------------------------------------
FROM python:3.11-slim AS app

# PYTHONDONTWRITEBYTECODE: the image is read-only in practice, so .pyc files
# are dead weight. PYTHONUNBUFFERED: without it, `docker logs` shows nothing
# until a buffer fills, which makes a failed start look like a hang.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Dependencies from the manifest alone, before the source, for the same caching
# reason. `pip install .` without the app present would fail, so the package
# directory is stubbed out for this layer only.
COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir . \
    && rm -rf app

COPY app/ ./app/
COPY schema/ ./schema/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY --from=ui /ui/dist ./web/dist

# Writable state, all under one directory so a single volume persists a run.
# Created and chowned *before* the volume is mounted: Docker takes the mount
# point's ownership from the image, and a root-owned /srv/state would leave the
# unprivileged user unable to open its own database.
RUN mkdir -p /srv/state/uploads \
    && useradd --create-home --uid 10001 agent \
    && chown -R agent:agent /srv
USER agent

ENV DB_PATH=/srv/state/migration.db \
    CHECKPOINT_PATH=/srv/state/checkpoints.db \
    UPLOAD_DIR=/srv/state/uploads

# No model server is assumed. `app/llm.py` returns None on every failure and the
# callers fall back to lexical scoring, so the container completes a migration
# with nothing else running — it just asks more questions, which is the correct
# way to degrade. Point these at a real host to get semantic scoring.
ENV REASONING_BASE_URL=http://host.docker.internal:11434 \
    EMBEDDING_BASE_URL=http://host.docker.internal:11434 \
    TARGET_API_BASE=http://127.0.0.1:8000/mock-target/v1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
