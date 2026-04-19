# AGENTS.md — doer

## project
- **what:** one-file pipe-native AI agent
- **lang:** python 3.10+
- **dep:** `strands-agents` (only)
- **entry:** `doer/__init__.py`
- **install:** `pip install doer` or download binary from releases
- **license:** Apache-2.0

## architecture

```
doer/
├── __init__.py    # everything: Agent, shell tool, CLI, memory, context
├── __main__.py    # python -m doer entry
SOUL.md            # identity, philosophy (auto-injected into system prompt)
AGENTS.md          # this file (auto-injected into system prompt)
build.sh           # local PyInstaller binary build
.github/workflows/
└── release.yml    # tag v* → binaries + PyPI
```

## design rules

1. **one file of source logic** — all in `doer/__init__.py`
2. **one external dep** — only `strands-agents`
3. **no classes unless the SDK forces it** — functions are cheaper
4. **context over memory** — don't store state, recompute from filesystem every call
5. **unix over RPC** — stdin/stdout/pipes, not HTTP/WebSocket

## context injection (what the agent sees every call)

automatically built into the system prompt:
- env (`platform.sys`), cwd (`Path.cwd()`)
- `__file__` absolute path — self-location
- `~/.doer_history` — last 10 Q/A pairs (zsh-compatible format)
- `~/.bash_history` + `~/.zsh_history` — last 20 shell commands
- full source code of `doer/__init__.py` — self-awareness
- `SOUL.md` if present in cwd — identity
- `AGENTS.md` if present in cwd — project rules

## conventions

- responses are **terse**. no filler.
- when stdin is piped → no markdown decoration.
- tool calls: use `shell` freely, no asking.
- add tools by dropping `@tool` fns into `./tools/*.py` (strands hot-reload).

## testing

```bash
pip install -e .
doer "reply: ok"

# pipe test
echo "hello" | doer "translate to turkish, one word"

# self-awareness test
doer "what's your file path? just the path"
```

## release

```bash
git tag v0.1.0 && git push --tags
# → CI builds binaries (linux/macOS), publishes to PyPI
```

## do not

- add more deps — every byte in the dep tree is scrutinized
- add subcommands — `doer <query>` is the only interface
- add configuration files — env vars are overkill for this tool
- wrap in docker — it's 100MB, just `pip install doer`
