# Findings — GR00T × Doer Integration

## What Already Works (v0.9.0)
1. ✅ ZMQ client (`_gr00t_client.py`) — full protocol support with auto-reconnect
2. ✅ Brain mode — LLM calls `gr00t_action` tool with observation JSON
3. ✅ Pipe mode — `echo obs | doer --gr00t "task"` (LLM bypass)
4. ✅ Observation hydration — flat keys → nested dict, list→ndarray, image path→loaded
5. ✅ Auto-spawn server — `doer --gr00t-serve <ckpt>`
6. ✅ Training bridge — gr00t tool calls land in training JSONL
7. ✅ Reconnect logic — exponential backoff, health tracking, configurable retries
8. ✅ Status command — `--gr00t-status` shows connectivity + schema + timing
9. ✅ Observation validation — validates against modality config shape/type
10. ✅ Control loop — `--gr00t-loop` continuous obs→action at target Hz
11. ✅ Camera capture — OpenCV frame grab → numpy → GR00T video format
12. ✅ State reader — file-based or callable state injection per step
13. ✅ Frequency control — rate limiting with timing stats (avg Hz/ms reporting)

## Gaps for Native VLA Support
1. ❌ **No local inference** — doer can only talk to a remote ZMQ server, no in-process GR00T model
2. ❌ **No TRT integration** — no way to build/use TRT engines from doer
3. ❌ **No action executor** — action dict comes back but nothing sends it to the robot
4. ❌ **No modality config authoring** — custom robots need a config.py; doer doesn't help create one
5. ❌ **No dataset recording** — can't record demonstrations for finetuning
6. ❌ **No Docker-aware mode** — doer doesn't know about the gr00t-thor container

## Architectural Observations
- doer is "one file, no classes" — GR00T client is already the largest exception (`_gr00t_client.py` is separate)
- The ZMQ protocol is simple enough that doer should focus on **orchestration**, not reimplementing GR00T internals
- The real value-add is: camera → observation → GR00T → action → robot, all from a single `doer` pipe
- TRT engines are GPU-arch-specific; doer should delegate building to the container
- Training loop already captures gr00t tool calls; the gap is **recording raw demonstrations** (obs/action pairs)

## Key Integration Points
- `gr00t.eval.run_gr00t_server` is the bridge — doer should make starting it frictionless
- The Docker container (`gr00t-thor`) has everything; doer needs `docker exec` awareness
- SO100 example in repo shows how to create NEW_EMBODIMENT modality configs
- HuggingFace model download is already handled by `huggingface_hub` (doer has `[hf]` extra)

## Design Principles (from AGENTS.md)
- One file per concern (ok to have `_gr00t_client.py` separate)
- Unix over RPC — pipe observation in, get action out
- Env vars over config — `DOER_GR00T_*` knobs
- No new deps unless behind an extra (`[gr00t]`)
