# Train on yourself

`doer` closes its own loop. Collect → train → hot-swap. One file. No new services.

<div class="ascii-box">use doer                  do --train               DOER_ADAPTER=...
   │                         │                          │
   ▼                         ▼                          ▼
~/.doer_training.jsonl  →  mlx_lm.tuner  →  ~/.doer_adapter/adapters.safetensors</div>

## the loop

```bash
# 1. collect — every `do "..."` call appends a full turn
do "fix the failing test"
do "explain this stacktrace" < err.log
do "write a bash one-liner that ..."
# ... keep using doer for real work, ~100+ turns

# 2. inspect your corpus
do --train-status
# → 127 turns | 2453.1KB | /Users/you/.doer_training.jsonl

# 3. train (Apple Silicon only)
pip install 'doer-cli[mlx]'        # pulls strands-mlx + mlx-lm
do --train 200                     # 200 LoRA iters, rank 8, AdamW, lr 1e-5
# → ~/.doer_adapter/adapters.safetensors

# 4. hot-swap your trained self
DOER_PROVIDER=mlx DOER_ADAPTER=~/.doer_adapter do "fix the failing test"
```

## what gets recorded

Every `do "..."` call appends **one JSON line** to `~/.doer_training.jsonl`:

```json
{
  "ts": 1776587093,
  "model": "bedrock global.anthropic.claude-opus-4-7 @ us-west-2",
  "query": "original user query",
  "system": "<full _prompt() — SOUL + AGENTS + history + source, ~20KB>",
  "messages": [
    {"role": "user",      "content": [{"text": "..."}]},
    {"role": "assistant", "content": [{"text": "..."}, {"toolUse": {...}}]},
    {"role": "user",      "content": [{"toolResult": {...}}]},
    {"role": "assistant", "content": [{"text": "..."}]}
  ],
  "tools": [{"name": "shell", "description": "...", "input_schema": {...}}]
}
```

### why fat

Disk is cheap. 20KB × 1000 turns ≈ 20MB.

The system prompt is **already** the live prompt that regenerates every call
(cwd, history, source). Training on it matches how the model will be used.
Self-contained records are ops-simple: you can delete the live repo tomorrow
and the corpus still trains.

## why native tool-call tokens

Under the hood, `_strands_to_openai()` converts Strands `ContentBlock` messages
to OpenAI chat format — **with `tool_calls` kept as structured data**, not
stringified. When mlx-lm applies the tokenizer's chat template, Qwen/Llama/etc.
emit their **native** tool-call tokens (e.g. `<tool_call>...</tool_call>`).

The adapter learns **real** tool use. Not a string-matching impression of it.

## what `--train` does

Under ~50 lines. Calls `mlx_lm.tuner` directly. No `strands-mlx` trainer indirection.

| step | detail |
|---|---|
| load model | `DOER_MLX_MODEL` (default `mlx-community/Qwen3-1.7B-4bit`) |
| filter | drop records with empty `messages` (failed turns) |
| split | 90% train / 10% valid, seeded shuffle |
| convert | Strands → OpenAI `{messages, tools}` |
| LoRA | rank 8, scale 20.0, 8 layers, no dora |
| optimizer | AdamW, lr `1e-5` (tune via CLI soon) |
| checkpoint | every `max(100, iters//2)` steps |
| output | `~/.doer_adapter/adapters.safetensors` + `adapter_config.json` |

## env knobs

| var | default | purpose |
|---|---|---|
| `DOER_MLX_MODEL` | `mlx-community/Qwen3-1.7B-4bit` | base model for training + MLX inference |
| `DOER_ADAPTER` | *(unset)* | path to LoRA adapter for hot-swap |
| `DOER_DEBUG` | *(unset)* | print training-log append errors |

## commands

```bash
do --train              # 200 iters (default)
do --train 500          # 500 iters
do --train-status       # show corpus size + path
```

## dependency footprint

```bash
pip install doer-cli              # strands-agents[ollama]  — no training, no mlx
pip install 'doer-cli[mlx]'       # + strands-mlx + mlx-lm  — inference + training
```

Default install stays lean. MLX is opt-in (~500MB of wheels for Apple Silicon).

## privacy

```bash
ls -l ~/.doer_training.jsonl
# -rw-------  1 you  staff  2453133 Apr 20 01:44

rm ~/.doer_training.jsonl          # nuke corpus
rm -rf ~/.doer_adapter             # nuke adapter
```

Mode `0600`. Never leaves your machine. Never reported. Never phoned home.
Your **filesystem** is the training loop.

## when this matters

- You keep typing the same kinds of queries → fine-tune on your own Q/A.
- You have project-specific idioms (`SOUL.md`, `AGENTS.md`) → the adapter absorbs them.
- You want a **small, fast, offline** model that knows *your* voice → train on 4am Bedrock turns, serve from MLX the next morning.

> **The cathedral labels the tokens. The chisel learns them.**
