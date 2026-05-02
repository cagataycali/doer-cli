"""Thin ZMQ client wrapper for GR00T PolicyServer.

Isolated from doer/__init__.py so optional deps (pyzmq, msgpack, numpy, pillow)
don't break bare installs. Imported lazily by the `gr00t_action` tool and the
`--gr00t` CLI dispatch.

Protocol: REQ/REP over ZMQ, msgpack-framed payloads with numpy ndarray support.
Matches gr00t/policy/server_client.py wire format.

## Phase 1 enhancements (v0.9.0):
- Automatic reconnect on ZMQ state machine corruption (REQ stuck after timeout)
- Configurable retry with exponential backoff
- Connection health tracking (consecutive failures, last success time)
- `status()` — comprehensive server status (ping + modality config + timing)
- Observation validation against modality config schema
- Batch observation support (multi-timestep)
- Video array support (multi-frame)

## Phase 2 enhancements (v0.9.0):
- `run_loop()` — continuous obs→action control loop at target Hz
- Camera capture via OpenCV (v4l2/USB/CSI)
- State reader (stdin pipe, file, or callable)
- Action writer (stdout JSON lines, pipeable)
- Frequency control with timing stats
- Episode management (reset at start, graceful termination)
"""
from __future__ import annotations

import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

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


# ─── REQ/REP client with reconnect ─────────────────────────────────────────
class _Client:
    """ZMQ REQ client with automatic reconnect and retry logic.

    ZMQ REQ sockets have a strict state machine: send → recv → send → recv.
    If recv times out, the socket is stuck and cannot send again. This client
    automatically destroys and recreates the socket when that happens.

    Retry policy:
    - Up to DOER_GR00T_RETRIES attempts (default: 3)
    - Exponential backoff between retries (0.5s, 1s, 2s, ...)
    - Socket recreated after each failure
    - Gives up after max retries and raises RuntimeError
    """

    _instances: dict[str, "_Client"] = {}

    def __init__(self, host: str, port: int, timeout_ms: int, api_token: str | None,
                 max_retries: int = 3):
        self.ctx = zmq.Context.instance()
        self.host = host
        self.port = port
        self.timeout_ms = timeout_ms
        self.api_token = api_token
        self.max_retries = max_retries

        # Health tracking
        self._consecutive_failures = 0
        self._total_calls = 0
        self._total_failures = 0
        self._last_success_time: float | None = None
        self._last_failure_time: float | None = None
        self._last_latency_ms: float = 0.0
        self._latencies: list[float] = []  # rolling window of last 100

        self._init_socket()

    def _init_socket(self) -> None:
        """Create a fresh REQ socket."""
        if hasattr(self, "sock") and self.sock is not None:
            try:
                self.sock.close(linger=0)
            except Exception:
                pass
        self.sock = self.ctx.socket(zmq.REQ)
        self.sock.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        self.sock.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
        self.sock.setsockopt(zmq.LINGER, 0)
        # TCP keepalive to detect dead connections
        self.sock.setsockopt(zmq.TCP_KEEPALIVE, 1)
        self.sock.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 10)
        self.sock.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 5)
        self.sock.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)
        self.sock.connect(f"tcp://{self.host}:{self.port}")

    @classmethod
    def get(cls) -> "_Client":
        host = os.environ.get("DOER_GR00T_HOST", "localhost")
        port = int(os.environ.get("DOER_GR00T_PORT", "5555"))
        tmo = int(os.environ.get("DOER_GR00T_TIMEOUT_MS", "15000"))
        tok = os.environ.get("DOER_GR00T_API_TOKEN") or None
        retries = int(os.environ.get("DOER_GR00T_RETRIES", "3"))
        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = cls(host, port, tmo, tok, retries)
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

    @property
    def health(self) -> dict:
        """Current connection health stats."""
        return {
            "host": self.host,
            "port": self.port,
            "timeout_ms": self.timeout_ms,
            "max_retries": self.max_retries,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "consecutive_failures": self._consecutive_failures,
            "last_success": self._last_success_time,
            "last_failure": self._last_failure_time,
            "last_latency_ms": self._last_latency_ms,
            "avg_latency_ms": (sum(self._latencies) / len(self._latencies)
                               if self._latencies else 0.0),
        }

    def call(self, endpoint: str, data: dict | None = None) -> Any:
        """Call an endpoint with automatic retry and reconnect.

        On timeout or ZMQ error:
        1. Recreates the socket (fixes REQ state machine)
        2. Retries with exponential backoff
        3. Raises RuntimeError after max_retries exhausted
        """
        req: dict = {"endpoint": endpoint}
        if data is not None:
            req["data"] = data
        if self.api_token:
            req["api_token"] = self.api_token

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._total_calls += 1
            t0 = time.monotonic()
            try:
                self.sock.send(msgpack.packb(req, default=_encode, use_bin_type=True))
                raw = self.sock.recv()
                elapsed_ms = (time.monotonic() - t0) * 1000

                # Success — update health
                self._consecutive_failures = 0
                self._last_success_time = time.time()
                self._last_latency_ms = elapsed_ms
                self._latencies.append(elapsed_ms)
                if len(self._latencies) > 100:
                    self._latencies = self._latencies[-100:]

                resp = msgpack.unpackb(raw, object_hook=_decode, raw=False)
                if isinstance(resp, dict) and "error" in resp:
                    raise RuntimeError(resp["error"])
                return resp

            except zmq.Again:
                # Timeout — socket stuck, must rebuild
                last_error = RuntimeError(
                    f"gr00t timeout after {self.timeout_ms}ms "
                    f"(endpoint={endpoint}, attempt={attempt + 1}/{self.max_retries + 1})"
                )
            except zmq.ZMQError as e:
                last_error = RuntimeError(f"gr00t zmq error: {e}")
            except RuntimeError:
                raise  # Server-side errors (from response) propagate immediately

            # Failure — update health, reconnect, backoff
            self._consecutive_failures += 1
            self._total_failures += 1
            self._last_failure_time = time.time()
            self._init_socket()

            if attempt < self.max_retries:
                backoff = 0.5 * (2 ** attempt)  # 0.5, 1.0, 2.0, ...
                time.sleep(backoff)

        # All retries exhausted
        raise last_error or RuntimeError(f"gr00t call failed after {self.max_retries + 1} attempts")


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


# ─── T1.2: comprehensive status ────────────────────────────────────────────
def status() -> str:
    """Comprehensive server status: connectivity, modality config, timing, health.

    Returns JSON with:
      - connected: bool
      - ping_latency_ms: float
      - modality_config: dict | null
      - embodiment: str (from env)
      - server_endpoint: str
      - client_health: dict (consecutive failures, avg latency, etc.)
    """
    host = os.environ.get("DOER_GR00T_HOST", "localhost")
    port = int(os.environ.get("DOER_GR00T_PORT", "5555"))
    embodiment = os.environ.get("DOER_GR00T_EMBODIMENT", "new_embodiment")

    result: dict[str, Any] = {
        "server_endpoint": f"tcp://{host}:{port}",
        "embodiment": embodiment,
        "connected": False,
        "ping_latency_ms": None,
        "modality_config": None,
        "client_health": None,
        "error": None,
    }

    try:
        client = _Client.get()
        result["client_health"] = client.health

        # Ping with timing
        t0 = time.monotonic()
        r = client.call("ping")
        ping_ms = (time.monotonic() - t0) * 1000
        if isinstance(r, dict) and r.get("status") == "ok":
            result["connected"] = True
            result["ping_latency_ms"] = round(ping_ms, 2)
        else:
            result["error"] = f"unexpected ping response: {r}"
            return json.dumps(result, ensure_ascii=False, default=str)

        # Modality config
        try:
            config_resp = client.call("get_modality_config")
            result["modality_config"] = _tojson(config_resp)
        except Exception as e:
            result["modality_config"] = f"(unavailable: {e})"

    except Exception as e:
        result["error"] = str(e)

    return json.dumps(result, ensure_ascii=False, default=str)


# ─── T1.3: observation validation ──────────────────────────────────────────
def validate_observation(obs: dict, modality_config: dict | None = None) -> list[str]:
    """Validate an observation dict against the server's modality config.

    Returns a list of warning/error strings. Empty list = valid.
    If modality_config is None, fetches from server.
    """
    warnings: list[str] = []

    if modality_config is None:
        try:
            raw = get_modality_config()
            modality_config = json.loads(raw)
        except Exception as e:
            return [f"cannot fetch modality config: {e}"]

    # Check required modalities exist
    for modality in ("state", "video"):
        if modality in modality_config and modality not in obs:
            warnings.append(f"missing required modality: {modality}")

    # Check shapes if config provides them
    for modality, config in modality_config.items():
        if modality not in obs:
            continue
        if isinstance(config, dict) and "shape" in config:
            expected_shape = config["shape"]
            sub = obs[modality]
            if isinstance(sub, dict):
                for key, val in sub.items():
                    if isinstance(val, np.ndarray):
                        # Check last dimensions match (batch/time dims are flexible)
                        actual_tail = list(val.shape[-len(expected_shape):])
                        if actual_tail != expected_shape:
                            warnings.append(
                                f"{modality}.{key}: shape {list(val.shape)} "
                                f"tail doesn't match expected {expected_shape}"
                            )

    return warnings


# ─── Phase 2: camera capture ────────────────────────────────────────────────
def capture_frame(
    device: int | str = 0,
    width: int = 640,
    height: int = 480,
) -> np.ndarray:
    """Capture a single frame from a camera device via OpenCV.

    Args:
        device: Camera device index (int) or device path (str like "/dev/video0")
        width: Desired frame width
        height: Desired frame height

    Returns:
        np.ndarray of shape (1, 1, H, W, 3) uint8 — ready for GR00T video input

    Raises:
        RuntimeError: If camera open/read fails
    """
    try:
        import cv2  # type: ignore
    except ImportError:
        raise ImportError(
            "camera capture requires opencv: pip install opencv-python-headless"
        )

    cap = cv2.VideoCapture(device if isinstance(device, int) else str(device))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open camera device: {device}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError(f"failed to read frame from camera: {device}")

    # OpenCV returns BGR, GR00T expects RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # Shape: (H, W, 3) → (1, 1, H, W, 3) for batch=1, timestep=1
    return frame_rgb[None, None, ...]


# ─── Phase 2: control loop ─────────────────────────────────────────────────
def run_loop(
    instruction: str,
    target_hz: float = 10.0,
    camera_device: int | str = 0,
    camera_width: int = 640,
    camera_height: int = 480,
    camera_name: str = "webcam",
    state_source: str | Callable | None = None,
    state_key: str = "joint_pos",
    max_steps: int = 0,
    reset_on_start: bool = True,
    output_file: Any = None,
    on_action: Callable[[dict, dict], None] | None = None,
    quiet: bool = False,
) -> dict:
    """Run a continuous observation → GR00T → action control loop.

    This is the core of `doer --gr00t-loop`: capture camera + state → send to
    GR00T server → output action → repeat at target Hz.

    Args:
        instruction: Natural-language task description for GR00T
        target_hz: Target loop frequency in Hz (default: 10 = 100ms per step)
        camera_device: OpenCV camera index or path (set to -1 to disable camera)
        camera_width: Camera resolution width
        camera_height: Camera resolution height
        camera_name: Name for the camera key in observation (e.g. "webcam", "ego_view")
        state_source: Where to read robot state from:
            - None: no state (video-only)
            - str: path to file (re-read each step, JSON array of floats)
            - callable: function() → list[float] or np.ndarray
        state_key: Key name for state in observation (e.g. "joint_pos")
        max_steps: Maximum steps (0 = infinite, stop with Ctrl+C)
        reset_on_start: Whether to call reset() on the server before starting
        output_file: File object to write action JSON lines to (default: stdout)
        on_action: Optional callback(action_dict, info_dict) per step
        quiet: Suppress timing stats on stderr

    Returns:
        dict with loop statistics:
          - steps: int (total steps completed)
          - elapsed_s: float (total wall time)
          - avg_hz: float (actual average frequency)
          - avg_inference_ms: float (server inference time)
          - avg_loop_ms: float (total loop time per step)
          - exit_reason: str ("max_steps" | "interrupted" | "error")
    """
    if output_file is None:
        output_file = sys.stdout

    use_camera = camera_device != -1
    client = _Client.get()
    period_s = 1.0 / target_hz if target_hz > 0 else 0.0

    # Reset episode
    if reset_on_start:
        try:
            client.call("reset", {"options": None})
        except Exception as e:
            sys.stderr.write(f"(doer: reset failed: {e}, continuing anyway)\n")

    # Stats
    steps = 0
    inference_times: list[float] = []
    loop_times: list[float] = []
    start_time = time.monotonic()
    exit_reason = "unknown"

    # Signal handling for graceful shutdown
    _interrupted = False

    def _sigint_handler(sig, frame):
        nonlocal _interrupted
        _interrupted = True

    old_handler = signal.signal(signal.SIGINT, _sigint_handler)

    try:
        while not _interrupted:
            if max_steps > 0 and steps >= max_steps:
                exit_reason = "max_steps"
                break

            loop_start = time.monotonic()

            # 1. Build observation
            obs: dict = {}

            # Camera capture
            if use_camera:
                try:
                    frame = capture_frame(camera_device, camera_width, camera_height)
                    obs[f"video.{camera_name}"] = frame
                except Exception as e:
                    sys.stderr.write(f"(doer: camera error step {steps}: {e})\n")
                    # Use blank frame on failure
                    obs[f"video.{camera_name}"] = np.zeros(
                        (1, 1, camera_height, camera_width, 3), dtype=np.uint8
                    )

            # State reading
            if state_source is not None:
                try:
                    if callable(state_source):
                        state_val = state_source()
                    elif isinstance(state_source, str):
                        # Read from file (re-read each step for live updates)
                        state_text = Path(state_source).read_text().strip()
                        state_val = json.loads(state_text)
                    else:
                        state_val = None

                    if state_val is not None:
                        if isinstance(state_val, list):
                            state_val = np.asarray(state_val, dtype=np.float32)
                        obs[f"state.{state_key}"] = state_val
                except Exception as e:
                    sys.stderr.write(f"(doer: state read error step {steps}: {e})\n")

            # Language instruction
            obs["annotation.human.action.task_description"] = [instruction]

            # 2. Hydrate and send to server
            hydrated = _hydrate(obs)
            try:
                resp = client.call("get_action", {"observation": hydrated, "options": None})
            except RuntimeError as e:
                sys.stderr.write(f"(doer: inference error step {steps}: {e})\n")
                exit_reason = "error"
                break

            # 3. Parse response
            if isinstance(resp, (list, tuple)) and len(resp) >= 1:
                action = resp[0]
                info = resp[1] if len(resp) > 1 else {}
            elif isinstance(resp, dict):
                action = resp
                info = {}
            else:
                action = resp
                info = {}

            # Track inference time
            inf_time = info.get("inference_time_ms", 0.0) if isinstance(info, dict) else 0.0
            inference_times.append(inf_time)

            # 4. Output action
            action_json = json.dumps(
                {"action": _tojson(action), "info": _tojson(info), "step": steps},
                ensure_ascii=False,
            )
            output_file.write(action_json + "\n")
            output_file.flush()

            # 5. Callback
            if on_action:
                try:
                    on_action(action, info)
                except Exception as e:
                    sys.stderr.write(f"(doer: on_action callback error: {e})\n")

            steps += 1
            loop_end = time.monotonic()
            loop_ms = (loop_end - loop_start) * 1000
            loop_times.append(loop_ms)

            # 6. Timing stats (every 50 steps)
            if not quiet and steps % 50 == 0:
                avg_loop = sum(loop_times[-50:]) / min(50, len(loop_times))
                avg_inf = sum(inference_times[-50:]) / min(50, len(inference_times))
                actual_hz = 1000.0 / avg_loop if avg_loop > 0 else 0
                sys.stderr.write(
                    f"(doer: step={steps} hz={actual_hz:.1f} "
                    f"loop={avg_loop:.1f}ms inf={avg_inf:.1f}ms)\n"
                )

            # 7. Rate limiting (sleep to hit target Hz)
            elapsed = loop_end - loop_start
            sleep_time = period_s - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        if _interrupted:
            exit_reason = "interrupted"

    finally:
        signal.signal(signal.SIGINT, old_handler)

    # Build stats
    total_elapsed = time.monotonic() - start_time
    stats = {
        "steps": steps,
        "elapsed_s": round(total_elapsed, 3),
        "avg_hz": round(steps / total_elapsed, 2) if total_elapsed > 0 else 0,
        "avg_inference_ms": round(sum(inference_times) / len(inference_times), 2) if inference_times else 0,
        "avg_loop_ms": round(sum(loop_times) / len(loop_times), 2) if loop_times else 0,
        "exit_reason": exit_reason,
    }

    if not quiet:
        sys.stderr.write(f"(doer: loop done — {json.dumps(stats)})\n")

    return stats


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
