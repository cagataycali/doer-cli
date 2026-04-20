# doer HF Jobs — cloud training on HuggingFace credits

Train **doer** models on HF infrastructure using the `cagataydev/doer-training` dataset.

## Why

- Local MLX works on-device but is slow/small (Apple Silicon, ~2GB models)
- HF Jobs = elastic A100/H200 GPUs, billed by minute, pulls dataset directly from hub
- Single UV script per trainer → no repo setup, no Dockerfile, just `hf jobs uv run`

## Scripts

| Script                | What                                 | GPU        | ~Cost (500 turns) |
|-----------------------|--------------------------------------|------------|-------------------|
| `train_text.py`       | SFT text-only (Qwen3-1.7B full FT)   | a10g-large | ~$1.50 (1h)       |
| `train_text_lora.py`  | LoRA text-only (any base model)      | t4-medium  | ~$0.30 (30min)    |
| `train_vlm.py`        | VLM with image records (Qwen2.5-VL)  | a100-large | ~$5 (2h)          |
| `train_omni.py`       | Text+audio+image (Qwen3-Omni)        | h200       | ~$10 (2h)         |

## Usage

```bash
# List hardware + costs
hf jobs hardware

# Text LoRA — cheapest, fastest, best for doer-size datasets
hf jobs uv run \
  --flavor t4-medium \
  --secrets HF_TOKEN \
  hf_jobs/train_text_lora.py \
  --model Qwen/Qwen3-1.7B \
  --iters 500

# Full fine-tune — if LoRA isn't enough
hf jobs uv run \
  --flavor a10g-large \
  --secrets HF_TOKEN \
  hf_jobs/train_text.py \
  --model Qwen/Qwen3-1.7B \
  --epochs 3

# VLM — when you have image turns (currently 3 in dataset)
hf jobs uv run \
  --flavor a100-large \
  --secrets HF_TOKEN \
  hf_jobs/train_vlm.py

# Monitor
hf jobs ps
hf jobs logs <job_id>
```

## Output

All scripts push trained weights to `cagataydev/doer-{variant}` automatically.

Then locally:
```bash
DOER_MLX_MODEL=cagataydev/doer-vlm doer --img photo.jpg "what's this?"
```
