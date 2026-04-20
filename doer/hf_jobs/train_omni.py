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
#   "librosa>=0.10",
#   "soundfile>=0.12",
# ]
# ///
"""
doer HF Jobs · Omni LoRA trainer (text + audio + image)

Pulls cagataydev/doer-training → filters records with ANY modality (image/audio/
video/text) → LoRA-finetunes Qwen2.5-Omni-7B → pushes merged model to
cagataydev/doer-omni.

Usage:
    hf jobs uv run --flavor h200 --secrets HF_TOKEN \\
      hf_jobs/train_omni.py --iters 200
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
    ap.add_argument("--model", default="Qwen/Qwen2.5-Omni-7B")
    ap.add_argument("--dataset", default="cagataydev/doer-training")
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--push-to", default="cagataydev/doer-omni")
    ap.add_argument("--private", action="store_true", default=True)
    ap.add_argument("--merge", action="store_true", default=True)
    args = ap.parse_args()

    import torch
    from PIL import Image
    from datasets import Dataset
    from transformers import (AutoProcessor, AutoModelForVision2Seq,
                              TrainingArguments)
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer, SFTConfig
    from huggingface_hub import HfApi, hf_hub_download, whoami

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("❌ HF_TOKEN not set.", file=sys.stderr); sys.exit(1)
    print(f"🤗 {whoami(token=token).get('name')}")

    # ── load raw jsonl ───────────────────────────────────────────────────
    print(f"📥 loading {args.dataset} (raw JSONL)")
    jsonl_path = hf_hub_download(args.dataset, "data/train.jsonl",
                                 repo_type="dataset", token=token)
    raw = []
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                try: raw.append(json.loads(line))
                except: pass
    print(f"   {len(raw)} raw records")

    # ── extract any-modality records ─────────────────────────────────────
    def extract_bytes(block, key="image"):
        if not isinstance(block, dict) or key not in block: return None
        b = block[key].get("source", {}).get("bytes")
        if isinstance(b, bytes): return b
        if isinstance(b, str):
            if b.startswith("b'") or b.startswith('b"'):
                try:
                    import ast; return ast.literal_eval(b)
                except: pass
            try: return base64.b64decode(b)
            except: pass
        return None

    def convert(rec):
        """Omni supports image + audio + text. Accept any record."""
        images, audios = [], []
        msgs = []
        sys_msg = rec.get("system", "").strip()
        if sys_msg:
            msgs.append({"role": "system",
                         "content": [{"type": "text", "text": sys_msg[:2000]}]})
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
                        b = extract_bytes(c, "image")
                        if b:
                            try:
                                images.append(Image.open(io.BytesIO(b)).convert("RGB"))
                                parts.append({"type": "image"})
                            except Exception: pass
                    elif "audio" in c:
                        b = extract_bytes(c, "audio")
                        if b:
                            audios.append(b)
                            parts.append({"type": "audio"})
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

        if not msgs or all(m["role"] != "assistant" for m in msgs):
            return None
        return {"images": images, "audios": audios, "messages": msgs}

    records = [c for c in (convert(r) for r in raw) if c]
    n_text = sum(1 for r in records if not r["images"] and not r["audios"])
    n_img = sum(1 for r in records if r["images"])
    n_aud = sum(1 for r in records if r["audios"])
    print(f"   {len(records)} usable records (text:{n_text} img:{n_img} aud:{n_aud})")
    if len(records) < 10:
        print(f"❌ Need ≥10 records, found {len(records)}.")
        sys.exit(2)

    # ── processor + model ────────────────────────────────────────────────
    print(f"📥 loading {args.model}")
    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True, token=token)
    model = AutoModelForVision2Seq.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, device_map="auto",
        trust_remote_code=True, token=token,
    )
    model.config.use_cache = False

    model = get_peft_model(model, LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r, lora_alpha=args.lora_r * 2, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
    ))
    model.print_trainable_parameters()

    def collate_fn(examples):
        texts, img_lists, aud_lists = [], [], []
        for ex in examples:
            texts.append(processor.apply_chat_template(
                ex["messages"], tokenize=False, add_generation_prompt=False))
            img_lists.append(ex["images"] or None)
            aud_lists.append(ex["audios"] or None)
        kwargs = {"text": texts, "return_tensors": "pt",
                  "padding": True, "truncation": True, "max_length": 4096}
        if any(img_lists): kwargs["images"] = [i or [] for i in img_lists]
        if any(aud_lists): kwargs["audios"] = [a or [] for a in aud_lists]
        batch = processor(**kwargs)
        labels = batch["input_ids"].clone()
        labels[labels == processor.tokenizer.pad_token_id] = -100
        batch["labels"] = labels
        return batch

    ds = Dataset.from_list(records)
    split = ds.train_test_split(test_size=max(1, len(ds)//10), seed=42)
    train_ds, eval_ds = split["train"], split["test"]
    print(f"   train={len(train_ds)} eval={len(eval_ds)}")

    out = Path("/tmp/doer-omni-out"); out.mkdir(exist_ok=True)
    cfg = SFTConfig(
        output_dir=str(out), max_steps=args.iters,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr, lr_scheduler_type="cosine", warmup_ratio=0.05,
        logging_steps=5, save_steps=max(50, args.iters // 3),
        save_total_limit=2, bf16=True, gradient_checkpointing=True,
        report_to="none", remove_unused_columns=False,
        dataset_kwargs={"skip_prepare_dataset": True},
    )
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=train_ds,
                         eval_dataset=eval_ds, data_collator=collate_fn,
                         processing_class=processor.tokenizer)
    print(f"🚀 training Omni {args.iters} steps...")
    trainer.train()
    print("✅ done")

    trainer.save_model(str(out / "adapter"))
    api = HfApi(token=token)
    api.create_repo(args.push_to, private=args.private, exist_ok=True, repo_type="model")
    if args.merge:
        print("🔀 merging...")
        merged = model.merge_and_unload()
        merged.save_pretrained(str(out / "merged"), safe_serialization=True)
        processor.save_pretrained(str(out / "merged"))
        api.upload_folder(folder_path=str(out / "merged"), repo_id=args.push_to, repo_type="model",
                          commit_message=f"doer Omni merged · {args.iters} steps")
    else:
        api.upload_folder(folder_path=str(out / "adapter"), repo_id=args.push_to, repo_type="model",
                          commit_message=f"doer Omni adapter · {args.iters} steps")

    # model card — centralized generator with validated YAML frontmatter
    card = _build_model_card(
        model_id=args.push_to,
        base_model=args.model,
        dataset_id=args.dataset,
        training={
            "steps": args.iters,
            "lora_r": args.lora_r,
            "lora_alpha": getattr(args, "lora_alpha", args.lora_r * 2),
            "train_n": len(train_ds),
            "eval_n": 0,
            "text_n": n_text,
            "image_n": n_img,
            "audio_n": n_aud,
        },
        kind="omni",
    )
    (out / "README.md").write_text(card)
    api.upload_file(path_or_fileobj=str(out / "README.md"), path_in_repo="README.md",
                    repo_id=args.push_to, repo_type="model")
    print(f"✅ DONE → https://huggingface.co/{args.push_to}")


if __name__ == "__main__":
    main()
