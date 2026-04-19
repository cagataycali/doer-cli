#!/usr/bin/env python3
"""doer — one-file pipe-native self-aware agent. strands-agents + ollama only."""
import os, sys, subprocess, time
from pathlib import Path

os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
_PIPED = not sys.stdin.isatty() or not sys.stdout.isatty()
_HIST = Path.home() / ".doer_history"

# config (override via env)
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_OLLAMA_MODEL = os.environ.get("DOER_MODEL", "qwen3:1.7b")
_N_DOER = int(os.environ.get("DOER_HISTORY", "10"))    # doer Q/A pairs
_N_SHELL = int(os.environ.get("DOER_SHELL_HISTORY", "20"))  # bash+zsh commands

from strands import Agent, tool
from strands.models.ollama import OllamaModel
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
    """Read own source. Works in dev and PyInstaller frozen binary."""
    try:
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            for c in (base / "doer" / "__init__.py", base / "__init__.py"):
                if c.exists(): return c.read_text()
            return f"(frozen; source not bundled at {base})"
        return Path(__file__).read_text()
    except Exception as e:
        return f"(source unavailable: {e})"


def _doer_history(n: int) -> str:
    """Last n Q/A pairs from ~/.doer_history."""
    if not _HIST.exists(): return "(empty)"
    try:
        out = []
        for ln in _HIST.read_text(errors="ignore").splitlines():
            if ":0;# doer_q:" in ln:
                out.append(f"Q: {ln.split(':0;# doer_q:', 1)[1].strip()}")
            elif ":0;# doer_a:" in ln:
                out.append(f"A: {ln.split(':0;# doer_a:', 1)[1].strip()}")
        return "\n".join(out[-n * 2:]) or "(empty)"
    except Exception as e:
        return f"(err: {e})"


def _shell_history(n: int) -> str:
    """Last n commands from ~/.bash_history + ~/.zsh_history (merged, chronological)."""
    entries = []
    home = Path.home()
    bh = home / ".bash_history"
    if bh.exists():
        try:
            for ln in bh.read_text(errors="ignore").splitlines():
                ln = ln.strip()
                if ln: entries.append(("bash", 0, ln))
        except Exception: pass
    zh = home / ".zsh_history"
    if zh.exists():
        try:
            for block in zh.read_text(errors="ignore").split("\n: "):
                block = block.lstrip(": ").strip()
                if ":0;" in block:
                    hdr, _, cmd = block.partition(":0;")
                    try: ts = int(hdr.split(":")[0])
                    except: ts = 0
                    cmd = cmd.replace("\\\n", " ").strip()
                    if cmd: entries.append(("zsh", ts, cmd))
        except Exception: pass
    entries.sort(key=lambda e: e[1])
    return "\n".join(f"[{s}] {c}" for s, _, c in entries[-n:]) or "(empty)"


def _ctx(name: str) -> str:
    """Read a context file from cwd."""
    f = Path.cwd() / name
    if f.exists() and f.is_file():
        try: return f.read_text(errors="ignore").strip()
        except Exception as e: return f"(err reading {name}: {e})"
    return ""


def _append(q: str, a: str):
    """Append Q/A to history."""
    try:
        ts = int(time.time())
        a_flat = str(a).replace("\n", " ")[:1000]
        with _HIST.open("a", encoding="utf-8") as f:
            f.write(f": {ts}:0;# doer_q: {q}\n")
            f.write(f": {ts}:0;# doer_a: {a_flat}\n")
        os.chmod(_HIST, 0o600)
    except Exception: pass


def _prompt() -> str:
    soul = _ctx("SOUL.md")
    agents = _ctx("AGENTS.md")
    parts = [f"env: {sys.platform} | cwd: {Path.cwd()} | model: ollama {_OLLAMA_MODEL} @ {_OLLAMA_HOST}"]
    if soul:   parts.append(f"# SOUL.md\n{soul}")
    if agents: parts.append(f"# AGENTS.md\n{agents}")
    parts.append(f"# recent Q/A (last {_N_DOER})\n{_doer_history(_N_DOER)}")
    parts.append(f"# recent shell (last {_N_SHELL}, bash+zsh)\n{_shell_history(_N_SHELL)}")
    parts.append(f"# source ({Path(__file__).resolve()})\n```python\n{_source()}\n```")
    return "\n\n".join(parts)


def _agent():
    kw = dict(
        model=OllamaModel(host=_OLLAMA_HOST, model_id=_OLLAMA_MODEL, keep_alive="5m"),
        tools=[shell],
        system_prompt=_prompt(),
        load_tools_from_directory=True,
        conversation_manager=NullConversationManager(),
    )
    if _PIPED: kw["callback_handler"] = null_callback_handler
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
        print(f"model:    ollama {_OLLAMA_MODEL} @ {_OLLAMA_HOST}", file=sys.stderr)
        print(f"history:  {_N_DOER} Q/A pairs from {_HIST}", file=sys.stderr)
        print(f"shell:    {_N_SHELL} cmds from ~/.bash_history + ~/.zsh_history", file=sys.stderr)
        print(f"context:  SOUL.md + AGENTS.md from cwd (if present)", file=sys.stderr)
        print(f"env:      DOER_MODEL, OLLAMA_HOST, DOER_HISTORY, DOER_SHELL_HISTORY", file=sys.stderr)
        sys.exit(1)
    print(str(ask(q)).strip())


if __name__ == "__main__":
    cli()
