# Music generation (ACE-Step 1.5 on Modal)

The **Compose** mode of the AI assistant generates new pieces for a scene. [`modal_app.py`](modal_app.py) runs
[ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) (MIT) in a [Modal](https://modal.com) function. When the server posts a
request, a GPU container starts. It stops again once it is idle, so you only pay for the seconds a piece takes. The server stores
the piece in the chosen library folder and tags it (title, artist `ACE-Step`, the description as comment). An analysis agent or the
cloud analysis then rates it like any other song.

This is not an agent: the server calls the function, and nothing connects to the server.

```bash
pip install modal && modal setup
cd agents/musicgen && modal deploy modal_app.py
```

The endpoint uses Modal's proxy auth: Modal rejects requests without a valid key and secret before a container starts. To connect
the server:

1. In the Modal dashboard, create a proxy auth token (Settings → Proxy Auth Tokens). You can reuse the token of the cloud analysis.
2. Under Settings → AI Assistant → Music generation, enter the URL that `modal deploy` prints together with the token's key and
   secret.

With a Groq key (preferred, e.g. gpt-oss-120b) or a Gemini key, the assistant turns the scene into the English description that ACE-Step expects (genre, instruments, mood,
tempo), plus a title and lyrics when vocals are selected. You can refine it in the chat ("darker, slower"). Without either key,
your text is used as the description as it is.

## Options (environment variables at deploy time)

| Variable | Default | Meaning |
|---|---|---|
| `DT_MUSIC_GPU` | `L4` | GPU type. The 24 GB of an L4 or A10G run the models without offloading. |
| `DT_MUSIC_DIT` | `acestep-v15-xl-sft` | The composer. The XL models (4B) give the best quality and fit an L4 without offloading. `acestep-v15-sft` (2B) is about twice as fast. `acestep-v15-turbo` needs only 8 steps and takes seconds, with plainer sound. |
| `DT_MUSIC_REWRITE_CAPTION` | `0` | `1` lets the ACE-Step planner rewrite the description. It tends to drop the specific instruments, so it's off. |
| `DT_MUSIC_STEPS` | `50` | Diffusion steps of the non-turbo models (32 to 64 recommended). Turbo always uses 8. |
| `DT_MUSIC_LM` | `acestep-5Hz-lm-1.7B` | The planner (structure, BPM, key, lyrics timing). `acestep-5Hz-lm-4B` plans a little better, but next to an XL composer it only fits a GPU with more memory than an L4 (e.g. `DT_MUSIC_GPU=L40S`). |
| `DT_MUSIC_MAX_CONTAINERS` | `1` | Caps the number of parallel generations, and with it the cost. |
| `DT_MUSIC_IDLE_SECONDS` | `120` | How long a container stays warm after its last piece. |

To download the models beforehand on a cheap CPU container, use the same options as for the deployment. This also repairs a
download that was cut off:

```bash
modal run modal_app.py::download
```

The first start downloads the models (about 10 GB) into the Modal volume `dungeontuber-musicgen-models` and takes a few minutes.
Later cold starts only load the models. A warm container composes a two-minute piece in seconds.

The app is pinned to a tested ACE-Step commit (`ACE_STEP_COMMIT`). A newer commit may change its Python API.

## Getting good results

* ACE-Step reads the song structure from the lyrics. Instrumental pieces get `[Instrumental]`. Pieces with vocals need lyrics with
  section tags (`[Verse]`, `[Chorus]`, …). If the assistant sends none, the ACE-Step planner writes them.
* Real instruments and a recorded production in the description ("lute and fiddle, live tavern recording") sound far better than
  ambient, pad or drone words, which push the result toward synthesizers. The assistant is instructed accordingly.
* For faster, cheaper pieces, deploy the 2B model and the 1.7B planner:

```bash
DT_MUSIC_DIT=acestep-v15-sft DT_MUSIC_LM=acestep-5Hz-lm-1.7B modal deploy modal_app.py
```
