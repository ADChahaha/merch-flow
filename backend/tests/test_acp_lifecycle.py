import subprocess
import sys
import time
from unittest.mock import patch

import pytest
from app.agent import acp


def test_resolve_command_uses_augmented_path(monkeypatch, tmp_path):
    seen = {}
    def which(name, *, path):
        seen.update(name=name, path=path)
        return 'dsh.cmd'
    monkeypatch.setattr(acp.shutil, 'which', which)
    assert acp.resolve_command(path=str(tmp_path)) == 'dsh.cmd'
    assert seen['path'] == str(tmp_path)


def test_acp_exit_wakes_pending_request_without_timeout(tmp_path):
    real_popen = subprocess.Popen
    # 先读请求、输出一条非协议 JSON，然后直接退出，不给响应。
    def launch(*args, **kwargs):
        return real_popen([sys.executable, '-c', "import sys; sys.stdin.readline(); print('[]', flush=True)"], **kwargs)
    with patch.object(acp.subprocess, 'Popen', launch):
        started = time.monotonic()
        with acp.AcpClient(tmp_path, timeout=10) as client:
            with pytest.raises(acp.AcpError, match='断开'):
                client.initialize()
        assert time.monotonic() - started < 5
