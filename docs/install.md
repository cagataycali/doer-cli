# Install

Three paths. All three give you `do` on your `$PATH`.

## pipx <small>(recommended)</small>

Isolated, auto-updatable, no venv shenanigans.

```bash
pipx install doer-cli
```

## pip

Any venv. Global if you insist.

```bash
pip install doer-cli
```

## curl one-liner

Prebuilt binary. No Python needed. Installs into `~/.local/bin` (override with `DOER_INSTALL_DIR`).

```bash
curl -sSL https://raw.githubusercontent.com/cagataycali/doer-cli/main/install.sh | sh
```

!!! note "two binaries"
    Every install gives you both:

    - **`do`** — short form, because shell + brevity = love
    - **`doer`** — long form, when `do` feels too cryptic

## requirements

- Python **3.10+** (for pip/pipx paths)
- [Ollama](https://ollama.com) running locally (or set `OLLAMA_HOST`)
- A model pulled: `ollama pull qwen3:1.7b`

## verify

```bash
do "reply: ok"
# → ok
```
