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
_MLX_MODEL = os.environ.get("DOER_MLX_MODEL", "mlx-community/Qwen3-1.7B-4bit")
_ADAPTER = os.environ.get("DOER_ADAPTER", "")
_TRAIN_JSONL = Path.home() / ".doer_training.jsonl"

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


def _append(q: str, a, agent=None, model_desc: str = ""):
    """Append Q/A to human-readable history + dense training JSONL.

    ~/.doer_history       — flat Q/A pairs for prompt context recall (unchanged)
    ~/.doer_training.jsonl — full turn (system + messages + tools) per line, ready to train
    """
    ts = int(time.time())
    # 1. legacy human-grep history (unchanged format, used by _doer_history for prompt context)
    try:
        a_flat = str(a).replace("\n", " ")[:1000]
        with _HIST.open("a", encoding="utf-8") as f:
            f.write(f": {ts}:0;# doer_q: {q}\n")
            f.write(f": {ts}:0;# doer_a: {a_flat}\n")
        os.chmod(_HIST, 0o600)
    except Exception: pass
    # 2. dense training record: full agent.messages + system + tool specs
    if agent is None: return
    try:
        import json
        msgs = [dict(m) if isinstance(m, dict) else m for m in (agent.messages or [])]
        tools = []
        reg = getattr(agent, "tool_registry", None)
        if reg:
            for name, t in getattr(reg, "registry", {}).items():
                try:
                    spec = t.tool_spec if hasattr(t, "tool_spec") else None
                    if spec: tools.append({"name": spec.get("name", name),
                                           "description": spec.get("description", ""),
                                           "input_schema": spec.get("inputSchema", {}).get("json", {})})
                except Exception: pass
        rec = {"ts": ts, "model": model_desc, "query": q,
               "system": agent.system_prompt or "",
               "messages": msgs, "tools": tools}
        with _TRAIN_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        os.chmod(_TRAIN_JSONL, 0o600)
    except Exception as e:
        if os.environ.get("DOER_DEBUG"): sys.stderr.write(f"(train log err: {e})\n")



def train(iters: int = 200, lr: float = 1e-5, batch_size: int = 1, num_layers: int = 8,
          adapter_path: str = "", model_id: str = "", val_frac: float = 0.1):
    """In-process LoRA training on ~/.doer_training.jsonl.

    Calls mlx_lm.tuner directly — no strands-mlx trainer indirection.
    Splits JSONL into train/valid, formats each record via the target tokenizer's chat template.
    """
    import json, random, tempfile, mlx.optimizers as optim, mlx.core as mx
    from types import SimpleNamespace
    from mlx_lm import load
    from mlx_lm.tuner.trainer import TrainingArgs, train as _train
    from mlx_lm.tuner.datasets import CacheDataset, load_dataset
    from mlx_lm.tuner.utils import linear_to_lora_layers, print_trainable_parameters, build_schedule
    from mlx_lm.utils import save_config
    if not _TRAIN_JSONL.exists():
        sys.stderr.write(f"no training data at {_TRAIN_JSONL}\n"); return 1
    model_id = model_id or _MLX_MODEL
    adapter_path = Path(adapter_path or Path.home() / ".doer_adapter")
    adapter_path.mkdir(parents=True, exist_ok=True)
    sys.stderr.write(f"doer: loading {model_id}\n")
    model, tok = load(model_id, tokenizer_config={"trust_remote_code": True})
    # read dense records → format via tokenizer chat template → write train/valid .jsonl
    records = [json.loads(ln) for ln in _TRAIN_JSONL.read_text().splitlines() if ln.strip()]
    if len(records) < 2:
        sys.stderr.write(f"need >=2 records, have {len(records)}\n"); return 1
    def _to_chat(rec):
        out = [{"role": "system", "content": rec.get("system", "")}]
        for m in rec.get("messages", []):
            role = m.get("role", "user"); content = m.get("content", "")
            if isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict):
                        if "text" in c: parts.append(c["text"])
                        elif "toolUse" in c:
                            tu = c["toolUse"]
                            parts.append(f"[tool_call: {tu.get('name','?')}({json.dumps(tu.get('input',{}),ensure_ascii=False)})]")
                        elif "toolResult" in c:
                            tr = c["toolResult"]
                            txt = " ".join(x.get("text","") for x in tr.get("content",[]) if isinstance(x,dict))
                            parts.append(f"[tool_result: {txt}]")
                content = "".join(parts)
            out.append({"role": role, "content": str(content)})
        try:
            return {"text": tok.apply_chat_template(out, tokenize=False, add_generation_prompt=False)}
        except Exception:
            return {"text": "\n".join(f"{m['role']}: {m['content']}" for m in out)}
    random.seed(0); random.shuffle(records)
    n_val = max(1, int(len(records) * val_frac))
    train_recs = [_to_chat(r) for r in records[n_val:]]
    valid_recs = [_to_chat(r) for r in records[:n_val]]
    sys.stderr.write(f"doer: {len(train_recs)} train / {len(valid_recs)} valid\n")
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        (dp / "train.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in train_recs))
        (dp / "valid.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in valid_recs))
        args = SimpleNamespace(data=str(dp), hf_dataset=None, train=True, test=False,
                               prompt_feature=None, completion_feature=None, chat_feature=None,
                               text_feature="text", mask_prompt=False)
        train_set, valid_set, _ = load_dataset(args, tok)
        model.freeze()
        linear_to_lora_layers(model, num_layers, {"rank": 8, "dropout": 0.0, "scale": 20.0}, use_dora=False)
        print_trainable_parameters(model)
        save_config({"model": model_id, "iters": iters, "lr": lr, "batch_size": batch_size,
                     "num_layers": num_layers, "fine_tune_type": "lora"},
                    adapter_path / "adapter_config.json")
        targs = TrainingArgs(batch_size=batch_size, iters=iters, val_batches=max(1, n_val),
                             steps_per_report=10, steps_per_eval=max(50, iters//4),
                             steps_per_save=max(100, iters//2),
                             adapter_file=adapter_path / "adapters.safetensors",
                             max_seq_length=2048, grad_checkpoint=True, grad_accumulation_steps=1)
        opt = optim.AdamW(learning_rate=lr)
        _train(model=model, args=targs, optimizer=opt,
               train_dataset=CacheDataset(train_set), val_dataset=CacheDataset(valid_set),
               training_callback=None)
    sys.stderr.write(f"doer: trained → {adapter_path}/adapters.safetensors\n")
    sys.stderr.write(f"       use: DOER_PROVIDER=mlx DOER_ADAPTER={adapter_path} do \"...\"\n")
    return 0


def _model():
    """Build model from provider. Auto-detect: bedrock if AWS creds, else ollama."""
    p = _PROVIDER
    if not p:
        # auto: bedrock if creds present, else mlx on apple silicon if available, else ollama
        if os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE"):
            p = "bedrock"
        elif sys.platform == "darwin" and os.uname().machine == "arm64":
            try:
                __import__("strands_mlx")
                p = "mlx"
            except ImportError:
                p = "ollama"
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
    if p == "mlx":
        # optional extra: pip install doer-cli[mlx] — pulls strands-mlx + mlx-lm
        from strands_mlx import MLXModel
        adapter = _ADAPTER or None
        m = MLXModel(model_id=_MLX_MODEL, adapter_path=adapter)
        tag = f"mlx {_MLX_MODEL}" + (f" +adapter:{adapter}" if adapter else "")
        return m, tag
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
    _, desc = _model()
    a = _agent()
    r = a(q)
    _append(q, r, agent=a, model_desc=desc)
    return r


class _Callable(sys.modules[__name__].__class__):
    def __call__(self, q): return ask(q)
sys.modules[__name__].__class__ = _Callable


def cli():
    global _PIPED
    _PIPED = True
    argv = sys.argv[1:]
    # --train [iters]  — in-process LoRA on ~/.doer_training.jsonl
    if argv and argv[0] in ("--train", "-t"):
        iters = 200
        if len(argv) > 1 and argv[1].isdigit(): iters = int(argv[1])
        sys.exit(train(iters=iters))
    # --train-status  — show dataset size
    if argv and argv[0] == "--train-status":
        import json
        if not _TRAIN_JSONL.exists():
            print(f"no training data at {_TRAIN_JSONL}", file=sys.stderr); sys.exit(1)
        lines = _TRAIN_JSONL.read_text().splitlines()
        n = len([l for l in lines if l.strip()])
        sz = _TRAIN_JSONL.stat().st_size
        print(f"{n} turns | {sz/1024:.1f}KB | {_TRAIN_JSONL}", file=sys.stderr)
        sys.exit(0)
    stdin = "" if sys.stdin.isatty() else sys.stdin.read().strip()
    args = " ".join(argv).strip()
    q = "\n\n".join(x for x in [args, stdin] if x)
    if not q:
        _, desc = _model()
        print("usage: doer <query>   |   echo data | doer <query>", file=sys.stderr)
        print(f"model:    {desc}", file=sys.stderr)
        print(f"history:  {_N_DOER} Q/A pairs from {_HIST}", file=sys.stderr)
        print(f"shell:    {_N_SHELL} cmds from ~/.bash_history + ~/.zsh_history", file=sys.stderr)
        print(f"context:  SOUL.md + AGENTS.md from cwd (if present)", file=sys.stderr)
        print(f"env:      DOER_PROVIDER (ollama|bedrock), DOER_MODEL, OLLAMA_HOST,", file=sys.stderr)
        print(f"          DOER_BEDROCK_MODEL, DOER_BEDROCK_REGION, AWS_BEARER_TOKEN_BEDROCK,", file=sys.stderr)
        print(f"          DOER_MAX_TOKENS, DOER_TEMPERATURE, DOER_TOP_P, DOER_CACHE_PROMPT,", file=sys.stderr)
        print(f"          DOER_BEDROCK_GUARDRAIL_ID, DOER_BEDROCK_GUARDRAIL_VERSION,", file=sys.stderr)
        print(f"          DOER_ANTHROPIC_BETA (comma-sep), DOER_ADDITIONAL_REQUEST_FIELDS (JSON),", file=sys.stderr)
        print(f"          DOER_HISTORY, DOER_SHELL_HISTORY,", file=sys.stderr)
        print(f"          DOER_MLX_MODEL, DOER_ADAPTER  (mlx provider — Apple Silicon)", file=sys.stderr)
        print(f"train:    do --train [iters]   (LoRA on ~/.doer_training.jsonl → ~/.doer_adapter)", file=sys.stderr)
        print(f"          do --train-status    (show dataset size)", file=sys.stderr)
        sys.exit(1)
    print(str(ask(q)).strip())


if __name__ == "__main__":
    cli()
