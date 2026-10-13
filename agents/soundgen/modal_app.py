"""Background music, ambiences and sound effects on demand on Modal (https://modal.com): Stable Audio 3
(github.com/Stability-AI/stable-audio-3, Stability AI Community License) turns a description into audio. A GPU container starts when a
request is posted and stops again when it is idle, so you only pay for the seconds a sound takes.

    pip install modal && modal setup
    modal secret create huggingface HF_TOKEN=hf_...     # the models are gated: accept their license on Hugging Face first
    cd agents/soundgen && modal deploy modal_app.py

The endpoint is protected by Modal's proxy auth like the music generation (agents/musicgen/modal_app.py): Modal rejects requests
without a valid key and secret before any container starts. It takes the same JSON as the music generation (caption, duration, bpm,
seed), plus `kind` ("music", "ambience" or "sfx"), and answers with an mp3.

The models are downloaded into a Modal volume on the first start, so later starts only load them. To fill the volume beforehand on
a CPU container (also after changing DT_SOUND_MODEL):

    modal run modal_app.py::download
"""
import asyncio
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import modal

# medium (1.4B) does music, ambiences and effects up to 380 s and needs a GPU with Flash Attention 2 (Ampere or newer, not a T4);
# small-music and small-sfx (433M, 120 s) do one of them and also run without a GPU (DT_SOUND_GPU=none)
MODEL = os.environ.get("DT_SOUND_MODEL", "medium")
GPU = os.environ.get("DT_SOUND_GPU", "L4")
STEPS = int(os.environ.get("DT_SOUND_STEPS", "8"))  # the released models are distilled to 8 steps without guidance
MAX_CONTAINERS = int(os.environ.get("DT_SOUND_MAX_CONTAINERS", "1"))  # caps the parallel generations and with it the cost
IDLE_SECONDS = int(os.environ.get("DT_SOUND_IDLE_SECONDS", "120"))  # how long a container stays warm after its last sound
HF_SECRET = os.environ.get("DT_SOUND_HF_SECRET", "huggingface")  # the Modal secret with HF_TOKEN

# the Stable Audio 3 release this app is tested with; a newer commit may change the Python API
SA3_COMMIT = "77e0398c26f7d22d801ec1bb036307e8b231f741"
FLASH_ATTN_WHEEL = ("https://github.com/mjun0812/flash-attention-prebuild-wheels/releases/download/v0.7.16/"
                    "flash_attn-2.6.3+cu126torch2.7-cp311-cp311-linux_x86_64.whl")
HF_HOME = "/hf"

MIN_SECONDS = 1
MAX_SECONDS = 380 if MODEL.startswith("medium") else 120
MAX_CAPTION = 1024
KINDS = ("music", "ambience", "sfx")
# The models were trained on Freesound and AudioSparx with their metadata; these tags steer them (docs/guides/prompting.md).
PREFIX = {
    "music": "TrackType: Music, VocalType: Instrumental",
    "ambience": "TrackType: SFX, ambience, field recording",
    "sfx": "TrackType: SFX",
}
HAS_TAGS = re.compile(r"\bTrackType\s*:", re.IGNORECASE)
HAS_BPM = re.compile(r"\b\d{2,3}\s*BPM\b", re.IGNORECASE)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libsndfile1")
    .pip_install("torch==2.7.1", "torchaudio==2.7.1", index_url="https://download.pytorch.org/whl/cu126")
    .pip_install(FLASH_ATTN_WHEEL)  # the medium model produces static noise without it
    .pip_install(f"stable-audio-3 @ git+https://github.com/Stability-AI/stable-audio-3.git@{SA3_COMMIT}", "fastapi[standard]")
    # the options of `modal deploy` are read again when the container imports this file: the image carries them
    .env({"HF_HOME": HF_HOME, "TOKENIZERS_PARALLELISM": "false", "DT_SOUND_MODEL": MODEL, "DT_SOUND_STEPS": str(STEPS)})
)

models = modal.Volume.from_name("dungeontuber-soundgen-models", create_if_missing=True)
secrets = [modal.Secret.from_name(HF_SECRET)]

app = modal.App("dungeontuber-soundgen", image=image)


def log(message: str):
    print(f"[soundgen] {message}", file=sys.stderr, flush=True)


def load_model(device: str, refresh: bool = False):
    """Loads the model, downloading it into the volume on the first start (a marker keeps later starts from asking Hugging Face).
    `refresh` asks Hugging Face anyway and completes a download that was cut off."""
    marker = Path(HF_HOME) / f".complete-{MODEL}"
    if marker.exists() and not refresh:
        os.environ["HF_HUB_OFFLINE"] = "1"  # read when huggingface_hub is imported
    else:
        log(f"downloading {MODEL}, this takes a few minutes")
    from stable_audio_3 import StableAudioModel

    model = StableAudioModel.from_pretrained(MODEL, device=device, model_half=device == "cuda")
    if not marker.exists():
        marker.write_text(MODEL, encoding="utf-8")
        models.commit()
    return model


@app.function(volumes={HF_HOME: models}, secrets=secrets, timeout=3600, cpu=4, memory=16384)
def download():
    """Fills the volume with the model (`modal run modal_app.py::download`); no GPU needed."""
    started = time.monotonic()
    load_model("cpu", refresh=True)
    log(f"{MODEL} ready in {time.monotonic() - started:.0f} s")


def describe(request: dict) -> tuple[str, str]:
    """The prompt for Stable Audio 3 and the kind of sound: the description behind the dataset tags of its kind, with the tempo."""
    kind = str(request.get("kind") or "music").lower()
    kind = kind if kind in KINDS else "music"
    caption = str(request.get("caption") or request.get("prompt") or "").strip()
    bpm = request.get("bpm")
    if kind == "music" and isinstance(bpm, (int, float)) and 30 <= bpm <= 300 and not HAS_BPM.search(caption):
        caption = f"{caption.rstrip('. ')}, {int(bpm)} BPM"
    if not HAS_TAGS.search(caption):
        caption = f"{PREFIX[kind]}, {caption}"
    return caption[:MAX_CAPTION], kind


def to_mp3(audio, sample_rate: int) -> bytes:
    import soundfile

    with tempfile.TemporaryDirectory(prefix="dt-soundgen-") as tmp:
        wav, mp3 = Path(tmp) / "sound.wav", Path(tmp) / "sound.mp3"
        soundfile.write(wav, audio[0].cpu().numpy().T, sample_rate)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3)],
                       check=True)
        return mp3.read_bytes()


@app.cls(gpu=None if GPU.lower() == "none" else GPU, max_containers=MAX_CONTAINERS, scaledown_window=IDLE_SECONDS, timeout=900,
         volumes={HF_HOME: models}, secrets=secrets)
class SoundGen:
    @modal.enter()
    def start(self):
        import torch

        started = time.monotonic()
        self.model = load_model("cuda" if torch.cuda.is_available() else "cpu")
        log(f"{MODEL} ready in {time.monotonic() - started:.0f} s")

    def generate(self, request: dict) -> tuple[bytes, dict]:
        seed = request.get("seed")
        seed = int(seed) if isinstance(seed, int) and 0 <= seed < 2 ** 31 else random.randint(0, 2 ** 31 - 1)
        prompt, kind = describe(request)
        default = {"music": 120, "ambience": 60, "sfx": 5}[kind]
        duration = float(min(max(float(request.get("duration") or default), MIN_SECONDS), MAX_SECONDS))
        log(f"generating {kind}, {duration:.0f} s, {STEPS} steps: {prompt[:160]}")
        audio = self.model.generate(prompt=prompt, duration=duration, steps=STEPS, cfg_scale=1.0, seed=seed)
        return to_mp3(audio, self.model.model.sample_rate), {"seed": seed, "duration": duration, "kind": kind}

    @modal.asgi_app(requires_proxy_auth=True)
    def web(self):
        from fastapi import FastAPI, HTTPException, Request, Response

        api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @api.post("/")
        async def generate(request: Request):
            try:
                body = await request.json()
            except ValueError:
                raise HTTPException(status_code=400, detail="JSON expected")
            if not isinstance(body, dict) or not str(body.get("caption") or body.get("prompt") or "").strip():
                raise HTTPException(status_code=400, detail="The description is missing")
            started = time.monotonic()
            try:
                data, info = await asyncio.to_thread(self.generate, body)
            except Exception as e:  # reported to the caller
                raise HTTPException(status_code=500, detail=str(e) or type(e).__name__)
            log(f"generated {info['duration']:.0f} s of {info['kind']} in {time.monotonic() - started:.1f} s")
            return Response(content=data, media_type="audio/mpeg", headers={"X-Seed": str(info["seed"])})

        return api
