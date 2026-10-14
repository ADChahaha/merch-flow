"""Source AND shipping executable: CLI, ACP, HTTP job API and SQLite roundtrip.

Set MERCH_TEST_BACKEND to the built executable; CI must supply it after freezing.
The only fake is the external ACP peer. No paid model or remote site is used.
"""

import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest

from app.agent.processes import kill_process_tree

BACKEND = Path(__file__).resolve().parents[1]
SAMPLE = "中文・日本語・缶バッジ 🛍️"


@pytest.fixture(params=["source", "frozen"])
def backend_command(request):
    if request.param == "source":
        return [sys.executable, str(BACKEND / "run.py")]
    binary = os.getenv("MERCH_TEST_BACKEND")
    if not binary:
        pytest.skip("Set MERCH_TEST_BACKEND after building the shipping executable")
    executable = Path(binary).resolve()
    assert executable.is_file(), f"Missing packaged backend: {executable}"
    return [str(executable)]


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path / "中文 日本語 space"
    root.mkdir()
    node = shutil.which("node")
    assert node, "Node is required for the offline ACP integration test"
    peer = root / "acp.cjs"
    shutil.copyfile(Path(__file__).parent / "fixtures" / "acp_unicode.cjs", peer)
    if os.name == "nt":
        # Use the same .cmd shim route as the globally installed npm dsh.
        # ASCII contents avoid depending on cmd's batch-file code page.
        (root / "dsh.cmd").write_text(
            '@"' + node + '" "%~dp0acp.cjs" %*\r\n', encoding="utf-8"
        )
    else:
        shim = root / "dsh"
        shim.write_text("#!/bin/sh\nexec " + shlex.join([node, str(peer)]) + ' "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": str(root) + os.pathsep + env.get("PATH", ""),
        "EC_DATA_DIR": str(root), "DSH_HOME": str(root / "dsh-home"),
        "EC_DB_URL": f"sqlite:///{root / 'test.db'}",
        "DEEPSEEK_API_KEY": "offline-test-not-a-key", "EC_PROXY": "",
        "EC_AGENT_TOTAL_TIMEOUT": "45",
        # Wrong startup settings must not change our wire protocol.
        "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp936",
        "NO_PROXY": "127.0.0.1,localhost",
    })
    return root, env


def run_cli(command, args, root, env):
    result = subprocess.run(command + args, cwd=root, env=env, capture_output=True, timeout=45)
    # Strict decoding: errors='replace' would hide the regression being tested.
    stdout, stderr = result.stdout.decode("utf-8"), result.stderr.decode("utf-8")
    assert "\ufffd" not in stdout + stderr
    return result.returncode, stdout, stderr


def test_harness_unicode_pipes(backend_command, runtime):
    root, env = runtime
    out = root / "任务 output"
    code, stdout, stderr = run_cli(backend_command, [
        "--harness", "--url", "https://example.com/", "--out", str(out), "--extra", SAMPLE,
    ], root, env)
    assert code == 0, (stdout, stderr)
    events = [json.loads(line) for line in stdout.splitlines()]
    logs = [event["text"] for event in events if event["type"] == "log"]
    assert "read（in_progress）" in logs
    assert "工具调用（completed）" in logs
    assert "dsh: 诊断：" + SAMPLE in logs
    result = next(event for event in events if event["type"] == "result")
    assert result["error"] == ""
    assert result["reply"] == SAMPLE
    assert result["products"][0]["name"] == SAMPLE
    saved = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert saved["products"] == result["products"]


def test_fetch_unicode_and_cli_errors(backend_command, runtime):
    root, env = runtime
    html = f"<!doctype html><html><head><meta charset='utf-8'><title>{SAMPLE}</title></head><body>{SAMPLE}</body></html>"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        code, stdout, stderr = run_cli(backend_command, ["--fetch", "json", url], root, env)
        assert code == 0, stderr
        assert json.loads(stdout)["title"] == SAMPLE
        target = root / "保存 日本語 🛍️.html"
        code, stdout, stderr = run_cli(backend_command, ["--fetch", "raw", url, str(target)], root, env)
        assert code == 0, stderr
        assert str(target) in stdout and "字符）" in stdout
        assert target.read_text(encoding="utf-8") == html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    code, _, stderr = run_cli(backend_command, ["--fetch"], root, env)
    assert code == 2 and "用法:" in stderr
    code, _, stderr = run_cli(backend_command, ["--browser", "check", "--未知🛍️"], root, env)
    assert code == 2 and "--未知🛍️" in stderr


def test_job_api_unicode_roundtrip(backend_command, runtime):
    root, env = runtime
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env["EC_PORT"] = str(port)
    base = f"http://127.0.0.1:{port}"

    def request(path, payload=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = Request(base + path, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=3) as response:
            return json.load(response)

    # Files avoid a full stdout/stderr pipe blocking the server during the test.
    with (root / "server.log").open("wb") as log:
        proc = subprocess.Popen(backend_command, cwd=root, env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                assert proc.poll() is None, (root / "server.log").read_bytes()
                try:
                    request("/api/health")
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("Packaged server did not start")
            job = request("/api/agent/jobs", {"url": "https://example.com/", "prompt": SAMPLE})
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                job = request(f"/api/agent/jobs/{job['id']}")
                if job["status"] != "running":
                    break
                time.sleep(0.1)
            assert job["status"] == "done", job
            assert job["products"][0]["name"] == SAMPLE
            assert "工具调用（completed）" in [line["text"] for line in job["log"]]
            assert "\ufffd" not in json.dumps(job, ensure_ascii=False)
            # Read SQLite independently: the UI's in-memory response isn't enough.
            import sqlite3
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with sqlite3.connect(root / "test.db") as db:
                    names = db.execute("SELECT name FROM agent_products").fetchall()
                if names:
                    break
                time.sleep(0.1)
            assert (SAMPLE,) in names
        finally:
            kill_process_tree(proc)
