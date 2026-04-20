# Install

Three paths. All three give you `do` and `doer` on your `$PATH`.

=== "pipx (recommended)"

    Isolated, auto-updatable, no venv shenanigans.

    ```bash
    pipx install doer-cli
    ```

    Upgrade later:
    ```bash
    pipx upgrade doer-cli
    ```

=== "pip"

    Any venv. Global if you insist.

    ```bash
    pip install doer-cli
    ```

=== "curl (binary, coming soon)"

    Prebuilt binaries will land on GitHub Releases shortly. For now, use `pipx`.

    !!! note "what to expect"
        ```bash
        # once released:
        curl -sSL https://github.com/cagataycali/doer-cli/releases/latest/download/install.sh | sh
        ```
        Installs to `~/.local/bin`. No Python required.

### optional extras

```bash
pip install 'doer-cli[mlx]'   # local text inference + LoRA training (Apple Silicon)
pip install 'doer-cli[vlm]'   # vision/audio/video + VLM LoRA (Apple Silicon)
pip install 'doer-cli[hf]'    # huggingface dataset upload for your training corpus
pip install 'doer-cli[all]'   # everything above
```

Each extra is opt-in. The default install stays lean.

## two binaries, one brain

```bash
do   "quick question"     # short form — shell loves brevity
doer "longer query"       # long form — when clarity wins
```

Both resolve to the same entry point.

## requirements

| requirement       | notes                                     |
| ----------------- | ----------------------------------------- |
| Python **3.10+**                            | only for `pip`/`pipx` paths                       |
| [Ollama](https://ollama.com) *or* AWS creds | one of the two — `doer` auto-detects              |
| A model                                     | `ollama pull qwen3:1.7b` *or* Bedrock Claude access *or* MLX base (auto-download) |
| Apple Silicon *(for MLX only)*              | M1/M2/M3/M4 Mac — opt-in `[mlx]` extra           |
| Apple Silicon *(for multimodal)*            | `[vlm]` extra — vision/audio/video via `mlx-vlm`   |

## pick a backend

`doer` auto-detects at runtime:

1. `--img`/`--audio`/`--video` flag present **and** `mlx-vlm` installed → **mlx-vlm** (routes to vision/audio/omni model)
2. AWS creds present (`AWS_BEARER_TOKEN_BEDROCK` / STS / SSO) → **bedrock**
3. Apple Silicon **and** `strands_mlx` installed → **mlx**
4. Fallback → **ollama**

Override with `DOER_PROVIDER=bedrock|mlx|mlx-vlm|ollama`.

### bedrock (cloud, default)

Frontier Claude models, zero local compute. Requires AWS credentials and Bedrock model access.

```bash
# simplest: bearer token (get one from the Bedrock console)
export AWS_BEARER_TOKEN_BEDROCK=abc...

# or standard AWS creds
export AWS_PROFILE=my-profile

do "reply: ok"
# → ok
```

**Defaults** (all overridable via env):

| setting | value |
|---|---|
| model | `global.anthropic.claude-opus-4-7` |
| region | `us-west-2` |
| context | **1M tokens** (via `context-1m-2025-08-07` beta, auto) |
| output | **128k tokens** (Opus 4.7 native max) |

Pin a different model:
```bash
DOER_BEDROCK_MODEL=us.anthropic.claude-sonnet-4-20250514-v1:0 do "..."
DOER_BEDROCK_MODEL=global.anthropic.claude-opus-4-6  do "..."
```

### ollama (local, private)

No API keys. Runs on your laptop. Great for offline and sensitive work.

```bash
# macOS
brew install ollama
ollama serve &
ollama pull qwen3:1.7b

# linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:1.7b

# force ollama even when AWS creds exist
DOER_PROVIDER=ollama do "reply: ok"
# → ok
```

Switch ollama model:
```bash
DOER_MODEL=llama3.2:3b do "explain this file"
DOER_MODEL=qwen3:4b    do "write a sql query"
```

Persist your choice:
```bash
echo 'export DOER_PROVIDER=ollama' >> ~/.zshrc
echo 'export DOER_MODEL=qwen3:4b'  >> ~/.zshrc
```


### mlx (Apple Silicon, opt-in)

For on-device inference with a LoRA adapter you trained yourself. Requires Apple Silicon (M-series).

```bash
pip install 'doer-cli[mlx]'        # adds strands-mlx + mlx-lm (~500MB)

# first run downloads the base model from HF
DOER_PROVIDER=mlx do "reply: ok"
# → ok

# hot-swap your trained self (see: Train on yourself)
DOER_PROVIDER=mlx DOER_ADAPTER=~/.doer_adapter do "..."
```

Change base model:
```bash
DOER_MLX_MODEL=mlx-community/Qwen3-4B-4bit do "..."
```

See [**Train on yourself**](train.md) for the full collect → train → swap loop.


### mlx-vlm (multimodal on Apple Silicon, opt-in)

Vision, audio, and video via `mlx-vlm` — routed automatically when you pass
`--img`, `--audio`, or `--video` flags.

```bash
pip install 'doer-cli[vlm]'        # adds mlx-vlm + datasets

do --img screenshot.png  "what's in this UI?"
do --audio meeting.wav   "transcribe + action items"
do --video clip.mp4      "what's happening here?"
do --img a.png --audio b.wav "..."   # omni model (auto-picked)
```

Models are auto-selected based on the modality mix; override with env vars:

| modality        | default model                                           | env override             |
|-----------------|---------------------------------------------------------|--------------------------|
| image only      | `mlx-community/Qwen2.5-VL-3B-Instruct-4bit`             | `DOER_MLX_VLM_MODEL`     |
| audio only      | `mlx-community/gemma-3n-E2B-it-4bit`                    | `DOER_MLX_AUDIO_MODEL`   |
| image + audio   | `mlx-community/Qwen3-Omni-30B-A3B-Instruct-4bit`        | `DOER_MLX_OMNI_MODEL`    |

Train a VLM LoRA on your own multimodal corpus:

```bash
do --train-vlm 300                             # → ~/.doer_vlm_adapter
DOER_PROVIDER=mlx-vlm DOER_VLM_ADAPTER=~/.doer_vlm_adapter do --img x.png "..."
```

## troubleshooting

!!! warning "`connection refused` (Ollama)"
    Ollama isn't running. `ollama serve` in another terminal.

!!! warning "`model not found` (Ollama)"
    Pull it first: `ollama pull qwen3:1.7b`

!!! warning "`AccessDeniedException` / `ValidationException` (Bedrock)"
    Your AWS creds don't have access to the default model. Either request access in the Bedrock console, or switch:
    `DOER_BEDROCK_MODEL=us.anthropic.claude-sonnet-4-20250514-v1:0 do "..."`

!!! warning "`invalid beta flag` (Bedrock)"
    A model rejected a beta header you set. Clear it: `DOER_ANTHROPIC_BETA="" do "..."`

!!! warning "`temperature/top_p` 400 error (Bedrock)"
    Opus 4.7+ rejects any non-default sampling values. Unset `DOER_TEMPERATURE` / `DOER_TOP_P`, or pin an older model.

!!! warning "slow first call"
    Ollama loads the model into RAM on first call. Subsequent calls are fast.
    Ambient tip: `ollama run qwen3:1.7b "" &` to warm it in the background.

!!! warning "`command not found: do`"
    `pipx` installed but `~/.local/bin` isn't on `$PATH`. Run `pipx ensurepath` and restart your shell.

## uninstall

```bash
pipx uninstall doer-cli     # pipx users
pip  uninstall doer-cli     # pip users
rm ~/.local/bin/do ~/.local/bin/doer    # binary users
```

That's it. No config dirs. No leftovers. Nothing to clean up.
