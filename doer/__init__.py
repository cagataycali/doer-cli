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
# MLX VLM models per capability. User can override via DOER_MLX_VLM_MODEL.
# Defaults chosen for speed on M1/M2 — upgrade to Qwen3-Omni-30B-A3B-4bit for audio+video.
_MLX_VLM_MODEL = os.environ.get("DOER_MLX_VLM_MODEL", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
_MLX_AUDIO_MODEL = os.environ.get("DOER_MLX_AUDIO_MODEL", "mlx-community/gemma-3n-E2B-it-4bit")  # 2B, vision+audio+video
_MLX_OMNI_MODEL = os.environ.get("DOER_MLX_OMNI_MODEL", "mlx-community/Qwen3-Omni-30B-A3B-Instruct-4bit")
_VLM_ADAPTER = os.environ.get("DOER_VLM_ADAPTER", "")
_ATTACH = {"images": [], "audio": [], "video": []}  # per-call multimodal attachments


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


def _append(q: str, a, agent=None, model_desc: str = "", attachments=None):
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
        if attachments:
            for _k in ("images", "audio", "video"):
                _v = attachments.get(_k) or []
                if _v: rec[_k] = [str(Path(_p).resolve()) for _p in _v]
        with _TRAIN_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        os.chmod(_TRAIN_JSONL, 0o600)
    except Exception as e:
        if os.environ.get("DOER_DEBUG"): sys.stderr.write(f"(train log err: {e})\n")



def _strands_to_openai(messages):
    """Convert Strands ContentBlock messages to OpenAI chat format.

    Preserves tool_calls as structured data so the tokenizer's chat template
    emits native tool-call tokens (<tool_call>...</tool_call> on Qwen3, etc.)
    instead of training the model to output literal '[tool_call: ...]' strings.
    """
    import json as _json
    out = []
    for m in messages or []:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not isinstance(content, list):
            out.append({"role": role, "content": str(content)})
            continue
        # parallel accumulators: text, tool_uses (assistant), tool_results (as separate tool msgs)
        text_parts, tool_uses, tool_results = [], [], []
        for c in content:
            if not isinstance(c, dict): continue
            if "text" in c:
                text_parts.append(c["text"])
            elif "toolUse" in c:
                tu = c["toolUse"]
                tool_uses.append({
                    "id": tu.get("toolUseId", ""),
                    "type": "function",
                    "function": {
                        "name": tu.get("name", "unknown"),
                        "arguments": _json.dumps(tu.get("input", {}), ensure_ascii=False),
                    },
                })
            elif "toolResult" in c:
                tr = c["toolResult"]
                txt_parts = []
                for rc in tr.get("content", []):
                    if isinstance(rc, dict) and "text" in rc:
                        txt_parts.append(rc["text"])
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tr.get("toolUseId", ""),
                    "content": "".join(txt_parts),
                })
        if role == "assistant":
            msg = {"role": "assistant", "content": "".join(text_parts)}
            if tool_uses: msg["tool_calls"] = tool_uses
            if msg["content"] or tool_uses:
                out.append(msg)
        else:  # user role: text + tool_results become separate messages (OpenAI pattern)
            if text_parts:
                out.append({"role": "user", "content": "".join(text_parts)})
            out.extend(tool_results)  # tool messages go AFTER the assistant with tool_calls
    return out


def train(iters: int = 200, lr: float = 1e-5, batch_size: int = 1, num_layers: int = 8,
          adapter_path: str = "", model_id: str = "", val_frac: float = 0.1):
    """In-process LoRA training on ~/.doer_training.jsonl.

    Calls mlx_lm.tuner directly — no strands-mlx trainer indirection.
    Emits OpenAI-format {messages, tools} records; mlx-lm's ChatDataset handles
    tokenizer chat-template application, preserving native tool-call tokens.
    """
    import json, random, tempfile
    from types import SimpleNamespace
    try:
        import mlx.optimizers as optim
        from mlx_lm import load
        from mlx_lm.tuner.trainer import TrainingArgs, train as _train
        from mlx_lm.tuner.datasets import CacheDataset, load_dataset
        from mlx_lm.tuner.utils import linear_to_lora_layers, print_trainable_parameters
        from mlx_lm.utils import save_config
    except ImportError as e:
        sys.stderr.write(f"training requires mlx-lm: pip install 'doer-cli[mlx]'\n  ({e})\n"); return 1
    if not _TRAIN_JSONL.exists():
        sys.stderr.write(f"no training data at {_TRAIN_JSONL}\n"); return 1
    model_id = model_id or _MLX_MODEL
    adapter_path = Path(os.path.expanduser(adapter_path) if adapter_path else Path.home() / ".doer_adapter")
    adapter_path.mkdir(parents=True, exist_ok=True)
    sys.stderr.write(f"doer: loading {model_id}\n")
    model, tok = load(model_id, tokenizer_config={"trust_remote_code": True})
    records = []
    for ln in _TRAIN_JSONL.read_text().splitlines():
        if not ln.strip(): continue
        r = json.loads(ln)
        # skip empty + multi-modal (use --train-vlm for those)
        if r.get("messages") and not (r.get("images") or r.get("audio") or r.get("video")):
            records.append(r)
    if len(records) < 2:
        sys.stderr.write(f"need >=2 usable records, have {len(records)}\n"); return 1
    def _rec_to_chat(rec):
        """Dense strands record → mlx-lm ChatDataset {messages, tools} entry."""
        msgs = [{"role": "system", "content": rec.get("system", "")}] if rec.get("system") else []
        msgs.extend(_strands_to_openai(rec.get("messages", [])))
        tools = rec.get("tools", []) or None
        entry = {"messages": msgs}
        if tools:
            # convert doer tool spec {name, description, input_schema} → OpenAI function spec
            entry["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t.get("description", ""),
                "parameters": t.get("input_schema", {})
            }} for t in tools]
        return entry
    random.seed(0); random.shuffle(records)
    n_val = max(1, int(len(records) * val_frac))
    train_recs = [_rec_to_chat(r) for r in records[n_val:]]
    valid_recs = [_rec_to_chat(r) for r in records[:n_val]]
    sys.stderr.write(f"doer: {len(train_recs)} train / {len(valid_recs)} valid\n")
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        for name, recs in (("train", train_recs), ("valid", valid_recs)):
            (dp / f"{name}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs))
        args = SimpleNamespace(data=str(dp), hf_dataset=None, train=True, test=False,
                               prompt_feature=None, completion_feature=None,
                               chat_feature="messages", text_feature=None, mask_prompt=False)
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


def train_vlm(iters=300, lr=1e-5, adapter_path="", model_id="", lora_rank=8):
    """VLM LoRA on multi-modal records. Delegates to strands-mlx vision trainer tool."""
    import json, tempfile
    try:
        from strands_mlx.tools.mlx_vision_trainer import mlx_vision_trainer
        from datasets import Dataset
    except ImportError as e:
        sys.stderr.write("vlm training requires: pip install 'doer-cli[mlx]' datasets (" + str(e) + ")" + chr(10))
        return 1
    if not _TRAIN_JSONL.exists():
        sys.stderr.write("no training data at " + str(_TRAIN_JSONL) + chr(10)); return 1
    model_id = model_id or _MLX_VLM_MODEL
    adapter_path = str(Path(os.path.expanduser(adapter_path) if adapter_path else Path.home() / ".doer_vlm_adapter"))
    records = []
    for ln in _TRAIN_JSONL.read_text().splitlines():
        if not ln.strip(): continue
        r = json.loads(ln)
        if r.get("messages") and r.get("images"):
            if all(Path(p).exists() for p in r["images"]):
                records.append(r)
    if len(records) < 2:
        sys.stderr.write("need >=2 multi-modal records with images, have " + str(len(records)) + chr(10))
        sys.stderr.write("  (collect via: do --img screenshot.png describe-this)" + chr(10))
        return 1
    sys.stderr.write("doer-vlm: " + str(len(records)) + " multi-modal records" + chr(10))
    rows = []
    for r in records:
        msgs = _strands_to_openai(r.get("messages", []))
        if r.get("system"):
            msgs = [{"role":"system", "content": r["system"]}] + msgs
        rows.append({"messages": msgs, "images": r["images"]})
    ds = Dataset.from_list(rows)
    with tempfile.TemporaryDirectory() as d:
        ds_path = Path(d) / "doer_vlm_dataset"
        ds.save_to_disk(str(ds_path))
        sys.stderr.write("doer-vlm: delegating to strands-mlx vision trainer" + chr(10))
        result = mlx_vision_trainer(
            action="train", model=model_id, dataset=str(ds_path),
            adapter_path=adapter_path, learning_rate=lr, lora_rank=lora_rank,
            max_steps=iters, batch_size=1, apply_chat_template=True,
        )
        if result.get("status") == "success":
            for c in result.get("content", []):
                sys.stderr.write(c.get("text", "") + chr(10))
            sys.stderr.write("doer-vlm: DOER_PROVIDER=mlx-vlm DOER_VLM_ADAPTER=" + adapter_path + " do --img X.png '...'" + chr(10))
            return 0
        for c in result.get("content", []):
            sys.stderr.write("ERR: " + c.get("text", "") + chr(10))
        return 1


def _model():
    """Build model from provider. Auto-detect: mlx-vlm if attachments, else bedrock/mlx/ollama."""
    p = _PROVIDER
    has_attach = bool(_ATTACH["images"] or _ATTACH["audio"] or _ATTACH["video"])
    # attachments force mlx-vlm (even if user set other provider)
    if has_attach:
        try:
            __import__("mlx_vlm")
            if p and p not in ("mlx-vlm",):
                sys.stderr.write("(doer: attachments present - switching from " + p + " to mlx-vlm)" + chr(10))
            p = "mlx-vlm"
        except ImportError:
            sys.stderr.write("(doer: attachments present but mlx-vlm not installed - falling back)" + chr(10))
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
        try:
            from strands_mlx import MLXModel
        except ImportError:
            sys.stderr.write("mlx provider requires: pip install 'doer-cli[mlx]'\n"); sys.exit(1)
        adapter = os.path.expanduser(_ADAPTER) if _ADAPTER else None
        m = MLXModel(model_id=_MLX_MODEL, adapter_path=adapter)
        tag = f"mlx {_MLX_MODEL}" + (f" +adapter:{adapter}" if adapter else "")
        return m, tag
    if p == "mlx-vlm":
        try:
            from strands_mlx import MLXVisionModel
        except ImportError:
            sys.stderr.write("mlx-vlm provider requires: pip install 'doer-cli[mlx]'" + chr(10)); sys.exit(1)
        adapter = os.path.expanduser(_VLM_ADAPTER) if _VLM_ADAPTER else None
        # pick best model for the attachment mix (unless user forced DOER_MLX_VLM_MODEL)
        has_img = bool(_ATTACH["images"])
        has_aud = bool(_ATTACH["audio"])
        has_vid = bool(_ATTACH["video"])
        if "DOER_MLX_VLM_MODEL" in os.environ:
            chosen = _MLX_VLM_MODEL
        elif has_aud and (has_img or has_vid):
            chosen = _MLX_OMNI_MODEL  # needs full omni
        elif has_aud:
            chosen = _MLX_AUDIO_MODEL
        else:
            chosen = _MLX_VLM_MODEL  # image and/or video
        m = MLXVisionModel(model_id=chosen, adapter_path=adapter)
        tag = "mlx-vlm " + chosen + ((" +adapter:" + adapter) if adapter else "")
        return m, tag
        # default: ollama
    from strands.models.ollama import OllamaModel
    return OllamaModel(host=_OLLAMA_HOST, model_id=_OLLAMA_MODEL, keep_alive="5m"), f"ollama {_OLLAMA_MODEL} @ {_OLLAMA_HOST}"


def _compact_prompt_for_vlm(full_prompt):
    """VLMs perform best with no system prompt. Return empty string."""
    return ""


def _prompt(model_desc: str) -> str:
    soul = _ctx("SOUL.md")
    agents = _ctx("AGENTS.md")
    parts = [f"env: {sys.platform} | cwd: {Path.cwd()} | model: {model_desc}"]
    if any(_ATTACH.values()):
        _bits = [k + "=" + str(len(v)) for k, v in _ATTACH.items() if v]
        parts.append("# attachments\nuser has attached: " + ", ".join(_bits) + " (see user message content blocks)")
    if soul:   parts.append(f"# SOUL.md\n{soul}")
    if agents: parts.append(f"# AGENTS.md\n{agents}")
    parts.append(f"# recent Q/A (last {_N_DOER})\n{_doer_history(_N_DOER)}")
    parts.append(f"# recent shell (last {_N_SHELL}, bash+zsh)\n{_shell_history(_N_SHELL)}")
    parts.append(f"# source ({Path(__file__).resolve()})\n```python\n{_source()}\n```")
    return "\n\n".join(parts)


def _agent():
    """Build a fresh agent. Returns (agent, model_desc) to avoid double _model() cost."""
    m, desc = _model()
    sp = _prompt(desc)
    # VLM calls: compact prompt + drop shell tool (VLMs have limited tool support + small windows)
    use_tools = not any(_ATTACH.values())
    if not use_tools:
        sp = _compact_prompt_for_vlm(sp)
    kw = dict(
        model=m,
        tools=[shell] if use_tools else [],
        system_prompt=sp,
        load_tools_from_directory=True,
        conversation_manager=NullConversationManager(),
    )
    if _PIPED: kw["callback_handler"] = null_callback_handler
    return Agent(**kw), desc


def _build_content(q):
    """Build Strands ContentBlock list for MLXVisionModel.

    Images: native Strands image content block (works everywhere)
    Audio/video: <audio>PATH</audio> / <video>PATH</video> tags embedded in text,
                 which MLXVisionModel._extract_media_from_messages() parses via regex.
    Text query stays first so prompt context comes before media.
    """
    import mimetypes
    # gather valid paths first
    valid_imgs, valid_aud, valid_vid = [], [], []
    for img_path in _ATTACH["images"]:
        p = Path(img_path).expanduser().resolve()
        if p.exists():
            valid_imgs.append(p)
        else:
            sys.stderr.write("(doer: missing image: " + str(p) + ")" + chr(10))
    for ap in _ATTACH["audio"]:
        p = Path(ap).expanduser().resolve()
        if p.exists():
            valid_aud.append(p)
        else:
            sys.stderr.write("(doer: missing audio: " + str(p) + ")" + chr(10))
    for vp in _ATTACH["video"]:
        p = Path(vp).expanduser().resolve()
        if p.exists():
            valid_vid.append(p)
        else:
            sys.stderr.write("(doer: missing video: " + str(p) + ")" + chr(10))

    # build text: query + <audio>/<video> tags for MLXVisionModel regex parser
    text = q
    for ap in valid_aud:
        text += " <audio>" + str(ap) + "</audio>"
    for vp in valid_vid:
        text += " <video>" + str(vp) + "</video>"

    content = [{"text": text}]

    # images as native content blocks (bytes + format)
    for p in valid_imgs:
        try:
            mime, _ = mimetypes.guess_type(str(p))
            fmt = (mime or "image/png").split("/")[-1]
            if fmt == "jpg": fmt = "jpeg"  # normalize
            content.append({"image": {"format": fmt, "source": {"bytes": p.read_bytes()}}})
        except Exception as e:
            sys.stderr.write("(doer: image load err " + str(p) + ": " + str(e) + ")" + chr(10))
    return content


def ask(q, images=None, audio=None, video=None):
    """doer('query', images=[...], audio=[...], video=[...])"""
    _ATTACH["images"] = list(images or [])
    _ATTACH["audio"] = list(audio or [])
    _ATTACH["video"] = list(video or [])
    try:
        a, desc = _agent()
        content = _build_content(q)
        # any attachment → send content list (image block AND/OR audio/video tags in text)
        if any(_ATTACH.values()):
            r = a(content)  # Strands accepts list[ContentBlock] directly
        else:
            r = a(q)
        _append(q, r, agent=a, model_desc=desc,
                attachments=dict(_ATTACH) if any(_ATTACH.values()) else None)
        return r
    finally:
        _ATTACH["images"] = []; _ATTACH["audio"] = []; _ATTACH["video"] = []


class _Callable(sys.modules[__name__].__class__):
    def __call__(self, q, **kw): return ask(q, **kw)
sys.modules[__name__].__class__ = _Callable


def upload_hf(repo: str = "", private: bool = True):
    """Upload ~/.doer_training.jsonl to a HuggingFace dataset (private by default)."""
    try:
        from huggingface_hub import HfApi, whoami, CommitOperationAdd
    except ImportError as e:
        sys.stderr.write("upload requires huggingface_hub: pip install 'doer-cli[hf]'\n  (" + str(e) + ")\n"); return 1
    if not _TRAIN_JSONL.exists() or _TRAIN_JSONL.stat().st_size == 0:
        sys.stderr.write("no training data at " + str(_TRAIN_JSONL) + "\n"); return 1
    import hashlib, tempfile
    from datetime import datetime

    lines = [l for l in _TRAIN_JSONL.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
    n = len(lines); sz_kb = _TRAIN_JSONL.stat().st_size / 1024
    digest = hashlib.sha256(_TRAIN_JSONL.read_bytes()).hexdigest()

    token = os.environ.get("HF_TOKEN") or None
    api = HfApi(token=token)
    user = whoami(token=token).get("name")
    repo_id = repo or os.environ.get("DOER_HF_REPO") or (user + "/doer-training")
    sys.stderr.write(str(n) + " turns | " + str(round(sz_kb,1)) + "KB -> " + repo_id + " (" + ("private" if private else "public") + ")\n")

    api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)
    readme = ("---\nlicense: apache-2.0\npretty_name: doer training turns\ntags:\n- agent\n- tool-use\n- strands-agents\n- doer\n---\n\n# doer training data\n\n"
              "One JSON record per `do \"...\"` call. Schema: `ts, model, query, system, messages, tools` (+ optional `images, audio, video`).\n\n"
              "## stats\n\n- records: " + str(n) + "\n- size: " + str(round(sz_kb,1)) + " KB\n- sha256: `" + digest + "`\n- last upload: " + datetime.utcnow().isoformat() + "Z\n")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(readme); readme_path = f.name
    try:
        api.create_commit(
            repo_id=repo_id, repo_type="dataset",
            operations=[
                CommitOperationAdd(path_in_repo="data/train.jsonl", path_or_fileobj=str(_TRAIN_JSONL)),
                CommitOperationAdd(path_in_repo="README.md",        path_or_fileobj=readme_path),
            ],
            commit_message="upload " + str(n) + " turns (" + str(round(sz_kb,1)) + "KB, sha256:" + digest[:8] + ")",
        )
    finally:
        Path(readme_path).unlink(missing_ok=True)
    sys.stderr.write("done: https://huggingface.co/datasets/" + repo_id + "\n")
    return 0


def cli():
    global _PIPED
    _PIPED = True
    argv = sys.argv[1:]
    # --train [iters]  — in-process LoRA on ~/.doer_training.jsonl
    if argv and argv[0] == "--train":
        iters = 200
        if len(argv) > 1 and argv[1].isdigit(): iters = int(argv[1])
        sys.exit(train(iters=iters))
    if argv and argv[0] == "--train-vlm":
        iters = 300
        if len(argv) > 1 and argv[1].isdigit(): iters = int(argv[1])
        sys.exit(train_vlm(iters=iters))
    # --upload-hf [repo]  — upload ~/.doer_training.jsonl to HuggingFace (private dataset)
    if argv and argv[0] in ("--upload-hf", "--upload-hf-public"):
        repo = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else ""
        sys.exit(upload_hf(repo=repo, private=(argv[0] == "--upload-hf")))
    # --train-status  — show dataset size
    if argv and argv[0] == "--train-status":
        import json
        if not _TRAIN_JSONL.exists():
            print("no training data at " + str(_TRAIN_JSONL), file=sys.stderr); sys.exit(1)
        lines = [l for l in _TRAIN_JSONL.read_text().splitlines() if l.strip()]
        n = len(lines); n_text = 0; n_img = 0; n_aud = 0; n_vid = 0
        for l in lines:
            try: r = json.loads(l)
            except: continue
            if r.get("images"): n_img += 1
            elif r.get("audio"): n_aud += 1
            elif r.get("video"): n_vid += 1
            else: n_text += 1
        sz = _TRAIN_JSONL.stat().st_size
        import hashlib
        local_sha = hashlib.sha256(_TRAIN_JSONL.read_bytes()).hexdigest()
        print(str(n) + " turns | " + str(round(sz/1024,1)) + "KB | sha256:" + local_sha[:8] + " | " + str(_TRAIN_JSONL), file=sys.stderr)
        print("  text:" + str(n_text) + "  image:" + str(n_img) + "  audio:" + str(n_aud) + "  video:" + str(n_vid), file=sys.stderr)
        # optional: check HF remote state (only if huggingface_hub installed, quick best-effort)
        try:
            from huggingface_hub import HfApi, whoami
            api = HfApi()
            repo_id = os.environ.get("DOER_HF_REPO") or (whoami().get("name") + "/doer-training")
            commits = api.list_repo_commits(repo_id, repo_type="dataset")
            if commits:
                latest = commits[0]
                msg = latest.title if hasattr(latest, "title") else ""
                import re
                m = re.search(r"sha256:([0-9a-f]{8})", msg)
                remote_sha = m.group(1) if m else "?"
                in_sync = (remote_sha == local_sha[:8])
                marker = "in sync" if in_sync else "out of sync — run: doer --upload-hf"
                print("  hf:    " + repo_id + " | " + msg + " | " + marker, file=sys.stderr)
        except ImportError:
            pass
        except Exception as e:
            print("  hf:    (remote check skipped: " + str(e)[:60] + ")", file=sys.stderr)
        sys.exit(0)
    imgs, auds, vids = [], [], []
    rest = []
    _i = 0
    while _i < len(argv):
        _a = argv[_i]
        if _a in ("--img", "--image") and _i + 1 < len(argv):
            imgs.append(argv[_i+1]); _i += 2
        elif _a == "--audio" and _i + 1 < len(argv):
            auds.append(argv[_i+1]); _i += 2
        elif _a == "--video" and _i + 1 < len(argv):
            vids.append(argv[_i+1]); _i += 2
        else:
            rest.append(_a); _i += 1
    stdin = "" if sys.stdin.isatty() else sys.stdin.read().strip()
    args = " ".join(rest).strip()
    q = "\n\n".join(x for x in [args, stdin] if x)
    if not q and not (imgs or auds or vids):
        _, desc = _model()
        print("usage: doer <query>                          # text", file=sys.stderr)
        print("       echo data | doer <query>              # piped stdin", file=sys.stderr)
        print("       doer --img X.png <query>              # vision (auto-switches to mlx-vlm)", file=sys.stderr)
        print("       doer --audio X.wav <query>            # audio", file=sys.stderr)
        print("       doer --video X.mp4 <query>            # video frames", file=sys.stderr)
        print("       doer --img a.png --audio b.wav <q>    # omni (auto-picks omni model)", file=sys.stderr)
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
        print(f"          DOER_MLX_MODEL, DOER_ADAPTER,  DOER_MLX_VLM_MODEL, DOER_MLX_AUDIO_MODEL, DOER_MLX_OMNI_MODEL, DOER_VLM_ADAPTER", file=sys.stderr)
        print(f"train:    doer --train [iters]        (text LoRA → ~/.doer_adapter)", file=sys.stderr)
        print(f"          doer --train-vlm [iters]    (VLM LoRA on multi-modal records → ~/.doer_vlm_adapter)", file=sys.stderr)
        print(f"          doer --train-status         (dataset size + text/image/audio/video breakdown)", file=sys.stderr)
        print(f"upload:   doer --upload-hf [repo]       (private HF dataset, default: <user>/doer-training)", file=sys.stderr)
        print(f"          doer --upload-hf-public [repo]  (public dataset)", file=sys.stderr)
        sys.exit(1)
    if not q and (imgs or auds or vids):
        q = "describe / analyze the attached media"
    print(str(ask(q, images=imgs, audio=auds, video=vids)).strip())


if __name__ == "__main__":
    cli()
