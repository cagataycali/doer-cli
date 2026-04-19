# Installation

doer needs **two things**: Ollama running somewhere + the `doer` package.

---

## 1. Install Ollama

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
    docker run -d \
      -v ollama:/root/.ollama \
      -p 11434:11434 \
      --name ollama \
      ollama/ollama
    ```

=== "Windows"

    Download the installer: <https://ollama.com/download/windows>

Verify it's running:

```bash
curl http://localhost:11434/api/tags
```

---

## 2. Pull a Model

Default (fast & tiny — runs on anything):

```bash
ollama pull qwen3.5:0.8b     # ~600 MB, doer's default
```

Scale up for more power:

```bash
ollama pull qwen3.5:4b       # ~2.5 GB  (balanced)
ollama pull qwen3:8b         # ~5 GB
ollama pull llama3.2:3b      # ~2 GB    (Meta)
ollama pull gpt-oss:20b      # ~12 GB   (OpenAI open-weights)
ollama pull qwen3.5:35b      # ~20 GB   (big brain)
ollama pull deepseek-r1:32b  # ~20 GB   (reasoning)
```

See the [Ollama library](https://ollama.com/library) for the full list.

Override with `export DOER_MODEL=qwen3:8b`.

See the [Ollama library](https://ollama.com/library) for more.

---

## 3. Install doer

=== "pip"

    ```bash
    pip install doer
    ```

=== "pipx (isolated)"

    ```bash
    pipx install doer
    ```

=== "From source"

    ```bash
    git clone https://github.com/cagataycali/doer.git
    cd doer
    pip install -e .
    ```

=== "Standalone binary (no Python)"

    Download from [releases](https://github.com/cagataycali/doer/releases/latest):

    ```bash
    curl -sSL https://github.com/cagataycali/doer/releases/latest/download/doer-$(uname -s | tr A-Z a-z)-$(uname -m) -o /usr/local/bin/doer
    chmod +x /usr/local/bin/doer
    ```

    Or build yourself — see [Standalone Binary](../guide/binary.md).

---

## 4. Configure (Optional)

Two env vars control everything:

| Var | Default | Purpose |
|---|---|---|
| `DOER_MODEL` | `qwen3.5:0.8b` | Ollama model ID |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |

```bash
# use a different model
export DOER_MODEL=llama3.2:3b

# point at a remote ollama
export OLLAMA_HOST=http://192.168.1.10:11434
```

Persist them in `~/.zshrc` / `~/.bashrc`.

---

## 5. Verify

```bash
doer "hello"
# → hi!
```

If you get a connection error — Ollama isn't running. Start it:

```bash
ollama serve
```

If you get a "model not found" error — pull it first:

```bash
ollama pull $DOER_MODEL
```

---

## Requirements

- **Python** 3.10+ (skip this if using the standalone binary)
- **Ollama** running locally or remotely
- **At least one model** pulled

That's it. No API keys. No cloud account. No credit card.
