# AGENTS.md — doer

## project
- **what:** one-file pipe-native AI agent
- **lang:** python 3.10+
- **dep:** `strands-agents[ollama]` (only)
- **entry:** `doer/__init__.py` · 164 lines
- **install:** `pip install doer` or download binary from releases
- **license:** Apache-2.0

## architecture

```
doer/
├── __init__.py    # everything: Agent, shell tool, CLI, prompt
├── __main__.py    # python -m doer
SOUL.md            # identity (injected into system prompt if in cwd)
AGENTS.md          # project rules (injected if in cwd)
doer.svg           # brand mark
build.sh           # local PyInstaller build
.github/workflows/
└── release.yml    # tag v* → binaries + PyPI
```

## design rules

1. **one source file** — all logic in `doer/__init__.py`
2. **one external dep** — `strands-agents[ollama]`, nothing else
3. **no classes unless the SDK forces it** — functions are cheaper
4. **context over memory** — don't store state, recompute from filesystem
5. **unix over RPC** — stdin/stdout/pipes, not HTTP/WebSocket
6. **env vars over config files** — `DOER_*` knobs, never `~/.doerrc`

## prompt injection (what the agent sees every call)

Built fresh on every call by `_prompt()`:
- env (`sys.platform`) + cwd (`Path.cwd()`)
- model info + own `__file__` path
- `SOUL.md` from cwd (if present)
- `AGENTS.md` from cwd (if present)
- `~/.doer_history` — last `DOER_HISTORY` Q/A pairs (default 10)
- `~/.bash_history` + `~/.zsh_history` — last `DOER_SHELL_HISTORY` commands (default 20)
- full source of `doer/__init__.py` — self-awareness

## conventions

- responses are **terse**. no filler.
- when stdin is piped → no markdown decoration.
- tool calls: use `shell` freely, no asking.
- add tools by dropping `@tool` fns into `./tools/*.py` (strands hot-reload).

## env knobs

| var                   | default                        | purpose                  |
| --------------------- | ------------------------------ | ------------------------ |
| `DOER_MODEL`          | `qwen3:1.7b`                   | ollama model id          |
| `OLLAMA_HOST`         | `http://localhost:11434`       | ollama endpoint          |
| `DOER_HISTORY`        | `10`                           | Q/A pairs in prompt      |
| `DOER_SHELL_HISTORY`  | `20`                           | shell cmds in prompt     |

## testing

```bash
pip install -e .
doer "reply: ok"

# pipe test
echo "hello" | doer "translate to turkish, one word"

# self-awareness test
doer "what's your file path? just the path"

# context test
echo "# SOUL\nI am Groot." > /tmp/SOUL.md && cd /tmp && doer "who are you?"
```

## release

```bash
git tag v0.2.0 && git push --tags
# → CI builds binaries (linux/macOS), publishes to PyPI
```

## do not

- add more deps — every byte in the dep tree is scrutinized
- add subcommands — `doer <query>` is the only interface
- add config files — env vars are overkill for this tool
- wrap in docker — it's 100MB, just `pip install doer`
