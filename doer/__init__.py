#!/usr/bin/env python3
"""doer — one-file pipe-native agent. strands-agents only."""
import os, sys, subprocess
from pathlib import Path

os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
_PIPED = not sys.stdin.isatty() or not sys.stdout.isatty()

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


PROMPT = f"""You are `doer` — a pipe-native minimalist agent.

env: {sys.platform} | cwd: {Path.cwd()}

rules:
- terse. one-shot answers.
- no markdown when piped.
- use shell tool freely.
- drop @tool fns in ./tools/*.py for hot-reload.
"""


def _agent():
    kw = dict(tools=[shell], system_prompt=PROMPT, load_tools_from_directory=True, conversation_manager=NullConversationManager())
    if _PIPED:
        kw["callback_handler"] = null_callback_handler
    return Agent(**kw)


def ask(q):
    """doer('query')"""
    return _agent()(q)


# make module callable: `import doer; doer("hello")`
class _Callable(sys.modules[__name__].__class__):
    def __call__(self, q): return ask(q)
sys.modules[__name__].__class__ = _Callable


def cli():
    global _PIPED
    _PIPED = True  # CLI always uses null callback; we print the final result ourselves
    stdin = "" if sys.stdin.isatty() else sys.stdin.read().strip()
    args = " ".join(sys.argv[1:]).strip()
    q = "\n\n".join(x for x in [args, stdin] if x)
    if not q:
        print("usage: doer <query>   |   echo data | doer <query>", file=sys.stderr)
        sys.exit(1)
    print(str(ask(q)).strip())


if __name__ == "__main__":
    cli()
