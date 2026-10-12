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

# --- fpcalc (Chromaprint) ------------------------------------------------------
# audio fingerprints for the AcoustID metadata lookup (core/musiclookup.py): the static build of the release, checked by its hash
FROM alpine:3.20 AS fpcalc
ARG TARGETARCH
RUN set -eu; \
    version=1.6.1; \
    case "${TARGETARCH:-amd64}" in \
      amd64) arch=x86_64; sha=fc16cd37a70168040bc9ceb45f1d4d1216f5a75bc4c9cf8564bea70ac6a45733 ;; \
      arm64) arch=arm64;  sha=7eaf5d655c4aa172ab28e3c870b8bb61dd2c327ac94de145676f88842cf6215a ;; \
      *) echo "no fpcalc build for ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    wget -q -O /tmp/fpcalc.tar.gz "https://github.com/acoustid/chromaprint/releases/download/v${version}/chromaprint-fpcalc-${version}-linux-${arch}.tar.gz"; \
    echo "${sha}  /tmp/fpcalc.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/fpcalc.tar.gz -C /tmp; \
    install -m 755 "$(find /tmp -type f -name fpcalc | head -n 1)" /fpcalc

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
# deno runs the JavaScript yt-dlp needs for YouTube, fpcalc identifies songs by their sound (AcoustID)
COPY --from=mwader/static-ffmpeg:7.1.1 /ffmpeg /ffprobe /usr/local/bin/
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno
COPY --from=fpcalc /fpcalc /usr/local/bin/fpcalc

RUN fpcalc -version \
    && useradd --create-home --uid 1000 dungeontuber     && mkdir -p /data /music && chown dungeontuber:dungeontuber /data

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
