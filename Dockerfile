# syntax=docker/dockerfile:1
# DungeonTuber server image
#   docker build -t dungeontuber .
#   docker run -p 8765:8765 -e DT_PASSWORD=secret -v ./music:/music -v dt-data:/data dungeontuber

# --- web frontend ----------------------------------------------------------
FROM node:24-alpine AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --prefer-offline --no-audit --no-fund
COPY web/ ./
COPY core/locales/ /src/core/locales/
RUN npm run build -- --outDir /src/server/static

# --- python wheel ------------------------------------------------------------
FROM python:3.12-slim AS wheel
WORKDIR /src
# build backend installed once (cached layer) and used with --no-isolation, so a rebuild does not download setuptools again
RUN --mount=type=cache,target=/root/.cache/pip pip install build "setuptools>=69"
COPY pyproject.toml README.md DungeonTuber.py ./
COPY core/ core/
COPY server/ server/
COPY --from=web /src/server/static/ server/static/
RUN python -m build --wheel --no-isolation --outdir /dist

# --- runtime -----------------------------------------------------------------
FROM python:3.12-slim
LABEL org.opencontainers.image.title="DungeonTuber" \
      org.opencontainers.image.description="RPG music player server with mood filtering and WiZ lights" \
      org.opencontainers.image.source="https://github.com/gandulf/DungeonTuber" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DT_HOST=0.0.0.0 \
    DT_PORT=8765 \
    DT_DATA_DIR=/data \
    DT_LIBRARY=/music

# Static builds copied from small images (no package installation): ffmpeg/ffprobe convert the audio of imported YouTube links,
# deno runs the JavaScript yt-dlp needs for YouTube
COPY --from=mwader/static-ffmpeg:7.1.1 /ffmpeg /ffprobe /usr/local/bin/
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

RUN useradd --create-home --uid 1000 dungeontuber     && mkdir -p /data /music && chown dungeontuber:dungeontuber /data

# optional extras of the wheel: "s3" adds boto3 for S3 compatible library storage (--build-arg EXTRAS= to leave it out)
ARG EXTRAS=s3

# Dependencies in their own layer: it only depends on pyproject.toml (and EXTRAS), so a source change
# (compose watch rebuild) reuses it and only reinstalls the small wheel below
RUN --mount=type=bind,source=pyproject.toml,target=/tmp/pyproject.toml     --mount=type=cache,target=/root/.cache/pip     python - <<'EOF'
import os, subprocess, sys, tomllib
project = tomllib.load(open("/tmp/pyproject.toml", "rb"))["project"]
deps = list(project["dependencies"])
for extra in filter(None, os.environ.get("EXTRAS", "").split(",")):
    deps += project["optional-dependencies"][extra.strip()]
subprocess.check_call([sys.executable, "-m", "pip", "install", "--root-user-action=ignore", *deps])
EOF

COPY --from=wheel /dist/*.whl /tmp/
RUN pip install --no-cache-dir --no-deps --root-user-action=ignore /tmp/*.whl && rm -rf /tmp/*.whl

USER dungeontuber
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"DT_PORT\", \"8765\")}/api/health', timeout=4)"

CMD ["dungeontuber-server"]
