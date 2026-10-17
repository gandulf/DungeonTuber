"""Music generation on demand on Modal (https://modal.com): ACE-Step 1.5 (github.com/ace-step/ACE-Step-1.5, MIT) composes a piece from
a description. A GPU container starts when the DungeonTuber server posts a request and stops again when it is idle, so you only pay
for the seconds a piece takes.

    pip install modal && modal setup
    cd agents/musicgen && modal deploy modal_app.py

The endpoint is protected by Modal's proxy auth like the cloud analysis (agents/voxalyzer/modal_app.py): Modal rejects requests
without a valid key and secret before any container starts. Enter the URL that `modal deploy` prints together with the key and secret
of a proxy auth token (Modal dashboard -> Settings -> Proxy Auth Tokens) in DungeonTuber under Settings -> AI Assistant.

The models (about 10 GB, the XL models more) are downloaded into a Modal volume on the first start, so later starts only load them.
To fill the volume beforehand on a cheap CPU container (also after changing DT_MUSIC_DIT or DT_MUSIC_LM, and to repair a download
that was cut off):

    modal run modal_app.py::download

Cold starts restore a GPU memory snapshot (Modal, experimental) taken after each deploy, with both models already on the GPU;
DT_MUSIC_GPU_SNAPSHOT=0 loads them on every start instead.
"""
import asyncio
import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path

import modal

GPU = os.environ.get("DT_MUSIC_GPU", "L4")  # 24 GB: the 2B DiT and the 1.7B planner fit without offloading
# the base size (2B); turbo composes in seconds, acestep-v15-sft (or acestep-v15-base) needs many more steps for richer, more detailed audio
DIT_MODEL = os.environ.get("DT_MUSIC_DIT", "acestep-v15-xl-sft")
# diffusion steps of the non-turbo models (docs/en/INFERENCE.md: 32-64 for quality); turbo is distilled to 8 steps
STEPS = int(os.environ.get("DT_MUSIC_STEPS", "50"))
# The planner may rewrite the description; it then drops the specific instruments of the assistant's description (lute, bagpipe, …)
# and translates or generalizes it, so it is off by default. It still chooses the tempo, the key and the language.
REWRITE_CAPTION = os.environ.get("DT_MUSIC_REWRITE_CAPTION", "0") == "1"
# the planner (song structure, bpm, key); next to an XL composer the 4B planner does not fit into the 22 GB of an L4
# (CUDA out of memory), it needs a GPU with more memory (DT_MUSIC_GPU=L40S)
LM_MODEL = os.environ.get("DT_MUSIC_LM", "acestep-5Hz-lm-1.7B")
MAX_CONTAINERS = int(os.environ.get("DT_MUSIC_MAX_CONTAINERS", "1"))  # caps the parallel generations and with it the cost
IDLE_SECONDS = int(os.environ.get("DT_MUSIC_IDLE_SECONDS", "120"))  # how long a container stays warm after its last piece
# Modal's experimental GPU memory snapshot: ACE-Step loads straight onto the GPU, so there is no CPU snapshot to fall back to
GPU_SNAPSHOT = os.environ.get("DT_MUSIC_GPU_SNAPSHOT", "1") == "1"

# the ACE-Step release this app is tested with; a newer commit may change the Python API
ACE_STEP_COMMIT = "ca1e85fe9430179831e6bc6be790c332190a3866"
ACE_STEP_DIR = "/opt/ace-step"
CHECKPOINTS = "/checkpoints"

MIN_SECONDS, MAX_SECONDS = 10, 600
MAX_CAPTION = 512
MAX_LYRICS = 4096
INSTRUMENTAL = "[Instrumental]"  # ACE-Step reads instrumental music from the lyrics, its `instrumental` flag alone does nothing
SECTION_TAG = re.compile(r"\[[^\]\n]{1,60}\]")

# random seeds from the OS: the state of `random` is frozen in the memory snapshot, every restore would draw the same seeds
SEEDS = random.SystemRandom()

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-runtime-ubuntu22.04", add_python="3.11")
    .apt_install("git", "ffmpeg", "libsndfile1")
    .pip_install("uv")
    .run_commands(
        f"git clone https://github.com/ace-step/ACE-Step-1.5.git {ACE_STEP_DIR} && git -C {ACE_STEP_DIR} checkout {ACE_STEP_COMMIT}",
        # into the Python of the image; uv honours the CUDA wheels and the local nano-vllm package that the project names
        f"cd {ACE_STEP_DIR} && uv pip install --system --python $(command -v python) -e .",
    )
    .pip_install("fastapi[standard]")
    .env({"ACESTEP_PROJECT_ROOT": ACE_STEP_DIR, "ACESTEP_CHECKPOINTS_DIR": CHECKPOINTS, "TOKENIZERS_PARALLELISM": "false",
          # the options of `modal deploy` are read again when the container imports this file: the image carries them
          "DT_MUSIC_DIT": DIT_MODEL, "DT_MUSIC_LM": LM_MODEL, "DT_MUSIC_STEPS": str(STEPS),
          "DT_MUSIC_REWRITE_CAPTION": "1" if REWRITE_CAPTION else "0",
          "DT_MUSIC_GPU_SNAPSHOT": "1" if GPU_SNAPSHOT else "0"})
)

checkpoints = modal.Volume.from_name("dungeontuber-musicgen-models", create_if_missing=True)

app = modal.App("dungeontuber-musicgen", image=image)


def log(message: str):
    print(f"[musicgen] {message}", file=sys.stderr, flush=True)


def ensure_models():
    """Downloads the models the app uses into the volume, completing a download that was cut off.

    ACE-Step itself only checks that a model folder holds one weights file, so a cut-off download of a model with several shards
    would never be completed. snapshot_download skips the files that are complete and fetches the rest; a marker per model is only
    written when its download finished, so later starts do not ask Hugging Face again.
    """
    from acestep.model_downloader import SUBMODEL_REGISTRY, download_main_model, download_submodel

    root = Path(CHECKPOINTS)
    for name in ("main", DIT_MODEL, LM_MODEL):
        if name != "main" and name not in SUBMODEL_REGISTRY:
            continue  # part of the main model
        marker = root / f".complete-{name}"
        if marker.exists():
            continue
        started = time.monotonic()
        log(f"downloading {name}, this takes a few minutes")
        if name == "main":
            ok, message = download_main_model(root, force=True, prefer_source="huggingface")
        else:
            ok, message = download_submodel(name, root, force=True, prefer_source="huggingface")
        if not ok:
            raise RuntimeError(f"Download of {name} failed: {message}")
        marker.write_text(message, encoding="utf-8")
        checkpoints.commit()
        log(f"{name} complete in {time.monotonic() - started:.0f} s")


@app.function(volumes={CHECKPOINTS: checkpoints}, timeout=3600, cpu=2)
def download():
    """Fills the volume with the models (`modal run modal_app.py::download`); no GPU needed."""
    ensure_models()


@app.cls(gpu=GPU, max_containers=MAX_CONTAINERS, scaledown_window=IDLE_SECONDS, timeout=1800, volumes={CHECKPOINTS: checkpoints},
         enable_memory_snapshot=GPU_SNAPSHOT, experimental_options={"enable_gpu_snapshot": True} if GPU_SNAPSHOT else None)
class MusicGen:
    @modal.enter(snap=True)
    def start(self):
        """Loads both models onto the GPU; with the GPU snapshot this runs once per snapshot, restores skip it."""
        from acestep.handler import AceStepHandler
        from acestep.llm_inference import LLMHandler

        started = time.monotonic()
        ensure_models()
        self.dit = AceStepHandler()
        status, ok = self.dit.initialize_service(project_root=ACE_STEP_DIR, config_path=DIT_MODEL, device="cuda")
        if not ok:
            raise RuntimeError(f"ACE-Step DiT: {status}")
        self.lm = LLMHandler()
        status, ok = self.lm.initialize(checkpoint_dir=CHECKPOINTS, lm_model_path=LM_MODEL, backend="pt", device="cuda")
        if not ok:
            raise RuntimeError(f"ACE-Step LM: {status}")
        log(f"{DIT_MODEL} + {LM_MODEL} ready in {time.monotonic() - started:.0f} s")

    def lyrics(self, caption: str, lyrics: str, instrumental: bool, language: str) -> tuple[str, str]:
        """The lyrics ACE-Step composes from and their language; without lyrics for a piece with vocals its planner writes them."""
        if instrumental:
            # section tags without words give an instrumental piece its structure over time ([Intro - harp], [Climax], …)
            lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
            structure = bool(lines) and all(SECTION_TAG.fullmatch(line) for line in lines)
            return (lyrics if structure else INSTRUMENTAL), "unknown"
        if lyrics.strip():
            return lyrics, language
        from acestep.inference import create_sample

        sample = create_sample(self.lm, caption, instrumental=False, vocal_language=None if language == "unknown" else language)
        if sample.success and sample.lyrics.strip() and sample.lyrics.strip() != INSTRUMENTAL:
            log(f"the planner wrote the lyrics ({len(sample.lyrics)} characters, {sample.language or language})")
            return sample.lyrics[:MAX_LYRICS], sample.language or language
        log(f"no lyrics for a piece with vocals: {sample.error or sample.status_message}")
        return "", language

    def generate(self, request: dict) -> tuple[bytes, dict]:
        from acestep.constants import VALID_LANGUAGES
        from acestep.inference import GenerationConfig, GenerationParams, generate_music

        seed = request.get("seed")
        seed = int(seed) if isinstance(seed, int) and seed >= 0 else SEEDS.randint(0, 2 ** 31 - 1)
        bpm = request.get("bpm")
        instrumental = bool(request.get("instrumental", True))
        caption = str(request.get("caption") or "").strip()
        if instrumental and "instrumental" not in caption.lower():
            caption = f"instrumental, {caption}"  # keeps unwanted vocals away, besides the [Instrumental] lyrics
        caption = caption[:MAX_CAPTION]
        language = str(request.get("language") or "unknown").lower()
        lyrics, language = self.lyrics(caption, str(request.get("lyrics") or "")[:MAX_LYRICS], instrumental,
                                        language if language in VALID_LANGUAGES else "unknown")
        # turbo is distilled: 8 steps, no guidance (the pipeline sets it to 1.0), shift 3; the other models need many steps and guidance
        turbo = self.dit.is_turbo_model()
        params = GenerationParams(
            caption=caption,
            lyrics=lyrics,
            instrumental=instrumental,
            vocal_language=language,
            duration=float(min(max(float(request.get("duration") or 120), MIN_SECONDS), MAX_SECONDS)),
            bpm=int(bpm) if isinstance(bpm, (int, float)) and 30 <= bpm <= 300 else None,
            seed=seed,
            inference_steps=8 if turbo else STEPS,
            guidance_scale=1.0 if turbo else 7.0,
            shift=3.0 if turbo else 1.0,
            use_cot_caption=REWRITE_CAPTION,
        )
        log(f"composing {params.duration:.0f} s, {'instrumental' if instrumental else f'vocals ({language})'}, {len(lyrics)} characters of lyrics, "
            f"{params.inference_steps} steps: {caption[:160]}")
        config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[seed], audio_format="mp3", mp3_bitrate="192k")
        with tempfile.TemporaryDirectory(prefix="dt-musicgen-") as tmp:
            result = generate_music(self.dit, self.lm, params, config, save_dir=tmp)
            if not result.success or not result.audios or not result.audios[0].get("path"):
                raise RuntimeError(result.error or result.status_message or "no audio")
            data = Path(result.audios[0]["path"]).read_bytes()
        return data, {"seed": seed, "duration": params.duration}

    @modal.asgi_app(requires_proxy_auth=True)
    def web(self):
        from fastapi import FastAPI, HTTPException, Request, Response

        api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @api.post("/")
        async def compose(request: Request):
            try:
                body = await request.json()
            except ValueError:
                raise HTTPException(status_code=400, detail="JSON expected")
            if not isinstance(body, dict) or not str(body.get("caption") or "").strip():
                raise HTTPException(status_code=400, detail="The description is missing")
            started = time.monotonic()
            try:
                data, info = await asyncio.to_thread(self.generate, body)
            except Exception as e:  # reported to the server, which shows it in the chat
                raise HTTPException(status_code=500, detail=str(e) or type(e).__name__)
            log(f"composed {info['duration']:.0f} s in {time.monotonic() - started:.1f} s")
            return Response(content=data, media_type="audio/mpeg", headers={"X-Seed": str(info["seed"])})

        return api
