# DungeonTuber server image
#   docker build -t dungeontuber .
#   docker run -p 8765:8765 -e DT_PASSWORD=secret -v ./music:/music -v dt-data:/data dungeontuber

# --- web frontend ----------------------------------------------------------
FROM node:24-alpine AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
COPY core/locales/ /src/core/locales/
RUN npm run build -- --outDir /src/server/static

# --- python wheel ------------------------------------------------------------
FROM python:3.12-slim AS wheel
WORKDIR /src
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md DungeonTuber.py ./
COPY core/ core/
COPY server/ server/
COPY --from=web /src/server/static/ server/static/
RUN python -m build --wheel --outdir /dist

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

# optional extras of the wheel: "s3" adds boto3 for S3 compatible library storage (--build-arg EXTRAS= to leave it out)
ARG EXTRAS=s3
COPY --from=wheel /dist/*.whl /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/*.whl)${EXTRAS:+[$EXTRAS]}" \
    && rm -rf /tmp/*.whl \
    && useradd --create-home --uid 1000 dungeontuber \
    && mkdir -p /data /music && chown dungeontuber:dungeontuber /data

USER dungeontuber
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"DT_PORT\", \"8765\")}/api/health', timeout=4)"

CMD ["dungeontuber-server"]
