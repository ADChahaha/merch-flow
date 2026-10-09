"""用真实子进程验证删除、超时和 ACP 退出能结束独立进程组中的后代。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
import pytest

from app.agent.acp import AcpClient
from app.agent.jobs import JobManager, LiveJob
from app.agent.processes import kill_process_tree


@pytest.mark.parametrize("action", ["delete", "timeout", "shutdown", "acp_stop"])
def test_stopping_task_kills_detached_descendants(tmp_path, monkeypatch, action):
    child_pid = tmp_path / "child.json"
    script = tmp_path / "parent.py"
    script.write_text(
        "import subprocess, sys, time, json\n"
        "from pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "start_new_session=True)\n"
        "ready = Path(sys.argv[1])\n"
        "ready.with_suffix('.tmp').write_text(json.dumps(child.pid))\n"
        "ready.with_suffix('.tmp').replace(ready)\n"
        "time.sleep(60)\n", encoding="utf-8",
    )
    proc = subprocess.Popen([sys.executable, str(script), str(child_pid)], start_new_session=True)
    child = None
    try:
        deadline = time.monotonic() + 10
        while not child_pid.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        child = psutil.Process(json.loads(child_pid.read_text()))
        if os.name != "nt":
            assert os.getpgid(child.pid) != os.getpgid(proc.pid)
        manager = JobManager()
        manager._jobs[1] = LiveJob(id=1, url="https://example.com")
        manager._procs[1] = proc
        if action == "delete":
            # 不访问用户数据，只验证 delete() 的进程清理路径。
            from contextlib import contextmanager
            import app.agent.jobs as jobs
            class EmptySession:
                def get(self, *args):
                    return None
            @contextmanager
            def empty_scope():
                yield EmptySession()
            monkeypatch.setattr(jobs, "session_scope", empty_scope)
            manager.delete(1)
        elif action == "timeout":
            manager._on_timeout(1)
            assert "超时" in manager._jobs[1].error
        elif action == "shutdown":
            manager.shutdown()
        else:
            client = AcpClient(cwd=tmp_path)
            client.proc = proc
            client.stop()
        assert proc.poll() is not None
        deadline = time.monotonic() + 5
        while child.is_running() and child.status() != psutil.STATUS_ZOMBIE and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
    finally:
        if child is not None and child.is_running():
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        kill_process_tree(proc)
