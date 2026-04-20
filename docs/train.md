# Train on yourself

`doer` closes its own loop. Collect → train → hot-swap. Text, vision, audio, video — all in one file. No new services.

<div class="ascii-box">use doer                  do --train              DOER_ADAPTER=...
   │                         do --train-vlm                │
   ▼                            │                          ▼
~/.doer_training.jsonl  →  mlx_lm.tuner       →  ~/.doer_adapter/...
                         or mlx_vlm.lora      →  ~/.doer_vlm_adapter/...</div>

## the loop

```bash
# 1. collect — every `do "..."` call appends a full turn
do "fix the failing test"
do --img screenshot.png "label the bugs"
do --audio standup.wav  "bullet the action items"
# ... keep using doer for real work, ~100+ turns across modalities

# 2. inspect your corpus
do --train-status
# → 127 turns | 2453.1KB | sha256:250c406b | /Users/you/.doer_training.jsonl
#     text:102  image:18  audio:3  video:4
#     hf:    cagataydev/doer-training | in sync

# 3. train (Apple Silicon only)
pip install 'doer-cli[mlx]'        # text LoRA
pip install 'doer-cli[vlm]'        # vision LoRA (adds mlx-vlm + datasets)

do --train 200                     # text LoRA   → ~/.doer_adapter
do --train-vlm 300                 # vision LoRA → ~/.doer_vlm_adapter

# 4. hot-swap your trained self
DOER_PROVIDER=mlx     DOER_ADAPTER=~/.doer_adapter         do "fix the failing test"
DOER_PROVIDER=mlx-vlm DOER_VLM_ADAPTER=~/.doer_vlm_adapter do --img x.png "what's this?"
```

!!! tip "automate collection"
    `doer` doesn't ship a scheduler — use real cron.

    ```cron
    */5 * * * * cd ~/repo && doer "read a random file, explain it" >/dev/null 2>&1
    ```

    One line. Survives reboots. Appends to `~/.doer_training.jsonl` forever.
    Cron strips your env, so export `AWS_BEARER_TOKEN_BEDROCK` (or your
    provider creds) inside the script if the shell doesn't inherit it.

## what gets recorded

Every `do "..."` call appends **one JSON line** to `~/.doer_training.jsonl`:

```json
{
  "ts": 1776587093,
  "model": "bedrock global.anthropic.claude-opus-4-7 @ us-west-2",
  "query": "original user query",
  "system": "<full _build_prompt() — SOUL + AGENTS + history + source, ~20KB>",
  "messages": [
    {"role": "user",      "content": [{"text": "..."}, {"image": {...}}]},
    {"role": "assistant", "content": [{"text": "..."}, {"toolUse": {...}}]},
    {"role": "user",      "content": [{"toolResult": {...}}]},
    {"role": "assistant", "content": [{"text": "..."}]}
  ],
  "tools": [{"name": "shell", "description": "...", "input_schema": {...}}],
  "media": {"images": ["./shot.png"], "audio": [], "video": []}
}
```

### why fat

Disk is cheap. 20KB × 1000 turns ≈ 20MB.

The system prompt is **already** the live prompt that regenerates every call
(cwd, history, source). Training on it matches how the model will be used.
Self-contained records are ops-simple: you can delete the live repo tomorrow
and the corpus still trains.

### why native tool-call tokens

Under the hood, `_strands_to_openai()` converts Strands `ContentBlock`
messages to OpenAI chat format — **with `tool_calls` kept as structured
data**, not stringified. When `mlx_lm` applies the tokenizer's chat
template, Qwen/Llama/etc. emit their **native** tool-call tokens (e.g.
`<tool_call>...</tool_call>`).

The adapter learns **real** tool use. Not a string-matching impression of it.

## what `--train` does (text)

Under ~50 lines. Calls `mlx_lm.tuner` directly. No `strands-mlx` trainer indirection.

| step | detail |
|---|---|
| load model | `DOER_MLX_MODEL` (default `mlx-community/Qwen3-1.7B-4bit`) |
| filter | drop records with empty `messages` **and** skip any record carrying media (those go to `--train-vlm`) |
| split | 90% train / 10% valid, seeded shuffle |
| convert | Strands → OpenAI `{messages, tools}` |
| LoRA | rank 8, scale 20.0, 8 layers, no dora |
| optimizer | AdamW, lr `1e-5` |
| checkpoint | every `max(100, iters//2)` steps |
| output | `~/.doer_adapter/adapters.safetensors` + `adapter_config.json` |

## what `--train-vlm` does (vision)

```bash
pip install 'doer-cli[vlm]'
do --train-vlm 300
```

| step | detail |
|---|---|
| load model | `DOER_MLX_VLM_MODEL` (default `mlx-community/Qwen2.5-VL-3B-Instruct-4bit`) |
| filter | **keep only** records that carry image/audio/video media |
| compact | flatten multimodal `ContentBlock`s into a chat-template–friendly form |
| LoRA | rank 8 on vision projector + LM layers |
| output | `~/.doer_vlm_adapter/adapters.safetensors` + `adapter_config.json` |

Use the trained adapter by pointing `DOER_VLM_ADAPTER` at it:

```bash
DOER_PROVIDER=mlx-vlm DOER_VLM_ADAPTER=~/.doer_vlm_adapter \
  do --img login.png "spot the accessibility issues"
```

## share the dataset (HuggingFace)

Keep your corpus in sync across machines. Back it up. Or train remotely.

```bash
pip install 'doer-cli[hf]'

do --upload-hf                        # → <user>/doer-training (private)
do --upload-hf cagataydev/my-data     # custom repo
do --upload-hf-public                 # public dataset
```

Idempotent — a single atomic commit per run (`data/train.jsonl` + a README
with schema, stats, sha). Reuses `huggingface-cli login` or `HF_TOKEN`.

Check sync state:

```bash
do --train-status
# → 127 turns | 2453.1KB | sha256:250c406b | ~/.doer_training.jsonl
#     text:102  image:18  audio:3  video:4
#     hf:    cagataydev/doer-training | upload 127 turns (...) | in sync
```

**Round-trip elsewhere:**

```bash
hf download cagataydev/doer-training --repo-type dataset --local-dir /tmp/d
cp /tmp/d/data/train.jsonl ~/.doer_training.jsonl
do --train 200
```

## train in the cloud (HuggingFace Jobs)

Laptop LoRA caps out at ~1.7B models on Apple Silicon. For anything bigger — full fine-tunes, Qwen3-4B+, VLM, Omni — burn HF credits instead of battery. Doer bundles three single-file UV scripts under `doer/hf_jobs/` (accessible via `doer --hf-jobs` after install) that run directly on HF infrastructure via `hf jobs uv run`.

```bash
# one-shot dispatchers (reads from cagataydev/doer-training, pushes merged model)
doer --hf-jobs text                    # Qwen3-1.7B LoRA, T4, ~$0.30
doer --hf-jobs vlm                     # Qwen2.5-VL-3B image+text, A100, ~$5
doer --hf-jobs omni                    # Qwen2.5-Omni-7B, H200, ~$10

# override anything via env or pass-through flags
MODEL=Qwen/Qwen3-4B FLAVOR=a10g-large doer --hf-jobs text --iters 1000

# monitor
doer --hf-jobs ps
doer --hf-jobs logs <job_id>
doer --hf-jobs hw              # hardware list + $/hour
```

Each trainer is **one file** with inline UV deps — no repo setup, no Dockerfile. It pulls the dataset via `hf_hub_download` (raw JSONL, bypasses Arrow schema issues caused by heterogeneous records), runs SFT LoRA with `trl` + `peft`, **merges the adapter into the base**, and pushes the full merged model to `cagataydev/doer-<model-short>` (private).

Merged output is a drop-in for `transformers.AutoModelForCausalLM.from_pretrained` — no LoRA glue required on the consumer side.

**Validated on T4-medium (v0.6.0 release):** 522 records → 468 train / 53 eval, Qwen3-1.7B LoRA r=16 (17.4M params, 1.00%), 50 steps in 33 min → eval_loss **0.149**, token accuracy **97.6%**, 3.44 GB merged model uploaded automatically.

Use the trained model anywhere:

```bash
# inference via transformers (any platform)
DOER_PROVIDER=transformers DOER_MODEL=cagataydev/doer-qwen3-17b do "what is doer"

# convert to MLX for Apple Silicon
mlx_lm.convert --hf-path cagataydev/doer-qwen3-17b -q --q-bits 4 \
               --mlx-path ~/.cache/doer-mlx
DOER_PROVIDER=mlx DOER_MLX_MODEL=~/.cache/doer-mlx do "..."
```

See `hf_jobs/README.md` in the repo for the full cost table, design rules, and extend instructions.

## env knobs

| var | default | purpose |
|---|---|---|
| `DOER_MLX_MODEL` | `mlx-community/Qwen3-1.7B-4bit` | base model for text training + MLX inference |
| `DOER_ADAPTER` | *(unset)* | path to text LoRA adapter for hot-swap |
| `DOER_MLX_VLM_MODEL` | `mlx-community/Qwen2.5-VL-3B-Instruct-4bit` | vision base model (image) |
| `DOER_MLX_AUDIO_MODEL` | `mlx-community/gemma-3n-E2B-it-4bit` | audio base model |
| `DOER_MLX_OMNI_MODEL` | `mlx-community/Qwen3-Omni-30B-A3B-Instruct-4bit` | mixed (image + audio) base model |
| `DOER_VLM_ADAPTER` | *(unset)* | path to VLM LoRA adapter for hot-swap |
| `DOER_HF_REPO` | `<user>/doer-training` | target HF dataset repo |
| `HF_TOKEN` | *(fallback: `~/.cache/huggingface/token`)* | HF auth |
| `DOER_MAX_SEQ_LEN` | `16384` | max sequence length for LoRA training (raise for long records, lower to save RAM) |
| `DOER_DEBUG` | *(unset)* | print training-log append errors |

## commands

```bash
do --train              # text LoRA, 200 iters
do --train 500          # text LoRA, 500 iters
do --train-vlm          # vision LoRA, 300 iters
do --train-vlm 500      # vision LoRA, 500 iters
do --train-status       # corpus stats + modality breakdown + HF sync
do --upload-hf          # push corpus to private HF dataset
do --upload-hf-public   # push corpus to public HF dataset
```

## dependency footprint

```bash
pip install doer-cli              # core — no training, no mlx, no upload
pip install 'doer-cli[mlx]'       # + strands-mlx + mlx-lm  — text training + MLX inference
pip install 'doer-cli[vlm]'       # + mlx-vlm + datasets    — multimodal + VLM training
pip install 'doer-cli[hf]'        # + huggingface-hub       — corpus upload
pip install 'doer-cli[all]'       # everything
```

Each extra is lazy-imported — zero cost if unused.

## privacy

```bash
ls -l ~/.doer_training.jsonl
# -rw-------  1 you  staff  2453133 Apr 20 01:44

rm ~/.doer_training.jsonl              # nuke corpus
rm -rf ~/.doer_adapter ~/.doer_vlm_adapter   # nuke adapters
```

Mode `0600`. Never leaves your machine unless **you** run `--upload-hf`.
Your **filesystem** is the training loop.

## when this matters

- You keep typing the same kinds of queries → fine-tune on your own Q/A.
- You have project-specific idioms (`SOUL.md`, `AGENTS.md`) → the adapter absorbs them.
- You screenshot bugs all day → train a VLM adapter on **your** UI + **your** feedback style.
- You want a **small, fast, offline** model that knows *your* voice → train on 4am Bedrock turns, serve from MLX the next morning.

> **The cathedral labels the tokens. The chisel learns them.**
