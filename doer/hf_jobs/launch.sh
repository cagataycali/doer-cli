#!/usr/bin/env bash
# doer HF Jobs launcher — wraps `hf jobs uv run`
set -euo pipefail

MODE="${1:-help}"
shift || true

DATASET="${DATASET:-cagataydev/doer-training}"
REGION="${REGION:-us-east-1}"

case "$MODE" in
  gen)
    FLAVOR="${FLAVOR:-cpu-basic}"
    MODEL="${MODEL:-global.anthropic.claude-opus-4-7}"
    PROVIDER="${PROVIDER:-bedrock}"
    CONCURRENCY="${CONCURRENCY:-8}"
    PROMPTS="${1:-$(dirname "$0")/prompts.example.txt}"
    shift || true
    echo "🦆 Launching dataset generator on $FLAVOR"
    echo "   prompts=$PROMPTS provider=$PROVIDER model=$MODEL concurrency=$CONCURRENCY"
    echo "   → $DATASET"
    # Secrets: always HF_TOKEN; add AWS_BEARER_TOKEN_BEDROCK only if provider=bedrock
    SECRETS=(--secrets HF_TOKEN)
    if [ "$PROVIDER" = "bedrock" ]; then
      SECRETS+=(--secrets AWS_BEARER_TOKEN_BEDROCK)
    fi
    # If prompts is a local file we need to ship it alongside the script.
    # hf jobs uv run takes a script path; we rely on user passing hf:// or absolute path
    # that's already on the job host, OR they pass `-` and pipe via stdin.
    hf jobs uv run \
      --flavor "$FLAVOR" \
      "${SECRETS[@]}" \
      "$(dirname "$0")/gen_dataset.py" \
      "$PROMPTS" \
      --dataset "$DATASET" \
      --provider "$PROVIDER" \
      --model "$MODEL" \
      --concurrency "$CONCURRENCY" \
      "$@"
    ;;
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
  gen [prompts]    Generate dataset via doer runs (cheap, cpu)  — ~\$0.60/500-prompts
  text             Text LoRA (cheap, Qwen3-1.7B default)       — ~\$0.30/run
  vlm              VLM LoRA (images, Qwen2.5-VL-3B default)     — ~\$5/run
  omni             Omni (text+audio+image, Qwen2.5-Omni-7B)     — ~\$10/run
  ps               List running jobs
  logs <id>        Tail logs of a job
  hw               Show hardware options

Env vars:
  FLAVOR       override hardware (default: cpu-basic for gen, t4-medium for text)
  MODEL        override base model (text/vlm/omni) or gen model
  ITERS        training steps (text/vlm/omni) — for gen, use --iters N as extra arg
  DATASET      override dataset (default: cagataydev/doer-training)
  PROVIDER     gen-only: bedrock | ollama | anthropic | openai  (default: bedrock)
  CONCURRENCY  gen-only: parallel in-flight calls (default: 8)

Examples:
  # Dataset generation (default prompts, Bedrock, append to doer-training)
  ./launch.sh gen
  ./launch.sh gen my_prompts.txt --iters 500
  ./launch.sh gen hf://Anthropic/hh-rlhf:chosen --iters 100
  PROVIDER=ollama MODEL=qwen3:1.7b ./launch.sh gen prompts.txt

  # Training
  ./launch.sh text                              # defaults
  ./launch.sh text --iters 1000                 # pass through
  MODEL=Qwen/Qwen3-4B FLAVOR=a10g-large ./launch.sh text
  ./launch.sh vlm --min-records 1
  ./launch.sh ps
HELP
    ;;
esac
