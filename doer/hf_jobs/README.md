# doer HF Jobs — cloud training on HuggingFace credits

Train **doer** models on HF infrastructure using the `cagataydev/doer-training` dataset. Three trainers, one launcher, zero repo setup.

## why

- Local MLX LoRA on Apple Silicon works great for ~500-turn datasets on 1.7B models.
- For **bigger bases**, **full fine-tunes**, or **multimodal (VLM / Omni)** you want a real GPU.
- HF Jobs = elastic T4 → H200, billed by minute, pulls dataset straight from hub, no k8s / no Dockerfile.
- UV scripts → **one file per trainer**, inline deps, `hf jobs uv run` handles everything.

## scripts

| Script                | What                                    | GPU        | Cost (500-turn run) |
|-----------------------|-----------------------------------------|------------|---------------------|
| `gen_dataset.py`      | **Dataset generation** via doer runs    | cpu-basic  | ~$0.05 (500 prompts) |
| `train_text_lora.py`  | Text SFT LoRA (Qwen3-1.7B default)      | t4-medium  | ~$0.30 (30 min)     |
| `train_vlm.py`        | VLM LoRA (Qwen2.5-VL-3B, image+text)    | a100-large | ~$5 (2 h)           |
| `train_omni.py`       | Omni LoRA (text+audio+image, Qwen-7B)   | h200       | ~$10 (2 h)          |

All merge the LoRA into the base weights and push the **full merged model** to `cagataydev/doer-<model-short>` (private) — drop-in for `transformers.AutoModelForCausalLM.from_pretrained`.

## usage

```bash
# one-shot via launcher (recommended)
./launch.sh text                        # text LoRA, defaults
./launch.sh vlm --min-records 1         # VLM, accept ≥1 image record
./launch.sh omni                        # omni, big-GPU run

# override anything via env
MODEL=Qwen/Qwen3-4B FLAVOR=a10g-large ./launch.sh text --iters 1000
ITERS=2000 ./launch.sh text

# monitor
./launch.sh ps                          # list jobs
./launch.sh logs <job_id>               # tail logs
./launch.sh hw                          # hardware list + $/hour

# direct (if you want to skip the launcher)
hf jobs uv run --flavor t4-medium --secrets HF_TOKEN train_text_lora.py \
  --model Qwen/Qwen3-1.7B --iters 500
```

## dataset generation (new in v0.7.0)

The full loop is now cloud-native: **generate → train → deploy**. Burn HF credits instead of your laptop.

```bash
# default: 59 example prompts × Bedrock Opus 4.7, append to cagataydev/doer-training
./launch.sh gen

# your own prompts (one per line, blank/# ignored)
./launch.sh gen my_prompts.txt --iters 500

# from an existing HF dataset (column auto-detected, default "prompt")
./launch.sh gen hf://Anthropic/hh-rlhf:chosen --iters 1000

# use a different provider / model
PROVIDER=ollama MODEL=qwen3:1.7b ./launch.sh gen prompts.txt
PROVIDER=anthropic ./launch.sh gen prompts.txt   # needs ANTHROPIC_API_KEY secret

# crank concurrency (Bedrock handles 8-16 easily)
CONCURRENCY=16 ./launch.sh gen prompts.txt --iters 1000
```

### how it works

1. **Pulls your prompts** from file / HF dataset / stdin
2. **Pulls existing dataset** and computes sha256 of every existing `query` → dedupe set
3. Spawns a `ThreadPoolExecutor`, runs doer concurrently (each prompt → fresh `Agent` → full turn)
4. Captures each turn as a dense record (same schema as local `_log_turn()`): `{ts, model, query, system, messages, tools, generated_by}`
5. **Appends** to `cagataydev/doer-training` (creates if missing), updates README with fresh stats
6. Idempotent — rerun same prompts, nothing happens

### secrets

| Secret                       | Required when                        |
|------------------------------|--------------------------------------|
| `HF_TOKEN`                   | always (dataset push + dedupe read)  |
| `AWS_BEARER_TOKEN_BEDROCK`   | `PROVIDER=bedrock` (default)         |
| `ANTHROPIC_API_KEY`          | `PROVIDER=anthropic`                 |
| `OPENAI_API_KEY`             | `PROVIDER=openai`                    |

Launcher auto-wires the right secret based on `PROVIDER`.

### provenance

Every generated record carries `"generated_by": "doer --hf-jobs gen @ <job_id>"` so you can
filter synthetic vs. human records later:

```python
from datasets import load_dataset
ds = load_dataset("cagataydev/doer-training", split="train")
human = ds.filter(lambda r: "generated_by" not in r or not r["generated_by"])
synth = ds.filter(lambda r: r.get("generated_by", "").startswith("doer --hf-jobs gen"))
print(len(human), "human;", len(synth), "synthetic")
```

### cost math (Bedrock Opus 4.7 defaults)

- **HF compute**: `cpu-basic` = $0.01/hr. 500 prompts at ~0.5/sec with concurrency=8 → ~2min → **$0.0003**
- **Bedrock inference**: ~$15/1M input tokens × ~80K tokens/turn × 500 prompts = ~$0.60
- **Total**: **~$0.60 per 500-record dataset** (~$1.20/1K, ~$6/5K)

Switch to `PROVIDER=ollama` for zero inference cost but much slower (needs model pre-loaded on job).

## validated (v0.6.0)

End-to-end test on T4-medium, job `69e647b7cd8c002f31e00271`:

| metric                     | value                                |
|----------------------------|--------------------------------------|
| dataset loaded             | **521 / 522** records usable         |
| split                      | 468 train / 53 eval                  |
| base                       | `Qwen/Qwen3-1.7B`                    |
| trainable params           | 17,432,576 (1.00% of 1.74B)          |
| steps / time               | 50 / 33 min                          |
| **eval_loss**              | **0.149**                            |
| **eval token accuracy**    | **97.6%**                            |
| final model                | `cagataydev/doer-qwen3-1.7b-test` (3.44 GB) |
| total cost                 | ~$0.35                               |

## use your cloud-trained model

```bash
# anywhere with transformers
DOER_PROVIDER=transformers \
  DOER_MODEL=cagataydev/doer-qwen3-17b \
  do "what is doer"

# or convert to MLX for Apple Silicon
mlx_lm.convert --hf-path cagataydev/doer-qwen3-17b -q --q-bits 4 \
               --mlx-path ~/.cache/doer-mlx
DOER_PROVIDER=mlx DOER_MLX_MODEL=~/.cache/doer-mlx do "..."
```

## design rules

1. **one file per trainer** — no shared util modules. Disk is cheap; indirection is not.
2. **UV inline deps** — each script's `# /// script` block declares everything. No `requirements.txt`, no Dockerfile.
3. **raw JSONL load** via `hf_hub_download` — the doer dataset has heterogeneous records (some have `images`/`audio`/`video` keys, some don't) which breaks Arrow schema inference. Per-line `json.loads` is robust.
4. **merge + push by default** — output is a drop-in replacement. LoRA adapters alone force consumers to juggle `peft` glue.
5. **preserve tool calls** — Strands `toolUse`/`toolResult` blocks become `<tool_call>`/`<tool_result>` tags so the tokenizer's chat template lays down native tool-call tokens. Trains real tool-use, not string mimicry.

## extend

Want a new trainer? Copy `train_text_lora.py`, swap the model/processor class, adjust the collator. No plugin system, no base class — just Python.
