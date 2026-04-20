# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "torch>=2.4",
#   "transformers>=4.46",
#   "peft>=0.13",
#   "datasets>=3.0",
#   "trl>=0.12",
#   "accelerate>=1.1",
#   "bitsandbytes>=0.44",
#   "huggingface-hub>=0.26",
# ]
# ///
"""
doer HF Jobs · Text LoRA trainer

Pulls cagataydev/doer-training (text records) → LoRA-finetunes base model →
pushes merged model to cagataydev/doer-{model-short-name}.

Usage (on HF):
    hf jobs uv run --flavor t4-medium --secrets HF_TOKEN \\
      hf_jobs/train_text_lora.py --model Qwen/Qwen3-1.7B --iters 500

Runs locally too (needs a GPU):
    uv run hf_jobs/train_text_lora.py --model Qwen/Qwen3-1.7B --iters 50
"""
import argparse, json, os, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-1.7B", help="Base model repo")
    ap.add_argument("--dataset", default="cagataydev/doer-training", help="HF dataset")
    ap.add_argument("--iters", type=int, default=500)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--max-len", type=int, default=8192)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--push-to", default=None, help="Target repo (default: cagataydev/doer-<model-short>)")
    ap.add_argument("--private", action="store_true", default=True)
    ap.add_argument("--merge", action="store_true", default=True, help="Merge LoRA + push full model")
    ap.add_argument("--bf16", action="store_true", default=True)
    args = ap.parse_args()

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              TrainingArguments, DataCollatorForLanguageModeling)
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer
    from huggingface_hub import HfApi, whoami

    # ── sanity ────────────────────────────────────────────────────────────
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("❌ HF_TOKEN not set. Pass via --secrets HF_TOKEN.", file=sys.stderr)
        sys.exit(1)
    user = whoami(token=token).get("name", "anonymous")
    print(f"🤗 logged in as: {user}")

    short = args.model.split("/")[-1].lower().replace(".", "").replace("-", "")
    push_to = args.push_to or f"cagataydev/doer-{short}"
    print(f"📦 will push → {push_to} (private={args.private})")

    # ── dataset ───────────────────────────────────────────────────────────
    # Load raw JSONL directly — the dataset has heterogeneous schema (some records
    # have images/audio/video, some don't) which breaks the datasets library's
    # strict Arrow schema inference. Raw JSONL is robust.
    print(f"📥 loading {args.dataset} (raw JSONL)")
    from huggingface_hub import hf_hub_download
    jsonl_path = hf_hub_download(args.dataset, "data/train.jsonl", repo_type="dataset", token=token)
    raw_records = []
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                try: raw_records.append(json.loads(line))
                except: pass
    print(f"   {len(raw_records)} raw records")

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True, token=token)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    # Convert fat doer records → SFT messages (text-only)
    def to_messages(rec):
        sys_msg = rec.get("system", "").strip()
        msgs = []
        if sys_msg:
            msgs.append({"role": "system", "content": sys_msg[:4000]})  # cap system
        for m in rec.get("messages", []):
            role = m.get("role", "user")
            content = m.get("content", "")
            # Strands format: content can be list of {text:...}|{toolUse:...}|{toolResult:...}
            if isinstance(content, list):
                text_parts = []
                for c in content:
                    if not isinstance(c, dict): continue
                    if "text" in c:
                        text_parts.append(c["text"])
                    elif "toolUse" in c:
                        tu = c["toolUse"]
                        text_parts.append(f"<tool_call>{json.dumps({'name':tu.get('name'),'input':tu.get('input')})}</tool_call>")
                    elif "toolResult" in c:
                        tr = c["toolResult"]
                        tr_content = tr.get("content", [])
                        if isinstance(tr_content, list):
                            tr_text = "\n".join(x.get("text","") for x in tr_content if isinstance(x, dict) and "text" in x)
                        else:
                            tr_text = str(tr_content)[:1000]
                        text_parts.append(f"<tool_result>{tr_text[:2000]}</tool_result>")
                    elif "image" in c or "audio" in c or "video" in c:
                        continue  # skip multimodal for text trainer
                content = "\n".join(text_parts).strip()
            if content:
                msgs.append({"role": role, "content": content})
        return msgs

    def format_fn(rec):
        msgs = to_messages(rec)
        # skip if no user/assistant turn
        roles = [m["role"] for m in msgs]
        if "user" not in roles or "assistant" not in roles:
            return {"text": ""}
        try:
            text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        except Exception:
            # fallback
            text = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
        return {"text": text}

    from datasets import Dataset
    formatted = []
    for r in raw_records:
        f = format_fn(r)
        if f["text"] and 50 < len(f["text"]) < 60000:
            formatted.append(f)
    print(f"   {len(formatted)} usable records after filter")
    ds = Dataset.from_list(formatted)

    # 90/10 split
    split = ds.train_test_split(test_size=0.1, seed=42)
    train_ds, eval_ds = split["train"], split["test"]
    print(f"   train={len(train_ds)}  eval={len(eval_ds)}")

    # ── model ─────────────────────────────────────────────────────────────
    print(f"📥 loading {args.model}")
    dtype = torch.bfloat16 if args.bf16 else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
        token=token,
    )
    model.config.use_cache = False

    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    # ── train ─────────────────────────────────────────────────────────────
    out = Path("/tmp/doer-out")
    out.mkdir(exist_ok=True)

    targs = TrainingArguments(
        output_dir=str(out),
        max_steps=args.iters,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=max(50, args.iters // 5),
        save_strategy="steps",
        save_steps=max(100, args.iters // 3),
        save_total_limit=2,
        bf16=args.bf16,
        gradient_checkpointing=True,
        report_to="none",
        push_to_hub=False,
        remove_unused_columns=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=targs,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        processing_class=tok,
    )
    print(f"🚀 training {args.iters} steps...")
    trainer.train()
    print("✅ training done")

    # ── merge + push ──────────────────────────────────────────────────────
    adapter_dir = out / "adapter"
    trainer.save_model(str(adapter_dir))
    print(f"💾 adapter → {adapter_dir}")

    api = HfApi(token=token)
    api.create_repo(push_to, private=args.private, exist_ok=True, repo_type="model")

    if args.merge:
        print("🔀 merging LoRA → base ...")
        merged = model.merge_and_unload()
        merged_dir = out / "merged"
        merged.save_pretrained(str(merged_dir), safe_serialization=True)
        tok.save_pretrained(str(merged_dir))
        print(f"📤 pushing merged model → {push_to}")
        api.upload_folder(folder_path=str(merged_dir), repo_id=push_to, repo_type="model",
                          commit_message=f"doer merged LoRA · {args.iters} steps · base={args.model}")
    else:
        print(f"📤 pushing adapter → {push_to}")
        api.upload_folder(folder_path=str(adapter_dir), repo_id=push_to, repo_type="model",
                          commit_message=f"doer LoRA adapter · {args.iters} steps · base={args.model}")

    # model card
    card = f"""---
base_model: {args.model}
tags: [doer, lora, sft, qwen3]
datasets: [{args.dataset}]
---

# doer — fine-tune of `{args.model}`

Trained on [`{args.dataset}`]({args.dataset}) — {len(train_ds)} text turns.

- **base**: `{args.model}`
- **method**: LoRA r={args.lora_r} α={args.lora_alpha} (merged)
- **steps**: {args.iters}, lr={args.lr}
- **dataset**: {len(train_ds)} train / {len(eval_ds)} eval records

## Use

```bash
pip install doer-cli
DOER_PROVIDER=transformers \\
  DOER_MODEL={push_to} \\
  doer "what is doer"
```

Generated by `doer/hf_jobs/train_text_lora.py` on HF Jobs.
"""
    (out / "README.md").write_text(card)
    api.upload_file(path_or_fileobj=str(out / "README.md"), path_in_repo="README.md",
                    repo_id=push_to, repo_type="model", commit_message="add model card")

    print(f"✅ DONE → https://huggingface.co/{push_to}")

if __name__ == "__main__":
    main()
