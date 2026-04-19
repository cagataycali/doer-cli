#!/usr/bin/env python3
"""
🐣 tiny - one file agent. jack of all trades. pipe-friendly.
"""
import os, sys, time
from pathlib import Path
from datetime import datetime

# detect pipe mode FIRST (before any rich-using import)
_PIPED = (not sys.stdin.isatty()) or (not sys.stdout.isatty())

os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
if _PIPED:
    # silence rich/strands_tools decoration in pipe mode
    os.environ["STRANDS_TOOL_CONSOLE_MODE"] = "disabled"
    os.environ["NO_COLOR"] = "1"
    os.environ["TERM"] = "dumb"
    # redirect stderr to devnull so shell tool rich-prints vanish
    import io
    sys.stderr = open(os.devnull, "w")
else:
    os.environ.setdefault("STRANDS_TOOL_CONSOLE_MODE", "enabled")

from strands import Agent
from strands.handlers.callback_handler import null_callback_handler
from strands_tools import shell

# ---------- bash history ----------
HIST_FILES = [Path.home() / ".bash_history", Path.home() / ".zsh_history"]
TINY_HIST = Path.home() / ".tiny_history"
TINY_HIST.touch(exist_ok=True)


def _read_history(n=50):
    lines = []
    for hf in HIST_FILES + [TINY_HIST]:
        if not hf.exists():
            continue
        try:
            with open(hf, encoding="utf-8", errors="ignore") as f:
                lines.extend(f.readlines()[-n:])
        except Exception:
            pass
    return "".join(lines[-n:])


def _append_history(query, response):
    try:
        ts = int(time.time())
        with open(TINY_HIST, "a", encoding="utf-8") as f:
            f.write(f": {ts}:0;# tiny: {query}\n")
            f.write(f": {ts}:0;# tiny_result: {str(response)[:2000]}\n")
    except Exception:
        pass


# ---------- tools ----------
from strands import tool


@tool
def system_prompt(action: str = "view", content: str = "") -> str:
    """View or append to system prompt (persisted to ~/.tiny_prompt)."""
    p = Path.home() / ".tiny_prompt"
    if action == "view":
        return p.read_text() if p.exists() else "(empty)"
    if action == "append":
        with open(p, "a") as f:
            f.write(f"\n{content}")
        return f"appended {len(content)} chars"
    if action == "set":
        p.write_text(content)
        return f"set {len(content)} chars"
    return "actions: view|append|set"


@tool
def manage_tools(action: str = "list", code: str = "", name: str = "") -> str:
    """Create/list hot-reloadable tools. action=create writes ./tools/<name>.py"""
    tools_dir = Path.cwd() / "tools"
    tools_dir.mkdir(exist_ok=True)
    if action == "list":
        return "\n".join(str(p) for p in tools_dir.glob("*.py")) or "(no tools)"
    if action == "create":
        if not name or not code:
            return "need name + code"
        (tools_dir / f"{name}.py").write_text(code)
        return f"created tools/{name}.py - hot-reload active"
    return "actions: list|create"


# ---------- prompt ----------
def _build_prompt():
    hist = _read_history(30)
    custom = ""
    cp = Path.home() / ".tiny_prompt"
    if cp.exists():
        custom = cp.read_text()
    cwd = Path.cwd()
    return f"""🐣 You are tiny - a pipe-friendly minimal shell agent.

Environment: {sys.platform} | cwd: {cwd} | time: {datetime.now().isoformat()}

You are:
- Minimal: brief, direct, pipe-friendly output (no markdown when piped)
- Shell-native: use shell tool freely
- Self-extending: create new tools via manage_tools when needed
- Context-aware: recent shell history below

## Recent shell history:
```
{hist}
```

## Custom instructions:
{custom}

Respond with just the answer. Be terse. If output will be piped, no decoration.
"""


# ---------- agent ----------
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        # when piped, silence streaming callback (pipe-friendly)
        cb = None
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            cb = null_callback_handler
        kwargs = dict(
            tools=[shell, system_prompt, manage_tools],
            system_prompt=_build_prompt(),
            load_tools_from_directory=True,
        )
        if cb is not None:
            kwargs["callback_handler"] = cb
        _agent = Agent(**kwargs)
        # hot-reload handled natively by strands via load_tools_from_directory=True
    return _agent


def ask(query: str) -> str:
    result = _get_agent()(query)
    _append_history(query, result)
    return str(result)


# ---------- cli ----------
def cli():
    piped = not sys.stdin.isatty()
    stdin_data = sys.stdin.read().strip() if piped else ""
    args = " ".join(sys.argv[1:]).strip()

    # combine
    parts = [p for p in [args, stdin_data] if p]
    query = "\n\n".join(parts)

    if not query:
        # interactive REPL
        print("🐣 tiny - Ctrl+D to exit")
        while True:
            try:
                q = input("🐣 ")
                if not q.strip():
                    continue
                print(ask(q))
            except (EOFError, KeyboardInterrupt):
                print()
                break
        return

    # one-shot (pipe or arg)
    result = ask(query)
    # only print final if piped (otherwise agent already streamed it)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stdout.write(str(result).rstrip() + chr(10))
        sys.stdout.flush()


# module-level callable: import tiny; tiny("query")
class _Callable(sys.modules[__name__].__class__):
    def __call__(self, q):
        return ask(q)


sys.modules[__name__].__class__ = _Callable


if __name__ == "__main__":
    cli()
