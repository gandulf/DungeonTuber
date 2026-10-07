# DungeonTuber agents

Agents are small programs that connect *out* to a DungeonTuber server (see **Settings → Agents**):

| Program | Folder | Does |
|---|---|---|
| `dt-wiz-light.exe` | [`wiz`](wiz/README.md) | controls WiZ lights next to the bulbs |
| `dt-voxalyzer.exe` | [`voxalyzer`](voxalyzer/README.md) | analyses songs (categories, tags, genres, BPM) |
| `dt-youtube.exe` | [`youtube`](youtube/README.md) | downloads YouTube audio with yt-dlp and uploads it |

## One configuration for all agents on a machine

All agents read the same file, `agents.json`:

```json
{ "server": "https://music.example.com", "token": "<agent token>", "name": "my-pc" }
```

* **Get it from the server:** create the agent token under **Settings → Agents** and click **Download agents.json**. The file has the address of your server and the new token.
* **Where to put it:** next to the agent programs, or in the DungeonTuber data folder (`%APPDATA%\DungeonTuber` on Windows, `~/.config/DungeonTuber` elsewhere), or anywhere and point `DT_AGENT_CONFIG` at it.
* **Precedence:** command line option, then environment variable (`DT_SERVER`, `DT_AGENT_TOKEN`, `DT_AGENT_NAME`), then `agents.json`, then the default. `name` is optional (default: the computer name).

With the file in place every agent starts without arguments. Keep it private: the token lets a program act as an agent of your server. A new token (Settings → Agents) locks out all agents that use the old one, so download the file again.

## Start them together (Windows)

[`start-agents.cmd`](start-agents.cmd) starts the agent programs that are in the same folder, each in its own window, and skips the ones that are missing:

```bat
start-agents.cmd
start-agents.cmd --server https://music.example.com --token <token>   :: options are passed to every agent
```

Put `dt-wiz-light.exe`, `dt-voxalyzer.exe`, `dt-youtube.exe`, `agents.json` and `start-agents.cmd` into one folder (all of them are attached to every release), and add a shortcut to `start-agents.cmd` to the Startup folder (`shell:startup`) to run the agents at login.
