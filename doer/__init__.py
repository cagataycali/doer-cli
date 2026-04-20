#!/usr/bin/env python3
"""doer — one-file pipe-native self-aware agent. strands-agents + ollama/bedrock."""
import os, sys, subprocess, time
from pathlib import Path

os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
_PIPED = not sys.stdin.isatty() or not sys.stdout.isatty()
_HIST = Path.home() / ".doer_history"

# config (override via env)
_PROVIDER = os.environ.get("DOER_PROVIDER", "").lower()  # "", "ollama", "bedrock"
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_OLLAMA_MODEL = os.environ.get("DOER_MODEL", "qwen3:1.7b")
_BEDROCK_MODEL = os.environ.get("DOER_BEDROCK_MODEL", "global.anthropic.claude-opus-4-7")
_BEDROCK_REGION = os.environ.get("DOER_BEDROCK_REGION", os.environ.get("AWS_REGION", "us-west-2"))
_N_DOER = int(os.environ.get("DOER_HISTORY", "10"))    # doer Q/A pairs
_N_SHELL = int(os.environ.get("DOER_SHELL_HISTORY", "20"))  # bash+zsh commands

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


def _pairs():
    """Parse ~/.doer_history into [(q, a), ...] pairs (chronological)."""
    if not _HIST.exists(): return []
    out, q = [], None
    for ln in _HIST.read_text(errors="ignore").splitlines():
        if ":0;# doer_q:" in ln: q = ln.split(":0;# doer_q:", 1)[1].strip()
        elif ":0;# doer_a:" in ln and q is not None:
            a = ln.split(":0;# doer_a:", 1)[1].strip()
            if q and a: out.append((q, a))
            q = None
    return out


def export(fmt: str = "sharegpt", out=None, with_system: bool = True):
    """Export ~/.doer_history as a training dataset (JSONL).

    fmt: 'sharegpt' (Qwen/Llama default) | 'chatml' | 'alpaca' | 'openai'
    out: file path or None (stdout). with_system: include doer's live prompt.
    """
    import json
    if fmt not in ("sharegpt", "chatml", "alpaca", "openai"):
        sys.stderr.write(f"unknown fmt: {fmt} (use sharegpt|chatml|alpaca|openai)\n"); return 0
    pairs = _pairs()
    if not pairs:
        sys.stderr.write("(no Q/A pairs in ~/.doer_history)\n"); return 0
    _, desc = _model()
    sysp = _prompt(desc) if with_system else None
    fh = open(out, "w", encoding="utf-8") if out else sys.stdout
    try:
        for q, a in pairs:
            if fmt == "sharegpt":
                conv = []
                if sysp: conv.append({"from": "system", "value": sysp})
                conv += [{"from": "human", "value": q}, {"from": "gpt", "value": a}]
                rec = {"conversations": conv}
            elif fmt in ("chatml", "openai"):
                msgs = []
                if sysp: msgs.append({"role": "system", "content": sysp})
                msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
                rec = {"messages": msgs}
            else:  # alpaca
                rec = {"instruction": q, "input": "", "output": a}
                if sysp: rec["system"] = sysp
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    finally:
        if out: fh.close()
    sys.stderr.write(f"exported {len(pairs)} pairs → {out or 'stdout'} ({fmt})\n")
    return len(pairs)


def _model():
    """Build model from provider. Auto-detect: bedrock if AWS creds, else ollama."""
    p = _PROVIDER
    if not p:
        # auto: bedrock if creds present, else ollama
        if os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE"):
            p = "bedrock"
        else:
            p = "ollama"
    if p == "bedrock":
        from strands.models.bedrock import BedrockModel
        cfg = {"model_id": _BEDROCK_MODEL}
        cfg["max_tokens"] = int(os.environ.get("DOER_MAX_TOKENS", "128000"))  # Opus 4.7 max; override via env
        # temperature/top_p: opt-in only (Opus 4.7 rejects any non-default value)
        if os.environ.get("DOER_TEMPERATURE"): cfg["temperature"] = float(os.environ["DOER_TEMPERATURE"])
        if os.environ.get("DOER_TOP_P"): cfg["top_p"] = float(os.environ["DOER_TOP_P"])
        if os.environ.get("DOER_CACHE_PROMPT", "").lower() in ("1","true","yes"):
            try:
                from strands.types.content import CacheConfig
                cfg["cache_config"] = CacheConfig(strategy="auto")
            except Exception:
                cfg["cache_prompt"] = "default"
            cfg["cache_tools"] = "default"
        if os.environ.get("DOER_BEDROCK_GUARDRAIL_ID"):
            cfg["guardrail_id"] = os.environ["DOER_BEDROCK_GUARDRAIL_ID"]
            if os.environ.get("DOER_BEDROCK_GUARDRAIL_VERSION"):
                cfg["guardrail_version"] = os.environ["DOER_BEDROCK_GUARDRAIL_VERSION"]
        # additional_request_fields: raw JSON passthrough for Bedrock Converse (guardrails, anthropic_beta, etc.)
        _arf = {}
        if os.environ.get("DOER_ADDITIONAL_REQUEST_FIELDS"):
            import json as _json
            try: _arf = _json.loads(os.environ["DOER_ADDITIONAL_REQUEST_FIELDS"])
            except Exception: _arf = {}
        # convenience: DOER_ANTHROPIC_BETA="context-1m-2025-08-07,..." — default enables 1M context on Claude
        _default_beta = "context-1m-2025-08-07" if "claude" in _BEDROCK_MODEL.lower() or "opus" in _BEDROCK_MODEL.lower() else ""
        _betas = [b.strip() for b in os.environ.get("DOER_ANTHROPIC_BETA", _default_beta).split(",") if b.strip()]
        if _betas:
            existing = _arf.get("anthropic_beta", [])
            if isinstance(existing, str): existing = [existing]
            _arf["anthropic_beta"] = list(dict.fromkeys(existing + _betas))  # dedupe, preserve order
        if _arf:
            cfg["additional_request_fields"] = _arf
        return BedrockModel(region_name=_BEDROCK_REGION, **cfg), f"bedrock {_BEDROCK_MODEL} @ {_BEDROCK_REGION}"
    # default: ollama
    from strands.models.ollama import OllamaModel
    return OllamaModel(host=_OLLAMA_HOST, model_id=_OLLAMA_MODEL, keep_alive="5m"), f"ollama {_OLLAMA_MODEL} @ {_OLLAMA_HOST}"


def _prompt(model_desc: str) -> str:
    soul = _ctx("SOUL.md")
    agents = _ctx("AGENTS.md")
    parts = [f"env: {sys.platform} | cwd: {Path.cwd()} | model: {model_desc}"]
    if soul:   parts.append(f"# SOUL.md\n{soul}")
    if agents: parts.append(f"# AGENTS.md\n{agents}")
    parts.append(f"# recent Q/A (last {_N_DOER})\n{_doer_history(_N_DOER)}")
    parts.append(f"# recent shell (last {_N_SHELL}, bash+zsh)\n{_shell_history(_N_SHELL)}")
    parts.append(f"# source ({Path(__file__).resolve()})\n```python\n{_source()}\n```")
    return "\n\n".join(parts)


def _agent():
    m, desc = _model()
    kw = dict(
        model=m,
        tools=[shell],
        system_prompt=_prompt(desc),
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
    argv = sys.argv[1:]
    # --export [fmt] [--out PATH] [--no-system]  — dump ~/.doer_history as JSONL training dataset
    if argv and argv[0] in ("--export", "-x"):
        fmt = "sharegpt"
        out = None
        with_system = True
        i = 1
        while i < len(argv):
            a = argv[i]
            if a in ("--out", "-o") and i + 1 < len(argv): out = argv[i + 1]; i += 1
            elif a == "--no-system": with_system = False
            elif a in ("-h", "--help"):
                print("usage: doer --export [sharegpt|chatml|alpaca|openai] [--out path.jsonl] [--no-system]", file=sys.stderr)
                print("  default: sharegpt → stdout, system prompt included", file=sys.stderr)
                sys.exit(0)
            elif not a.startswith("-"): fmt = a  # positional: format
            i += 1
        n = export(fmt=fmt, out=out, with_system=with_system)
        sys.exit(0 if n else 1)
    stdin = "" if sys.stdin.isatty() else sys.stdin.read().strip()
    args = " ".join(argv).strip()
    q = "\n\n".join(x for x in [args, stdin] if x)
    if not q:
        _, desc = _model()
        print("usage: doer <query>   |   echo data | doer <query>", file=sys.stderr)
        print("       doer --export [sharegpt|chatml|alpaca|openai] [--out path] [--no-system]", file=sys.stderr)
        print(f"model:    {desc}", file=sys.stderr)
        print(f"history:  {_N_DOER} Q/A pairs from {_HIST}", file=sys.stderr)
        print(f"shell:    {_N_SHELL} cmds from ~/.bash_history + ~/.zsh_history", file=sys.stderr)
        print(f"context:  SOUL.md + AGENTS.md from cwd (if present)", file=sys.stderr)
        print(f"env:      DOER_PROVIDER (ollama|bedrock), DOER_MODEL, OLLAMA_HOST,", file=sys.stderr)
        print(f"          DOER_BEDROCK_MODEL, DOER_BEDROCK_REGION, AWS_BEARER_TOKEN_BEDROCK,", file=sys.stderr)
        print(f"          DOER_MAX_TOKENS, DOER_TEMPERATURE, DOER_TOP_P, DOER_CACHE_PROMPT,", file=sys.stderr)
        print(f"          DOER_BEDROCK_GUARDRAIL_ID, DOER_BEDROCK_GUARDRAIL_VERSION,", file=sys.stderr)
        print(f"          DOER_ANTHROPIC_BETA (comma-sep), DOER_ADDITIONAL_REQUEST_FIELDS (JSON),", file=sys.stderr)
        print(f"          DOER_HISTORY, DOER_SHELL_HISTORY", file=sys.stderr)
        sys.exit(1)
    print(str(ask(q)).strip())


if __name__ == "__main__":
    cli()
