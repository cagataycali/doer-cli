# History

doer keeps a persistent Q/A log and also scrapes your shell history to inject context into every call.

## Three History Sources

### 1. doer history — `~/.doer_history`

Bash-compatible format. Every Q/A pair is appended:

```
: 1713500000:0;# doer_q: what's my ip?
: 1713500000:0;# doer_a: 192.168.1.5
: 1713500042:0;# doer_q: tldr this file
: 1713500042:0;# doer_a: it's a shell script that...
```

- Last 10 Q/A pairs injected into system prompt.
- Mode `0600` — private.
- No conversation bleed: each call is stateless (`NullConversationManager`), history is *context only*.

### 2. Bash history — `~/.bash_history`

Last ~30 commands (plain lines).

### 3. Zsh history — `~/.zsh_history`

Last ~30 commands, `: ts:0;cmd` format, timestamp-sorted.

## What the Agent Sees

Merged in the system prompt:

```
recent doer Q/A (last 10):
Q: what's my ip?
A: 192.168.1.5
...

recent shell commands (last 20, bash+zsh):
[zsh] cd ~/project
[zsh] git pull
[bash] make build
...
```

## Why?

- **Context-rich** — the agent knows what you're working on without you re-explaining.
- **Zero friction** — no memory tool, no setup, no sidecar.
- **Private** — never leaves your machine. No telemetry.

## Clear History

```bash
rm ~/.doer_history
```

Your shell history (`~/.bash_history`, `~/.zsh_history`) is managed by your shell — doer only reads it.
