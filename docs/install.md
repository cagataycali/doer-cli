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

=== "curl (binary, coming soon)"

    Prebuilt binaries will land on GitHub Releases shortly. For now, use `pipx`.

    !!! note "what to expect"
        ```bash
        # once released:
        curl -sSL https://github.com/cagataycali/doer-cli/releases/latest/download/install.sh | sh
        ```
        Installs to `~/.local/bin`. No Python required.

## two binaries, one brain

```bash
do   "quick question"     # short form — shell loves brevity
doer "longer query"       # long form — when clarity wins
```

Both resolve to the same entry point.

## requirements

| requirement       | notes                                     |
| ----------------- | ----------------------------------------- |
| Python **3.10+**                            | only for `pip`/`pipx` paths                       |
| [Ollama](https://ollama.com) *or* AWS creds | one of the two — `doer` auto-detects              |
| A model                                     | `ollama pull qwen3:1.7b` *or* Bedrock Claude access |

## pick a backend

`doer` auto-detects at runtime: **Bedrock if AWS creds exist, else Ollama.** Override with `DOER_PROVIDER`.

### bedrock (cloud, default)

Frontier Claude models, zero local compute. Requires AWS credentials and Bedrock model access.

```bash
# simplest: bearer token (get one from the Bedrock console)
export AWS_BEARER_TOKEN_BEDROCK=abc...

# or standard AWS creds
export AWS_PROFILE=my-profile

do "reply: ok"
# → ok
```

**Defaults** (all overridable via env):

| setting | value |
|---|---|
| model | `global.anthropic.claude-opus-4-7` |
| region | `us-west-2` |
| context | **1M tokens** (via `context-1m-2025-08-07` beta, auto) |
| output | **128k tokens** (Opus 4.7 native max) |

Pin a different model:
```bash
DOER_BEDROCK_MODEL=us.anthropic.claude-sonnet-4-20250514-v1:0 do "..."
DOER_BEDROCK_MODEL=global.anthropic.claude-opus-4-6  do "..."
```

### ollama (local, private)

No API keys. Runs on your laptop. Great for offline and sensitive work.

```bash
# macOS
brew install ollama
ollama serve &
ollama pull qwen3:1.7b

# linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:1.7b

# force ollama even when AWS creds exist
DOER_PROVIDER=ollama do "reply: ok"
# → ok
```

Switch ollama model:
```bash
DOER_MODEL=llama3.2:3b do "explain this file"
DOER_MODEL=qwen3:4b    do "write a sql query"
```

Persist your choice:
```bash
echo 'export DOER_PROVIDER=ollama' >> ~/.zshrc
echo 'export DOER_MODEL=qwen3:4b'  >> ~/.zshrc
```

## troubleshooting

!!! warning "`connection refused` (Ollama)"
    Ollama isn't running. `ollama serve` in another terminal.

!!! warning "`model not found` (Ollama)"
    Pull it first: `ollama pull qwen3:1.7b`

!!! warning "`AccessDeniedException` / `ValidationException` (Bedrock)"
    Your AWS creds don't have access to the default model. Either request access in the Bedrock console, or switch:
    `DOER_BEDROCK_MODEL=us.anthropic.claude-sonnet-4-20250514-v1:0 do "..."`

!!! warning "`invalid beta flag` (Bedrock)"
    A model rejected a beta header you set. Clear it: `DOER_ANTHROPIC_BETA="" do "..."`

!!! warning "`temperature/top_p` 400 error (Bedrock)"
    Opus 4.7+ rejects any non-default sampling values. Unset `DOER_TEMPERATURE` / `DOER_TOP_P`, or pin an older model.

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
