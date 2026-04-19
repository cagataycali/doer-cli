# Context

Every call, the agent reads your shell like a person reads a room.

**No database. No config. The filesystem is the memory.**

## what gets injected

<div class="grid cards" markdown>

-   **`SOUL.md` (cwd)**

    Who **doer** is inside this project. Identity, voice, rules.

-   **`AGENTS.md` (cwd)**

    Project-specific conventions. Architecture. Don't-dos.

-   **`~/.doer_history`**

    Last N Q/A pairs, zsh-compatible format. Controlled by `DOER_HISTORY`.

-   **`~/.bash_history` + `~/.zsh_history`**

    Merged chronologically. Controlled by `DOER_SHELL_HISTORY`.

-   **`./tools/*.py`**

    Any `@tool` function. Hot-reloaded by Strands on every call.

-   **Own source**

    Full `doer/__init__.py` is in the system prompt. Full self-awareness.

</div>

## why this design

- **No state** means no stale context. Every call reads fresh.
- **No config files** means no `~/.doerrc` to lose, rsync, or corrupt.
- **Filesystem** is the one thing every Unix user already knows.

## example: project-specific behavior

```bash
cd ~/my-project
cat > SOUL.md <<EOT
# SOUL
You are a code reviewer for this Python project.
Terse. Ruthless. Suggest fixes in diff format.
EOT

git diff | do "review"
# → reviews in diff format, terse, ruthless
```

Leave the directory, the SOUL vanishes. Pure.
