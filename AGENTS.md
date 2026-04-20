# AGENTS.md — doer

## project
- **what:** one-file pipe-native AI agent
- **lang:** python 3.10+
- **dep:** `strands-agents[ollama]` (core); optional extras: `[mlx]` · `[vlm]` · `[hf]` · `[all]`
- **entry:** `doer/__init__.py` · ~730 lines
- **install:** `pip install doer-cli` or download binary from releases
- **license:** Apache-2.0

## architecture

```
doer/
├── __init__.py    # everything: Agent, shell tool, CLI, prompt
├── __main__.py    # python -m doer
hf_jobs/           # cloud training (burn HF credits, not battery)
├── train_text_lora.py  # UV script: any causal LM → LoRA → merged push
├── train_vlm.py        # UV script: Qwen2.5-VL image+text LoRA
├── train_omni.py       # UV script: Qwen-Omni text+audio+image LoRA
├── launch.sh           # one-shot dispatcher (text|vlm|omni|ps|logs|hw)
└── README.md
SOUL.md            # identity (injected into system prompt if in cwd)
AGENTS.md          # project rules (injected if in cwd)
doer.svg           # brand mark
build.sh           # local PyInstaller build
.github/workflows/
└── release.yml    # tag v* → binaries + PyPI
```

## design rules

1. **one source file** — all logic in `doer/__init__.py`
2. **lean deps** — `strands-agents[ollama]` core; `mlx`/`vlm`/`hf` are opt-in extras, zero cost if unused
3. **no classes unless the SDK forces it** — functions are cheaper
4. **context over memory** — don't store state, recompute from filesystem
5. **unix over RPC** — stdin/stdout/pipes, not HTTP/WebSocket
6. **env vars over config files** — `DOER_*` knobs, never `~/.doerrc`

## prompt injection (what the agent sees every call)

Built fresh on every call by `_build_prompt()`:
- env (`sys.platform`) + cwd (`Path.cwd()`)
- model info + own `__file__` path
- `SOUL.md` from cwd (if present)
- `AGENTS.md` from cwd (if present)
- `~/.doer_history` — last `DOER_HISTORY` Q/A pairs (default 10)
- `~/.bash_history` + `~/.zsh_history` — last `DOER_SHELL_HISTORY` commands (default 20)
- `--img` / `--audio` / `--video` flags → raw media attached (auto-routes to VLM)
- full source of `doer/__init__.py` — self-awareness

## conventions

- responses are **terse**. no filler.
- when stdin is piped → no markdown decoration.
- tool calls: use `shell` freely, no asking.
- add tools by dropping `@tool` fns into `./tools/*.py` (strands hot-reload).

## env knobs

| var                              | default                                           | purpose                       |
| -------------------------------- | ------------------------------------------------- | ----------------------------- |
| `DOER_PROVIDER`                  | *auto* (bedrock if AWS creds, else ollama)        | `ollama` \| `bedrock`         |
| `DOER_MODEL`                     | `qwen3:1.7b`                                      | ollama model id               |
| `OLLAMA_HOST`                    | `http://localhost:11434`                          | ollama endpoint               |
| `DOER_BEDROCK_MODEL`             | `global.anthropic.claude-opus-4-7`                | bedrock model id              |
| `DOER_BEDROCK_REGION`            | `$AWS_REGION` or `us-west-2`                      | bedrock region                |
| `AWS_BEARER_TOKEN_BEDROCK`       | *(unset)*                                         | bearer-token auth for bedrock |
| `DOER_MAX_TOKENS`                | `128000` (Opus 4.7 native max)                    | bedrock max_tokens            |
| `DOER_TEMPERATURE`               | *(model default)*                                 | bedrock temperature           |
| `DOER_TOP_P`                     | *(model default)*                                 | bedrock top_p                 |
| `DOER_CACHE_PROMPT`              | *off*                                             | bedrock prompt caching (1/true) |
| `DOER_BEDROCK_GUARDRAIL_ID`      | *(unset)*                                         | bedrock guardrail id          |
| `DOER_BEDROCK_GUARDRAIL_VERSION` | *(unset)*                                         | bedrock guardrail version     |
| `DOER_ANTHROPIC_BETA`            | `context-1m-2025-08-07` (on Claude models)        | comma-sep `anthropic_beta` headers |
| `DOER_ADDITIONAL_REQUEST_FIELDS` | *(unset)*                                         | raw JSON for `additional_request_fields` |
| `DOER_HISTORY`                   | `10`                                              | Q/A pairs in prompt           |
| `DOER_SHELL_HISTORY`             | `20`                                              | shell cmds in prompt          |
| `DOER_MLX_MODEL`                 | `mlx-community/Qwen3-1.7B-4bit`                   | mlx model id (Apple Silicon)  |
| `DOER_ADAPTER`                   | *(unset)*                                         | LoRA adapter path (hot-swap)  |
| `DOER_MAX_SEQ_LEN`               | `32768`                                           | mlx LoRA training max seq len |
| `DOER_MLX_VLM_MODEL`             | `mlx-community/Qwen2.5-VL-3B-Instruct-4bit`       | vision model (--img)          |
| `DOER_MLX_AUDIO_MODEL`            | `mlx-community/gemma-3n-E2B-it-4bit`              | audio model (--audio)         |
| `DOER_MLX_OMNI_MODEL`             | `mlx-community/Qwen3-Omni-30B-A3B-Instruct-4bit`  | omni (img+audio mix)          |
| `DOER_VLM_ADAPTER`                | *(unset)*                                         | VLM LoRA adapter path         |
| `DOER_DEBUG`                     | *(unset)*                                         | print training-log errors     |
| `DOER_HF_REPO`                   | `<hf-user>/doer-training`                         | target HF dataset for upload  |
| `HF_TOKEN`                       | *(fallback: `~/.cache/huggingface/token`)*        | HuggingFace auth token        |

### provider auto-detect

- if `--img`/`--audio`/`--video` flag present AND `mlx-vlm` installed → **mlx-vlm** (auto-routes to vision/audio/omni model)
- else if any of `AWS_BEARER_TOKEN_BEDROCK`, `AWS_ACCESS_KEY_ID`, or `AWS_PROFILE` is set → **bedrock**
- else if on `darwin-arm64` AND `strands_mlx` importable → **mlx**
- otherwise → **ollama**
- force with `DOER_PROVIDER=ollama|bedrock|mlx|mlx-vlm`

### bedrock notes

- **zero new deps** — `boto3` comes with `strands-agents` core
- credentials via normal boto3 chain (env vars, `~/.aws/credentials`, IAM role, SSO)
- supports bearer-token auth via `AWS_BEARER_TOKEN_BEDROCK`
- full feature surface: guardrails, prompt caching (`cache_config` auto), max_tokens, temperature, top_p
- extend by editing `_model()` in `doer/__init__.py` — the SDK's `BedrockConfig` TypedDict has the full list

### Claude Opus 4.7 defaults (breaking changes from 4.6)

- **Default model**: `global.anthropic.claude-opus-4-7` (1M context, 128k output, adaptive thinking)
- **`max_tokens`** defaults to `128000` (the model's native max)
- **`anthropic_beta`** defaults to `context-1m-2025-08-07` (enables 1M context window)
- **`temperature` / `top_p`** — **do not set** on Opus 4.7+; any non-default value returns 400. Doer only sends these when `DOER_TEMPERATURE` / `DOER_TOP_P` are explicitly set.
- **No `output-300k` yet**: despite appearing in the SDK's `AnthropicBetaParam` list, `output-300k-2026-03-24` isn't accepted by Bedrock for Opus 4.7 (returns `invalid beta flag`). Opus 4.7's real output cap is **128k**, per the [launch notes](https://docs.claude.com/en/docs/about-claude/models/whats-new-claude-4-7).

To opt out of the default beta: `DOER_ANTHROPIC_BETA="" doer "..."`

### bedrock beta headers (`anthropic-beta`)

Both env vars route into Bedrock Converse as `additional_request_fields`.
`DOER_ANTHROPIC_BETA` is the convenient shortcut; `DOER_ADDITIONAL_REQUEST_FIELDS` is the escape hatch. They **merge** — `anthropic_beta` values are concatenated and deduped.

```bash
# 1M context window (Claude 4+)
DOER_ANTHROPIC_BETA=context-1m-2025-08-07 doer "huge prompt..."

# stack multiple betas
DOER_ANTHROPIC_BETA="context-1m-2025-08-07,interleaved-thinking-2025-05-14" doer "..."

# raw escape hatch (for beta fields other than anthropic_beta)
DOER_ADDITIONAL_REQUEST_FIELDS='{"anthropic_beta":["context-1m-2025-08-07"],"tools":[...]}' doer "..."
```

Authoritative list: [anthropic-sdk-python/types/anthropic_beta_param.py](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/anthropic_beta_param.py). Common headers for Claude Opus 4.7 / Sonnet 4+:

| header                                 | what it does                                   |
| -------------------------------------- | ---------------------------------------------- |
| `context-1m-2025-08-07`                | 1M context window                              |
| `context-management-2025-06-27`        | server-side context editing                    |
| `extended-cache-ttl-2025-04-11`        | 1-hour prompt cache (vs 5min default)          |
| `interleaved-thinking-2025-05-14`      | interleaved extended thinking + tool use       |
| `output-128k-2025-02-19`               | 128K output tokens                             |
| `output-300k-2026-03-24`               | 300K output tokens                             |
| `fast-mode-2026-02-01`                 | low-latency inference                          |
| `token-efficient-tools-2025-02-19`     | fine-grained tool streaming                    |
| `computer-use-2025-01-24`              | computer use tool                              |
| `code-execution-2025-05-22`            | server-side code execution                     |
| `files-api-2025-04-14`                 | files API                                      |
| `mcp-client-2025-11-20`                | MCP client beta                                |
| `skills-2025-10-02`                    | claude skills                                  |
| `advisor-tool-2026-03-01`              | advisor tool                                   |

**Caveats**:
- Not every beta is available on Bedrock yet (API returns `invalid beta flag` — harmless, just drop the unsupported one)
- Not every beta is valid for every model (e.g. `output-300k` is Opus 4.7+ only)

## testing

```bash
pip install -e .
doer "reply: ok"

# pipe test
echo "hello" | doer "translate to turkish, one word"

# self-awareness test
doer "what's your file path? just the path"

# context test
echo "# SOUL\nI am Groot." > /tmp/SOUL.md && cd /tmp && doer "who are you?"
```

## release

```bash
git tag v0.2.0 && git push --tags
# → CI builds binaries (linux/macOS), publishes to PyPI
```

## training loop (mlx provider, Apple Silicon)

doer closes the training loop **in one repo**, one file, no indirection:

```bash
# 1. collect  — every `do "..."` call appends a full turn to ~/.doer_training.jsonl
do "fix the failing test"
do "explain this stacktrace" < err.log
do "write a bash one-liner that ..."
# ... x100+

# 2. inspect
do --train-status
# → 127 turns | 2453.1KB | /Users/you/.doer_training.jsonl

# 3. train   — in-process LoRA via mlx_lm.tuner (no strands-mlx trainer)
pip install 'doer-cli[mlx]'   # text LoRA
pip install 'doer-cli[vlm]'   # vision LoRA (adds mlx-vlm + datasets)

do --train 200                # text LoRA   → ~/.doer_adapter/adapters.safetensors
do --train-vlm 300            # vision LoRA → ~/.doer_vlm_adapter/adapters.safetensors

# 4. use     — hot-swap your trained self
DOER_PROVIDER=mlx     DOER_ADAPTER=~/.doer_adapter         do "fix the failing test"
DOER_PROVIDER=mlx-vlm DOER_VLM_ADAPTER=~/.doer_vlm_adapter do --img x.png "what's this?"
```

### ~/.doer_training.jsonl format

One record per `do` call, fat/dense, self-contained:

```json
{
  "ts": 1776587093,
  "model": "bedrock global.anthropic.claude-opus-4-7 @ us-west-2",
  "query": "original user query",
  "system": "<full _prompt() output — SOUL + AGENTS + history + source, ~20KB>",
  "messages": [
    {"role": "user",      "content": [{"text": "..."}]},
    {"role": "assistant", "content": [{"text": "..."}, {"toolUse": {...}}]},
    {"role": "user",      "content": [{"toolResult": {...}}]},
    {"role": "assistant", "content": [{"text": "..."}]}
  ],
  "tools": [{"name": "shell", "description": "...", "input_schema": {...}}]
}
```

**Why fat:** disk is cheap (~20KB × 1000 turns = 20MB), self-contained records are ops-simple, training on the *live* system prompt (which regenerates every call from cwd/history/source anyway) matches how the model will be used.

**Why one repo:** the training loop is ~50 lines calling `mlx_lm.tuner` directly. No `strands-mlx` trainer indirection. You own every line.

### dependency footprint

- default install: `strands-agents[ollama]` — no mlx, no training
- `pip install 'doer-cli[mlx]'` → adds `strands-mlx` (which pulls `mlx-lm`, ~500MB) — inference + training
- training uses `mlx_lm.tuner.*` directly; strands-mlx only used for `MLXModel` inference wrapper


## upload to huggingface (private dataset)

Push `~/.doer_training.jsonl` to a private HF dataset — share across machines, back it up, or train remotely.

```bash
# install optional hf extra (lazy import — no cost if unused)
pip install 'doer-cli[hf]'

# push to <user>/doer-training (private by default)
doer --upload-hf

# custom repo
doer --upload-hf cagataydev/my-agent-data

# public dataset
doer --upload-hf-public

# check sync state (shows local sha vs last remote commit)
doer --train-status
# → 105 turns | 16215.3KB | sha256:250c406b | /Users/cagatay/.doer_training.jsonl
#     text:102  image:1  audio:0  video:2
#     hf:    cagataydev/doer-training | upload 105 turns (...) | in sync
```

### how it works

- **Idempotent**: single atomic commit per run (jsonl + README with schema/stats/sha).
- **Auth**: reuses `huggingface-cli login` (`~/.cache/huggingface/token`) or `HF_TOKEN` env.
- **Repo default**: `<your-hf-username>/doer-training`. Override with `DOER_HF_REPO=...` or positional arg.
- **Private by default** — use `--upload-hf-public` to opt out.
- **No change to dep tree** unless you `pip install 'doer-cli[hf]'` (lazy import in `upload_hf()`).

### round-trip: download + train elsewhere

```bash
# on another machine
hf download cagataydev/doer-training --repo-type dataset --local-dir /tmp/doer-data
cp /tmp/doer-data/data/train.jsonl ~/.doer_training.jsonl
doer --train 200
```

## cloud training via HuggingFace Jobs

For scale-up (bigger models, full fine-tunes, multimodal), doer ships three
self-contained UV scripts in `hf_jobs/` that run on HF infrastructure:

| script               | target                                      | hardware   | cost  |
|----------------------|---------------------------------------------|------------|-------|
| `train_text_lora.py` | Any causal LM (Qwen3-1.7B default)          | t4-medium  | ~$0.30 |
| `train_vlm.py`       | Qwen2.5-VL-3B (images + text)               | a100-large | ~$5   |
| `train_omni.py`      | Qwen2.5-Omni-7B (text + audio + image)      | h200       | ~$10  |

One command dispatches a job:

```bash
./hf_jobs/launch.sh text                     # defaults
./hf_jobs/launch.sh vlm --min-records 1
MODEL=Qwen/Qwen3-4B FLAVOR=a10g-large ./hf_jobs/launch.sh text --iters 1000
./hf_jobs/launch.sh ps
```

### design rules (same as doer core)

1. **one file per trainer** — no helper modules, no shared utilities. If you
   want text+VLM you copy-paste the shared bits. Disk is cheap; indirection
   is not.
2. **UV inline dependencies** — each script declares its deps in the top
   `# /// script ... # ///` block. `hf jobs uv run` handles the rest.
3. **raw JSONL loading** (not `datasets.load_dataset`) — the dataset has
   heterogeneous schemas (some records have `images`/`audio`/`video` keys,
   some don't). Arrow schema inference breaks on that. `hf_hub_download`
   + per-line `json.loads` is robust.
4. **merge + push full model by default** — output is a drop-in replacement
   (`transformers.AutoModelForCausalLM.from_pretrained(repo)` just works).
   LoRA adapters alone force consumers to juggle `peft` glue.
5. **Strands → OpenAI message translation** happens in the trainer —
   `toolUse` / `toolResult` blocks become `<tool_call>` / `<tool_result>`
   tags so the tokenizer's chat template can lay down native tool-call
   tokens. Training learns real tool-use, not string mimicry.
6. **no repo setup, no Dockerfile** — everything lives in `hf_jobs/*.py`.
   `hf jobs uv run --flavor <gpu> --secrets HF_TOKEN hf_jobs/<script>.py …`
   is the whole deploy story.

### validated run (v0.6.0 release)

- job `69e647b7cd8c002f31e00271` on t4-medium, 33 min, ~$0.35
- 522 records → 468 train / 53 eval
- Qwen3-1.7B + LoRA r=16 (17.4M trainable params, 1.00% of base)
- final eval_loss = **0.149**, mean token accuracy = **97.6%**
- 3.44 GB merged model auto-pushed to `cagataydev/doer-qwen3-1.7b-test`

### use your cloud-trained model

```bash
# inference via transformers
DOER_PROVIDER=transformers \
  DOER_MODEL=cagataydev/doer-qwen3-17b \
  do "what is doer"

# or via mlx (after converting: mlx_lm.convert --hf-path <repo>)
DOER_PROVIDER=mlx DOER_MLX_MODEL=<mlx-repo> do "..."
```


## do not

- add more deps — every byte in the dep tree is scrutinized
- add subcommands — `doer <query>` is the only interface
- add config files — env vars are overkill for this tool
- wrap in docker — it's 100MB, just `pip install doer-cli`
