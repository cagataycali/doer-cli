# Tasks — Native VLA Support for Doer-CLI

## Phase 1: Robust ZMQ Client Hardening
- [x] T1.1: Add reconnect logic to `_Client` (ZMQ REQ socket gets stuck after timeout)
  - Implemented: auto-recreate socket on timeout, configurable retries with exponential backoff
  - TCP keepalive for dead connection detection
  - Health tracking (consecutive failures, latencies, success timestamps)
  - `DOER_GR00T_RETRIES` env var (default: 3)
- [x] T1.2: Add `--gr00t-status` command that shows server info + modality config + embodiment
  - Returns JSON: connected, ping_latency_ms, modality_config, client_health, endpoint
- [x] T1.3: Add observation validation against `get_modality_config` response
  - `validate_observation(obs, config)` → list of warnings (empty = valid)
  - Checks missing modalities and shape mismatches
- [x] T1.4: Add batch observation support (multiple timesteps in one call)
  - State (T, D) → (1, T, D) auto-reshape
  - Already worked; now explicitly tested
- [x] T1.5: Support video arrays (multi-frame) not just single images
  - Video (T, H, W, C) → (1, T, H, W, C) auto-reshape
  - Tested with multi-frame numpy arrays

## Phase 2: Control Loop (`doer --gr00t-loop`)
- [x] T2.1: Implement `--gr00t-loop` mode: continuous obs→action at target Hz
  - `run_loop()` function: camera→GR00T→action→stdout at configurable Hz
  - JSON Lines output (one action per line, includes step counter)
  - Graceful Ctrl+C handling with stats summary
- [x] T2.2: Camera capture integration (OpenCV/v4l2) — grab frame → numpy → hydrate
  - `capture_frame()`: opens camera, grabs BGR, converts RGB, shapes for GR00T
  - `--camera N` flag (device index, -1 to disable)
  - `--camera-name`, `--camera-width`, `--camera-height` options
- [x] T2.3: State reader integration — read joint state from stdin pipe or file
  - `--state-file F`: reads JSON array from file each step
  - Also accepts callable via Python API
- [x] T2.4: Action writer — output action JSON to stdout (pipeable to robot controller)
  - JSON Lines format: `{"action": {...}, "info": {...}, "step": N}`
  - Pipeable: `doer --gr00t-loop "task" | python robot_controller.py`
- [x] T2.5: Frequency control — target Hz with timing stats (like GR00T benchmark)
  - Sleep-based rate limiting to hit target Hz
  - Stats: avg_hz, avg_inference_ms, avg_loop_ms, steps, elapsed_s
  - Periodic stderr reporting every 50 steps
- [x] T2.6: Episode management — auto `reset` at start, handle termination signals
  - `--no-reset` to skip, otherwise auto-resets
  - SIGINT handler for graceful exit with stats

## Phase 3: Docker-Aware Server Management
- [ ] T3.1: `doer --gr00t-serve` should detect Thor and auto-use Docker container
- [ ] T3.2: Add `--gr00t-container` flag to specify container name (default: `gr00t-thor-dev`)
- [ ] T3.3: Auto-download model inside container if not present
- [ ] T3.4: TRT engine build from doer: `doer --gr00t-build-trt <ckpt> <dataset> <tag>`
- [ ] T3.5: Status command shows container health + GPU utilization + model loaded

## Phase 4: Demonstration Recording
- [ ] T4.1: `doer --gr00t-record` mode — record obs/action pairs to LeRobot format
- [ ] T4.2: Record camera frames as video (MP4/h264) alongside state/action parquet
- [ ] T4.3: Episode segmentation — start/stop recording with keyboard shortcuts
- [ ] T4.4: Upload recorded dataset to HuggingFace (reuse existing `--upload-hf` infra)
- [ ] T4.5: Convert recorded data to GR00T LeRobot format for finetuning

## Phase 5: Modality Config Authoring
- [ ] T5.1: `doer --gr00t-init-embodiment` — interactive wizard for NEW_EMBODIMENT config
- [ ] T5.2: Auto-detect camera resolution + joint DOF from first observation
- [ ] T5.3: Generate `modality_config.py` compatible with GR00T finetuning
- [ ] T5.4: Validate config against known embodiment tags

## Phase 6: End-to-End Finetuning Bridge
- [ ] T6.1: `doer --gr00t-finetune` — launch finetuning inside container
- [ ] T6.2: Monitor training progress (loss, eval metrics) via ZMQ or log parsing
- [ ] T6.3: Auto-swap model after finetuning (restart server with new checkpoint)
- [ ] T6.4: A/B test: run old vs new policy side by side

## Phase 7: Multi-Robot Orchestration
- [ ] T7.1: Multiple `--gr00t-host` targets (one doer controlling N robots)
- [ ] T7.2: Embodiment routing — different tags for different robots
- [ ] T7.3: Shared language instruction broadcasting
- [ ] T7.4: Fleet status dashboard (all robots + all GR00T servers)

## Priority Order
**Immediate** (Phase 1-2): Harden client + control loop = doer can run a real robot
**Short-term** (Phase 3): Docker management = zero-friction Thor deployment  
**Medium-term** (Phase 4-5): Recording + config = custom robot onboarding
**Long-term** (Phase 6-7): Finetuning bridge + multi-robot = production fleet

## Current Working Context
- Thor device: `cagatay` (aarch64, CUDA 13.0, Driver 580.00)
- Docker image: `gr00t-thor` (built, tested)
- Container: `gr00t-thor-dev` (running, GPU verified)
- Repo: `/home/cagatay/_gr00t` (N1.7 cloned, submodules init'd)
- Doer: `/home/cagatay/doer-cli` (v0.8.0, gr00t client merged)
- Gist: https://gist.github.com/cagataycali/1a580ffae58a68a033a64acd51803a3e
