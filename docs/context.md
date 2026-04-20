# Context

Every call, the agent reads your shell **like a person reads a room**.

**No database. No config. The filesystem is the memory.**

## what gets injected

<div class="grid cards" markdown>

-   **`SOUL.md` (cwd)**

    Who **doer** is inside this project. Identity, voice, rules.

-   **`AGENTS.md` (cwd)**

    Project conventions. Architecture. Don't-dos.

-   **`~/.doer_history`**

    Last N Q/A pairs, zsh-compatible. Tuned via `DOER_HISTORY`.

    *Sibling file:* `~/.doer_training.jsonl` stores **full** turns (system + messages + tools) for self-training — see [Train](train.md).

-   **`~/.bash_history` + `~/.zsh_history`**

    Merged chronologically. Tuned via `DOER_SHELL_HISTORY`.

-   **`./tools/*.py`**

    Any `@tool` function. Strands hot-reloads on every call.

-   **Own source**

    Full `doer/__init__.py` is in the system prompt. Full self-awareness.

-   **`--img` / `--audio` / `--video`**

    Raw media attached at call time. Routes to `mlx-vlm` (vision, audio, or omni model) automatically.

</div>

## how the prompt is assembled

```
┌──────────────────────────────────┐
│ 1. base persona (terse, unix)    │
├──────────────────────────────────┤
│ 2. SOUL.md   (cwd, if present)   │
├──────────────────────────────────┤
│ 3. AGENTS.md (cwd, if present)   │
├──────────────────────────────────┤
│ 4. own source code (self-aware)  │
├──────────────────────────────────┤
│ 5. last N Q/A from history       │
├──────────────────────────────────┤
│ 6. last N shell commands         │
├──────────────────────────────────┤
│ 7. your query + stdin            │
├──────────────────────────────────┤
│ 8. --img / --audio / --video     │
│    (raw bytes, VLM-routed)       │
└──────────────────────────────────┘
```

Everything recomputed. Every call. No cache to invalidate.

## why this design

- **No state** means no stale context. Every call reads fresh.
- **No config files** means no `~/.doerrc` to sync, lose, or corrupt.
- **Filesystem** is the one abstraction every Unix user already knows.
- **Directory = scope.** `cd` is the context switch.

## example: project-specific behavior

```bash
cd ~/my-python-service
cat > SOUL.md <<'EOT'
# SOUL
You are a code reviewer for this Python service.
Terse. Ruthless. Suggest fixes in unified diff format.
Prefer stdlib. Reject anything that adds a dependency.
EOT

git diff | do "review"
# → reviews in diff format, terse, ruthless, no-deps-added
```

Leave the directory → the SOUL vanishes. Pure.

## example: project rules

`AGENTS.md` is a simple markdown file with the rules of your project.
It survives across LLMs, editors, and agents (Cursor, Aider, Claude, DevDuck…).

```markdown title="./AGENTS.md"
# my-service — agent rules

- **lang:** python 3.11+
- **style:** black, ruff, no `print()` — use `logging`
- **tests:** `pytest -x` must pass before commit
- **DO NOT** add dependencies without explicit approval
- **DO NOT** touch `migrations/` — hand-written
- when unsure: ask, don't guess
```

`doer` reads it. So do most modern coding agents. One file, many tools.

## example: history-aware flow

```bash
$ cd proj && do "what's the first thing I did today?"
you ran `git pull` at 09:12.
$ do "and what did I break last hour?"
the last failing test run was `pytest test_auth` at 14:47 —
  you committed a refactor of `jwt.py` at 14:44.
```

No chat history service. Just `~/.zsh_history` + `~/.doer_history` + timestamps.
The shell **is** the memory.

## size limits

| knob                    | effect                                    |
| ----------------------- | ----------------------------------------- |
| `DOER_HISTORY=10`       | inject 10 Q/A pairs (default)             |
| `DOER_SHELL_HISTORY=20` | inject 20 shell commands (default)        |
| `DOER_MAX_TOKENS=2000`  | cap model output                          |

Smaller = faster + cheaper. Bigger = more context. Tune per machine.

## leave no trace

To reset any session memory:

```bash
rm ~/.doer_history          # clears Q/A log (prompt context)
rm ~/.doer_training.jsonl   # clears training corpus
rm -rf ~/.doer_adapter      # clears trained LoRA adapter
```

That's it. No app state. No database. Nothing to vacuum.
