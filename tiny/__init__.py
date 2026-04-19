#!/usr/bin/env python3
"""
🐣 tiny - one file agent. jack of all trades. pipe-friendly.
"""
import os, sys, time
from pathlib import Path
from datetime import datetime

_PIPED = (not sys.stdin.isatty()) or (not sys.stdout.isatty())

import subprocess
from strands import Agent, tool
from strands.handlers.callback_handler import null_callback_handler


@tool
def shell(command: str, timeout: int = 60) -> str:
    """Execute shell command. Returns stdout+stderr."""
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        out = (r.stdout or "") + (r.stderr or "")
        return out.strip() or f"(exit {r.returncode})"
    except subprocess.TimeoutExpired:
        return f"(timeout after {timeout}s)"
    except Exception as e:
        return f"(error: {e})"

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
    """Manage hot-reloadable tools in ./tools/.
    actions: list | create (needs name+code) | read (needs name) | delete (needs name)
    Strands auto-reloads from ./tools/*.py — just drop a file with @tool decorated fn.
    """
    tools_dir = Path.cwd() / "tools"
    tools_dir.mkdir(exist_ok=True)
    if action == "list":
        files = list(tools_dir.glob("*.py"))
        return "\n".join(f.name for f in files) or "(no tools)"
    if action == "create":
        if not name or not code:
            return "need name + code"
        (tools_dir / f"{name}.py").write_text(code)
        return f"created tools/{name}.py — hot-reload active"
    if action == "read":
        f = tools_dir / f"{name}.py"
        return f.read_text() if f.exists() else f"no tools/{name}.py"
    if action == "delete":
        f = tools_dir / f"{name}.py"
        if f.exists():
            f.unlink()
            return f"deleted tools/{name}.py"
        return f"no tools/{name}.py"
    return "actions: list | create | read | delete"


@tool
def manage_messages(action: str = "list", n: int = 10) -> str:
    """Inspect/manage agent conversation messages.
    actions: list (last n) | count | clear | summary (role counts)
    """
    a = _agent
    if a is None or not hasattr(a, "messages"):
        return "(no agent yet)"
    msgs = a.messages or []
    if action == "count":
        return str(len(msgs))
    if action == "clear":
        a.messages.clear()
        return "cleared"
    if action == "summary":
        from collections import Counter
        roles = Counter(m.get("role", "?") if isinstance(m, dict) else getattr(m, "role", "?") for m in msgs)
        return f"total={len(msgs)} " + " ".join(f"{k}={v}" for k, v in roles.items())
    if action == "list":
        out = []
        for i, m in enumerate(msgs[-n:]):
            if isinstance(m, dict):
                role = m.get("role", "?")
                content = m.get("content", "")
            else:
                role = getattr(m, "role", "?")
                content = getattr(m, "content", "")
            s = str(content)[:200].replace("\n", " ")
            out.append(f"[{i}] {role}: {s}")
        return "\n".join(out) or "(empty)"
    return "actions: list | count | clear | summary"


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
            tools=[shell, system_prompt, manage_tools, manage_messages],
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
