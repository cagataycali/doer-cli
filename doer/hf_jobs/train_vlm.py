# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "torch>=2.4",
#   "transformers>=4.49",
#   "peft>=0.13",
#   "datasets>=3.0",
#   "trl>=0.12",
#   "accelerate>=1.1",
#   "bitsandbytes>=0.44",
#   "huggingface-hub>=0.26",
#   "Pillow>=10",
#   "qwen-vl-utils",
# ]
# ///
"""
doer HF Jobs · VLM LoRA trainer (image + text)

Pulls cagataydev/doer-training → filters records with images → LoRA-finetunes
Qwen2.5-VL-3B → pushes merged model to cagataydev/doer-vlm.

Usage:
    hf jobs uv run --flavor a100-large --secrets HF_TOKEN \\
      hf_jobs/train_vlm.py --iters 300
"""
import argparse, base64, io, json, os, sys
from pathlib import Path


def _build_model_card(model_id, base_model, dataset_id, training, kind="text"):
    """Inline model card builder — validated YAML frontmatter (per AGENTS.md: one file per trainer)."""
    import time as _t
    pretty = model_id.split("/")[-1].replace("-", " ").replace("_", " ").title()
    meta = {
        "text": ("text-generation", ["doer","lora","sft","tool-use","function-calling","agent","qwen3"],
                 f"DOER_PROVIDER=transformers DOER_MODEL={model_id} doer \"what is doer\""),
        "vlm":  ("image-text-to-text", ["doer","lora","vlm","vision","multimodal","agent","qwen2.5-vl"],
                 f"DOER_PROVIDER=mlx-vlm DOER_MLX_VLM_MODEL={model_id} doer --img photo.jpg \"describe\""),
        "omni": ("any-to-any", ["doer","lora","omni","multimodal","vision","audio","agent"],
                 f"DOER_PROVIDER=transformers DOER_MODEL={model_id} doer --img x.png --audio y.wav \"describe\""),
    }[kind]
    pipeline_tag, tags, usage = meta
    yaml = f"""---
base_model: {base_model}
datasets:
  - {dataset_id}
language:
  - en
library_name: transformers
license: apache-2.0
pipeline_tag: {pipeline_tag}
pretty_name: {pretty}
tags:
"""
    for t in tags:
        yaml += f"  - {t}\n"
    yaml += "---\n"

    mod_line = ""
    if kind == "omni":
        parts = []
        if training.get("text_n"):  parts.append(f"{training['text_n']} text")
        if training.get("image_n"): parts.append(f"{training['image_n']} image")
        if training.get("audio_n"): parts.append(f"{training['audio_n']} audio")
        if parts: mod_line = f"- **Modality mix**: {', '.join(parts)}\n"

    body = f"""
# {pretty}

Fine-tune of [`{base_model}`](https://huggingface.co/{base_model}) on [`{dataset_id}`](https://huggingface.co/datasets/{dataset_id}) — agent tool-use & instruction-following data from [`doer`](https://github.com/cagataycali/doer-cli).

## 🎯 Training

- **Base model**: `{base_model}`
- **Method**: LoRA (r={training.get("lora_r","?")}, α={training.get("lora_alpha","?")}, merged)
- **Steps**: {training.get("steps","?")}
- **Learning rate**: {training.get("lr","?")}
- **Dataset**: `{dataset_id}` — {training.get("train_n","?")} train / {training.get("eval_n","?")} eval
{mod_line}
## 🚀 Use

```bash
pip install doer-cli
{usage}
```

## 🔗 Links

- **Base**: https://huggingface.co/{base_model}
- **Dataset**: https://huggingface.co/datasets/{dataset_id}
- **doer CLI**: https://github.com/cagataycali/doer-cli

---
*Auto-generated on {_t.strftime('%Y-%m-%d %H:%M UTC', _t.gmtime())}.*
"""
    return yaml + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-VL-3B-Instruct")
    ap.add_argument("--dataset", default="cagataydev/doer-training")
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--push-to", default="cagataydev/doer-vlm")
    ap.add_argument("--private", action="store_true", default=True)
    ap.add_argument("--merge", action="store_true", default=True)
    ap.add_argument("--min-records", type=int, default=3, help="Skip training if fewer image records")
    args = ap.parse_args()

    import torch
    from PIL import Image
    from datasets import Dataset
    from transformers import (AutoProcessor, AutoModelForVision2Seq,
                              TrainingArguments)
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer, SFTConfig
    from huggingface_hub import HfApi, whoami

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("❌ HF_TOKEN not set.", file=sys.stderr); sys.exit(1)
    user = whoami(token=token).get("name")
    print(f"🤗 {user}")

    # ── Extract image records ─────────────────────────────────────────────
    print(f"📥 loading {args.dataset} (raw JSONL)")
    from huggingface_hub import hf_hub_download
    jsonl_path = hf_hub_download(args.dataset, "data/train.jsonl", repo_type="dataset", token=token)
    raw = []
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                try: raw.append(json.loads(line))
                except: pass
    print(f"   {len(raw)} raw records")

    def extract_image_bytes(content_block):
        """Extract bytes from Strands image block: {'image':{'format','source':{'bytes':...}}}"""
        if not isinstance(content_block, dict) or "image" not in content_block:
            return None
        img = content_block["image"]
        src = img.get("source", {})
        b = src.get("bytes")
        if b is None:
            return None
        # Can be bytes, str (hex/repr), or base64 str
        if isinstance(b, bytes):
            return b
        if isinstance(b, str):
            # Try: literal bytes repr, base64, hex
            if b.startswith("b'") or b.startswith('b"'):
                try:
                    import ast
                    return ast.literal_eval(b)
                except Exception:
                    pass
            try:
                return base64.b64decode(b)
            except Exception:
                pass
        return None

    def convert(rec):
        """Convert doer record → {image: PIL.Image, messages: [...]} or None."""
        images = []
        msgs = []
        sys_msg = rec.get("system", "").strip()
        if sys_msg:
            msgs.append({"role": "system", "content": [{"type": "text", "text": sys_msg[:2000]}]})

        for m in rec.get("messages", []):
            role = m.get("role", "user")
            content = m.get("content", [])
            parts = []
            if isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict): continue
                    if "text" in c:
                        parts.append({"type": "text", "text": c["text"]})
                    elif "image" in c:
                        b = extract_image_bytes(c)
                        if b:
                            try:
                                img = Image.open(io.BytesIO(b)).convert("RGB")
                                images.append(img)
                                parts.append({"type": "image"})
                            except Exception as e:
                                print(f"  skip bad image: {e}", file=sys.stderr)
                    elif "toolUse" in c:
                        tu = c["toolUse"]
                        parts.append({"type": "text",
                                      "text": f"<tool_call>{json.dumps({'name':tu.get('name'),'input':tu.get('input')})}</tool_call>"})
                    elif "toolResult" in c:
                        tr = c["toolResult"]
                        trc = tr.get("content", [])
                        t = "\n".join(x.get("text","") for x in trc if isinstance(x,dict) and "text" in x) if isinstance(trc, list) else str(trc)
                        parts.append({"type": "text", "text": f"<tool_result>{t[:1500]}</tool_result>"})
            elif isinstance(content, str):
                parts.append({"type": "text", "text": content})

            if parts:
                msgs.append({"role": role, "content": parts})

        if not images:
            return None
        return {"images": images, "messages": msgs}

    print("🔍 extracting multimodal records...")
    mm_records = []
    for rec in raw:
        c = convert(rec)
        if c:
            mm_records.append(c)
    print(f"   {len(mm_records)} records with images")

    if len(mm_records) < args.min_records:
        print(f"❌ Need ≥{args.min_records} image records, found {len(mm_records)}.")
        print(f"   Collect more with:  doer --img photo.jpg 'what is this?'")
        sys.exit(2)

    # ── Load processor + model ───────────────────────────────────────────
    print(f"📥 loading {args.model}")
    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True, token=token)
    model = AutoModelForVision2Seq.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
        token=token,
    )
    model.config.use_cache = False

    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r, lora_alpha=args.lora_r * 2, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    # ── Collator (VLM needs custom) ──────────────────────────────────────
    def collate_fn(examples):
        texts, image_lists = [], []
        for ex in examples:
            text = processor.apply_chat_template(ex["messages"], tokenize=False, add_generation_prompt=False)
            texts.append(text)
            image_lists.append(ex["images"])
        batch = processor(text=texts, images=image_lists, return_tensors="pt", padding=True, truncation=True, max_length=4096)
        labels = batch["input_ids"].clone()
        labels[labels == processor.tokenizer.pad_token_id] = -100
        # Mask image tokens
        if hasattr(processor, "image_token_id"):
            labels[labels == processor.image_token_id] = -100
        batch["labels"] = labels
        return batch

    ds = Dataset.from_list(mm_records)
    split = ds.train_test_split(test_size=max(1, len(ds)//10), seed=42) if len(ds) >= 10 else {"train": ds, "test": ds}
    train_ds, eval_ds = split["train"], split["test"]
    print(f"   train={len(train_ds)} eval={len(eval_ds)}")

    out = Path("/tmp/doer-vlm-out"); out.mkdir(exist_ok=True)

    sft_cfg = SFTConfig(
        output_dir=str(out),
        max_steps=args.iters,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=5,
        save_strategy="steps",
        save_steps=max(50, args.iters // 3),
        save_total_limit=2,
        bf16=True,
        gradient_checkpointing=True,
        report_to="none",
        remove_unused_columns=False,
        dataset_kwargs={"skip_prepare_dataset": True},
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_cfg,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=collate_fn,
        processing_class=processor.tokenizer,
    )
    print(f"🚀 training VLM {args.iters} steps...")
    trainer.train()
    print("✅ done")

    adapter_dir = out / "adapter"
    trainer.save_model(str(adapter_dir))

    api = HfApi(token=token)
    api.create_repo(args.push_to, private=args.private, exist_ok=True, repo_type="model")

    if args.merge:
        print("🔀 merging...")
        merged = model.merge_and_unload()
        merged_dir = out / "merged"
        merged.save_pretrained(str(merged_dir), safe_serialization=True)
        processor.save_pretrained(str(merged_dir))
        api.upload_folder(folder_path=str(merged_dir), repo_id=args.push_to, repo_type="model",
                          commit_message=f"doer VLM merged · {args.iters} steps · {len(train_ds)} image records")
    else:
        api.upload_folder(folder_path=str(adapter_dir), repo_id=args.push_to, repo_type="model",
                          commit_message=f"doer VLM adapter · {args.iters} steps")

    # model card — centralized generator with validated YAML frontmatter
    card = _build_model_card(
        model_id=args.push_to,
        base_model=args.model,
        dataset_id=args.dataset,
        training={
            "steps": args.iters,
            "lora_r": args.lora_r,
            "lora_alpha": getattr(args, "lora_alpha", args.lora_r * 2),
            "train_n": len(mm_records),
            "eval_n": 0,
            "image_n": len(mm_records),
        },
        kind="vlm",
    )
    (out / "README.md").write_text(card)
    api.upload_file(path_or_fileobj=str(out / "README.md"), path_in_repo="README.md",
                    repo_id=args.push_to, repo_type="model")
    print(f"✅ DONE → https://huggingface.co/{args.push_to}")

if __name__ == "__main__":
    main()
