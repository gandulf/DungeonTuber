# Sounds and background music (Stable Audio 3 on Modal)

[`modal_app.py`](modal_app.py) runs [Stable Audio 3](https://github.com/Stability-AI/stable-audio-3) in a
[Modal](https://modal.com) function. It turns a description into background music, an ambience (rain, a tavern crowd, a cave) or a
sound effect (a sword clash, a door). When a request comes in, a GPU container starts. It stops again once it is idle, so you only pay
for the seconds a sound takes.

This is not an agent: the server calls the function, and nothing connects to the server. In DungeonTuber, the **Generate** mode of
the AI assistant (kinds Background music, Ambience and Sound effect) turns a scene into a description, creates the sound and stores it in the effects folder (or a folder you choose).
Enter the URL that `modal deploy` prints and the key and secret of a proxy auth token under Settings → AI Assistant → Sound
generation, or set `DT_SOUNDGEN_URL`, `DT_SOUNDGEN_KEY` and `DT_SOUNDGEN_SECRET` on the server.

Stable Audio 3 makes instrumental audio only, without singing. For songs with vocals, use the [music generation](../musicgen/README.md)
(ACE-Step).

## Deploy

The models are gated on Hugging Face:

1. Accept the license on the model page: [stable-audio-3-medium](https://huggingface.co/stabilityai/stable-audio-3-medium)
   (or the small model you deploy).
2. If the first start reports that access to `google/t5gemma-b-b-ul2` is missing, accept that license too.
3. Create a read token on Hugging Face and store it as a Modal secret.
4. Deploy the app:

```bash
pip install modal && modal setup
modal secret create huggingface HF_TOKEN=hf_...
cd agents/soundgen && modal deploy modal_app.py
```

The endpoint uses Modal's proxy auth like the music generation: Modal rejects requests without a valid key and secret before a
container starts. Create a proxy auth token in the Modal dashboard (Settings → Proxy Auth Tokens), or reuse the one of the music
generation.

## Request

`POST` JSON to the URL that `modal deploy` prints, with the headers `Modal-Key` and `Modal-Secret`. The answer is an mp3, and the
`X-Seed` header carries the seed.

| Field | Meaning |
|---|---|
| `caption` (or `prompt`) | English description, e.g. `"rain on a canvas tent, distant thunder, crackling campfire"` |
| `kind` | `music` (default), `ambience` or `sfx`. It puts the dataset tags in front (`TrackType: Music, VocalType: Instrumental` or `TrackType: SFX`) unless the description already has `TrackType:` |
| `duration` | Seconds: 1 to 380 (`medium`) or 1 to 120 (small models). Defaults: music 120, ambience 60, sfx 5 |
| `bpm` | Tempo of music, appended as `… 110 BPM` |
| `seed` | For a reproducible result; random without it |

The body is the same as for the music generation, so this URL also works as the music generation endpoint under Settings → AI
Assistant. You then get instrumental pieces from Stable Audio 3 instead of ACE-Step.

```bash
curl -X POST "$URL" -H "Modal-Key: $KEY" -H "Modal-Secret: $SECRET" -H "Content-Type: application/json" \
     -d '{"kind": "ambience", "caption": "busy medieval tavern, murmuring crowd, clinking mugs, fire crackling", "duration": 60}' \
     -o tavern.mp3
```

## Options (environment variables at deploy time)

| Variable | Default | Meaning |
|---|---|---|
| `DT_SOUND_MODEL` | `medium` | `medium` (1.4B) does music, ambiences and effects up to 380 s. `small-music` and `small-sfx` (433M, 120 s) do one of them. |
| `DT_SOUND_GPU` | `L4` | GPU type. `medium` needs Flash Attention 2, so it needs Ampere or newer (L4, A10G, A100, …), not a T4. With `none` a small model runs on a CPU container. |
| `DT_SOUND_STEPS` | `8` | Diffusion steps. The released models are distilled to 8. |
| `DT_SOUND_MAX_CONTAINERS` | `1` | Caps the number of parallel generations, and with it the cost. |
| `DT_SOUND_IDLE_SECONDS` | `120` | How long a container stays warm after its last sound. |
| `DT_SOUND_GPU_SNAPSHOT` | `1` | Cold starts restore a memory snapshot with the model already loaded: Modal's experimental GPU snapshot on a GPU, a plain memory snapshot with `DT_SOUND_GPU=none`. The first starts after each `modal deploy` are slower while Modal takes the snapshot. `0` loads the model on every start. |
| `DT_SOUND_HF_SECRET` | `huggingface` | Name of the Modal secret with `HF_TOKEN`. |

The first start downloads the model into the Modal volume `dungeontuber-soundgen-models`. To do that beforehand on a CPU container
(also after changing `DT_SOUND_MODEL`, and to repair a download that was cut off), use the same options as for the deployment:

```bash
modal run modal_app.py::download
```

The app is pinned to a tested Stable Audio 3 commit (`SA3_COMMIT`). Stable Audio 3 itself takes well under a second for a
two-minute piece on a large GPU; the cold start of a container takes longer.

## Getting good results

The models learned from Freesound and AudioSparx descriptions, so describe a sound the way those sites do
([prompting guide](https://github.com/Stability-AI/stable-audio-3/blob/main/docs/guides/prompting.md)):

* **Music:** genre, instruments and how they sound, mood, BPM, e.g. *"A sombre medieval folk piece, solo lute with delicate finger
  picking, low drone of a hurdy-gurdy, cavernous reverb, 70 BPM"*.
* **Effects:** the source, the action and the recording, e.g. *"A heavy wooden door slamming shut in a stone hall, short decay,
  close mic"*. Keep the duration short.
* **Ambiences:** several layered sources and the place, e.g. *"night forest, crickets, an owl in the distance, wind in the leaves"*.

Licence: [Stability AI Community License](https://stability.ai/license). Free for individuals and organizations with less than
1 M USD annual revenue.
