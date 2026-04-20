#!/usr/bin/env python3
"""doer — one-file pipe-native self-aware agent.

doer("query")                         # python
doer <query>                          # shell
echo data | doer <query>              # stdin
doer --img X.png <query>              # vision
doer --train [iters]                  # text LoRA
doer --train-vlm [iters]              # vision LoRA
doer --train-status                   # stats + HF sync
doer --upload-hf [repo]               # push dataset

Layout (top → bottom, dependencies flow down):
    1. CONFIG         env knobs
    2. TOOLS          @tool shell
    3. CONTEXT        read filesystem, build prompt
    4. TRAINING LOG   write JSONL + legacy history
    5. OPENAI CONV    strands → openai for native tool tokens
    6. MODEL          provider selector
    7. AGENT          build one per call
    8. ASK            public entry + multimodal
    9. TRAIN          LoRA (text)
   10. TRAIN VLM      LoRA (vision)
   11. UPLOAD         HF dataset sync
   12. CLI            argv parsing
"""
from __future__ import annotations
import hashlib, json, mimetypes, os, re, subprocess, sys, tempfile, time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")

# ─── 1. CONFIG ──────────────────────────────────────────────────────────────
HIST      = Path.home() / ".doer_history"
TRAIN     = Path.home() / ".doer_training.jsonl"
PIPED     = not sys.stdin.isatty() or not sys.stdout.isatty()

def ENV(k, d=""): return os.environ.get(k, d)

PROVIDER       = ENV("DOER_PROVIDER").lower()             # "" auto | ollama | bedrock | mlx | mlx-vlm
OLLAMA_HOST    = ENV("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL   = ENV("DOER_MODEL", "qwen3:1.7b")
BEDROCK_MODEL  = ENV("DOER_BEDROCK_MODEL", "global.anthropic.claude-opus-4-7")
BEDROCK_REGION = ENV("DOER_BEDROCK_REGION", ENV("AWS_REGION", "us-west-2"))
MLX_MODEL      = ENV("DOER_MLX_MODEL", "cagataydev/doer")
MLX_VLM        = ENV("DOER_MLX_VLM_MODEL", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
MLX_AUDIO      = ENV("DOER_MLX_AUDIO_MODEL", "mlx-community/gemma-3n-E2B-it-4bit")
MLX_OMNI       = ENV("DOER_MLX_OMNI_MODEL", "mlx-community/Qwen3-Omni-30B-A3B-Instruct-4bit")
ADAPTER        = ENV("DOER_ADAPTER")
VLM_ADAPTER    = ENV("DOER_VLM_ADAPTER")
N_DOER         = int(ENV("DOER_HISTORY", "10"))
N_SHELL        = int(ENV("DOER_SHELL_HISTORY", "20"))
DEBUG          = bool(ENV("DOER_DEBUG"))

# per-call attachment buffer (reset after each ask)
_ATTACH: dict[str, list[str]] = {"images": [], "audio": [], "video": []}

from strands import Agent, tool
from strands.handlers.callback_handler import null_callback_handler
from strands.agent.conversation_manager import NullConversationManager


def _warn(msg: str) -> None:
    sys.stderr.write(f"(doer: {msg})\n")


# ─── 2. TOOLS ───────────────────────────────────────────────────────────────
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


# ─── 3. CONTEXT ─────────────────────────────────────────────────────────────
def _read_source() -> str:
    """Own source. Works frozen (PyInstaller) and dev."""
    try:
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            for c in (base / "doer" / "__init__.py", base / "doer.py", base / "__init__.py"):
                if c.exists(): return c.read_text()
            return f"(frozen; source not bundled at {base})"
        return Path(__file__).read_text()
    except Exception as e:
        return f"(source unavailable: {e})"


def _read_cwd(name: str) -> str:
    f = Path.cwd() / name
    if not (f.exists() and f.is_file()): return ""
    try: return f.read_text(errors="ignore").strip()
    except Exception as e: return f"(err reading {name}: {e})"


def _recent_qa(n: int) -> str:
    if not HIST.exists(): return "(empty)"
    try:
        out = []
        for ln in HIST.read_text(errors="ignore").splitlines():
            if ":0;# doer_q:" in ln:
                out.append("Q: " + ln.split(":0;# doer_q:", 1)[1].strip())
            elif ":0;# doer_a:" in ln:
                out.append("A: " + ln.split(":0;# doer_a:", 1)[1].strip())
        return "\n".join(out[-n * 2:]) or "(empty)"
    except Exception as e:
        return f"(err: {e})"


def _recent_shell(n: int) -> str:
    """Merge bash + zsh histories, sorted by timestamp (bash ts=0 → clumps early)."""
    entries: list[tuple[str, int, str]] = []
    # bash: one command per line, no timestamps
    bh = Path.home() / ".bash_history"
    if bh.exists():
        try:
            for ln in bh.read_text(errors="ignore").splitlines():
                ln = ln.strip()
                if ln: entries.append(("bash", 0, ln))
        except Exception: pass
    # zsh: ": TS:0;CMD" with \-newline continuations
    zh = Path.home() / ".zsh_history"
    if zh.exists():
        try:
            for block in zh.read_text(errors="ignore").split("\n: "):
                block = block.lstrip(": ").strip()
                if ":0;" not in block: continue
                hdr, _, cmd = block.partition(":0;")
                try: ts = int(hdr.split(":")[0])
                except ValueError: ts = 0
                cmd = cmd.replace("\\\n", " ").strip()
                if cmd: entries.append(("zsh", ts, cmd))
        except Exception: pass
    entries.sort(key=lambda e: e[1])
    return "\n".join(f"[{s}] {c}" for s, _, c in entries[-n:]) or "(empty)"


def _compact_for_vlm() -> str:
    """VLMs do best with a near-empty system prompt."""
    return ""


def _build_prompt(model_desc: str) -> str:
    """Full prompt: env + SOUL + AGENTS + Q/A history + shell + own source."""
    soul, agents = _read_cwd("SOUL.md"), _read_cwd("AGENTS.md")
    parts = [f"env: {sys.platform} | cwd: {Path.cwd()} | model: {model_desc}"]
    if any(_ATTACH.values()):
        bits = ", ".join(f"{k}={len(v)}" for k, v in _ATTACH.items() if v)
        parts.append(f"# attachments\nuser has attached: {bits} (see user message content blocks)")
    if soul:   parts.append(f"# SOUL.md\n{soul}")
    if agents: parts.append(f"# AGENTS.md\n{agents}")
    parts.append(f"# recent Q/A (last {N_DOER})\n{_recent_qa(N_DOER)}")
    parts.append(f"# recent shell (last {N_SHELL}, bash+zsh)\n{_recent_shell(N_SHELL)}")
    parts.append(f"# source ({Path(__file__).resolve()})\n```python\n{_read_source()}\n```")
    return "\n\n".join(parts)


# ─── 4. TRAINING LOG ────────────────────────────────────────────────────────
def _log_turn(q: str, a: Any, agent: Agent | None, model_desc: str,
              attachments: dict[str, list[str]] | None) -> None:
    """Append to ~/.doer_history (flat) and ~/.doer_training.jsonl (fat).

    Training log failures are LOUD (stderr), not silent. Corpus integrity matters.
    """
    ts = int(time.time())
    # 1. flat history (prompt-context recall)
    try:
        a_flat = str(a).replace("\n", " ")[:1000]
        with HIST.open("a", encoding="utf-8") as f:
            f.write(f": {ts}:0;# doer_q: {q}\n: {ts}:0;# doer_a: {a_flat}\n")
        os.chmod(HIST, 0o600)
    except Exception as e:
        _warn(f"history write failed: {e}")

    # 2. fat training record (ready for LoRA)
    if agent is None: return
    try:
        msgs = [dict(m) if isinstance(m, dict) else m for m in (agent.messages or [])]
        tools = []
        reg = getattr(agent, "tool_registry", None)
        if reg:
            for name, t in getattr(reg, "registry", {}).items():
                spec = getattr(t, "tool_spec", None)
                if not spec: continue
                tools.append({
                    "name": spec.get("name", name),
                    "description": spec.get("description", ""),
                    "input_schema": spec.get("inputSchema", {}).get("json", {}),
                })
        rec: dict[str, Any] = {"ts": ts, "model": model_desc, "query": q,
                               "system": agent.system_prompt or "",
                               "messages": msgs, "tools": tools}
        if attachments:
            for k in ("images", "audio", "video"):
                if attachments.get(k):
                    rec[k] = [str(Path(p).resolve()) for p in attachments[k]]
        with TRAIN.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        os.chmod(TRAIN, 0o600)
    except Exception as e:
        _warn(f"training log write failed: {e}")  # LOUD — dataset integrity


# ─── 5. STRANDS → OPENAI (native tool-call tokens) ──────────────────────────
def _strands_to_openai(messages: Iterable[dict]) -> list[dict]:
    """Convert Strands ContentBlock messages → OpenAI chat format.

    Keeps tool_calls structured so mlx-lm's chat template emits native
    `<tool_call>...</tool_call>` tokens (Qwen3) during training.
    """
    out: list[dict] = []
    for m in messages or []:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not isinstance(content, list):
            out.append({"role": role, "content": str(content)})
            continue
        texts, tool_uses, tool_results = [], [], []
        for c in content:
            if not isinstance(c, dict): continue
            if "text" in c:
                texts.append(c["text"])
            elif "toolUse" in c:
                tu = c["toolUse"]
                tool_uses.append({
                    "id": tu.get("toolUseId", ""),
                    "type": "function",
                    "function": {
                        "name": tu.get("name", "unknown"),
                        "arguments": json.dumps(tu.get("input", {}), ensure_ascii=False),
                    },
                })
            elif "toolResult" in c:
                tr = c["toolResult"]
                txt = "".join(rc["text"] for rc in tr.get("content", [])
                              if isinstance(rc, dict) and "text" in rc)
                tool_results.append({"role": "tool", "tool_call_id": tr.get("toolUseId", ""), "content": txt})
        if role == "assistant":
            msg: dict = {"role": "assistant", "content": "".join(texts)}
            if tool_uses: msg["tool_calls"] = tool_uses
            if msg["content"] or tool_uses: out.append(msg)
        else:
            if texts: out.append({"role": "user", "content": "".join(texts)})
            out.extend(tool_results)
    return out


# ─── 6. MODEL ───────────────────────────────────────────────────────────────
def _auto_provider() -> str:
    """Auto-detect: bedrock > mlx (on arm64) > ollama."""
    if any(ENV(k) for k in ("AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID", "AWS_PROFILE")):
        return "bedrock"
    if sys.platform == "darwin" and os.uname().machine == "arm64":
        try:
            __import__("strands_mlx"); return "mlx"
        except ImportError: pass
    return "ollama"


def _bedrock_model():
    from strands.models.bedrock import BedrockModel
    cfg: dict[str, Any] = {
        "model_id": BEDROCK_MODEL,
        "max_tokens": int(ENV("DOER_MAX_TOKENS", "128000")),
    }
    # temperature/top_p are opt-in (Opus 4.7 rejects non-defaults)
    if ENV("DOER_TEMPERATURE"): cfg["temperature"] = float(ENV("DOER_TEMPERATURE"))
    if ENV("DOER_TOP_P"): cfg["top_p"] = float(ENV("DOER_TOP_P"))
    # prompt caching
    if ENV("DOER_CACHE_PROMPT").lower() in ("1", "true", "yes"):
        try:
            from strands.types.content import CacheConfig
            cfg["cache_config"] = CacheConfig(strategy="auto")
        except Exception:
            cfg["cache_prompt"] = "default"
        cfg["cache_tools"] = "default"
    # guardrails
    if ENV("DOER_BEDROCK_GUARDRAIL_ID"):
        cfg["guardrail_id"] = ENV("DOER_BEDROCK_GUARDRAIL_ID")
        if ENV("DOER_BEDROCK_GUARDRAIL_VERSION"):
            cfg["guardrail_version"] = ENV("DOER_BEDROCK_GUARDRAIL_VERSION")
    # anthropic_beta: default 1M ctx on Claude, merge env, dedupe
    arf: dict[str, Any] = {}
    if ENV("DOER_ADDITIONAL_REQUEST_FIELDS"):
        try: arf = json.loads(ENV("DOER_ADDITIONAL_REQUEST_FIELDS"))
        except Exception: pass
    default_beta = "context-1m-2025-08-07" if re.search(r"(claude|opus)", BEDROCK_MODEL, re.I) else ""
    betas = [b.strip() for b in ENV("DOER_ANTHROPIC_BETA", default_beta).split(",") if b.strip()]
    if betas:
        existing = arf.get("anthropic_beta", [])
        if isinstance(existing, str): existing = [existing]
        arf["anthropic_beta"] = list(dict.fromkeys(existing + betas))
    if arf: cfg["additional_request_fields"] = arf
    return BedrockModel(region_name=BEDROCK_REGION, **cfg), f"bedrock {BEDROCK_MODEL} @ {BEDROCK_REGION}"


def _mlx_model():
    try: from strands_mlx import MLXModel
    except ImportError:
        _warn("mlx provider requires: pip install 'doer-cli[mlx]'"); sys.exit(1)
    adapter = os.path.expanduser(ADAPTER) if ADAPTER else None
    return (MLXModel(model_id=MLX_MODEL, adapter_path=adapter),
            f"mlx {MLX_MODEL}" + (f" +adapter:{adapter}" if adapter else ""))


def _mlx_vlm_model():
    try: from strands_mlx import MLXVisionModel
    except ImportError:
        _warn("mlx-vlm provider requires: pip install 'doer-cli[mlx]'"); sys.exit(1)
    # pick model based on modality mix (unless user explicitly set DOER_MLX_VLM_MODEL)
    has_img, has_aud, has_vid = bool(_ATTACH["images"]), bool(_ATTACH["audio"]), bool(_ATTACH["video"])
    if "DOER_MLX_VLM_MODEL" in os.environ:
        chosen = MLX_VLM
    elif has_aud and (has_img or has_vid): chosen = MLX_OMNI
    elif has_aud:                          chosen = MLX_AUDIO
    else:                                  chosen = MLX_VLM
    adapter = os.path.expanduser(VLM_ADAPTER) if VLM_ADAPTER else None
    return (MLXVisionModel(model_id=chosen, adapter_path=adapter),
            f"mlx-vlm {chosen}" + (f" +adapter:{adapter}" if adapter else ""))


def _ollama_model():
    from strands.models.ollama import OllamaModel
    return (OllamaModel(host=OLLAMA_HOST, model_id=OLLAMA_MODEL, keep_alive="5m"),
            f"ollama {OLLAMA_MODEL} @ {OLLAMA_HOST}")


def _model():
    """Build model. Attachments force mlx-vlm regardless of PROVIDER."""
    p = PROVIDER
    if any(_ATTACH.values()):
        try:
            __import__("mlx_vlm")
            if p and p != "mlx-vlm": _warn(f"attachments present — switching from {p} to mlx-vlm")
            p = "mlx-vlm"
        except ImportError:
            _warn("attachments present but mlx-vlm not installed — falling back")
    p = p or _auto_provider()
    return {
        "bedrock": _bedrock_model,
        "mlx":     _mlx_model,
        "mlx-vlm": _mlx_vlm_model,
        "ollama":  _ollama_model,
    }.get(p, _ollama_model)()


# ─── 7. AGENT ───────────────────────────────────────────────────────────────
def _agent() -> tuple[Agent, str]:
    """Fresh agent per call. Null conversation manager, no state."""
    m, desc = _model()
    use_tools = not any(_ATTACH.values())  # VLMs: no tools, compact prompt
    kwargs: dict[str, Any] = {
        "model": m,
        "tools": [shell] if use_tools else [],
        "system_prompt": _build_prompt(desc) if use_tools else _compact_for_vlm(),
        "load_tools_from_directory": True,
        "conversation_manager": NullConversationManager(),
    }
    if PIPED: kwargs["callback_handler"] = null_callback_handler
    return Agent(**kwargs), desc


def _build_multimodal_content(q: str) -> list[dict]:
    """Text + images (native blocks) + <audio>/<video> regex tags for MLXVisionModel."""
    imgs, auds, vids = [], [], []
    for lst, bucket, label in [
        (_ATTACH["images"], imgs, "image"),
        (_ATTACH["audio"],  auds, "audio"),
        (_ATTACH["video"],  vids, "video"),
    ]:
        for raw in lst:
            p = Path(raw).expanduser().resolve()
            (bucket.append(p) if p.exists() else _warn(f"missing {label}: {p}"))

    text = q + "".join(f" <audio>{p}</audio>" for p in auds) \
             + "".join(f" <video>{p}</video>" for p in vids)
    content: list[dict] = [{"text": text}]
    for p in imgs:
        try:
            mime, _ = mimetypes.guess_type(str(p))
            fmt = (mime or "image/png").split("/")[-1]
            if fmt == "jpg": fmt = "jpeg"
            content.append({"image": {"format": fmt, "source": {"bytes": p.read_bytes()}}})
        except Exception as e:
            _warn(f"image load {p}: {e}")
    return content


# ─── 8. ASK (public entry) ──────────────────────────────────────────────────
def ask(q: str, images=None, audio=None, video=None):
    """doer(q, images=[...], audio=[...], video=[...])"""
    _ATTACH["images"] = list(images or [])
    _ATTACH["audio"]  = list(audio  or [])
    _ATTACH["video"]  = list(video  or [])
    try:
        agent, desc = _agent()
        multimodal = any(_ATTACH.values())
        payload = _build_multimodal_content(q) if multimodal else q
        result = agent(payload)
        _log_turn(q, result, agent=agent, model_desc=desc,
                  attachments=dict(_ATTACH) if multimodal else None)
        return result
    finally:
        for k in _ATTACH: _ATTACH[k] = []


# module-callable: `import doer; doer("hi")`
class _Callable(sys.modules[__name__].__class__):
    def __call__(self, q, **kw): return ask(q, **kw)
sys.modules[__name__].__class__ = _Callable


# ─── 9. TRAIN (text LoRA) ───────────────────────────────────────────────────
def _record_to_chat(rec: dict) -> dict:
    """Fat doer record → mlx-lm ChatDataset {messages, tools} entry."""
    msgs = [{"role": "system", "content": rec["system"]}] if rec.get("system") else []
    msgs.extend(_strands_to_openai(rec.get("messages", [])))
    entry: dict = {"messages": msgs}
    if rec.get("tools"):
        entry["tools"] = [{
            "type": "function",
            "function": {"name": t["name"], "description": t.get("description", ""),
                         "parameters": t.get("input_schema", {})},
        } for t in rec["tools"]]
    return entry


def train(iters: int = 200, lr: float = 1e-5, batch_size: int = 1, num_layers: int = 8,
          adapter_path: str | Path = "", model_id: str = "", val_frac: float = 0.1) -> int:
    """In-process LoRA on ~/.doer_training.jsonl (text-only records)."""
    try:
        import mlx.optimizers as optim
        from mlx_lm import load
        from mlx_lm.tuner.trainer import TrainingArgs, train as _mlx_train
        from mlx_lm.tuner.datasets import CacheDataset, load_dataset
        from mlx_lm.tuner.utils import linear_to_lora_layers, print_trainable_parameters
        from mlx_lm.utils import save_config
    except ImportError as e:
        _warn(f"training requires: pip install 'doer-cli[mlx]' ({e})"); return 1
    if not TRAIN.exists():
        _warn(f"no training data at {TRAIN}"); return 1

    model_id = model_id or MLX_MODEL
    adapter_path = Path(os.path.expanduser(str(adapter_path)) if adapter_path else Path.home() / ".doer_adapter")
    adapter_path.mkdir(parents=True, exist_ok=True)

    _warn(f"loading {model_id}")
    model, tok = load(model_id, tokenizer_config={"trust_remote_code": True})

    # only text records — VLM records are skipped (use --train-vlm)
    records = []
    for ln in TRAIN.read_text().splitlines():
        if not ln.strip(): continue
        try: r = json.loads(ln)
        except json.JSONDecodeError: continue
        if r.get("messages") and not (r.get("images") or r.get("audio") or r.get("video")):
            records.append(r)
    if len(records) < 2:
        _warn(f"need ≥2 usable text records, have {len(records)}"); return 1

    import random; random.seed(0); random.shuffle(records)
    n_val = max(1, int(len(records) * val_frac))
    train_recs = [_record_to_chat(r) for r in records[n_val:]]
    valid_recs = [_record_to_chat(r) for r in records[:n_val]]
    _warn(f"{len(train_recs)} train / {len(valid_recs)} valid")

    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        for name, recs in (("train", train_recs), ("valid", valid_recs)):
            (dp / f"{name}.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in recs))
        from types import SimpleNamespace
        args = SimpleNamespace(
            data=str(dp), hf_dataset=None, train=True, test=False,
            prompt_feature=None, completion_feature=None,
            chat_feature="messages", text_feature=None, mask_prompt=False,
        )
        train_set, valid_set, _ = load_dataset(args, tok)
        model.freeze()
        lora_params = {"rank": 8, "dropout": 0.0, "scale": 20.0, "keys": None}
        linear_to_lora_layers(model, num_layers, lora_params, use_dora=False)
        print_trainable_parameters(model)
        save_config({
            "model": model_id, "iters": iters, "lr": lr, "batch_size": batch_size,
            "num_layers": num_layers, "fine_tune_type": "lora", "lora_parameters": lora_params,
        }, adapter_path / "adapter_config.json")
        targs = TrainingArgs(
            batch_size=batch_size, iters=iters, val_batches=max(1, n_val),
            steps_per_report=10, steps_per_eval=max(50, iters // 4),
            steps_per_save=max(100, iters // 2),
            adapter_file=adapter_path / "adapters.safetensors",
            max_seq_length=int(ENV("DOER_MAX_SEQ_LEN", "32768")), grad_checkpoint=True, grad_accumulation_steps=1,
        )
        _mlx_train(model=model, args=targs, optimizer=optim.AdamW(learning_rate=lr),
                   train_dataset=CacheDataset(train_set), val_dataset=CacheDataset(valid_set),
                   training_callback=None)
    _warn(f"trained → {adapter_path}/adapters.safetensors")
    _warn(f"use: DOER_PROVIDER=mlx DOER_ADAPTER={adapter_path} doer \"...\"")
    return 0


# ─── 10. TRAIN VLM (delegates to strands-mlx) ───────────────────────────────
def train_vlm(iters: int = 300, lr: float = 1e-5, adapter_path: str = "",
              model_id: str = "", lora_rank: int = 8) -> int:
    """VLM LoRA on multi-modal records. Delegates to strands-mlx vision trainer."""
    try:
        from strands_mlx.tools.mlx_vision_trainer import mlx_vision_trainer
        try:
            from datasets import Dataset
        except ImportError:
            sys.exit("vlm training requires: pip install 'doer-cli[vlm]'")
    except ImportError as e:
        _warn(f"vlm training requires: pip install 'doer-cli[mlx]' datasets ({e})"); return 1
    if not TRAIN.exists():
        _warn(f"no training data at {TRAIN}"); return 1

    model_id = model_id or MLX_VLM
    adapter_path = str(Path(os.path.expanduser(adapter_path) if adapter_path
                            else Path.home() / ".doer_vlm_adapter"))

    records = []
    for ln in TRAIN.read_text().splitlines():
        if not ln.strip(): continue
        try: r = json.loads(ln)
        except json.JSONDecodeError: continue
        if r.get("messages") and r.get("images") and all(Path(p).exists() for p in r["images"]):
            records.append(r)
    if len(records) < 2:
        _warn(f"need ≥2 multi-modal records, have {len(records)}")
        _warn("collect via: doer --img X.png describe-this"); return 1

    _warn(f"{len(records)} multi-modal records")
    rows = []
    for r in records:
        msgs = _strands_to_openai(r.get("messages", []))
        if r.get("system"): msgs = [{"role": "system", "content": r["system"]}] + msgs
        rows.append({"messages": msgs, "images": r["images"]})

    with tempfile.TemporaryDirectory() as d:
        ds_path = Path(d) / "doer_vlm_dataset"
        Dataset.from_list(rows).save_to_disk(str(ds_path))
        _warn("delegating to strands-mlx vision trainer")
        result = mlx_vision_trainer(
            action="train", model=model_id, dataset=str(ds_path),
            adapter_path=adapter_path, learning_rate=lr, lora_rank=lora_rank,
            max_steps=iters, batch_size=1, apply_chat_template=True,
        )
    ok = result.get("status") == "success"
    for c in result.get("content", []):
        sys.stderr.write(("" if ok else "ERR: ") + c.get("text", "") + "\n")
    if ok:
        _warn(f"use: DOER_PROVIDER=mlx-vlm DOER_VLM_ADAPTER={adapter_path} doer --img X.png '...'")
    return 0 if ok else 1


# ─── 11. UPLOAD (HuggingFace dataset) ───────────────────────────────────────
def upload_hf(repo: str = "", private: bool = True) -> int:
    """Upload ~/.doer_training.jsonl to a HF dataset (private by default)."""
    try:
        from huggingface_hub import HfApi, whoami, CommitOperationAdd
    except ImportError as e:
        _warn(f"upload requires: pip install 'doer-cli[hf]' ({e})"); return 1
    if not TRAIN.exists() or TRAIN.stat().st_size == 0:
        _warn(f"no training data at {TRAIN}"); return 1

    lines = [l for l in TRAIN.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
    n, sz_kb = len(lines), TRAIN.stat().st_size / 1024
    digest = hashlib.sha256(TRAIN.read_bytes()).hexdigest()

    token = ENV("HF_TOKEN") or None
    api = HfApi(token=token)
    user = whoami(token=token).get("name")
    repo_id = repo or ENV("DOER_HF_REPO") or f"{user}/doer-training"
    _warn(f"{n} turns | {sz_kb:.1f}KB → {repo_id} ({'private' if private else 'public'})")

    api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)
    readme = (
        f"---\nlicense: apache-2.0\npretty_name: doer training turns\n"
        f"tags:\n- agent\n- tool-use\n- strands-agents\n- doer\n---\n\n"
        f"# doer training data\n\n"
        f"One JSON record per `doer \"...\"` call. "
        f"Schema: `ts, model, query, system, messages, tools` "
        f"(+ optional `images, audio, video`).\n\n"
        f"## stats\n\n- records: {n}\n- size: {sz_kb:.1f} KB\n- sha256: `{digest}`\n"
        f"- last upload: {datetime.utcnow().isoformat()}Z\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(readme); readme_path = f.name
    try:
        api.create_commit(
            repo_id=repo_id, repo_type="dataset",
            operations=[
                CommitOperationAdd("data/train.jsonl", str(TRAIN)),
                CommitOperationAdd("README.md", readme_path),
            ],
            commit_message=f"upload {n} turns ({sz_kb:.1f}KB, sha256:{digest[:8]})",
        )
    finally:
        Path(readme_path).unlink(missing_ok=True)
    _warn(f"done: https://huggingface.co/datasets/{repo_id}")
    return 0


def _train_status() -> int:
    """Dataset stats + HF sync check."""
    if not TRAIN.exists():
        _warn(f"no training data at {TRAIN}"); return 1
    lines = [l for l in TRAIN.read_text().splitlines() if l.strip()]
    n_text = n_img = n_aud = n_vid = 0
    for l in lines:
        try: r = json.loads(l)
        except json.JSONDecodeError: continue
        if   r.get("images"): n_img += 1
        elif r.get("audio"):  n_aud += 1
        elif r.get("video"):  n_vid += 1
        else:                 n_text += 1
    sz = TRAIN.stat().st_size
    sha = hashlib.sha256(TRAIN.read_bytes()).hexdigest()
    print(f"{len(lines)} turns | {sz/1024:.1f}KB | sha256:{sha[:8]} | {TRAIN}", file=sys.stderr)
    print(f"  text:{n_text}  image:{n_img}  audio:{n_aud}  video:{n_vid}", file=sys.stderr)

    # HF sync check (best-effort, skipped if hub lib absent)
    try:
        from huggingface_hub import HfApi, whoami
        api = HfApi()
        repo_id = ENV("DOER_HF_REPO") or f"{whoami().get('name')}/doer-training"
        commits = api.list_repo_commits(repo_id, repo_type="dataset")
        if commits:
            msg = getattr(commits[0], "title", "") or ""
            m = re.search(r"sha256:([0-9a-f]{8})", msg)
            remote = m.group(1) if m else "?"
            marker = "in sync" if remote == sha[:8] else "out of sync — run: doer --upload-hf"
            print(f"  hf:    {repo_id} | {msg} | {marker}", file=sys.stderr)
    except ImportError:
        pass
    except Exception as e:
        print(f"  hf:    (remote check skipped: {str(e)[:60]})", file=sys.stderr)
    return 0


# ─── 12. CLI ────────────────────────────────────────────────────────────────
def _parse_argv(argv: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Pull --img/--audio/--video pairs out; return (rest, imgs, auds, vids)."""
    imgs: list[str] = []; auds: list[str] = []; vids: list[str] = []; rest: list[str] = []
    flag_map = {"--img": imgs, "--image": imgs, "--audio": auds, "--video": vids}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in flag_map and i + 1 < len(argv):
            flag_map[a].append(argv[i + 1]); i += 2
        else:
            rest.append(a); i += 1
    return rest, imgs, auds, vids


def _print_usage() -> None:
    _, desc = _model()
    lines = [
        "usage: doer <query>                          # text",
        "       echo data | doer <query>              # piped stdin",
        "       doer --img X.png <query>              # vision (auto → mlx-vlm)",
        "       doer --audio X.wav <query>            # audio",
        "       doer --video X.mp4 <query>            # video frames",
        "       doer --img a.png --audio b.wav <q>    # omni (auto-picks omni model)",
        "",
        f"model:    {desc}",
        f"history:  {N_DOER} Q/A pairs from {HIST}",
        f"shell:    {N_SHELL} cmds from ~/.bash_history + ~/.zsh_history",
        f"context:  SOUL.md + AGENTS.md from cwd (if present)",
        "env:      DOER_PROVIDER (ollama|bedrock|mlx|mlx-vlm), DOER_MODEL, OLLAMA_HOST,",
        "          DOER_BEDROCK_MODEL, DOER_BEDROCK_REGION, AWS_BEARER_TOKEN_BEDROCK,",
        "          DOER_MAX_TOKENS, DOER_TEMPERATURE, DOER_TOP_P, DOER_CACHE_PROMPT,",
        "          DOER_BEDROCK_GUARDRAIL_ID, DOER_BEDROCK_GUARDRAIL_VERSION,",
        "          DOER_ANTHROPIC_BETA (csv), DOER_ADDITIONAL_REQUEST_FIELDS (JSON),",
        "          DOER_HISTORY, DOER_SHELL_HISTORY, DOER_DEBUG,",
        "          DOER_MLX_MODEL, DOER_ADAPTER,",
        "          DOER_MLX_VLM_MODEL, DOER_MLX_AUDIO_MODEL, DOER_MLX_OMNI_MODEL, DOER_VLM_ADAPTER",
        "train:    doer --train [iters]            (text LoRA → ~/.doer_adapter)",
        "          doer --train-vlm [iters]        (VLM LoRA → ~/.doer_vlm_adapter)",
        "          doer --train-status             (stats + text/image/audio/video + HF sync)",
        "upload:   doer --upload-hf [repo]           (private HF dataset)",
        "          doer --upload-hf-public [repo]   (public HF dataset)",
        "hf-jobs:  doer --hf-jobs                  (print bundled hf_jobs/ path)",
        "          doer --hf-jobs text            (cloud text LoRA via HF Jobs)",
        "          doer --hf-jobs vlm             (cloud VLM LoRA via HF Jobs)",
        "          doer --hf-jobs omni            (cloud omni LoRA via HF Jobs)",
    ]
    for l in lines: print(l, file=sys.stderr)



def _hf_jobs_path() -> str:
    """Return absolute path to the bundled hf_jobs directory."""
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hf_jobs')


def _hf_jobs(argv: list) -> int:
    """Dispatch to bundled hf_jobs/launch.sh. With no args, print the path."""
    import os, subprocess
    d = _hf_jobs_path()
    launcher = os.path.join(d, 'launch.sh')
    if not argv:
        print(d)
        return 0
    if not os.path.exists(launcher):
        print(f'doer: launcher not found at {launcher}', file=sys.stderr)
        return 1
    os.chmod(launcher, 0o755)
    return subprocess.call([launcher] + argv)


def cli() -> None:
    global PIPED
    PIPED = True
    argv = sys.argv[1:]

    # fast-path subcommands (consume from argv[0])
    if argv:
        head = argv[0]
        if head == "--train":
            iters = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 200
            sys.exit(train(iters=iters))
        if head == "--train-vlm":
            iters = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 300
            sys.exit(train_vlm(iters=iters))
        if head in ("--upload-hf", "--upload-hf-public"):
            repo = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else ""
            sys.exit(upload_hf(repo=repo, private=(head == "--upload-hf")))
        if head == "--train-status":
            sys.exit(_train_status())
        if head == "--hf-jobs":
            sys.exit(_hf_jobs(argv[1:]))

    # main query path
    rest, imgs, auds, vids = _parse_argv(argv)
    stdin = "" if sys.stdin.isatty() else sys.stdin.read().strip()
    args_text = " ".join(rest).strip()
    q = "\n\n".join(x for x in [args_text, stdin] if x)

    if not q and not (imgs or auds or vids):
        _print_usage(); sys.exit(1)
    if not q:  # attachments without text
        q = "describe / analyze the attached media"

    print(str(ask(q, images=imgs, audio=auds, video=vids)).strip())


if __name__ == "__main__":
    cli()
