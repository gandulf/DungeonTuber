# Image generation (Stable Diffusion 3.5 Medium on Modal)

[`modal_app.py`](modal_app.py) runs [Stable Diffusion 3.5 Medium](https://huggingface.co/stabilityai/stable-diffusion-3.5-medium)
in a [Modal](https://modal.com) function and turns a prompt into an image (cover art, scene pictures, …). When a request is posted,
a GPU container starts. It stops again once it is idle, so you only pay for the seconds an image takes.

This is not an agent: callers post to the function, and nothing connects to the server.

## Deploy

The model is gated on Hugging Face:

1. Accept the license on the [model page](https://huggingface.co/stabilityai/stable-diffusion-3.5-medium).
2. Create a read token on Hugging Face and store it as a Modal secret (you can reuse the one of the sound generation).
3. Deploy the app:

```bash
pip install modal && modal setup
modal secret create huggingface HF_TOKEN=hf_...
cd agents/imagegen && modal deploy modal_app.py
```

The endpoint uses Modal's proxy auth like the music and sound generation: Modal rejects requests without a valid key and secret
before a container starts. Create a proxy auth token in the Modal dashboard (Settings → Proxy Auth Tokens), or reuse an existing one.

## Request

`POST` JSON to the URL that `modal deploy` prints, with the headers `Modal-Key` and `Modal-Secret`. The answer is the image, and the
`X-Seed` header carries the seed.

| Field | Meaning |
|---|---|
| `prompt` (or `caption`) | English description, e.g. `"a torch-lit dungeon corridor, moss on the stones, oil painting"` |
| `negative_prompt` | What to avoid, e.g. `"text, watermark, blurry"` |
| `width`, `height` | Pixels, 512 to 1440, rounded to multiples of 64. Default 1024 × 1024 |
| `steps` | Diffusion steps, 1 to 80. Default `DT_IMAGE_STEPS` |
| `guidance` | Classifier-free guidance, 0 to 20. Default `DT_IMAGE_GUIDANCE` |
| `seed` | For a reproducible result; random without it |
| `format` | `png` (default), `jpeg` or `webp` |

```bash
curl -X POST "$URL" -H "Modal-Key: $KEY" -H "Modal-Secret: $SECRET" -H "Content-Type: application/json" \
     -d '{"prompt": "a cozy medieval tavern at night, warm candle light, fantasy illustration", "width": 1344, "height": 768}' \
     -o tavern.png
```

Without the web endpoint, straight from the command line:

```bash
modal run modal_app.py --prompt "an ancient red dragon sleeping on a hoard of gold" --out dragon.png
```

## Options (environment variables at deploy time)

| Variable | Default | Meaning |
|---|---|---|
| `DT_IMAGE_MODEL` | `stabilityai/stable-diffusion-3.5-medium` | Hugging Face repository. `stabilityai/stable-diffusion-3.5-large-turbo` or `-large` also work, but need a GPU with more memory (`DT_IMAGE_GPU=A100-40GB`). |
| `DT_IMAGE_GPU` | `L4` | GPU type. The 24 GB of an L4 or A10G hold the model and its text encoders in bf16. |
| `DT_IMAGE_T5` | `0` | `1` also loads the T5-XXL text encoder (~9 GB): better for long prompts and text in images, slower cold starts. |
| `DT_IMAGE_GPU_SNAPSHOT` | `1` | Modal's experimental GPU memory snapshot: cold starts restore the pipeline already on the GPU. `0` falls back to a CPU snapshot plus the copy to the GPU. |
| `DT_IMAGE_STEPS` | `40` | Default diffusion steps (the model card recommends 40). |
| `DT_IMAGE_GUIDANCE` | `4.5` | Default guidance scale. |
| `DT_IMAGE_MAX_CONTAINERS` | `1` | Caps the number of parallel generations, and with it the cost. |
| `DT_IMAGE_IDLE_SECONDS` | `120` | How long a container stays warm after its last image. |
| `DT_IMAGE_HF_SECRET` | `huggingface` | Name of the Modal secret with `HF_TOKEN`. |

The first start downloads the model (about 20 GB with the T5 text encoder) into the Modal volume `dungeontuber-imagegen-models`. To
do that beforehand on a CPU container (also after changing `DT_IMAGE_MODEL`, and to repair a download that was cut off), use the same
options as for the deployment:

```bash
modal run modal_app.py::download
```

Cold starts restore a Modal memory snapshot with the pipeline already on the GPU (`DT_IMAGE_GPU_SNAPSHOT`, experimental). The
first starts after each `modal deploy` are slower while Modal takes the snapshot.

## Getting good results

* Describe the subject, the setting, the light and the style: *"a hooded rogue in a rain-soaked alley, lantern light, ink and
  watercolor illustration"*. SD 3.5 follows long, natural sentences well and, with T5 on, can render short text in quotes.
* Put the style and the main subject first. Two of the three text encoders (CLIP) read only the first 77 tokens (about 60 words)
  and log `The following part of your input was truncated…` for the rest; only the T5 encoder sees the whole prompt, and it is off
  unless `DT_IMAGE_T5=1`. The warning is harmless, but whatever comes after the first ~60 words is ignored without T5.
* Wide formats (1344 × 768) suit scene backgrounds, square ones cover art.
* Keep a seed you like and vary only the prompt to get a consistent series.

Licence: [Stability AI Community License](https://stability.ai/license). Free for individuals and organizations with less than
1 M USD annual revenue.
