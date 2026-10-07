"""Voxalyzer on demand on Modal (https://modal.com): a GPU container starts when the DungeonTuber server posts an mp3 and stops again
when it is idle, so you only pay for the seconds an analysis takes (the monthly free credit covers a lot of songs).

    pip install modal && modal setup
    cd agents/voxalyzer && modal deploy modal_app.py

The endpoint is protected by Modal's proxy auth: Modal rejects requests without a valid key and secret before any container starts.
Create a proxy auth token in the Modal dashboard (Settings -> Proxy Auth Tokens) and enter it together with the URL that `modal deploy`
prints in DungeonTuber under Settings -> Agents -> Cloud analysis.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import modal

GPU = os.environ.get("DT_CLOUD_GPU", "T4")  # e.g. "L4" is faster for a little more
CPU = float(os.environ.get("DT_CLOUD_CPU", "4"))  # reserved CPU cores: decoding and feature extraction run on the CPU, Modal reserves very little by default
MAX_CONTAINERS = int(os.environ.get("DT_CLOUD_MAX_CONTAINERS", "2"))  # caps the parallel analyses and with it the cost
IDLE_SECONDS = int(os.environ.get("DT_CLOUD_IDLE_SECONDS", "60"))  # how long a container stays warm after its last analysis

image = (
    # onnxruntime-gpu needs CUDA 13 and cuDNN 9 (libcublasLt.so.13): the plain debian_slim image has neither
    modal.Image.from_registry("nvidia/cuda:13.0.3-cudnn-runtime-ubuntu24.04", add_python="3.12")
    .apt_install("ffmpeg")
    .pip_install("numpy", "mutagen", "numba", "librosa", "pydub", "websockets", "onnxruntime-gpu", "fastapi[standard]")
    .env({"DT_MODEL_DIR": "/models", "PYTHONPATH": "/app"})  # PYTHONPATH also for the build step below
    .add_local_dir(Path(__file__).resolve().parent / "voxalyzer", remote_path="/app/voxalyzer", copy=True, ignore=["__pycache__", "*.pyc"])
    .run_commands("python -c \"from voxalyzer.models import ensure_models; ensure_models()\"")  # the models are part of the image
)

app = modal.App("dungeontuber-voxalyzer", image=image)


def log(message: str):
    print(f"[voxalyzer] {message}", file=sys.stderr, flush=True)  # stderr like the onnxruntime messages, which show up in the Modal logs


@app.cls(gpu=GPU, cpu=CPU, max_containers=MAX_CONTAINERS, scaledown_window=IDLE_SECONDS, timeout=900)
class Voxalyzer:
    @modal.enter()
    def start(self):
        import onnxruntime as ort
        from voxalyzer.analyzer import begin_session
        from voxalyzer.models import model_path

        # onnxruntime silently falls back to the CPU when the CUDA libraries are missing: say in the logs which one is used
        providers = ort.InferenceSession(model_path("msd-musicnn-1.onnx"), providers=["CUDAExecutionProvider", "CPUExecutionProvider"]).get_providers()
        self.device = "GPU" if providers[0] == "CUDAExecutionProvider" else "CPU only: check the CUDA libraries"
        log(f"execution providers: {providers} ({self.device})")
        self.session = begin_session()

    @modal.exit()
    def stop(self):
        from voxalyzer.analyzer import end_session
        end_session(self.session)

    @modal.asgi_app(requires_proxy_auth=True)
    def web(self):
        from fastapi import FastAPI, HTTPException, Request
        from voxalyzer.cloud import MAX_UPLOAD_BYTES, analyze_bytes

        api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @api.post("/")
        async def analyze(request: Request):
            data = await request.body()
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="File too large")
            started = time.monotonic()
            try:
                result = await asyncio.to_thread(analyze_bytes, data, self.session)
                log(f"analyzed {len(data) / 1e6:.1f} MB in {time.monotonic() - started:.1f} s ({self.device})")
                return result
            except Exception as e:  # reported to the server, which shows it with the file
                raise HTTPException(status_code=500, detail=str(e) or type(e).__name__)

        return api
