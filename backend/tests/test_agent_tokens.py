"""token 统计：从 dsh 会话日志/投影缓存里读整个会话的累计用量。

dsh 是外部命令行，格式换版本就可能读不到 —— 这里的约定是「读不到返回 None」，
统计失败绝不影响任务本身，所以测试重点覆盖各种残缺/损坏输入。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.tokens import format_tokens, format_usage, read_session_usage

SESSION = "a94b1840-f4f2-4d34-b557-557e4f0e8b32"


def make_log(tmp_path: Path, usage_events: list[dict]) -> Path:
    workdir = tmp_path / "sessions" / "--Users-x-backend-data-agent_jobs-1--" / SESSION
    workdir.mkdir(parents=True)
    log = workdir / "session.v3.jsonl"
    lines = [json.dumps({"type": "session", "version": 3})]
    for usage in usage_events:
        lines.append(
            json.dumps(
                {
                    "type": "assistant/message",
                    "data": {
                        "message": {"role": "assistant"},
                        "usage": usage,
                        # 流里也带一份 usage（不能重复计）
                        "stream": [{"chunk": {"type": "usage", "usage": usage}}],
                    },
                }
            )
        )
    log.write_text("\n".join(lines), encoding="utf-8")
    return log


def test_sums_usage_across_all_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    make_log(
        tmp_path,
        [
            {"inputTokens": 206, "outputTokens": 46, "cacheReadTokens": 9344, "cacheWriteTokens": 0},
            {"inputTokens": 47810, "outputTokens": 12403, "cacheReadTokens": 796544, "cacheWriteTokens": 128},
        ],
    )

    usage = read_session_usage(SESSION)
    assert usage == {
        "input": 48016,
        "output": 12449,
        "cache_read": 805888,
        "cache_write": 128,
        "total": 866481,
    }


def test_reads_zstd_log(tmp_path, monkeypatch):
    zstandard = pytest.importorskip("zstandard")
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    log = make_log(tmp_path, [{"inputTokens": 10, "outputTokens": 2, "cacheReadTokens": 3}])
    packed = log.with_suffix(".jsonl.zstd")
    packed.write_bytes(zstandard.ZstdCompressor().compress(log.read_bytes()))
    log.unlink()

    assert read_session_usage(SESSION)["total"] == 15


def test_falls_back_to_projection_cache(tmp_path, monkeypatch):
    """没有会话日志时（例如日志被清理）读 dsh 的投影缓存。"""
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    cache = tmp_path / "storages" / "session_projcache" / "sessions" / f"{SESSION}.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps(
            {
                "version": 7,
                "record": {
                    "rows": {
                        "tokenUsage": {
                            "val": {
                                "totals": {
                                    "uncachedInputTokens": 47810,
                                    "outputTokens": 12449,
                                    "cacheReadTokens": 796544,
                                    "cacheWriteTokens": 0,
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    usage = read_session_usage(SESSION)
    assert usage["input"] == 47810
    assert usage["total"] == 856803


def test_missing_or_broken_sources_return_none(tmp_path, monkeypatch):
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    assert read_session_usage("") is None
    assert read_session_usage("不存在的会话") is None

    # 日志坏行跳过，全 0 视为没读到
    make_log(tmp_path, [])
    assert read_session_usage(SESSION) is None

    workdir = tmp_path / "sessions" / "--x--" / SESSION
    workdir.mkdir(parents=True)
    (workdir / "session.v3.jsonl").write_text("not json\n{\"data\": {}}", encoding="utf-8")
    assert read_session_usage(SESSION) is None


def test_format_helpers():
    assert format_tokens(0) == "0"
    assert format_tokens(950) == "950"
    assert format_tokens(12449) == "12.4k"
    assert format_tokens(856803) == "856.8k"
    assert format_tokens(1_234_567) == "1.2M"

    text = format_usage({"input": 47810, "output": 12449, "cache_read": 796544, "total": 856803})
    assert "856.8k" in text and "12.4k" in text and "缓存命中" in text
