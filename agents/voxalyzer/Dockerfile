# 1. Use NVIDIA CUDA as the base
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

# 2. Set environment variables to avoid prompts during install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 3. Install System Dependencies Python,Pip
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*


# 4. Install project and dependencies
RUN pip3 install --no-cache-dir --break-system-packages numpy mutagen websockets onnx onnxruntime-gpu numba librosa pydub

# Copy project files
COPY voxalyzer/ ./voxalyzer/

# The models are not part of the repo: fetched from the GitHub release while building (DT_MODELS_URL to use another location)
ENV DT_MODEL_DIR=/models
RUN python3 -c "from voxalyzer.models import ensure_models; ensure_models()"

# Connects out to a DungeonTuber server: docker run --gpus all voxalyzer --token <token> --server <url>
ENTRYPOINT ["python3", "-m", "voxalyzer"]
