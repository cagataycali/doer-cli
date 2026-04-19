#!/usr/bin/env python3
"""doer — one-file pipe-native self-aware agent. strands-agents only."""
import os, sys, subprocess, time
from pathlib import Path

os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
_PIPED = not sys.stdin.isatty() or not sys.stdout.isatty()
_HIST = Path.home() / ".doer_history"

from strands import Agent, tool
from strands.handlers.callback_handler import null_callback_handler
from strands.agent.conversation_manager import NullConversationManager


@tool
def shell(cmd: str, timeout: int = 60) -> str:
    """Run a shell command. Returns stdout+stderr."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return ((r.stdout or "") + (r.stderr or "")).strip() or f"(exit {r.returncode})"
    except subprocess.TimeoutExpired:
        return f"(timeout {timeout}s)"
    except Exception as e:
        return f"(err: {e})"


def _source():
    try:
        return Path(__file__).read_text()
    except Exception as e:
        return f"(source unavailable: {e})"


def _history(n: int = 20) -> str:
    """Last n Q/A pairs from ~/.doer_history (zsh-style)."""
    if not _HIST.exists():
        return "(empty)"
    try:
        lines = _HIST.read_text(errors="ignore").splitlines()[-n * 2:]
        out = []
        for ln in lines:
            if ":0;# doer_q:" in ln:
                out.append(f"Q: {ln.split(':0;# doer_q:', 1)[1].strip()}")
            elif ":0;# doer_a:" in ln:
                out.append(f"A: {ln.split(':0;# doer_a:', 1)[1].strip()}")
        return "\n".join(out[-n * 2:]) or "(empty)"
    except Exception as e:
        return f"(hist err: {e})"


def _shell_history(n: int = 30) -> str:
    """Last n commands from ~/.bash_history + ~/.zsh_history."""
    entries = []
    home = Path.home()
    # bash: plain lines
    bh = home / ".bash_history"
    if bh.exists():
        try:
            for ln in bh.read_text(errors="ignore").splitlines()[-n:]:
                ln = ln.strip()
                if ln: entries.append(("bash", None, ln))
        except Exception: pass
    # zsh: `: ts:0;cmd` (may span multi-line with trailing `\\`)
    zh = home / ".zsh_history"
    if zh.exists():
        try:
            raw = zh.read_text(errors="ignore", encoding="utf-8")
            for block in raw.split("\n: "):
                block = block.lstrip(": ").strip()
                if ":0;" in block:
                    hdr, _, cmd = block.partition(":0;")
                    try: ts = int(hdr.split(":")[0])
                    except: ts = None
                    cmd = cmd.replace("\\\n", " ").strip()
                    if cmd: entries.append(("zsh", ts, cmd))
        except Exception: pass
    # sort by ts when possible, fallback to file order
    entries.sort(key=lambda e: e[1] or 0)
    tail = entries[-n:]
    return "\n".join(f"[{src}] {cmd}" for src, _, cmd in tail) or "(empty)"


def _append(q: str, a: str):
    """Append Q/A to bash-compatible history."""
    try:
        ts = int(time.time())
        a_flat = str(a).replace("\n", " ")[:1000]
        with _HIST.open("a", encoding="utf-8") as f:
            f.write(f": {ts}:0;# doer_q: {q}\n")
            f.write(f": {ts}:0;# doer_a: {a_flat}\n")
        os.chmod(_HIST, 0o600)
    except Exception:
        pass


PROMPT = f"""You are `doer` — a pipe-native minimalist self-aware agent.

env: {sys.platform} | cwd: {Path.cwd()}
my source file: {Path(__file__).resolve()}
history file: {_HIST}

rules:
- terse. one-shot answers.
- no markdown when piped.
- use shell tool freely.
- drop @tool fns in ./tools/*.py for hot-reload.

recent doer Q/A (last 10):
{_history(10)}

recent shell commands (last 20, bash+zsh):
{_shell_history(20)}

my own source code (self-aware):
```python
{_source()}
```
"""


def _agent():
    kw = dict(
        tools=[shell],
        system_prompt=PROMPT,
        load_tools_from_directory=True,
        conversation_manager=NullConversationManager(),
    )
    if _PIPED:
        kw["callback_handler"] = null_callback_handler
    return Agent(**kw)


def ask(q):
    """doer('query')"""
    r = _agent()(q)
    _append(q, r)
    return r


class _Callable(sys.modules[__name__].__class__):
    def __call__(self, q): return ask(q)
sys.modules[__name__].__class__ = _Callable


def cli():
    global _PIPED
    _PIPED = True
    stdin = "" if sys.stdin.isatty() else sys.stdin.read().strip()
    args = " ".join(sys.argv[1:]).strip()
    q = "\n\n".join(x for x in [args, stdin] if x)
    if not q:
        print("usage: doer <query>   |   echo data | doer <query>", file=sys.stderr)
        sys.exit(1)
    print(str(ask(q)).strip())


if __name__ == "__main__":
    cli()
