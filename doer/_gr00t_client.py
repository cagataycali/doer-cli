"""Thin ZMQ client wrapper for GR00T PolicyServer.

Isolated from doer/__init__.py so optional deps (pyzmq, msgpack, numpy, pillow)
don't break bare installs. Imported lazily by the `gr00t_action` tool and the
`--gr00t` CLI dispatch.

Protocol: REQ/REP over ZMQ, msgpack-framed payloads with numpy ndarray support.
Matches gr00t/policy/server_client.py wire format.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import msgpack  # type: ignore
    import numpy as np  # type: ignore
    import zmq  # type: ignore
except ImportError as _e:  # pragma: no cover - handled by caller
    raise ImportError(
        "gr00t extras not installed. Install with: pip install 'doer-cli[gr00t]'"
    ) from _e


# ─── ndarray codec (msgpack ext) ────────────────────────────────────────────
def _encode(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        buf = io.BytesIO()
        np.save(buf, obj, allow_pickle=False)
        return {"__ndarray_class__": True, "as_npy": buf.getvalue()}
    return obj


def _decode(obj: Any) -> Any:
    if isinstance(obj, dict) and obj.get("__ndarray_class__"):
        return np.load(io.BytesIO(obj["as_npy"]), allow_pickle=False)
    return obj


# ─── observation hydration ──────────────────────────────────────────────────
def _load_image(path: Path) -> "np.ndarray | None":
    """Load an image file → np.uint8 array with batch dim (1, H, W, 3)."""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return None
    try:
        arr = np.asarray(Image.open(path).convert("RGB"))
        return arr[None, ...]  # (1, H, W, 3)
    except Exception:
        return None


def _maybe_load_media(val: Any) -> Any:
    """Strings that point at existing image files get loaded to ndarrays."""
    if isinstance(val, str) and len(val) < 4096:
        try:
            p = Path(val).expanduser()
        except Exception:
            return val
        if p.exists() and p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}:
            arr = _load_image(p)
            if arr is not None:
                return arr
    return val


def _hydrate(obs: dict) -> dict:
    """Normalize observation dict values for GR00T policy server.

    Handles two input formats:
    1. **Flat keys** (pipe-mode convenience):
       ``{"state.left_arm": [0.1,...], "video.ego_view": "/tmp/cam.jpg"}``
       → restructured into nested ``{"state": {"left_arm": arr}, "video": {"ego_view": arr}}``
    2. **Nested dicts** (direct API):
       ``{"video": {"ego_view": arr}, "state": {...}, "language": {...}}``
       → values normalized in-place (lists→ndarray, paths→image).

    The GR00T PolicyServer's ``check_observation`` requires the nested format
    with top-level ``video``, ``state``, and ``language`` keys.

    Additional transforms:
    - Lists of numbers → ``np.ndarray(float32)``
    - File-path strings pointing to images → loaded ``np.uint8`` ndarray with batch dim
    - ``annotation.human.*`` flat keys → nested under ``"language"``
    - State arrays auto-wrapped to ``(1, 1, D)`` if 1-D
    - Video arrays auto-wrapped to ``(1, T, H, W, C)`` if missing batch dim
    """
    # Detect if keys are flat-style (contain dots like "state.left_arm")
    has_flat_keys = any("." in k for k in obs if k not in ("video", "state", "language"))
    has_nested_keys = any(k in ("video", "state", "language") and isinstance(obs[k], dict) for k in obs)

    if has_nested_keys and not has_flat_keys:
        # Already nested — just normalize values within each modality
        out: dict = {}
        for modality, sub in obs.items():
            if isinstance(sub, dict):
                out[modality] = {}
                for k, v in sub.items():
                    out[modality][k] = _normalize_value(k, v, modality)
            else:
                out[modality] = sub
        return out

    # Flat keys → restructure into nested format
    nested: dict = {"video": {}, "state": {}, "language": {}}
    extra: dict = {}

    for k, v in obs.items():
        if k.startswith("video."):
            subkey = k[len("video."):]
            nested["video"][subkey] = _normalize_value(subkey, v, "video")
        elif k.startswith("state."):
            subkey = k[len("state."):]
            nested["state"][subkey] = _normalize_value(subkey, v, "state")
        elif k.startswith("annotation.") or k.startswith("language."):
            # Language keys like "annotation.human.task_description"
            subkey = k[len("language."):] if k.startswith("language.") else k
            nested["language"][subkey] = v if isinstance(v, list) else [v]
        elif k in ("video", "state", "language"):
            # Top-level modality passed as non-dict (shouldn't happen, but handle)
            nested[k] = v
        else:
            extra[k] = v

    # Merge any extra keys into the appropriate modality or keep at top level
    for k, v in extra.items():
        nested[k] = v

    # Remove empty modalities to avoid confusing the server
    return {k: v for k, v in nested.items() if v}


def _normalize_value(key: str, v: Any, modality: str) -> Any:
    """Normalize a single observation value based on its modality."""
    if isinstance(v, np.ndarray):
        # Already an ndarray — just ensure correct shape
        if modality == "state" and v.ndim == 1:
            v = v.reshape(1, 1, -1)  # (D,) → (1, 1, D)
        elif modality == "state" and v.ndim == 2:
            v = v.reshape(1, *v.shape)  # (T, D) → (1, T, D)
        elif modality == "video" and v.ndim == 4:
            v = v[None, ...]  # (T, H, W, C) → (1, T, H, W, C)
        return v
    elif isinstance(v, list):
        try:
            arr = np.asarray(v, dtype=np.float32)
            if modality == "state":
                if arr.ndim == 1:
                    arr = arr.reshape(1, 1, -1)
                elif arr.ndim == 2:
                    arr = arr.reshape(1, *arr.shape)
            return arr
        except (TypeError, ValueError):
            return v
    elif isinstance(v, str):
        loaded = _maybe_load_media(v)
        if isinstance(loaded, np.ndarray) and modality == "video":
            # _load_image returns (1, H, W, 3) — need (1, T, H, W, 3)
            if loaded.ndim == 4:
                loaded = loaded[:, None, ...]  # (1, H, W, 3) → (1, 1, H, W, 3)
        return loaded
    return v


# ─── REQ/REP client (per-endpoint singleton cache) ──────────────────────────
class _Client:
    _instances: dict[str, "_Client"] = {}

    def __init__(self, host: str, port: int, timeout_ms: int, api_token: str | None):
        self.ctx = zmq.Context.instance()
        self.sock = self.ctx.socket(zmq.REQ)
        self.sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.sock.setsockopt(zmq.SNDTIMEO, timeout_ms)
        self.sock.setsockopt(zmq.LINGER, 0)
        self.sock.connect(f"tcp://{host}:{port}")
        self.api_token = api_token
        self.host = host
        self.port = port
        self.timeout_ms = timeout_ms

    @classmethod
    def get(cls) -> "_Client":
        host = os.environ.get("DOER_GR00T_HOST", "localhost")
        port = int(os.environ.get("DOER_GR00T_PORT", "5555"))
        tmo = int(os.environ.get("DOER_GR00T_TIMEOUT_MS", "15000"))
        tok = os.environ.get("DOER_GR00T_API_TOKEN") or None
        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = cls(host, port, tmo, tok)
        return cls._instances[key]

    @classmethod
    def invalidate(cls) -> None:
        """Force fresh socket on next call (ZMQ REQ state machine is strict)."""
        for c in list(cls._instances.values()):
            try:
                c.sock.close(linger=0)
            except Exception:
                pass
        cls._instances.clear()

    def call(self, endpoint: str, data: dict | None = None) -> Any:
        req: dict = {"endpoint": endpoint}
        if data is not None:
            req["data"] = data
        if self.api_token:
            req["api_token"] = self.api_token
        try:
            self.sock.send(msgpack.packb(req, default=_encode, use_bin_type=True))
            raw = self.sock.recv()
        except zmq.Again:
            # timeout → REQ socket is stuck, must rebuild
            _Client.invalidate()
            raise RuntimeError(
                f"gr00t timeout after {self.timeout_ms}ms (endpoint={endpoint})"
            )
        except zmq.ZMQError as e:
            _Client.invalidate()
            raise RuntimeError(f"gr00t zmq error: {e}")
        resp = msgpack.unpackb(raw, object_hook=_decode, raw=False)
        if isinstance(resp, dict) and "error" in resp:
            raise RuntimeError(resp["error"])
        return resp


# ─── JSON normalization (np → list for stdout) ──────────────────────────────
def _tojson(x: Any) -> Any:
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, dict):
        return {k: _tojson(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_tojson(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    return x


# ─── public API ─────────────────────────────────────────────────────────────
def call_gr00t(observation_json: str, instruction: str = "") -> str:
    """Send observation to GR00T policy server, return JSON action+info.

    Args:
        observation_json: JSON string of observation dict. Keys follow GR00T
            schema (e.g. 'video.webcam' as path, 'state.joint_pos' as list).
            Empty/non-JSON → treated as {}.
        instruction: Optional task description. Injected as
            'annotation.human.action.task_description' = [instruction].

    Returns:
        JSON string: {"action": {...}, "info": {...}}
    """
    obs_json_stripped = (observation_json or "").strip()
    if obs_json_stripped.startswith("{"):
        try:
            obs = json.loads(obs_json_stripped)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid observation JSON: {e}")
    else:
        obs = {}

    if instruction:
        # Support both flat and nested observation formats
        if "language" in obs and isinstance(obs["language"], dict):
            obs["language"].setdefault(
                "annotation.human.task_description", [[instruction]]
            )
        else:
            obs.setdefault(
                "annotation.human.action.task_description", [instruction]
            )

    obs = _hydrate(obs)
    client = _Client.get()
    resp = client.call("get_action", {"observation": obs, "options": None})

    # server_client returns a tuple [action, info] or sometimes a single dict
    if isinstance(resp, (list, tuple)) and len(resp) >= 1:
        action = resp[0]
        info = resp[1] if len(resp) > 1 else {}
    elif isinstance(resp, dict):
        action = resp
        info = {}
    else:
        action = resp
        info = {}

    return json.dumps(
        {"action": _tojson(action), "info": _tojson(info)},
        ensure_ascii=False,
    )


def ping() -> bool:
    """Health-check the server. Returns True if {status: ok}."""
    try:
        r = _Client.get().call("ping")
        if isinstance(r, dict):
            return r.get("status") == "ok"
        return False
    except Exception:
        return False


def reset(options: dict | None = None) -> str:
    """Reset an episode. Returns JSON string of server response."""
    data = {"options": options} if options is not None else {}
    resp = _Client.get().call("reset", data)
    return json.dumps(_tojson(resp), ensure_ascii=False)


def get_modality_config() -> str:
    """Fetch observation/action schema. Returns JSON string."""
    resp = _Client.get().call("get_modality_config")
    return json.dumps(_tojson(resp), ensure_ascii=False, default=str)


# ─── optional: auto-spawn server on Thor/CUDA host ──────────────────────────
def serve(
    model_path: str,
    embodiment_tag: str = "new_embodiment",
    host: str = "0.0.0.0",
    port: int = 5555,
    wait_ready: bool = True,
    ready_timeout_s: float = 60.0,
    extra_args: list[str] | None = None,
) -> subprocess.Popen:
    """Spawn `gr00t.eval.run_gr00t_server` as a subprocess.

    Returns the Popen handle so the caller can terminate/kill it. Blocks until
    the server answers `ping` (up to ready_timeout_s) when wait_ready=True.

    Caller must have `isaac-gr00t` installed in the active Python environment.
    Doer itself does not import `gr00t` — we just shell out to its launcher.
    """
    cmd = [
        sys.executable,
        "-m",
        "gr00t.eval.run_gr00t_server",
        "--model-path",
        str(model_path),
        "--embodiment-tag",
        embodiment_tag,
        "--host",
        host,
        "--port",
        str(port),
    ]
    if extra_args:
        cmd.extend(extra_args)

    sys.stderr.write(f"(doer --gr00t-serve: launching {' '.join(cmd)})\n")
    # inherit stdout/stderr so the user sees GR00T logs
    proc = subprocess.Popen(cmd)

    if not wait_ready:
        return proc

    # poll for readiness on localhost (regardless of bind host)
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::", "*") else host
    prev_host = os.environ.get("DOER_GR00T_HOST")
    prev_port = os.environ.get("DOER_GR00T_PORT")
    os.environ["DOER_GR00T_HOST"] = probe_host
    os.environ["DOER_GR00T_PORT"] = str(port)
    try:
        deadline = time.time() + ready_timeout_s
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"gr00t server exited early with code {proc.returncode}"
                )
            if ping():
                sys.stderr.write(
                    f"(doer --gr00t-serve: server ready on {probe_host}:{port})\n"
                )
                return proc
            _Client.invalidate()
            time.sleep(1.0)
        proc.terminate()
        raise RuntimeError(
            f"gr00t server did not become ready within {ready_timeout_s}s"
        )
    finally:
        # restore previous env — caller may re-set via --gr00t-host/--gr00t-port
        if prev_host is None:
            os.environ.pop("DOER_GR00T_HOST", None)
        else:
            os.environ["DOER_GR00T_HOST"] = prev_host
        if prev_port is None:
            os.environ.pop("DOER_GR00T_PORT", None)
        else:
            os.environ["DOER_GR00T_PORT"] = prev_port
