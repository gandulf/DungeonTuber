# DungeonTuber WiZ light agent

A small program that runs on a machine **in the same network as your WiZ bulbs** and connects *out* to the DungeonTuber server.
Use it when the server cannot reach the bulbs itself (e.g. it runs in the cloud): the server sends light commands over the
connection and the agent talks to the bulbs via UDP. While an agent is connected, discovery and all light commands go through it;
without one the server falls back to its own network.

## Setup

1. In DungeonTuber open **Settings > Lights** (SuperAdmin) and click **Create agent token**. The token is shown once; the server only
   stores a hash. (Alternatively set `DT_AGENT_TOKEN` on the server.) The token is separate from every user password and only allows
   agents to connect. A new token locks out agents using the old one.
2. On the machine next to the bulbs (Python 3.12):

   ```bash
   pip install ./agents/wiz            # or: pip install pywizlight websockets
   dt-wiz-agent --token <token>                       # server: https://dungeontuber.duckdns.org, or add --server <url>
   ```

   Settings can also be given as environment variables: `DT_SERVER`, `DT_AGENT_TOKEN`, `DT_AGENT_NAME`, `DT_BROADCAST`, `DT_FAKE_LIGHTS=1`.

Options: `--server` (default `https://dungeontuber.duckdns.org`), `--broadcast` (broadcast address of the bulb network, e.g. `192.168.1.255`; default `255.255.255.255`), `--wait` (seconds to wait
for bulbs while discovering), `--fake` (three simulated bulbs for testing), `--verbose`. The agent reconnects automatically.

## Protocol

WebSocket `/ws/agent` with `Authorization: Bearer <token>`. The agent sends `{"type": "hello", "kind": "lights", "name": "..."}`, the
server answers `{"type": "welcome"}` and then sends requests `{"id": 1, "op": ...}`; the agent replies
`{"id": 1, "ok": true, "result": ...}` or `{"id": 1, "ok": false, "error": "..."}`.

| op         | arguments      | result                                                 |
|------------|----------------|--------------------------------------------------------|
| `discover` |                | `[{"mac", "ip"}]`                                      |
| `state`    | `mac`          | `{"pilot": {...}, "kelvin": [min, max], "scenes": []}` |
| `pilot`    | `mac`, `params`| raw WiZ `setPilot` parameters                          |
| `off`      | `mac`          |                                                        |

## Single executable

```bash
pip install pyinstaller pywizlight websockets
python build.py          # -> dist/DungeonTuberWizAgent(.exe), settings via the same options / DT_* variables
```
