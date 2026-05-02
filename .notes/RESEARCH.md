# GR00T N1.7 VLA Integration Research

## Architecture Overview

### Isaac GR00T N1.7 Model
- **Type**: Vision-Language-Action (VLA) — takes images + language → outputs continuous robot actions
- **Backbone**: Cosmos-Reason2-2B (Qwen3-VL architecture)
- **Action Head**: Diffusion Transformer (DiT) with 32 layers, 4 denoising steps
- **Action Space**: Relative end-effector (delta from current pose)
- **Input**: multimodal — `video` (camera frames), `state` (joint positions), `language` (task instruction)
- **Output**: `action` dict — e.g. `action.joint_pos` (1, T, D) float32

### GR00T Policy API (`gr00t/policy/gr00t_policy.py`)
```python
from gr00t.policy import Gr00tPolicy
policy = Gr00tPolicy(
    model_path="checkpoints/GR00T-N1.7-3B",
    embodiment_tag=EmbodimentTag.NEW_EMBODIMENT,
    device="cuda:0",
)
# observation format:
obs = {
    "video": {"cam_name": np.ndarray},  # (B, T, H, W, 3) uint8
    "state": {"joint_pos": np.ndarray}, # (B, T, D) float32
    "language": {"task_description": [["pick up cube"]]}
}
action = policy.get_action(obs)  # → {"action.joint_pos": ndarray}
```

### GR00T Server/Client (`gr00t/policy/server_client.py`)
- **Transport**: ZMQ REQ/REP
- **Encoding**: msgpack with numpy ndarray extension
- **Endpoints**: `ping`, `get_action`, `reset`, `get_modality_config`, `kill`
- **Server launch**: `python -m gr00t.eval.run_gr00t_server --model-path <ckpt> --embodiment-tag <tag> --host 0.0.0.0 --port 5555`

### Embodiment Tags (pretrained, zero-shot ready)
| Tag | Robot |
|-----|-------|
| `OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT` | DROID |
| `XDOF` | Generic X-DOF |
| `REAL_G1` | Unitree G1 humanoid |
| `REAL_R1_PRO_SHARPA` | R1 Pro Sharpa |
| `NEW_EMBODIMENT` | Custom (needs finetuning + modality config) |

### TensorRT Deployment
- Full pipeline mode: ViT + LLM + DiT all in TRT engines
- Thor performance: 93.8ms E2E → **10.7 Hz** (1.54x over PyTorch)
- Build: `build_trt_pipeline.py --model-path <ckpt> --dataset-path <data> --embodiment-tag <tag>`
- Inference: `standalone_inference_script.py --inference-mode trt_full_pipeline`

### Doer-CLI Current State (v0.8.0)
- `doer/_gr00t_client.py` — ZMQ client matching GR00T wire format
- `gr00t_action` tool — LLM can call GR00T as a tool (brain mode)
- `--gr00t` CLI flag — pipe mode (stdin → ZMQ → stdout, LLM bypass)
- `--gr00t-serve` — auto-spawn server subprocess
- Observation hydration: flat keys (`state.joint_pos`) → nested dict → ndarray coercion
- Image loading: file paths auto-loaded via PIL → uint8 ndarray with batch dim
- Tests: `test_gr00t_client.py` + `test_gr00t_cli.py` with mock ZMQ server

### Key GR00T Source Files
| File | Purpose |
|------|---------|
| `gr00t/policy/gr00t_policy.py` | Gr00tPolicy class, get_action, inference |
| `gr00t/policy/server_client.py` | ZMQ server/client |
| `gr00t/data/embodiment_tags.py` | EmbodimentTag enum + resolution |
| `gr00t/data/types.py` | ModalityConfig, observation schema |
| `gr00t/eval/run_gr00t_server.py` | Server launcher CLI |
| `scripts/deployment/build_trt_pipeline.py` | TRT engine build |
| `scripts/deployment/standalone_inference_script.py` | Inference demo |
| `scripts/deployment/trt_model_forward.py` | TRT forward functions |
| `examples/SO100/so100_config.py` | Example: custom embodiment modality config |

### Wire Format (msgpack over ZMQ)
```
Request:  {"endpoint": "get_action", "data": {"observation": {...}, "options": null}}
Response: [action_dict, info_dict]
  action_dict: {"action.joint_pos": ndarray(1, horizon, D)}
  info_dict:   {"inference_time_ms": float}
```

### Data Format (LeRobot)
- Episodes stored as parquet + video files
- `meta/episodes.jsonl` — episode metadata
- Observation keys follow modality config schema
- Action keys: `action.joint_pos`, `action.gripper`, etc.
