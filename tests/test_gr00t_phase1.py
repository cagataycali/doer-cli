"""Tests for doer._gr00t_client Phase 1+2 enhancements.

Tests cover:
- T1.1: Reconnect logic (ZMQ REQ state machine recovery)
- T1.2: --gr00t-status (comprehensive server status)
- T1.3: Observation validation
- T1.4: Batch observation support
- T1.5: Video array (multi-frame) support
- T2.1: Control loop (run_loop)
- T2.2: Camera capture integration
- T2.5: Frequency control / timing stats

Run:
    pip install 'doer-cli[gr00t]' pytest
    pytest tests/test_gr00t_phase1.py -v
"""
from __future__ import annotations

import io
import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytest.importorskip("zmq")
pytest.importorskip("msgpack")
pytest.importorskip("numpy")

import msgpack  # noqa: E402
import numpy as np  # noqa: E402
import zmq  # noqa: E402


# ─── mock server (matches gr00t wire format) ────────────────────────────────
def _enc_hook(obj):
    if isinstance(obj, np.ndarray):
        buf = io.BytesIO()
        np.save(buf, obj, allow_pickle=False)
        return {"__ndarray_class__": True, "as_npy": buf.getvalue()}
    return obj


def _dec_hook(obj):
    if isinstance(obj, dict) and obj.get("__ndarray_class__"):
        return np.load(io.BytesIO(obj["as_npy"]), allow_pickle=False)
    return obj


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MockGR00TServer:
    """Enhanced mock server with configurable delays and failure modes."""

    def __init__(self, port: int, delay_ms: float = 0, fail_count: int = 0):
        self.port = port
        self.delay_ms = delay_ms
        self.fail_count = fail_count  # Number of initial requests to drop (no reply)
        self._request_count = 0
        self.ctx = zmq.Context.instance()
        self.sock = self.ctx.socket(zmq.REP)
        self.sock.bind(f"tcp://127.0.0.1:{port}")
        self.running = True
        self.calls: list[dict] = []
        self.reset_count = 0

    def stop(self):
        self.running = False
        try:
            self.sock.close(linger=0)
        except Exception:
            pass

    def serve_forever(self):
        poller = zmq.Poller()
        poller.register(self.sock, zmq.POLLIN)
        while self.running:
            try:
                socks = dict(poller.poll(timeout=100))
            except zmq.ZMQError:
                break
            if self.sock not in socks:
                continue
            try:
                raw = self.sock.recv()
            except zmq.ZMQError:
                break

            self._request_count += 1
            req = msgpack.unpackb(raw, object_hook=_dec_hook, raw=False)
            self.calls.append(req)

            # Simulate delay
            if self.delay_ms > 0:
                time.sleep(self.delay_ms / 1000.0)

            endpoint = req.get("endpoint") if isinstance(req, dict) else None
            data = req.get("data", {}) if isinstance(req, dict) else {}

            if endpoint == "ping":
                resp = {"status": "ok", "message": "Server is running"}
            elif endpoint == "kill":
                resp = {"status": "killed"}
                self.running = False
            elif endpoint == "get_modality_config":
                resp = {
                    "state": {"shape": [7], "dtype": "float32"},
                    "action": {"shape": [7], "dtype": "float32"},
                    "video": {"shape": [480, 640, 3], "dtype": "uint8"},
                }
            elif endpoint == "reset":
                self.reset_count += 1
                resp = {"reset_count": self.reset_count}
            elif endpoint == "get_action":
                obs = data.get("observation", {})
                state = obs.get("state", {})
                if isinstance(state, dict):
                    js = state.get("joint_pos")
                else:
                    js = None
                if isinstance(js, np.ndarray):
                    arr = js.astype(np.float32).reshape(1, -1)
                else:
                    arr = np.zeros((1, 7), dtype=np.float32)
                action = {"action.joint_pos": arr}

                # Extract instruction
                saw = ""
                lang = obs.get("language", {})
                if isinstance(lang, dict):
                    for lk, lv in lang.items():
                        if "task_description" in lk:
                            if isinstance(lv, list):
                                val = lv[0] if lv else ""
                                if isinstance(val, list):
                                    saw = val[0] if val else ""
                                else:
                                    saw = val
                            break
                if not saw:
                    flat_td = obs.get("annotation.human.action.task_description", [""])
                    if isinstance(flat_td, list) and flat_td:
                        saw = flat_td[0] if isinstance(flat_td[0], str) else ""

                info = {"inference_time_ms": 5.0, "saw_instruction": saw}
                resp = [action, info]
            else:
                resp = {"error": f"unknown endpoint: {endpoint}"}
            self.sock.send(msgpack.packb(resp, default=_enc_hook, use_bin_type=True))


@pytest.fixture
def mock_server():
    port = _free_port()
    srv = MockGR00TServer(port)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)

    os.environ["DOER_GR00T_HOST"] = "127.0.0.1"
    os.environ["DOER_GR00T_PORT"] = str(port)
    os.environ["DOER_GR00T_TIMEOUT_MS"] = "3000"
    os.environ["DOER_GR00T_RETRIES"] = "2"
    os.environ.pop("DOER_GR00T_API_TOKEN", None)

    from doer._gr00t_client import _Client
    _Client.invalidate()

    yield srv

    srv.stop()
    from doer._gr00t_client import _Client as C
    C.invalidate()
    t.join(timeout=2.0)


@pytest.fixture
def slow_server():
    """Server that responds slowly (500ms delay)."""
    port = _free_port()
    srv = MockGR00TServer(port, delay_ms=500)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)

    os.environ["DOER_GR00T_HOST"] = "127.0.0.1"
    os.environ["DOER_GR00T_PORT"] = str(port)
    os.environ["DOER_GR00T_TIMEOUT_MS"] = "2000"
    os.environ["DOER_GR00T_RETRIES"] = "1"
    os.environ.pop("DOER_GR00T_API_TOKEN", None)

    from doer._gr00t_client import _Client
    _Client.invalidate()

    yield srv

    srv.stop()
    from doer._gr00t_client import _Client as C
    C.invalidate()
    t.join(timeout=2.0)


# ─── T1.1: Reconnect Logic ─────────────────────────────────────────────────
class TestReconnect:
    def test_client_recovers_after_timeout(self):
        """Client should recreate socket and succeed on retry after timeout."""
        port = _free_port()
        # Start with no server → first call will timeout
        os.environ["DOER_GR00T_HOST"] = "127.0.0.1"
        os.environ["DOER_GR00T_PORT"] = str(port)
        os.environ["DOER_GR00T_TIMEOUT_MS"] = "500"
        os.environ["DOER_GR00T_RETRIES"] = "3"

        from doer._gr00t_client import _Client, ping
        _Client.invalidate()

        # No server → should fail after retries
        assert ping() is False

        # Now start a server on that port
        srv = MockGR00TServer(port)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)

        # Fresh client should now succeed
        _Client.invalidate()
        assert ping() is True

        srv.stop()
        _Client.invalidate()
        t.join(timeout=2.0)

    def test_health_tracking(self, mock_server):
        """Client tracks consecutive failures and success stats."""
        from doer._gr00t_client import _Client, ping
        assert ping() is True

        client = _Client.get()
        health = client.health
        assert health["total_calls"] >= 1
        assert health["consecutive_failures"] == 0
        assert health["last_success"] is not None
        assert health["last_latency_ms"] > 0

    def test_retry_with_backoff(self):
        """Client retries with exponential backoff."""
        port = _free_port()
        os.environ["DOER_GR00T_HOST"] = "127.0.0.1"
        os.environ["DOER_GR00T_PORT"] = str(port)
        os.environ["DOER_GR00T_TIMEOUT_MS"] = "200"
        os.environ["DOER_GR00T_RETRIES"] = "2"

        from doer._gr00t_client import _Client
        _Client.invalidate()

        client = _Client.get()
        t0 = time.monotonic()
        with pytest.raises(RuntimeError, match="timeout"):
            client.call("ping")
        elapsed = time.monotonic() - t0

        # With 200ms timeout and 2 retries (backoff 0.5s + 1.0s):
        # total ≈ 3 × 200ms timeout + 0.5s + 1.0s = ~2.1s minimum
        assert elapsed >= 1.5  # At least some backoff happened
        assert client._consecutive_failures == 3  # 1 initial + 2 retries
        _Client.invalidate()


# ─── T1.2: Status Command ──────────────────────────────────────────────────
class TestStatus:
    def test_status_connected(self, mock_server):
        from doer._gr00t_client import status
        result = json.loads(status())
        assert result["connected"] is True
        assert result["ping_latency_ms"] > 0
        assert result["modality_config"] is not None
        assert "state" in result["modality_config"]
        assert result["error"] is None

    def test_status_disconnected(self):
        """Status reports disconnection gracefully."""
        port = _free_port()
        os.environ["DOER_GR00T_HOST"] = "127.0.0.1"
        os.environ["DOER_GR00T_PORT"] = str(port)
        os.environ["DOER_GR00T_TIMEOUT_MS"] = "200"
        os.environ["DOER_GR00T_RETRIES"] = "0"

        from doer._gr00t_client import _Client, status
        _Client.invalidate()

        result = json.loads(status())
        assert result["connected"] is False
        assert result["error"] is not None
        _Client.invalidate()

    def test_status_includes_endpoint_info(self, mock_server):
        from doer._gr00t_client import status
        result = json.loads(status())
        assert "server_endpoint" in result
        assert "127.0.0.1" in result["server_endpoint"]
        assert result["embodiment"] == "new_embodiment"


# ─── T1.3: Observation Validation ──────────────────────────────────────────
class TestValidation:
    def test_validate_valid_observation(self, mock_server):
        from doer._gr00t_client import validate_observation
        obs = {
            "state": {"joint_pos": np.zeros((1, 1, 7), dtype=np.float32)},
            "video": {"webcam": np.zeros((1, 1, 480, 640, 3), dtype=np.uint8)},
        }
        warnings = validate_observation(obs)
        assert len(warnings) == 0

    def test_validate_missing_modality(self, mock_server):
        from doer._gr00t_client import validate_observation
        obs = {"video": {"webcam": np.zeros((1, 1, 480, 640, 3), dtype=np.uint8)}}
        warnings = validate_observation(obs)
        # Should warn about missing state
        assert any("state" in w for w in warnings)

    def test_validate_wrong_shape(self, mock_server):
        from doer._gr00t_client import validate_observation
        obs = {
            "state": {"joint_pos": np.zeros((1, 1, 3), dtype=np.float32)},  # Wrong: 3 not 7
            "video": {"webcam": np.zeros((1, 1, 480, 640, 3), dtype=np.uint8)},
        }
        warnings = validate_observation(obs)
        assert any("shape" in w for w in warnings)

    def test_validate_with_explicit_config(self):
        from doer._gr00t_client import validate_observation
        config = {"state": {"shape": [6]}, "video": {"shape": [224, 224, 3]}}
        obs = {
            "state": {"joint_pos": np.zeros((1, 1, 6), dtype=np.float32)},
            "video": {"cam": np.zeros((1, 1, 224, 224, 3), dtype=np.uint8)},
        }
        warnings = validate_observation(obs, modality_config=config)
        assert len(warnings) == 0


# ─── T1.4/T1.5: Batch and Video Array Support ──────────────────────────────
class TestBatchAndVideo:
    def test_hydrate_multi_frame_video(self):
        from doer._gr00t_client import _hydrate
        # Multi-frame video: (T, H, W, 3) auto-wrapped to (1, T, H, W, 3)
        frames = np.random.randint(0, 255, (5, 480, 640, 3), dtype=np.uint8)
        obs = {"video": {"webcam": frames}}
        result = _hydrate(obs)
        assert result["video"]["webcam"].shape == (1, 5, 480, 640, 3)

    def test_hydrate_batch_state(self):
        from doer._gr00t_client import _hydrate
        # Multi-timestep state: (T, D) → (1, T, D)
        state = np.random.randn(3, 7).astype(np.float32)
        obs = {"state": {"joint_pos": state}}
        result = _hydrate(obs)
        assert result["state"]["joint_pos"].shape == (1, 3, 7)

    def test_call_with_video_array(self, mock_server):
        from doer._gr00t_client import call_gr00t, _tojson
        # Prepare multi-frame observation as flat keys
        frames = np.random.randint(0, 255, (1, 2, 480, 640, 3), dtype=np.uint8)
        obs = {
            "video.webcam": _tojson(frames),
            "state.joint_pos": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        }
        resp = json.loads(call_gr00t(json.dumps(obs), instruction="grab"))
        assert "action" in resp


# ─── T2.1: Control Loop ────────────────────────────────────────────────────
class TestControlLoop:
    def test_loop_basic(self, mock_server):
        """run_loop completes max_steps iterations."""
        from doer._gr00t_client import run_loop
        import io as _io

        output = _io.StringIO()
        stats = run_loop(
            instruction="pick up cube",
            target_hz=100,  # fast — no real timing
            camera_device=-1,  # disable camera
            max_steps=5,
            reset_on_start=True,
            output_file=output,
            quiet=True,
        )

        assert stats["steps"] == 5
        assert stats["exit_reason"] == "max_steps"
        assert stats["avg_hz"] > 0
        assert stats["avg_inference_ms"] > 0

        # Check output lines are valid JSON
        lines = output.getvalue().strip().split("\n")
        assert len(lines) == 5
        for line in lines:
            d = json.loads(line)
            assert "action" in d
            assert "step" in d

    def test_loop_with_state_file(self, mock_server):
        """run_loop reads state from a file each step."""
        from doer._gr00t_client import run_loop
        import io as _io

        # Create state file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], f)
            state_path = f.name

        try:
            output = _io.StringIO()
            stats = run_loop(
                instruction="move arm",
                target_hz=100,
                camera_device=-1,
                state_source=state_path,
                state_key="joint_pos",
                max_steps=3,
                output_file=output,
                quiet=True,
            )
            assert stats["steps"] == 3
        finally:
            os.unlink(state_path)

    def test_loop_with_callable_state(self, mock_server):
        """run_loop accepts a callable for state source."""
        from doer._gr00t_client import run_loop
        import io as _io

        call_count = [0]

        def state_fn():
            call_count[0] += 1
            return [float(call_count[0])] * 7

        output = _io.StringIO()
        stats = run_loop(
            instruction="task",
            target_hz=100,
            camera_device=-1,
            state_source=state_fn,
            max_steps=4,
            output_file=output,
            quiet=True,
        )
        assert stats["steps"] == 4
        assert call_count[0] == 4

    def test_loop_on_action_callback(self, mock_server):
        """on_action callback is invoked per step."""
        from doer._gr00t_client import run_loop
        import io as _io

        actions_seen = []

        def on_action(action, info):
            actions_seen.append(action)

        output = _io.StringIO()
        run_loop(
            instruction="task",
            target_hz=100,
            camera_device=-1,
            max_steps=3,
            output_file=output,
            on_action=on_action,
            quiet=True,
        )
        assert len(actions_seen) == 3

    def test_loop_resets_on_start(self, mock_server):
        """run_loop calls reset() when reset_on_start=True."""
        from doer._gr00t_client import run_loop
        import io as _io

        output = _io.StringIO()
        run_loop(
            instruction="task",
            target_hz=100,
            camera_device=-1,
            max_steps=1,
            reset_on_start=True,
            output_file=output,
            quiet=True,
        )
        assert mock_server.reset_count >= 1

    def test_loop_no_reset(self, mock_server):
        """run_loop skips reset when reset_on_start=False."""
        from doer._gr00t_client import run_loop
        import io as _io

        initial_resets = mock_server.reset_count
        output = _io.StringIO()
        run_loop(
            instruction="task",
            target_hz=100,
            camera_device=-1,
            max_steps=1,
            reset_on_start=False,
            output_file=output,
            quiet=True,
        )
        assert mock_server.reset_count == initial_resets


# ─── T2.2: Camera Capture ──────────────────────────────────────────────────
class TestCameraCapture:
    def test_capture_frame_mock(self):
        """capture_frame returns correct shape with mocked cv2."""
        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        # Simulate a BGR frame
        fake_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)
        # cvtColor just returns the same shape (mocked)
        mock_cv2.cvtColor.return_value = fake_frame
        mock_cv2.COLOR_BGR2RGB = 4
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            from doer._gr00t_client import capture_frame
            frame = capture_frame(device=0, width=640, height=480)
            assert frame.shape == (1, 1, 480, 640, 3)
            assert frame.dtype == np.uint8

    def test_capture_frame_camera_not_opened(self):
        """capture_frame raises RuntimeError when camera fails to open."""
        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = False

        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            from doer._gr00t_client import capture_frame
            with pytest.raises(RuntimeError, match="cannot open camera"):
                capture_frame(device=99)


# ─── T2.5: Frequency Control ───────────────────────────────────────────────
class TestFrequencyControl:
    def test_target_hz_respected(self, mock_server):
        """Loop respects target Hz (approximately)."""
        from doer._gr00t_client import run_loop
        import io as _io

        output = _io.StringIO()
        t0 = time.monotonic()
        stats = run_loop(
            instruction="task",
            target_hz=20,  # 50ms per step
            camera_device=-1,
            max_steps=5,
            output_file=output,
            quiet=True,
        )
        elapsed = time.monotonic() - t0

        # 5 steps at 20Hz = 250ms minimum (+ some server latency)
        assert elapsed >= 0.2
        # But shouldn't take more than 2 seconds even with some overhead
        assert elapsed < 2.0
        # Average Hz should be roughly in the ballpark
        assert stats["avg_hz"] > 5  # At least some steps happened
