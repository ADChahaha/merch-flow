"""Exercise real byte streams, not mocked Popen keyword arguments."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.stdio import configure_stdio

BACKEND = Path(__file__).resolve().parents[1]
TEXT = "工具调用（completed） 日本語・缶バッジ 🛍️"


@pytest.mark.parametrize("legacy_encoding", ["cp936", "cp1252"])
def test_utf8_roundtrip_with_legacy_stdio(legacy_encoding):
    # Force the pre-fix Windows pipe encoding even on UTF-8 CI runners.
    script = '''
import sys
from app.stdio import configure_stdio
for stream in (sys.stdin, sys.stdout, sys.stderr):
    stream.reconfigure(encoding=sys.argv[1])
configure_stdio()
text = sys.stdin.readline().rstrip("\\n")
print(text)
print(text, file=sys.stderr)
'''
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": legacy_encoding}
    result = subprocess.run(
        [sys.executable, "-c", script, legacy_encoding], cwd=BACKEND, env=env,
        input=(TEXT + "\n").encode("utf-8"), capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode("utf-8").strip() == TEXT
    assert result.stderr.decode("utf-8").strip() == TEXT


def test_missing_or_replaced_streams_are_supported(monkeypatch):
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", None)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", None)
    configure_stdio()
    print(TEXT)
    assert stdout.getvalue() == TEXT + "\n"
