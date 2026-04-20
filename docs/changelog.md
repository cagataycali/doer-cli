# Changelog

Compressed history. Newest first.

## v0.4.0 — *closed the loop*

- **Self-training** — every `do "..."` call appends a dense, self-contained record to `~/.doer_training.jsonl` (full system prompt + messages + tool specs)
- **In-process LoRA** via `do --train [iters]` — calls `mlx_lm.tuner` directly, no `strands-mlx` trainer indirection (~50 lines)
- **Native tool-call tokens** — `_strands_to_openai()` preserves `tool_calls` as structured data so tokenizer chat templates emit real `<tool_call>` tokens (Qwen/Llama), not string mimicry
- **MLX provider** — `DOER_PROVIDER=mlx` for Apple Silicon on-device inference with LoRA hot-swap via `DOER_ADAPTER`
- **Corpus inspector** — `do --train-status` shows turn count, KB, path
- **Auto-detect extended** — provider order now `bedrock → mlx (Apple Silicon) → ollama`
- New env knobs: `DOER_MLX_MODEL`, `DOER_ADAPTER`, `DOER_DEBUG`
- Opt-in extra: `pip install 'doer-cli[mlx]'` pulls `strands-mlx` + `mlx-lm` (~500MB) — default install stays lean
- ~420 LOC (up from 221) — still one file, still one default dep
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
