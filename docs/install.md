# Install

Three paths. All three give you `do` and `doer` on your `$PATH`.

=== "pipx (recommended)"

    Isolated, auto-updatable, no venv shenanigans.

    ```bash
    pipx install doer-cli
    ```

    Upgrade later:
    ```bash
    pipx upgrade doer-cli
    ```

=== "pip"

    Any venv. Global if you insist.

    ```bash
    pip install doer-cli
    ```

=== "curl one-liner"

    Prebuilt binary. **No Python needed.**

    ```bash
    curl -sSL https://raw.githubusercontent.com/cagataycali/doer-cli/main/install.sh | sh
    ```

    Installs to `~/.local/bin` by default. Override:

    ```bash
    DOER_INSTALL_DIR=/usr/local/bin curl -sSL ... | sh
    ```

## two binaries, one brain

```bash
do   "quick question"     # short form — shell loves brevity
doer "longer query"       # long form — when clarity wins
```

Both resolve to the same entry point.

## requirements

| requirement       | notes                                     |
| ----------------- | ----------------------------------------- |
| Python **3.10+**  | only for `pip`/`pipx` paths               |
| [Ollama](https://ollama.com) | or point `OLLAMA_HOST` elsewhere |
| A model           | `ollama pull qwen3:1.7b` (default)        |

## ollama quickstart

```bash
# macOS
brew install ollama
ollama serve &
ollama pull qwen3:1.7b

# linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:1.7b
```

Test:
```bash
do "reply: ok"
# → ok
```

## switching models

Any model Ollama can run, `doer` can drive.

```bash
DOER_MODEL=llama3.2:3b do "explain this file"
DOER_MODEL=qwen3:4b    do "write a sql query"
```

Set it permanently in your shell rc:
```bash
echo 'export DOER_MODEL=qwen3:4b' >> ~/.zshrc
```

## troubleshooting

!!! warning "`connection refused`"
    Ollama isn't running. `ollama serve` in another terminal.

!!! warning "`model not found`"
    Pull it first: `ollama pull qwen3:1.7b`

!!! warning "slow first call"
    Ollama loads the model into RAM on first call. Subsequent calls are fast.
    Ambient tip: `ollama run qwen3:1.7b "" &` to warm it in the background.

!!! warning "`command not found: do`"
    `pipx` installed but `~/.local/bin` isn't on `$PATH`. Run `pipx ensurepath` and restart your shell.

## uninstall

```bash
pipx uninstall doer-cli     # pipx users
pip  uninstall doer-cli     # pip users
rm ~/.local/bin/do ~/.local/bin/doer    # binary users
```

That's it. No config dirs. No leftovers. Nothing to clean up.
