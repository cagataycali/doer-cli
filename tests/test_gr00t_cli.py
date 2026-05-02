"""End-to-end tests for the gr00t CLI subcommands using a mock server."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

import pytest

pytest.importorskip("zmq")
pytest.importorskip("msgpack")
pytest.importorskip("numpy")

# Reuse the mock server from the client test module
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_gr00t_client import MockGR00TServer, _free_port  # type: ignore


DOER_CMD = [sys.executable, "-m", "doer"]


@pytest.fixture
def server_env():
    port = _free_port()
    srv = MockGR00TServer(port)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)

    env = os.environ.copy()
    env["DOER_GR00T_HOST"] = "127.0.0.1"
    env["DOER_GR00T_PORT"] = str(port)
    env["DOER_GR00T_TIMEOUT_MS"] = "3000"

    yield env, srv
    srv.stop()
    t.join(timeout=2.0)


def test_cli_gr00t_ping(server_env):
    env, _ = server_env
    r = subprocess.run(DOER_CMD + ["--gr00t-ping"], env=env, capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr


def test_cli_gr00t_ping_missing_server():
    env = os.environ.copy()
    env["DOER_GR00T_HOST"] = "127.0.0.1"
    env["DOER_GR00T_PORT"] = str(_free_port())  # nothing listening
    env["DOER_GR00T_TIMEOUT_MS"] = "500"
    r = subprocess.run(DOER_CMD + ["--gr00t-ping"], env=env, capture_output=True, text=True, timeout=10)
    assert r.returncode == 1


def test_cli_gr00t_pipe_mode(server_env):
    env, _ = server_env
    obs = json.dumps({"state.joint_pos": [0.0] * 7})
    r = subprocess.run(
        DOER_CMD + ["--gr00t", "pick up cube"],
        input=obs, env=env, capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, r.stderr
    resp = json.loads(r.stdout.strip())
    assert "action" in resp and "info" in resp
    assert resp["info"]["saw_instruction"] == "pick up cube"


def test_cli_gr00t_schema(server_env):
    env, _ = server_env
    r = subprocess.run(DOER_CMD + ["--gr00t-schema"], env=env, capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout.strip())
    assert "state" in data and "action" in data


def test_cli_gr00t_reset(server_env):
    env, _ = server_env
    r1 = subprocess.run(DOER_CMD + ["--gr00t-reset"], env=env, capture_output=True, text=True, timeout=10)
    r2 = subprocess.run(DOER_CMD + ["--gr00t-reset"], env=env, capture_output=True, text=True, timeout=10)
    assert r1.returncode == 0 and r2.returncode == 0
    assert json.loads(r1.stdout.strip())["reset_count"] == 1
    assert json.loads(r2.stdout.strip())["reset_count"] == 2


def test_cli_flag_override_env(server_env):
    """--gr00t-host/--gr00t-port CLI flags override env when targeting server."""
    env, srv = server_env
    # Wipe env pointer — CLI flags must carry it
    clean_env = os.environ.copy()
    clean_env.pop("DOER_GR00T_HOST", None)
    clean_env.pop("DOER_GR00T_PORT", None)
    clean_env["DOER_GR00T_TIMEOUT_MS"] = "3000"

    r = subprocess.run(
        DOER_CMD + [
            "--gr00t-ping",
            "--gr00t-host", "127.0.0.1",
            "--gr00t-port", str(srv.port),
        ],
        env=clean_env, capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, r.stderr
