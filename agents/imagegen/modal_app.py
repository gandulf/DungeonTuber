"""Images on demand on Modal (https://modal.com): Stable Diffusion 3.5 Medium (huggingface.co/stabilityai/stable-diffusion-3.5-medium,
Stability AI Community License) turns a description into a picture. A GPU container starts when a request is posted and stops again
when it is idle, so you only pay for the seconds an image takes.

    pip install modal && modal setup
    modal secret create huggingface HF_TOKEN=hf_...     # the model is gated: accept its license on Hugging Face first
    cd agents/imagegen && modal deploy modal_app.py

The endpoint is protected by Modal's proxy auth like the music and sound generation (agents/musicgen, agents/soundgen): Modal rejects
requests without a valid key and secret before any container starts. It takes JSON (prompt, negative_prompt, width, height, steps,
guidance, seed, format) and answers with the image.

The model (about 20 GB with its text encoders) is downloaded into a Modal volume on the first start, so later starts only load it.
Cold starts restore a memory snapshot taken after each deploy. With the (experimental) GPU snapshot the pipeline comes back already on
the GPU; with DT_IMAGE_GPU_SNAPSHOT=0 the snapshot holds it on the CPU and only the copy to the GPU is left. The T5-XXL text encoder is skipped unless DT_IMAGE_T5=1: it is only worth its ~9 GB for long prompts and text in images.
To fill the volume beforehand on a CPU container (also after changing DT_IMAGE_MODEL, and to repair a download that was cut off):

    modal run modal_app.py::download
"""
import asyncio
import io
import os
import random
import sys
import time
from pathlib import Path

import modal

MODEL = os.environ.get("DT_IMAGE_MODEL", "stabilityai/stable-diffusion-3.5-medium")
GPU = os.environ.get("DT_IMAGE_GPU", "L4")  # 24 GB: the 2.5B MMDiT, the T5-XXL and both CLIP encoders fit in bf16 without offloading
GPU_SNAPSHOT = os.environ.get("DT_IMAGE_GPU_SNAPSHOT", "1") == "1"  # Modal's experimental GPU memory snapshot
T5 = os.environ.get("DT_IMAGE_T5", "0") == "1"  # without T5 only the CLIP encoders read the prompt (first 77 tokens)
STEPS = int(os.environ.get("DT_IMAGE_STEPS", "28"))  # the model card recommends 40 steps at guidance 4.5
GUIDANCE = float(os.environ.get("DT_IMAGE_GUIDANCE", "4.5"))
MAX_CONTAINERS = int(os.environ.get("DT_IMAGE_MAX_CONTAINERS", "1"))  # caps the parallel generations and with it the cost
IDLE_SECONDS = int(os.environ.get("DT_IMAGE_IDLE_SECONDS", "60"))  # how long a container stays warm after its last image
HF_SECRET = os.environ.get("DT_IMAGE_HF_SECRET", "huggingface")  # the Modal secret with HF_TOKEN

HF_HOME = "/hf"

MAX_PROMPT = 2048
MIN_SIDE, MAX_SIDE, DEFAULT_SIDE = 512, 1440, 1024  # SD 3.5 Medium is trained up to 1440 px; sides are rounded to multiples of 64
MAX_STEPS = 80
FORMATS = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.5.1", index_url="https://download.pytorch.org/whl/cu124")
    .pip_install("diffusers==0.32.2", "transformers==4.47.1", "accelerate==1.2.1", "sentencepiece==0.2.0", "protobuf==5.29.2",
                 "huggingface_hub[hf_transfer]==0.27.1", "pillow", "fastapi[standard]")
    # the options of `modal deploy` are read again when the container imports this file: the image carries them
    .env({"HF_HOME": HF_HOME, "HF_HUB_ENABLE_HF_TRANSFER": "1", "TOKENIZERS_PARALLELISM": "false", "DT_IMAGE_MODEL": MODEL,
          "DT_IMAGE_STEPS": str(STEPS), "DT_IMAGE_GUIDANCE": str(GUIDANCE), "DT_IMAGE_T5": "1" if T5 else "0",
          "DT_IMAGE_GPU_SNAPSHOT": "1" if GPU_SNAPSHOT else "0"})
)

models = modal.Volume.from_name("dungeontuber-imagegen-models", create_if_missing=True)
secrets = [modal.Secret.from_name(HF_SECRET)]

app = modal.App("dungeontuber-imagegen", image=image)


def log(message: str):
    print(f"[imagegen] {message}", file=sys.stderr, flush=True)


def marker() -> Path:
    return Path(HF_HOME) / f".complete-{MODEL.replace('/', '--')}"


def ensure_model(refresh: bool = False):
    """Downloads the model into the volume on the first start (a marker keeps later starts from asking Hugging Face).
    `refresh` asks Hugging Face anyway and completes a download that was cut off."""
    if marker().exists() and not refresh:
        os.environ["HF_HUB_OFFLINE"] = "1"  # read when huggingface_hub is imported
        return
    from huggingface_hub import snapshot_download

    started = time.monotonic()
    log(f"downloading {MODEL}, this takes a few minutes")
    # the single-file checkpoint duplicates the diffusers folders; only the latter are loaded
    snapshot_download(MODEL, ignore_patterns=["*.md", "*.gitattributes", "sd3.5_medium.safetensors", "text_encoders/*"])
    marker().write_text(MODEL, encoding="utf-8")
    models.commit()
    log(f"{MODEL} complete in {time.monotonic() - started:.0f} s")


@app.function(volumes={HF_HOME: models}, secrets=secrets, timeout=3600, cpu=2)
def download():
    """Fills the volume with the model (`modal run modal_app.py::download`); no GPU needed."""
    ensure_model(refresh=True)


def side(value, default: int = DEFAULT_SIDE) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return min(max(round(value / 64) * 64, MIN_SIDE), MAX_SIDE)


@app.cls(gpu=GPU, max_containers=MAX_CONTAINERS, scaledown_window=IDLE_SECONDS, timeout=900, volumes={HF_HOME: models},
         secrets=secrets, enable_memory_snapshot=True,
         experimental_options={"enable_gpu_snapshot": True} if GPU_SNAPSHOT else None)
class ImageGen:
    @modal.enter(snap=True)
    def load(self):
        """Runs before the memory snapshot is taken. Only a GPU snapshot has the GPU here; otherwise the pipeline stays on the CPU."""
        import torch
        from diffusers import StableDiffusion3Pipeline

        started = time.monotonic()
        ensure_model()
        extra = {} if T5 else {"text_encoder_3": None, "tokenizer_3": None}
        self.pipe = StableDiffusion3Pipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, **extra)
        if GPU_SNAPSHOT:
            self.pipe.to("cuda")
        log(f"{MODEL} loaded{'' if T5 else ' without T5'} in {time.monotonic() - started:.0f} s")

    @modal.enter(snap=False)
    def start(self):
        """Runs after every start or snapshot restore."""
        if self.pipe.device.type == "cuda":
            return
        started = time.monotonic()
        self.pipe.to("cuda")
        log(f"{MODEL} on the GPU in {time.monotonic() - started:.0f} s")

    def generate(self, request: dict) -> tuple[bytes, dict]:
        import torch

        seed = request.get("seed")
        seed = int(seed) if isinstance(seed, int) and 0 <= seed < 2 ** 31 else random.randint(0, 2 ** 31 - 1)
        prompt = str(request.get("prompt") or request.get("caption") or "").strip()[:MAX_PROMPT]
        negative = str(request.get("negative_prompt") or "").strip()[:MAX_PROMPT] or None
        width, height = side(request.get("width")), side(request.get("height"))
        steps = request.get("steps")
        steps = int(steps) if isinstance(steps, int) and 1 <= steps <= MAX_STEPS else STEPS
        guidance = request.get("guidance")
        guidance = float(guidance) if isinstance(guidance, (int, float)) and 0 <= guidance <= 20 else GUIDANCE
        fmt = str(request.get("format") or "png").lower().replace("jpg", "jpeg")
        fmt = fmt if fmt in FORMATS else "png"
        log(f"painting {width}x{height}, {steps} steps, guidance {guidance}: {prompt[:160]}")
        picture = self.pipe(prompt=prompt, negative_prompt=negative, width=width, height=height, num_inference_steps=steps,
                            guidance_scale=guidance, generator=torch.Generator("cuda").manual_seed(seed)).images[0]
        buffer = io.BytesIO()
        picture.save(buffer, format=fmt.upper(), **({"quality": 92} if fmt != "png" else {}))
        return buffer.getvalue(), {"seed": seed, "width": width, "height": height, "format": fmt}

    @modal.method()
    def paint(self, request: dict) -> tuple[bytes, dict]:
        """For `modal run` and other Modal clients; the web endpoint calls `generate` directly."""
        return self.generate(request)

    @modal.asgi_app(requires_proxy_auth=True)
    def web(self):
        from fastapi import FastAPI, HTTPException, Request, Response

        api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @api.post("/")
        async def paint(request: Request):
            try:
                body = await request.json()
            except ValueError:
                raise HTTPException(status_code=400, detail="JSON expected")
            if not isinstance(body, dict) or not str(body.get("prompt") or body.get("caption") or "").strip():
                raise HTTPException(status_code=400, detail="The prompt is missing")
            started = time.monotonic()
            try:
                data, info = await asyncio.to_thread(self.generate, body)
            except Exception as e:  # reported to the caller
                raise HTTPException(status_code=500, detail=str(e) or type(e).__name__)
            log(f"painted {info['width']}x{info['height']} in {time.monotonic() - started:.1f} s")
            return Response(content=data, media_type=FORMATS[info["format"]], headers={"X-Seed": str(info["seed"])})

        return api


@app.local_entrypoint()
def main(prompt: str, out: str = "image.png", width: int = DEFAULT_SIDE, height: int = DEFAULT_SIDE, seed: int = -1):
    """Paints one image from the command line without the web endpoint: `modal run modal_app.py --prompt "..."`."""
    request = {"prompt": prompt, "width": width, "height": height, "format": Path(out).suffix.lstrip(".") or "png"}
    if seed >= 0:
        request["seed"] = seed
    data, info = ImageGen().paint.remote(request)
    Path(out).write_bytes(data)
    print(f"{out}: {info['width']}x{info['height']}, seed {info['seed']}")
