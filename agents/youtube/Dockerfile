# DungeonTuber YouTube download agent.  The build context is the repository root (the agent uses core/ of the server):
#   docker build -f agents/youtube/Dockerfile -t dungeontuber-youtube-agent .
#   docker run --rm dungeontuber-youtube-agent --token <token> --server https://music.example.com
FROM python:3.12-slim
LABEL org.opencontainers.image.title="DungeonTuber YouTube agent" \
      org.opencontainers.image.description="Downloads YouTube audio with yt-dlp and uploads it to a DungeonTuber server" \
      org.opencontainers.image.source="https://github.com/gandulf/DungeonTuber" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Static builds copied from small images: ffmpeg/ffprobe convert the audio, deno runs the JavaScript yt-dlp needs for YouTube
COPY --from=mwader/static-ffmpeg:7.1.1 /ffmpeg /ffprobe /usr/local/bin/
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

COPY agents/youtube/ /src/agent/
RUN pip install --no-cache-dir /src/agent && rm -rf /src/agent \
    && useradd --create-home --uid 1000 agent
COPY core/ /app/core/

USER agent
# Connects out to a DungeonTuber server: --token <token> --server <url> (or DT_AGENT_TOKEN / DT_SERVER)
ENTRYPOINT ["dt-youtube-agent"]
