# Changelog

Compressed history. Newest first.

## v0.6.0 — *cloud training (HuggingFace Jobs)*

- **`hf_jobs/` suite** — burn HF credits instead of battery for scale-up training
  - `hf_jobs/train_text_lora.py` — any causal LM → LoRA → merged push (Qwen3-1.7B default)
  - `hf_jobs/train_vlm.py` — Qwen2.5-VL-3B image+text LoRA
  - `hf_jobs/train_omni.py` — Qwen2.5-Omni-7B text+audio+image LoRA
  - `hf_jobs/launch.sh` — one-shot dispatcher (`text`/`vlm`/`omni`/`ps`/`logs`/`hw`)
- **One file per trainer, inline UV deps** — no repo setup, no Dockerfile, `hf jobs uv run` handles everything
- **Raw JSONL loading** via `hf_hub_download` — bypasses Arrow schema churn on heterogeneous multimodal records
- **Merge + push by default** — output is a drop-in for `transformers.AutoModelForCausalLM.from_pretrained`, no `peft` glue on the consumer side
- **Tool calls preserved** — Strands `toolUse`/`toolResult` become native `<tool_call>`/`<tool_result>` tags so the chat template lays down real tool-call tokens
- **Validated end-to-end**: T4-medium, 522 records → 468/53, 50 steps / 33 min, eval_loss **0.149**, token accuracy **97.6%**, 3.44 GB merged model auto-pushed
- Local `--train` / `--train-vlm` unchanged — cloud is opt-in, laptop-first stays default
- New docs: [`train.md#train-in-the-cloud-huggingface-jobs`](train.md#train-in-the-cloud-huggingface-jobs)

## v0.5.0 — *multimodal + dataset publishing*

- **Multimodal input** — `--img`, `--audio`, `--video` flags route to `mlx-vlm` automatically
  - vision-only → `Qwen2.5-VL-3B`
  - audio-only → `gemma-3n-E2B-it`
  - mixed (image + audio) → `Qwen3-Omni-30B-A3B`
- **VLM LoRA training** — `do --train-vlm [iters]` trains on image/audio/video records
- **HuggingFace upload** — `do --upload-hf` / `do --upload-hf-public` publishes the corpus as an HF dataset (private by default). Idempotent, one atomic commit, reuses `huggingface-cli login`.
- **`--train-status` refreshed** — shows sha256, modality breakdown (text/image/audio/video), HF sync state
- **Structural refactor** — same CLI surface, clearer internals (PR #5). ~730 lines total.
- New env knobs: `DOER_MLX_VLM_MODEL`, `DOER_MLX_AUDIO_MODEL`, `DOER_MLX_OMNI_MODEL`, `DOER_VLM_ADAPTER`, `DOER_HF_REPO`, `DOER_CACHE_PROMPT`, `DOER_BEDROCK_GUARDRAIL_ID/VERSION`, `DOER_ADDITIONAL_REQUEST_FIELDS`
- New opt-in extras: `[vlm]` (mlx-vlm + datasets), `[hf]` (huggingface-hub), `[all]`

## v0.4.0 — *closed the loop*

- **Self-training** — every `do "..."` call appends a dense, self-contained record to `~/.doer_training.jsonl` (full system prompt + messages + tool specs)
- **In-process LoRA** via `do --train [iters]` — calls `mlx_lm.tuner` directly, no `strands-mlx` trainer indirection (~50 lines)
- **Native tool-call tokens** — `_strands_to_openai()` preserves `tool_calls` as structured data so tokenizer chat templates emit real `<tool_call>` tokens (Qwen/Llama), not string mimicry
- **MLX provider** — `DOER_PROVIDER=mlx` for Apple Silicon on-device inference with LoRA hot-swap via `DOER_ADAPTER`
- **Corpus inspector** — `do --train-status` shows turn count, KB, path
- **Auto-detect extended** — provider order now `bedrock → mlx (Apple Silicon) → ollama`
- New env knobs: `DOER_MLX_MODEL`, `DOER_ADAPTER`, `DOER_DEBUG`
- Opt-in extra: `pip install 'doer-cli[mlx]'` pulls `strands-mlx` + `mlx-lm` (~500MB) — default install stays lean
- ~420 LOC (up from 221) at the time — one file, one default dep
- New docs: [Train on yourself](train.md)

## v0.3.0 — *frontier by default*

- **Default model**: `global.anthropic.claude-opus-4-7` on Bedrock (was Ollama-only)
- **Auto-detect provider** — Bedrock if AWS creds exist, else Ollama fallback
- **1M context window** auto-enabled via `context-1m-2025-08-07` beta header
- **128k max output** (Opus 4.7 native cap; raise via `DOER_MAX_TOKENS`)
- Opt-in `temperature` / `top_p` — Opus 4.7+ rejects non-default sampling, so doer skips them unless explicitly set
- New env knobs: `DOER_PROVIDER`, `DOER_BEDROCK_MODEL`, `DOER_BEDROCK_REGION`, `DOER_ANTHROPIC_BETA`, `DOER_ADDITIONAL_REQUEST_FIELDS`
- 221 LOC (up from 164) — still one file, still one dep

## v0.2.1 — *curl or pipx*

- `do` shortcut alongside `doer` (less typing)
- One-line installer (`curl | sh`) planned via GitHub Releases
- Renamed to **`doer-cli`** on PyPI (`doer` was squatted)
- Repo moved to `github.com/cagataycali/doer-cli`
- Docs: migrated to **mkdocs-material** (mobile-first, proper nav, dark/light, cookbook)

## v0.2.0 — *new brand*

- Bold, solid, pipe-first identity (orange `#FF3D00` + black + paper)
- Custom SVG logo
- Clean README, stripped marketing copy
- Auto-inject `SOUL.md` + `AGENTS.md` into system prompt

## v0.1.x — *the primordial soup*

- **164 LOC** — fits on one screen (barely)
- Only dep: `strands-agents`
- Ollama-only (local, private, no keys)
- Injects own source, `$HOME/.bash_history`, `$HOME/.zsh_history`, `~/.doer_history`
- Hot-reload tools from `./tools/*.py`
- PyInstaller + Nuitka standalone binaries (linux/macos)
- Rename: `tiny` → `doer` (better verb)

## pre-history

- Spawned from **[DevDuck](https://github.com/cagataycali/devduck)** — 60+ tools, every protocol
- DevDuck asked itself at 4am: *what if we deleted almost everything?*
- Two hours later: `doer`.

---

> *the cathedral teaches you which stones are load-bearing.*
