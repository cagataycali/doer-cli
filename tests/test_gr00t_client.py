"""Tests for doer._gr00t_client against a mock ZMQ REP server.

Run manually (requires optional extras):
    pip install 'doer-cli[gr00t]' pytest
    pytest tests/test_gr00t_client.py -v

The test spawns a toy msgpack REP server on an ephemeral port, then exercises
call_gr00t / ping / reset / get_modality_config over a real socket.
"""
from __future__ import annotations

import io
import json
import os
import socket
import threading
import time

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
    def __init__(self, port: int):
        self.port = port
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
                break  # socket closed by stop()
            if self.sock not in socks:
                continue
            try:
                raw = self.sock.recv()
            except zmq.ZMQError:
                break
            req = msgpack.unpackb(raw, object_hook=_dec_hook, raw=False)
            self.calls.append(req)
            endpoint = req.get("endpoint") if isinstance(req, dict) else None
            data = req.get("data", {}) if isinstance(req, dict) else {}
            if endpoint == "ping":
                resp = {"status": "ok"}
            elif endpoint == "kill":
                resp = {"status": "killed"}
                self.running = False
            elif endpoint == "get_modality_config":
                resp = {
                    "state": {"shape": [7], "dtype": "float32"},
                    "action": {"shape": [7], "dtype": "float32"},
                }
            elif endpoint == "reset":
                self.reset_count += 1
                resp = {"reset_count": self.reset_count}
            elif endpoint == "get_action":
                # echo joint_pos (batch=1, T=1) for determinism
                obs = data.get("observation", {})

                # Handle both flat and nested observation formats
                # (client _hydrate restructures flat → nested)
                state = obs.get("state", {})
                if isinstance(state, dict):
                    js = state.get("joint_pos")
                else:
                    js = obs.get("state.joint_pos")
                if isinstance(js, np.ndarray):
                    arr = js.astype(np.float32).reshape(1, -1)
                else:
                    arr = np.zeros((1, 7), dtype=np.float32)
                action = {"action.joint_pos": arr}

                # Extract instruction from nested or flat format
                saw = ""
                lang = obs.get("language", {})
                if isinstance(lang, dict):
                    # Nested: language.annotation.human.task_description
                    for lk, lv in lang.items():
                        if "task_description" in lk:
                            if isinstance(lv, list):
                                # Could be [[str]] or [str]
                                val = lv[0] if lv else ""
                                if isinstance(val, list):
                                    saw = val[0] if val else ""
                                else:
                                    saw = val
                            break
                if not saw:
                    # Flat: annotation.human.action.task_description
                    flat_td = obs.get("annotation.human.action.task_description", [""])
                    if isinstance(flat_td, list) and flat_td:
                        saw = flat_td[0] if isinstance(flat_td[0], str) else ""

                info = {
                    "inference_time_ms": 1.0,
                    "saw_instruction": saw,
                }
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
    time.sleep(0.1)  # let bind settle

    # point doer client at this server
    os.environ["DOER_GR00T_HOST"] = "127.0.0.1"
    os.environ["DOER_GR00T_PORT"] = str(port)
    os.environ["DOER_GR00T_TIMEOUT_MS"] = "3000"
    os.environ.pop("DOER_GR00T_API_TOKEN", None)

    # force-fresh client cache so each test gets a new socket
    from doer._gr00t_client import _Client
    _Client.invalidate()

    yield srv

    srv.stop()
    from doer._gr00t_client import _Client as C
    C.invalidate()
    t.join(timeout=2.0)


# ─── tests ──────────────────────────────────────────────────────────────────
def test_ping_ok(mock_server):
    from doer._gr00t_client import ping
    assert ping() is True


def test_get_modality_config(mock_server):
    from doer._gr00t_client import get_modality_config
    js = get_modality_config()
    data = json.loads(js)
    assert "state" in data and "action" in data


def test_reset(mock_server):
    from doer._gr00t_client import reset
    r1 = json.loads(reset())
    r2 = json.loads(reset())
    assert r1["reset_count"] == 1
    assert r2["reset_count"] == 2


def test_call_gr00t_basic(mock_server):
    from doer._gr00t_client import call_gr00t
    obs = json.dumps({"state.joint_pos": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]})
    resp = json.loads(call_gr00t(obs, instruction="pick up the cube"))
    assert "action" in resp and "info" in resp
    ap = resp["action"]["action.joint_pos"]
    # server echoes input joint_pos reshaped to (1, 7)
    assert len(ap) == 1 and len(ap[0]) == 7
    assert resp["info"]["saw_instruction"] == "pick up the cube"


def test_call_gr00t_instruction_only(mock_server):
    """Empty observation JSON, just an instruction — still valid."""
    from doer._gr00t_client import call_gr00t
    resp = json.loads(call_gr00t("{}", instruction="wave hello"))
    assert resp["info"]["saw_instruction"] == "wave hello"


def test_call_gr00t_invalid_json(mock_server):
    from doer._gr00t_client import call_gr00t
    with pytest.raises(ValueError):
        call_gr00t('{"not-json":,}', instruction="x")


def test_call_gr00t_non_dict_observation_ignored(mock_server):
    """Non-JSON observation string is treated as empty obs."""
    from doer._gr00t_client import call_gr00t
    resp = json.loads(call_gr00t("not a json", instruction="task"))
    assert "action" in resp


def test_instruction_does_not_overwrite_existing(mock_server):
    """If observation already has task_description, explicit arg is not injected."""
    from doer._gr00t_client import call_gr00t
    obs = json.dumps({
        "annotation.human.action.task_description": ["existing task"]
    })
    resp = json.loads(call_gr00t(obs, instruction="overriding task"))
    assert resp["info"]["saw_instruction"] == "existing task"
