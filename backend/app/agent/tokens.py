"""统计 dsh 会话的 token 用量（整个 session 累计，含追问/续聊）。

数据源优先用 dsh 自己落盘的会话日志（`~/.dsh/sessions/<cwd>/<session>/session.vN.jsonl[.zstd]`）：
每条 assistant 消息都带 usage（inputTokens / outputTokens / cacheReadTokens / cacheWriteTokens），
累加就是整个会话的用量。dsh 的投影缓存（`~/.dsh/storages/session_projcache`）也能读，
但它偶尔滞后一步，所以只当日志读不到时的兜底。

dsh 内部格式换版本时这里读不到就返回 None，统计丢了不影响任务本身。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

DSH_HOME_ENV = "DSH_HOME"


def dsh_home() -> Path:
    """dsh 的数据目录：$DSH_HOME 优先，默认 ~/.dsh。"""
    value = (os.getenv(DSH_HOME_ENV) or "").strip()
    return Path(value).expanduser() if value else Path.home() / ".dsh"


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _usage(totals: dict) -> dict | None:
    """把 dsh 的 totals 折成我们的形状；全 0 视为没读到。"""
    usage = {
        "input": _int(totals.get("uncachedInputTokens") or totals.get("inputTokens")),
        "output": _int(totals.get("outputTokens")),
        "cache_read": _int(totals.get("cacheReadTokens")),
        "cache_write": _int(totals.get("cacheWriteTokens")),
    }
    usage["total"] = usage["input"] + usage["output"] + usage["cache_read"] + usage["cache_write"]
    return usage if usage["total"] > 0 else None


# --------------------------------------------------------------------------- #
# 会话日志（主数据源）
# --------------------------------------------------------------------------- #
def _session_log(session_id: str) -> Path | None:
    root = dsh_home() / "sessions"
    if not root.is_dir():
        return None
    candidates: list[Path] = []
    for workdir in root.iterdir():
        if not workdir.is_dir():
            continue
        session_dir = workdir / session_id
        if session_dir.is_dir():
            candidates.extend(path for path in session_dir.glob("session*.jsonl*") if path.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _log_lines(path: Path) -> list[str]:
    if path.suffix == ".zstd":
        try:
            import zstandard  # 可选依赖：装了就用进程内解压
        except ImportError:
            zstandard = None
        if zstandard is not None:
            with path.open("rb") as handle:
                data = zstandard.ZstdDecompressor().stream_reader(handle).read()
            return data.decode("utf-8", "replace").splitlines()
        zstd = shutil.which("zstd")
        if zstd is None:
            raise RuntimeError("读不了 .zstd 会话日志：没有 zstandard 也没有 zstd 命令")
        completed = subprocess.run(
            [zstd, "-d", "-c", str(path)], capture_output=True, timeout=120, check=False
        )
        if completed.returncode != 0:
            raise RuntimeError(f"zstd 解压失败：{completed.stderr[:200]!r}")
        return completed.stdout.decode("utf-8", "replace").splitlines()
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _sum_log(path: Path) -> dict | None:
    totals = {"uncachedInputTokens": 0, "outputTokens": 0, "cacheReadTokens": 0, "cacheWriteTokens": 0}
    for line in _log_lines(path):
        line = line.strip()
        if not line or '"usage"' not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = (event.get("data") or {}).get("usage") if isinstance(event, dict) else None
        if not isinstance(usage, dict):
            continue
        totals["uncachedInputTokens"] += _int(usage.get("inputTokens"))
        totals["outputTokens"] += _int(usage.get("outputTokens"))
        totals["cacheReadTokens"] += _int(usage.get("cacheReadTokens"))
        totals["cacheWriteTokens"] += _int(usage.get("cacheWriteTokens"))
    return _usage(totals)


# --------------------------------------------------------------------------- #
# 投影缓存（兜底）
# --------------------------------------------------------------------------- #
def _from_cache(session_id: str) -> dict | None:
    path = dsh_home() / "storages" / "session_projcache" / "sessions" / f"{session_id}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    row = (((record.get("record") or {}).get("rows") or {}).get("tokenUsage") or {})
    totals = (row.get("val") or {}).get("totals")
    if not isinstance(totals, dict):
        return None
    return _usage(totals)


def read_session_usage(session_id: str) -> dict | None:
    """整个 dsh 会话（含续聊）的累计 token；读不到返回 None。"""
    if not session_id:
        return None
    path = _session_log(session_id)
    if path is not None:
        try:
            usage = _sum_log(path)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            usage = None
        if usage is not None:
            return usage
    return _from_cache(session_id)


# --------------------------------------------------------------------------- #
# 展示
# --------------------------------------------------------------------------- #
def format_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def format_usage(usage: dict) -> str:
    return (
        f"Token 合计 {format_tokens(_int(usage.get('total')))}"
        f"（输入 {format_tokens(_int(usage.get('input')))}"
        f" · 输出 {format_tokens(_int(usage.get('output')))}"
        f" · 缓存命中 {format_tokens(_int(usage.get('cache_read')))}）"
    )
