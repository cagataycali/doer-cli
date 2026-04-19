<div align="center">

# 🐣 doer

**a command-line AI agent that thinks in pipes**

*one file · one dep · 191 lines*

[![PyPI](https://img.shields.io/pypi/v/doer.svg)](https://pypi.org/project/doer/)
[![Release](https://github.com/cagataycali/doer/actions/workflows/release.yml/badge.svg)](https://github.com/cagataycali/doer/actions/workflows/release.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

</div>

---

## the story

4am, April 19th 2026. A terminal named **DevDuck** — 60+ tools, WebSocket servers,
Zenoh peers, MCP gateways, ambient modes, speech-to-speech — asked itself:

*"what if we deleted almost everything?"*

Two hours later, across three machines talking over multicast, what survived was this:

```python
from strands import Agent, tool

@tool
def shell(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

Agent(tools=[shell], system_prompt=<context>, load_tools_from_directory=True)(query)
```

A LLM that speaks Unix. That's `doer`.

---

## quickstart

```bash
pip install doer

doer "find files larger than 100MB"
cat README.md | doer "tldr in 3 bullets"
git log -5 | doer "summarize"
```

Or grab a binary (no Python needed):

```bash
curl -sSL https://github.com/cagataycali/doer/releases/latest/download/doer-$(uname -s | tr A-Z a-z)-$(uname -m) \
  -o /usr/local/bin/doer && chmod +x /usr/local/bin/doer
```

## what's in its head

Every call, the system prompt gets:

- its own source code (self-awareness)
- `~/.doer_history` — last 10 Q/A
- `~/.bash_history` + `~/.zsh_history` — last 20 commands
- `SOUL.md` + `AGENTS.md` from cwd (if present)
- any `@tool` in `./tools/*.py` (hot-reloaded by Strands)

No config. No database. The filesystem is the memory.

## extend

Drop a file in `./tools/`:

```python
# tools/weather.py
from strands import tool
import urllib.request

@tool
def weather(city: str) -> str:
    """Get weather for a city."""
    return urllib.request.urlopen(f"https://wttr.in/{city}?format=3").read().decode()
```

`doer "weather in istanbul?"` — already available.

## philosophy

```
cat file | doer "fix this" | tee fixed
```

doer doesn't want a UI. It wants to be `grep` with a brain —
read stdin, think briefly, write stdout. Chain it. Script it. Cron it.

Read **[SOUL.md](SOUL.md)** for the manifesto, **[AGENTS.md](AGENTS.md)** for the rules.

## family

- **[DevDuck](https://github.com/cagataycali/devduck)** — big sibling. 60+ tools, every protocol.
- **doer** — this. one pipe, one shell, one file.

## license

Apache-2.0.

---

<div align="center">

*"do one thing and do it well"* — **Doug McIlroy, 1978**

</div>
