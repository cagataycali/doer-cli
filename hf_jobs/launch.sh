#!/usr/bin/env bash
# doer HF Jobs launcher — wraps `hf jobs uv run`
set -euo pipefail

MODE="${1:-help}"
shift || true

DATASET="${DATASET:-cagataydev/doer-training}"
REGION="${REGION:-us-east-1}"

case "$MODE" in
  text)
    FLAVOR="${FLAVOR:-t4-medium}"
    MODEL="${MODEL:-Qwen/Qwen3-1.7B}"
    ITERS="${ITERS:-500}"
    echo "🦆 Launching text LoRA on $FLAVOR"
    echo "   model=$MODEL iters=$ITERS dataset=$DATASET"
    hf jobs uv run \
      --flavor "$FLAVOR" \
      --secrets HF_TOKEN \
      "$(dirname "$0")/train_text_lora.py" \
      --model "$MODEL" \
      --dataset "$DATASET" \
      --iters "$ITERS" \
      "$@"
    ;;
  vlm)
    FLAVOR="${FLAVOR:-a100-large}"
    MODEL="${MODEL:-Qwen/Qwen2.5-VL-3B-Instruct}"
    ITERS="${ITERS:-300}"
    echo "🦆 Launching VLM LoRA on $FLAVOR"
    echo "   model=$MODEL iters=$ITERS dataset=$DATASET"
    hf jobs uv run \
      --flavor "$FLAVOR" \
      --secrets HF_TOKEN \
      "$(dirname "$0")/train_vlm.py" \
      --model "$MODEL" \
      --dataset "$DATASET" \
      --iters "$ITERS" \
      "$@"
    ;;
  omni)
    FLAVOR="${FLAVOR:-h200}"
    MODEL="${MODEL:-Qwen/Qwen2.5-Omni-7B}"
    ITERS="${ITERS:-200}"
    echo "🦆 Launching Omni (text+audio+image) on $FLAVOR"
    hf jobs uv run \
      --flavor "$FLAVOR" \
      --secrets HF_TOKEN \
      "$(dirname "$0")/train_omni.py" \
      --model "$MODEL" \
      --dataset "$DATASET" \
      --iters "$ITERS" \
      "$@"
    ;;
  ps) hf jobs ps ;;
  logs) hf jobs logs "${1:-}" ;;
  hw|hardware) hf jobs hardware ;;
  *)
    cat <<HELP
🦆 doer HF Jobs launcher

Usage: ./launch.sh <mode> [extra args...]

Modes:
  text          Text LoRA (cheap, Qwen3-1.7B default)     — ~\$0.30/run
  vlm           VLM LoRA (images, Qwen2.5-VL-3B default)   — ~\$5/run
  omni          Omni (text+audio+image, Qwen2.5-Omni-7B)   — ~\$10/run
  ps            List running jobs
  logs <id>     Tail logs of a job
  hw            Show hardware options

Env vars:
  FLAVOR   override hardware (e.g. a10g-large, a100-large, h200)
  MODEL    override base model
  ITERS    override training steps
  DATASET  override dataset (default: cagataydev/doer-training)

Examples:
  ./launch.sh text                              # defaults
  ./launch.sh text --iters 1000                 # pass through
  MODEL=Qwen/Qwen3-4B FLAVOR=a10g-large ./launch.sh text
  ./launch.sh vlm --min-records 1               # allow training on 1 image
  ./launch.sh ps
HELP
    ;;
esac
