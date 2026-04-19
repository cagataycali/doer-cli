<div align="center">
  <img src="doer.svg" alt="doer" width="160">
  <h1>doer</h1>
  <p><strong>One-file pipe-native AI agent. Ollama-only.</strong></p>
</div>

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

- **No cloud.** No API keys. 100% local inference via [Ollama](https://ollama.com).
- **One file.** ~180 LOC. Read it, understand it, trust it.
- **Pipe-native.** Detects pipes, stays silent when chained.
- **Self-aware.** Injects its own source into the system prompt.
- **Hot-reload.** Drop a `@tool` fn in `./tools/*.py` — live.

---

## Install

### 1. Install Ollama

=== "macOS / Linux"

    ```bash
    curl -fsSL https://ollama.com/install.sh | sh
    ```

=== "Homebrew"

    ```bash
    brew install ollama
    brew services start ollama
    ```

=== "Docker"

    ```bash
    docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
    ```

### 2. Pull a model

```bash
ollama pull qwen3.5:0.8b    # ~600 MB, doer's default (fast & tiny)
# or scale up:
ollama pull qwen3.5:4b       # ~2.5 GB
ollama pull qwen3:8b         # ~5 GB
ollama pull qwen3.5:35b      # ~20 GB (big brain)
ollama pull gpt-oss:20b      # OpenAI open-weights
```

### 3. Install doer

```bash
pip install doer           # or: pipx install doer
```

### 4. Standalone binary (no Python)

Download from [releases](https://github.com/cagataycali/doer/releases/latest):

```bash
# one-liner (linux / macos)
curl -sSL https://github.com/cagataycali/doer/releases/latest/download/doer-$(uname -s | tr A-Z a-z)-$(uname -m) -o /usr/local/bin/doer
chmod +x /usr/local/bin/doer
```

Or build yourself:

```bash
./build.sh   # PyInstaller onefile
```

---

## Configure

Two env vars. That's it.

| Var | Default | Purpose |
|---|---|---|
| `DOER_MODEL` | `qwen3.5:0.8b` | Ollama model to use |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |

```bash
export DOER_MODEL=llama3.2:3b
export OLLAMA_HOST=http://192.168.1.10:11434    # remote ollama
doer "hello"
```

---

## Use It

```bash
# one-shot
doer "what's my git branch?"

# pipe in
cat README.md | doer "tldr"
git diff | doer "write PR description"
pytest 2>&1 | doer "root cause?"

# chain
git log --oneline -20 | doer "group by theme" | doer "write changelog"

# from python
python -c "import doer; print(doer('uptime?'))"

# as a module
python -m doer "hostname"
```

---

## Hot-reload Tools

Drop a `@tool` fn in `./tools/*.py` — strands auto-loads it on next invocation.

```python
# tools/greet.py
from strands import tool

@tool
def greet(name: str) -> str:
    """Say hi."""
    return f"hi {name}!"
```

```bash
doer "greet alice"
# → hi alice!
```

---

## Docs

Full guide: **[doer.duck.nyc](https://doer.duck.nyc)**

- [Pipe-Native workflows](https://doer.duck.nyc/guide/pipe-native/)
- [Self-Awareness](https://doer.duck.nyc/guide/self-aware/)
- [Hot-Reload Tools](https://doer.duck.nyc/guide/hot-reload/)
- [Standalone Binary](https://doer.duck.nyc/guide/binary/)

---

## License

Apache-2.0
