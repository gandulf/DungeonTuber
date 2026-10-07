
To install dependencies under windows
```bash
pip install .[dev,windows]
```
To run from source (agent for a DungeonTuber server, or analyze files/folders locally):
```bash
python -m voxalyzer --token <token>
python -m voxalyzer C:/Music --force
```
Layout: the `voxalyzer/` package (`cli`, `agent`, `analyzer`, `models`, `mp3`, `memory`, `utils`); `models` downloads the ONNX models on first start.

To build under windows:
```bash
pyinstaller voxalyzer.spec
```

To use latest docker image to analyze local directory
```bash
docker run --gpus all -v C:/Users/gandu/Music/Test:/music ghcr.io/gandulf/dungeontuber-voxalyzer:latest /music --force
```

cd

Convert pb to onnx
```bash
docker run -it --rm -v "C:/DEV/git/Voxalyzer/models:/models" tensorflow/tensorflow:2.15.0 bash -c "pip install tf2onnx && python -m tf2onnx.convert --graphdef /models/deeptemp-k16-3.pb --output /models/model.onnx --inputs input:0 --outputs output:0"
```

## Run as DungeonTuber agent

The agent connects *out* to a DungeonTuber server (same agent token and WebSocket as the WiZ light agent, see `agents/wiz`). While it is
connected the server sends all analysis requests to it: the agent downloads each mp3 with a one-time ticket, analyzes it and returns the
result, which the server stores. Without a connected agent analysis is disabled in the UI.
```bash
voxalyzer --token <token> [--server https://dungeontuber.duckdns.org] [--name gpu-box]
docker run --gpus all ghcr.io/gandulf/dungeontuber-voxalyzer:latest --token <token> --server https://my.server
```
`DT_SERVER`, `DT_AGENT_TOKEN` and `DT_AGENT_NAME` can be used instead of the options, and so can the `agents.json` that all DungeonTuber agents share (see [`agents/README.md`](../README.md)). `--fake` (or `DT_FAKE_ANALYSIS=1`) skips the models and returns
mock categories, tags, genres and bpm, for testing without a GPU.

## Models

The ~31 MB of ONNX models are part of the repo but not of the releases. On the first start the agent downloads the missing ones from the static
URL `https://raw.githubusercontent.com/gandulf/DungeonTuber/master/agents/voxalyzer/models/<file>` (the files listed in `voxalyzer/models.py`, each verified
by SHA-256) into `%LOCALAPPDATA%/DungeonTuber/models` (`~/.cache/DungeonTuber/models` on Linux). `--fake` needs none of this.
`DT_MODELS_URL` points to another location, `DT_MODEL_DIR` to another folder (e.g. to put the files there manually when offline).
The Docker image downloads them while it is built.
