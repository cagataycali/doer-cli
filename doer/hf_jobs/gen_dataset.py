# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "strands-agents[ollama,bedrock]",
#   "huggingface-hub>=0.26",
#   "datasets>=3.0",
#   "boto3>=1.35",
# ]
# ///
"""
doer HF Jobs · Dataset generator

Runs `doer` against a list of prompts inside an HF Job, captures each full
turn (system + messages + tools) as a dense training record, and appends to
an HF dataset with sha256-based dedupe.

Input forms:
    prompts.txt                 one prompt per line (blank/# ignored)
    hf://user/repo              HF dataset, default column=prompt
    hf://user/repo:column_name  HF dataset, explicit column
    -                           stdin (one prompt per line)

Usage (on HF):
    hf jobs uv run --flavor cpu-basic \
      --secrets HF_TOKEN --secrets AWS_BEARER_TOKEN_BEDROCK \
      gen_dataset.py prompts.txt \
      --dataset cagataydev/doer-training \
      --iters 500 --concurrency 8

Runs locally too (needs Bedrock creds):
    uv run gen_dataset.py prompts.txt --iters 10 --concurrency 4
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, random, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


# ── record emission (mirrors doer/__init__.py::_log_turn) ────────────────

def _build_dataset_card(dataset_id, jsonl_text, job_id, appended_this_run=0):
    """Inline dataset card builder — validated YAML + real stats."""
    import json as _j, time as _t
    from collections import Counter as _C
    total, modal, models, total_chars, tool_calls = 0, _C(), _C(), 0, 0
    for line in (jsonl_text or "").splitlines():
        if not line.strip(): continue
        try: r = _j.loads(line)
        except: continue
        total += 1
        q = r.get("query", "")
        if "<image>" in q or "![" in q or "--img" in q: modal["image"] += 1
        elif "<audio>" in q or "--audio" in q: modal["audio"] += 1
        elif "<video>" in q or "--video" in q: modal["video"] += 1
        else: modal["text"] += 1
        models[r.get("model", "unknown")] += 1
        total_chars += len(_j.dumps(r, default=str))
        for msg in r.get("messages", []):
            if isinstance(msg.get("content"), list):
                for b in msg["content"]:
                    if isinstance(b, dict) and "toolUse" in b: tool_calls += 1

    def _size(n):
        for thr, lbl in [(1000,"n<1K"),(10000,"1K<n<10K"),(100000,"10K<n<100K"),
                         (1000000,"100K<n<1M"),(10000000,"1M<n<10M")]:
            if n < thr: return lbl
        return "n>10M"

    pretty = dataset_id.split("/")[-1].replace("-"," ").replace("_"," ").title()
    modal_tags = []
    if modal.get("image"): modal_tags.append("vision")
    if modal.get("audio"): modal_tags.append("audio")
    if modal.get("video"): modal_tags.append("video")

    yaml = f"""---
pretty_name: {pretty}
language:
  - en
license: apache-2.0
task_categories:
  - text-generation
  - question-answering
task_ids:
  - open-domain-qa
  - language-modeling
size_categories:
  - {_size(total)}
tags:
  - doer
  - agent
  - tool-use
  - function-calling
  - strands-agents
  - sft
  - instruction-tuning"""
    for t in modal_tags:
        yaml += f"\n  - {t}"
    yaml += """
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train.jsonl
---
"""

    mod_breakdown = "\n".join(f"  - **{k}**: {v:,}" for k,v in sorted(modal.items(), key=lambda x: -x[1])) or "  - (empty)"
    model_breakdown = "\n".join(f"  - `{m}`: {c:,}" for m,c in models.most_common(5)) or "  - (empty)"
    size_mb = total_chars / 1_048_576

    body = f"""
# {pretty}

> Dense training records from [`doer`](https://github.com/cagataycali/doer-cli) — a one-file, pipe-native AI agent.

Every record captures a **real agent turn**: full system prompt, user query, multi-step assistant responses (including tool calls + results), and tool schemas. Designed to teach language models *when* and *how* to use tools.

## 📊 Stats

- **Total records**: {total:,}
- **Total tool calls captured**: {tool_calls:,}
- **Dataset size**: {size_mb:.1f} MB
- **Last updated**: {_t.strftime('%Y-%m-%d %H:%M UTC', _t.gmtime())} (job `{job_id}`)
- **Appended this run**: {appended_this_run:,}

### Modality mix
{mod_breakdown}

### Top generator models
{model_breakdown}

## 📐 Schema

```jsonc
{{
  "ts": 1776707007,
  "model": "bedrock ... @ region",
  "query": "original user query",
  "system": "<full doer system prompt>",
  "messages": [
    {{"role": "user",      "content": [{{"text": "..."}}]}},
    {{"role": "assistant", "content": [{{"text": "..."}}, {{"toolUse": {{...}}}}]}},
    {{"role": "user",      "content": [{{"toolResult": {{...}}}}]}},
    {{"role": "assistant", "content": [{{"text": "..."}}]}}
  ],
  "tools": [{{"name": "shell", "description": "...", "input_schema": {{...}}}}]
}}
```

## 🚀 Use

```python
from datasets import load_dataset
ds = load_dataset("{dataset_id}", split="train")
```

```bash
pip install doer-cli
doer "some query"          # every call auto-logs to ~/.doer_training.jsonl
doer --upload-hf {dataset_id}
```

## ⚖️ License
Apache-2.0. Records may contain developer-environment info (cwd, shell history) — filter before downstream use.

## 🔗 Links
- **Repo**: https://github.com/cagataycali/doer-cli
- **Package**: https://pypi.org/project/doer-cli

---
*Auto-generated. Edits below this line are preserved across runs.*

<!-- USER_EDITS_BELOW -->
"""
    return yaml + body


def _build_record(q: str, agent, model_desc: str, job_id: str) -> dict:
    msgs = [dict(m) if isinstance(m, dict) else m for m in (agent.messages or [])]
    tools = []
    reg = getattr(agent, "tool_registry", None)
    if reg:
        for name, t in getattr(reg, "registry", {}).items():
            spec = getattr(t, "tool_spec", None)
            if not spec:
                continue
            tools.append({
                "name": spec.get("name", name),
                "description": spec.get("description", ""),
                "input_schema": spec.get("inputSchema", {}).get("json", {}),
            })
    return {
        "ts": int(time.time()),
        "model": model_desc,
        "query": q,
        "system": agent.system_prompt or "",
        "messages": msgs,
        "tools": tools,
        "generated_by": f"doer --hf-jobs gen @ {job_id}",
    }


def _prompt_hash(q: str) -> str:
    return hashlib.sha256(q.strip().encode("utf-8")).hexdigest()[:16]


# ── input loading ────────────────────────────────────────────────────────
def load_prompts(spec: str, max_n: int | None = None) -> list[str]:
    if spec == "-":
        lines = sys.stdin.read().splitlines()
    elif spec.startswith("hf://"):
        from datasets import load_dataset
        path = spec[5:]
        col = "prompt"
        if ":" in path:
            path, col = path.rsplit(":", 1)
        print(f"📥 loading HF dataset: {path} [col={col}]", flush=True)
        ds = load_dataset(path, split="train", token=os.environ.get("HF_TOKEN"))
        if col not in ds.column_names:
            sys.exit(f"❌ column '{col}' not in {path}; available: {ds.column_names}")
        lines = [str(x) for x in ds[col]]
    else:
        p = Path(spec)
        if not p.exists():
            sys.exit(f"❌ prompts file not found: {spec}")
        lines = p.read_text(encoding="utf-8").splitlines()

    prompts = [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]
    if max_n:
        prompts = prompts[:max_n]
    return prompts


def load_existing_hashes(dataset: str, token: str) -> set[str]:
    """Pull dataset (if exists) and return sha256 hashes of all existing prompts."""
    from huggingface_hub import hf_hub_download
    try:
        path = hf_hub_download(dataset, "data/train.jsonl",
                               repo_type="dataset", token=token)
    except Exception as e:
        print(f"ℹ️  dataset not found or empty ({e}); starting fresh", flush=True)
        return set()
    hashes = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("query"):
                    hashes.add(_prompt_hash(r["query"]))
            except Exception:
                continue
    print(f"🔎 dedupe index: {len(hashes)} existing prompts hashed", flush=True)
    return hashes


# ── doer agent wiring ────────────────────────────────────────────────────
def make_agent_factory(model_id: str, provider: str):
    """Return a callable that builds a fresh doer Agent per prompt (thread-safe)."""
    # Hotwire doer's env so _model() selects what we want BEFORE import.
    if provider == "bedrock":
        os.environ["DOER_PROVIDER"] = "bedrock"
        os.environ["DOER_BEDROCK_MODEL"] = model_id
    elif provider == "ollama":
        os.environ["DOER_PROVIDER"] = "ollama"
        os.environ["DOER_MODEL"] = model_id
    elif provider:
        os.environ["DOER_PROVIDER"] = provider

    # Quiet doer; we're doing bulk gen, don't want its stdout noise mid-run
    os.environ["DOER_QUIET"] = "1"
    # Disable hot-reload file watcher (not thread-safe, and unused in bulk gen)
    # User can override with DOER_LOAD_TOOLS_FROM_DIR=1 if they really want it.
    os.environ.setdefault("DOER_LOAD_TOOLS_FROM_DIR", "0")

    import doer, threading
    _lock = threading.Lock()
    def factory():
        # Defense-in-depth: even with watchers off, serialize Agent() ctor.
        # The agent(query) call itself runs in parallel threads just fine.
        with _lock:
            return doer._agent()
    return factory


def run_one(q: str, factory, job_id: str) -> dict | None:
    try:
        agent, model_desc = factory()
        _ = agent(q)  # runs the turn; agent.messages now populated
        return _build_record(q, agent, model_desc, job_id)
    except Exception as e:
        print(f"⚠️  prompt failed: {q[:60]!r} -> {e}", flush=True)
        return None


# ── dataset upload ───────────────────────────────────────────────────────
def append_to_dataset(records: list[dict], dataset: str, token: str,
                      private: bool, job_id: str) -> None:
    if not records:
        print("⚠️  no new records to upload", flush=True)
        return
    from huggingface_hub import HfApi, CommitOperationAdd, hf_hub_download

    api = HfApi(token=token)
    # Ensure repo exists
    api.create_repo(dataset, repo_type="dataset", private=private, exist_ok=True)

    # Pull existing jsonl (if any) and append
    existing_lines: list[str] = []
    try:
        path = hf_hub_download(dataset, "data/train.jsonl",
                               repo_type="dataset", token=token)
        existing_lines = Path(path).read_text(encoding="utf-8").splitlines()
    except Exception:
        pass

    new_lines = [json.dumps(r, ensure_ascii=False, default=str) for r in records]
    combined = "\n".join(existing_lines + new_lines) + "\n"
    buf = io.BytesIO(combined.encode("utf-8"))

    # Build a proper dataset card — stats from real data, validated YAML frontmatter
    readme = _build_dataset_card(
        dataset_id=dataset,
        jsonl_text=combined,
        job_id=job_id,
        appended_this_run=len(new_lines),
    )

    # Preserve user edits below <!-- USER_EDITS_BELOW --> marker if present on the hub
    try:
        existing_readme_path = hf_hub_download(
            dataset, "README.md", repo_type="dataset", token=token
        )
        existing_readme = Path(existing_readme_path).read_text(encoding="utf-8")
        edit_marker = "<!-- USER_EDITS_BELOW -->"
        if edit_marker in existing_readme:
            user_edits = existing_readme.split(edit_marker, 1)[1]
            if user_edits.strip():
                readme = readme + user_edits
    except Exception:
        pass

    api.create_commit(
        repo_id=dataset,
        repo_type="dataset",
        commit_message=f"[hf-job {job_id}] append {len(new_lines)} records",
        operations=[
            CommitOperationAdd("data/train.jsonl", buf),
            CommitOperationAdd("README.md", io.BytesIO(readme.encode("utf-8"))),
        ],
    )
    print(f"✅ pushed {len(new_lines)} new records → {dataset} "
          f"(total: {len(existing_lines) + len(new_lines)})", flush=True)


# ── main ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="doer dataset generator (HF Jobs)")
    ap.add_argument("prompts", help="prompts.txt | hf://user/ds[:col] | -")
    ap.add_argument("--dataset", default="cagataydev/doer-training",
                    help="Target HF dataset to append to")
    ap.add_argument("--iters", type=int, default=None,
                    help="Cap number of prompts processed (default: all)")
    ap.add_argument("--concurrency", type=int, default=8,
                    help="Parallel in-flight agent calls")
    ap.add_argument("--model", default="global.anthropic.claude-opus-4-7",
                    help="Model ID (Bedrock by default)")
    ap.add_argument("--provider", default="bedrock",
                    choices=["bedrock", "ollama", "anthropic", "openai"],
                    help="doer provider (default: bedrock)")
    ap.add_argument("--shuffle", action="store_true", default=False,
                    help="Shuffle prompt order before processing")
    ap.add_argument("--no-dedupe", action="store_true", default=False,
                    help="Skip dedupe against existing dataset")
    ap.add_argument("--public", action="store_true", default=False,
                    help="Create dataset as public (default: private)")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Generate but do NOT upload")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token and not args.dry_run:
        print("❌ HF_TOKEN not set. Pass via --secrets HF_TOKEN.", file=sys.stderr)
        sys.exit(1)

    job_id = os.environ.get("HF_JOB_ID", f"local-{int(time.time())}")
    print(f"🦆 doer dataset-gen · job={job_id} · provider={args.provider} · model={args.model}", flush=True)

    # 1) load prompts
    prompts = load_prompts(args.prompts, max_n=args.iters)
    if args.shuffle:
        random.shuffle(prompts)
    print(f"📝 {len(prompts)} prompts loaded", flush=True)

    # 2) dedupe
    skipped = 0
    if not args.no_dedupe and not args.dry_run:
        existing = load_existing_hashes(args.dataset, token)
        filtered = []
        for q in prompts:
            if _prompt_hash(q) in existing:
                skipped += 1
            else:
                filtered.append(q)
        prompts = filtered
        print(f"🔁 dedupe: {skipped} skipped, {len(prompts)} new to generate", flush=True)

    if not prompts:
        print("✅ nothing to do — dataset already has all these prompts", flush=True)
        return 0

    # 3) build agent factory
    factory = make_agent_factory(args.model, args.provider)

    # 4) run generation concurrently
    records: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = {ex.submit(run_one, q, factory, job_id): q for q in prompts}
        for i, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            if rec:
                records.append(rec)
            dt = time.time() - t0
            rate = i / dt if dt > 0 else 0
            eta = (len(prompts) - i) / rate if rate > 0 else 0
            print(f"[{i}/{len(prompts)}] {rate:.1f}/s eta={eta:.0f}s "
                  f"ok={len(records)} fail={i - len(records)}", flush=True)

    print(f"\n🎯 generation done: {len(records)}/{len(prompts)} successful "
          f"in {time.time() - t0:.1f}s", flush=True)

    # 5) upload
    if args.dry_run:
        out = Path("/tmp/gen_dataset_dryrun.jsonl")
        out.write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str)
                                 for r in records) + ("\n" if records else ""))
        print(f"🧪 dry-run: {len(records)} records written to {out}", flush=True)
    else:
        append_to_dataset(records, args.dataset, token,
                          private=not args.public, job_id=job_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
