<div align="center">

<img src="doer.svg" width="180" alt="doer">

# **DOER**

### `stdin → llm → stdout`

**A Unix citizen that thinks. One file. One dep. Zero ceremony.**

[![PyPI](https://img.shields.io/pypi/v/doer-cli.svg?style=for-the-badge&color=FF3D00&labelColor=0A0A0A)](https://pypi.org/project/doer-cli/)
[![License](https://img.shields.io/badge/APACHE-2.0-FAFAF7?style=for-the-badge&labelColor=0A0A0A)](LICENSE)
[![Python](https://img.shields.io/badge/PYTHON-3.10%2B-FAFAF7?style=for-the-badge&labelColor=0A0A0A)](https://python.org)

</div>

---

## install

```bash
pip install doer-cli    # package on PyPI
doer                    # binary on your PATH
```

## run

```bash
doer "find files larger than 100MB"
cat error.log  | doer "what broke"
git log -20    | doer "write release notes"
echo '{"a":1}' | doer "to yaml"
```

## what it is

```python
Agent(
    model=Ollama(...),
    tools=[shell] + hot_reload("./tools"),
    system_prompt=SOUL.md + AGENTS.md + ~/.doer_history + ~/.bash_history + ~/.zsh_history + own_source,
)(stdin + argv)
```

That's the entire architecture. **164 lines** of Python. It reads your shell like a person reads a room.

## context it sees every call

| source                   | what                                         |
| ------------------------ | -------------------------------------------- |
| `SOUL.md` (cwd)          | who it is in this project                    |
| `AGENTS.md` (cwd)        | rules for this project                       |
| `~/.doer_history`        | last N Q/A (default 10 — `DOER_HISTORY`)     |
| `~/.bash_history` + `~/.zsh_history` | last N commands (default 20 — `DOER_SHELL_HISTORY`) |
| `./tools/*.py`           | hot-reloaded `@tool` functions               |
| own source               | full self-awareness                          |

No database. No config file. **The filesystem is the memory.**

## env knobs

```bash
DOER_MODEL=qwen3:1.7b            # any ollama model
OLLAMA_HOST=http://localhost:11434
DOER_HISTORY=10                  # Q/A rows in prompt
DOER_SHELL_HISTORY=20            # shell rows in prompt
```

## extend in 60 seconds

```python
# ./tools/weather.py
from strands import tool
import urllib.request

@tool
def weather(city: str) -> str:
    """Weather for a city."""
    return urllib.request.urlopen(f"https://wttr.in/{city}?format=3").read().decode()
```

Next call: `doer "istanbul weather?"` — hot-reloaded, no restart.

## philosophy

```
┌─────┐       ┌──────┐       ┌──────┐
│stdin│──────▶│ doer │──────▶│stdout│
└─────┘       └──────┘       └──────┘
```

`grep` with a brain. Chain it. Script it. Cron it.

Read [**SOUL.md**](SOUL.md) for the manifesto. Read [**AGENTS.md**](AGENTS.md) for the rules.

## family

| project    | size       | purpose                           |
| ---------- | ---------- | --------------------------------- |
| **doer**   | 164 LOC    | one pipe, one shell, one file     |
| [**DevDuck**](https://github.com/cagataycali/devduck) | 60+ tools  | every protocol, every edge |

## license

Apache-2.0 · built in New York · 2026

---

<div align="center">

**`do one thing and do it well`** — Doug McIlroy, 1978

</div>
