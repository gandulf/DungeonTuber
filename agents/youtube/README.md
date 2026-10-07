# DungeonTuber YouTube download agent

YouTube blocks downloads from most data centers ("Sign in to confirm you're not a bot"). This agent runs yt-dlp on a machine YouTube does
not block, for example **your PC at home**, and connects *out* to the DungeonTuber server. While it is connected, every lookup and every
YouTube import of the server is done by the agent: it downloads and converts the video, splits chapters if requested, tags the mp3 files and
uploads them to the server, which stores them in the library. Without an agent the server downloads by itself.

The agent uses the same download code as the server (`core/ytimport.py` of this repository), so downloads behave the same everywhere.

## Setup

1. In DungeonTuber open **Settings → Agents** (SuperAdmin) and click **Create agent token**. The token is shown once; the server only stores a
   hash. One token is used for all agents, a new token locks out agents with the old one.
2. On the machine that downloads, pick one:

   * **Windows executable** from the [releases](https://github.com/gandulf/DungeonTuber/releases):

     ```bash
     DungeonTuberYouTubeAgent-<version>.exe --token <token> --server https://music.example.com
     ```

   * **Docker** (the image contains ffmpeg and deno):

     ```bash
     docker run -d --restart unless-stopped ghcr.io/gandulf/dungeontuber-youtube-agent --token <token> --server https://music.example.com
     ```

   * **From the repository** (Python 3.12):

     ```bash
     pip install ./agents/youtube
     python agents/youtube/dt_youtube_agent.py --token <token> --server https://music.example.com
     ```

   The settings can also be given as environment variables: `DT_SERVER`, `DT_AGENT_TOKEN`, `DT_AGENT_NAME`, `DT_COOKIES`,
   `DT_COOKIES_FROM_BROWSER`.

ffmpeg and deno (or node) are needed by yt-dlp; the Docker image contains them, otherwise they are downloaded once on first use (Windows and Linux).

## Build

```bash
cd agents/youtube
pip install pyinstaller .
python build.py          # dist/DungeonTuberYouTubeAgent.exe
docker build -f agents/youtube/Dockerfile -t dungeontuber-youtube-agent .     # from the repository root
```

## Options

| Option | Meaning |
|---|---|
| `--server` | URL of the DungeonTuber server (default `https://dungeontuber.duckdns.org`) |
| `--token` | agent token created in the settings |
| `--name` | name shown in the server log |
| `--cookies-from-browser BROWSER` | use the YouTube cookies of a browser profile on this machine (`firefox`, `chrome`, `edge`, ...) if YouTube still asks for a sign-in |
| `--cookies FILE` | the same with an exported `cookies.txt` |
| `--verbose` | debug output |

The agent reconnects automatically. Downloads run one at a time. If it asks for a sign-in anyway, the cookies of the server settings are *not*
used (they belong to the server); give the agent its own with one of the cookie options.

## Protocol

WebSocket `/ws/agent` with `Authorization: Bearer <token>`, like the other agents. The agent sends `{"type": "hello", "kind": "youtube", "name": "..."}`
and the server sends requests that the agent answers with `{"id": 1, "ok": true, "result": ...}` or `{"id": 1, "ok": false, "error": "..."}`.
While a request runs the agent may send `{"type": "progress", "id": 1, "message": "...", "percent": 40}`.

| op | arguments | result |
|---|---|---|
| `resolve` | `url`, `whole` | `{"title", "is_playlist", "has_video", "entries": [{"url", "title", "duration", "uploader", "chapters"}]}` |
| `download` | `url`, `upload`, `max_minutes`, `album`, `split` | `{"title", "name", "split", "files": [{"name", "title"}]}` |
| `version` | | the yt-dlp version |

For `download` the agent uploads each mp3 with `PUT <upload>/<index>` (raw body, same bearer token) before it answers; `<upload>` is a one-time
address (`/api/agents/uploads/<ticket>`) that is valid only while that request runs. With `split` the files are the chapters in order.
