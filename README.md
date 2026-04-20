<div align="center">

<img src="doer.svg" width="180" alt="doer">

# **DOER**

### `stdin → llm → stdout`

**A Unix citizen that thinks.**
**One file. One dep. Zero ceremony.**

[![PyPI](https://img.shields.io/pypi/v/doer-cli.svg?style=for-the-badge&color=FF3D00&labelColor=0A0A0A)](https://pypi.org/project/doer-cli/)
[![License](https://img.shields.io/badge/APACHE-2.0-FAFAF7?style=for-the-badge&labelColor=0A0A0A)](LICENSE)
[![Python](https://img.shields.io/badge/PYTHON-3.10%2B-FAFAF7?style=for-the-badge&labelColor=0A0A0A)](https://python.org)
[![Docs](https://img.shields.io/badge/DOCS-doer.duck.nyc-FF3D00?style=for-the-badge&labelColor=0A0A0A)](https://doer.duck.nyc)

📖 **[Full documentation →](https://doer.duck.nyc)**

</div>

---

## install

Pick your path. All three give you `do` on your `$PATH`.

```bash
# 1) pipx — isolated, auto-updatable (recommended)
pipx install doer-cli

# 2) pip — any venv
pip install doer-cli

# 3) one-liner (prebuilt binary, no Python needed)
# prebuilt binary installer — coming soon on GitHub Releases
```

> Two binaries get installed: **`do`** (short) and **`doer`** (long). Pick your poison.
>
> **`do` conflict?** Some shells have `do` as a keyword (bash/zsh loops). The binary still works — `do "hello"` is unambiguous because of the argument. But if your shell auto-completes weirdly, alias it:
> ```bash
> echo "alias d="doer"" >> ~/.zshrc  # or ~/.bashrc
> ```
> Then use `d "your query"`.

## run

```bash
do "find files larger than 100MB"

cat error.log  | do "what broke"
git log -20    | do "write release notes"
echo '{"a":1}' | do "to yaml"
curl -s api.io | do "summarize" | tee out.md
```

## what it is

```python
Agent(
    model=Ollama(...),
    tools=[shell] + hot_reload("./tools"),
    system_prompt=SOUL.md + AGENTS.md + ~/.doer_history
                + ~/.bash_history + ~/.zsh_history + own_source,
)(stdin + argv)
```

That's the entire architecture. **~420 lines** of Python. It reads your shell like a person reads a room — and can train on its own transcripts.

## context it sees every call

| source                 | what                                               |
| ---------------------- | -------------------------------------------------- |
| `SOUL.md` (cwd)        | who it is in this project                          |
| `AGENTS.md` (cwd)      | rules for this project                             |
| `~/.doer_history`      | last N Q/A (`DOER_HISTORY=10`)                     |
| `~/.bash_history` + `~/.zsh_history` | last N commands (`DOER_SHELL_HISTORY=20`) |
| `./tools/*.py`         | hot-reloaded `@tool` functions                     |
| own source             | full self-awareness                                |

No database. No config file. **The filesystem is the memory.**

## providers

Auto-picked by what's on your machine.

```bash
# Bedrock (default when AWS creds exist) — Claude Opus 4.7, 1M ctx, 128k out
export AWS_BEARER_TOKEN_BEDROCK=...   # or standard AWS_* creds
do "review this" < diff.patch

# Ollama (fallback) — local, private, no keys
ollama serve & ollama pull qwen3:1.7b
DOER_PROVIDER=ollama do "quick ping"
```

## env knobs

```bash
# provider selection
DOER_PROVIDER=                   # "" (auto) | "bedrock" | "ollama"

# bedrock (defaults tuned for Claude Opus 4.7)
DOER_BEDROCK_MODEL=global.anthropic.claude-opus-4-7
DOER_BEDROCK_REGION=us-west-2
DOER_MAX_TOKENS=128000           # Opus 4.7 native max
DOER_ANTHROPIC_BETA=context-1m-2025-08-07   # auto on Claude — "" to disable

# ollama
DOER_MODEL=qwen3:1.7b
OLLAMA_HOST=http://localhost:11434

# context
DOER_HISTORY=10                  # Q/A rows in prompt
DOER_SHELL_HISTORY=20            # shell rows in prompt
```

> **Opus 4.7 heads-up:** `temperature` / `top_p` return 400 on any non-default value — `doer` only sends them when you explicitly set `DOER_TEMPERATURE` / `DOER_TOP_P`.

## extend in 60 seconds

```python
# ./tools/weather.py
from strands import tool
import urllib.request

@tool
def weather(city: str) -> str:
    """Weather for a city."""
    return urllib.request.urlopen(f"https://wttr.in/{city}?format=3").read().decode()
```

Next call: `do "istanbul weather?"` — hot-reloaded, no restart.

## train on yourself (Apple Silicon)

`doer` closes its own loop. Every call appends a **dense, self-contained training record** to `~/.doer_training.jsonl` — full system prompt, all messages, tool specs, native tool-call tokens preserved.

```bash
# 1. collect (automatic — just use doer)
do "fix this stacktrace" < err.log
do "write a sql query that ..."
# ... 100+ real turns

# 2. inspect
do --train-status
# → 127 turns | 2453.1KB | /Users/you/.doer_training.jsonl

# 3. train — in-process LoRA (no strands-mlx trainer indirection)
pip install 'doer-cli[mlx]'
do --train 200                # 200 iters, LoRA rank 8, AdamW, lr 1e-5
# → ~/.doer_adapter/adapters.safetensors

# 4. use your trained self
DOER_PROVIDER=mlx DOER_ADAPTER=~/.doer_adapter do "fix this stacktrace" < err.log
```

Training calls `mlx_lm.tuner` directly. ~50 lines. Preserves native `<tool_call>` tokens via the tokenizer's chat template — your adapter learns **real** tool-use, not string mimicry. Opt-in extra (`doer-cli[mlx]`) pulls `strands-mlx` + `mlx-lm`; default install stays lean.

## philosophy

```
┌─────┐       ┌──────┐       ┌──────┐
│stdin│──────▶│  do  │──────▶│stdout│
└─────┘       └──────┘       └──────┘
```

`grep` with a brain. Chain it. Script it. Cron it.

Read [**SOUL.md**](SOUL.md) for the manifesto. Read [**AGENTS.md**](AGENTS.md) for the rules.

## family

| project    | size       | purpose                           |
| ---------- | ---------- | --------------------------------- |
| **doer**   | ~420 LOC   | one pipe, one shell, one file, one loop (collect→train→swap) |
| [**DevDuck**](https://github.com/cagataycali/devduck) | 60+ tools  | every protocol, every edge |

## uninstall

```bash
pipx uninstall doer-cli    # or: pip uninstall doer-cli
rm /usr/local/bin/do       # if installed via curl
```

## license

Apache-2.0 · built in New York · 2026

---

<div align="center">

**`do one thing and do it well`** — Doug McIlroy, 1978

</div>
