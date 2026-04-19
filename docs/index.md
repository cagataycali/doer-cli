<div align="center">
  <img src="doer.svg" alt="doer" width="160">
  <h1>doer</h1>
  <p><strong>One-file pipe-native AI agent. Ollama-only. ~180 LOC.</strong></p>
</div>

[![PyPI](https://badge.fury.io/py/doer.svg)](https://pypi.org/project/doer/)

---

## What Is doer?

A Unix-philosophy agent. Reads stdin, writes stdout, shuts up when piped, self-aware of its own source. **100% local inference via [Ollama](https://ollama.com) — no API keys, no cloud.**

```bash
# 1. install ollama + pull a model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:0.8b

# 2. install doer
pip install doer

# 3. use it
doer "list files modified today"
echo "some text" | doer "summarize"
git log -5 | doer "tldr"
```

---

## Why doer?

<div class="grid cards" markdown>

-   **🧘 Minimalist**

    One file. ~180 LOC. Two env vars to configure. Nothing else.

-   **🔒 Local-First**

    100% local inference via Ollama. No API keys. No telemetry. No cloud.

-   **🪈 Pipe-Native**

    Detects pipes automatically. Silent when scripted. Terse when interactive.

-   **🪞 Self-Aware**

    Injects its own source code into the system prompt. Knows what it is.

-   **🔥 Hot-Reload Tools**

    Drop a `@tool` function in `./tools/*.py` — instantly available.

-   **📦 Standalone Binary**

    PyInstaller + Nuitka build scripts. Runs without Python.

</div>

---

## 30-Second Demo

```bash
# one-shot
doer "what's my git branch?"

# pipe in
cat README.md | doer "tldr in 3 bullets"

# python
python -c "import doer; print(doer('hostname?'))"

# as a module
python -m doer "uptime"
```

---

## Architecture

```
stdin ──┐
        ├─→ doer.cli() ─→ Agent(Ollama + shell tool + ./tools/*) ─→ stdout
argv  ──┘                      ↑
                               └── system prompt:
                                   - own source code
                                   - recent Q/A history
                                   - recent shell commands
```

---

## Configure

Two env vars:

| Var | Default | Purpose |
|---|---|---|
| `DOER_MODEL` | `qwen3.5:0.8b` | Ollama model |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |

---

## Next Steps

- [Install](getting-started/installation.md)
- [Quickstart](getting-started/quickstart.md)
- [Pipe-Native workflows](guide/pipe-native.md)
- [Hot-reload tools](guide/hot-reload.md)

License: Apache-2.0
