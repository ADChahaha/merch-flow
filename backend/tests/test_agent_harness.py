"""harness 桥：任务目录、提示词、products.json 清洗、ACP 会话编排。

没有递归逻辑 —— 递归是 dsh agent（模型）的事。ACP 客户端整个换成假的，
不联网、不动模型，只验证我们编排的会话流程和日志/结果形状。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import app.agent.harness as harness_module
from app.agent.acp import AcpNotFound, summarize_update
from app.agent.harness import (
    build_prompt,
    normalize_product,
    read_products,
    run_task,
    write_workdir,
)

URL = "https://shop.example.com/fair/"


# --------------------------------------------------------------------------- #
# ACP 更新 → 日志
# --------------------------------------------------------------------------- #
def test_summarize_update_shapes():
    assert summarize_update(
        {"sessionUpdate": "agent_thought_chunk", "content": {"text": "想想"}}
    ) == {"level": "think", "text": "想想"}
    assert summarize_update(
        {"sessionUpdate": "agent_message_chunk", "content": {"text": "搞定"}}
    ) == {"level": "agent-chunk", "text": "搞定"}
    tool = summarize_update(
        {"sessionUpdate": "tool_call_update", "title": "./fetch", "status": "completed"}
    )
    assert tool == {"level": "tool", "text": "./fetch（completed）"}
    assert summarize_update({"sessionUpdate": "usage_update"}) is None
    assert summarize_update({"sessionUpdate": "agent_thought_chunk", "content": {"text": ""}}) is None


# --------------------------------------------------------------------------- #
# 提示词与任务目录
# --------------------------------------------------------------------------- #
def test_prompt_hands_url_to_agent():
    prompt = build_prompt(URL)
    assert URL in prompt
    assert "products.json" in prompt
    assert "自己判断" in prompt
    assert "./fetch" in prompt


def test_write_workdir_creates_tools_and_patch(tmp_path):
    write_workdir(tmp_path, URL, model="deepseek-v4-pro", thinking="max")

    assert (tmp_path / "fetch_page.py").exists()
    assert (tmp_path / "TASK.md").read_text(encoding="utf-8").count(URL) == 2
    wrapper = tmp_path / "fetch"
    assert wrapper.exists() and os.access(wrapper, os.X_OK)

    patch = (tmp_path / "dsh.patch.yml").read_text(encoding="utf-8")
    assert "model: deepseek-v4-pro" in patch
    assert "thinking: enabled" in patch
    assert "reasoningEffort: max" in patch


def test_write_workdir_thinking_off_disables_reasoning(tmp_path):
    """off 必须显式禁用：不写这段时 dsh 默认 high，等于没关。"""
    write_workdir(tmp_path, URL, model="deepseek-v4-flash", thinking="off")
    patch = (tmp_path / "dsh.patch.yml").read_text(encoding="utf-8")
    assert "model: deepseek-v4-flash" in patch
    assert "thinking: disabled" in patch
    assert "reasoningEffort: off" in patch


def test_fetch_script_is_runnable_python(tmp_path):
    write_workdir(tmp_path, URL, model="deepseek-v4-flash", thinking="off")
    script = (tmp_path / "fetch_page.py").read_text(encoding="utf-8")
    compile(script, "fetch_page.py", "exec")
    assert "app.agent.fetch" in script


# --------------------------------------------------------------------------- #
# products.json 清洗
# --------------------------------------------------------------------------- #
def test_normalize_product_cleans_fields():
    product = normalize_product(
        {
            "name": " 缶バッジ\r\n「テスト」 ",
            "price_text": "4,400円(税込)",
            "price": None,
            "date_text": "2026年10月23日(金)～11月8日(日)",
            "detail": "全8種",
            "image_urls": ["/img/a.jpg", "https://cdn.example.com/b.jpg", "", None],
            "source_url": "/pd/x/",
        },
        URL,
    )
    assert product is not None
    assert product["name"] == "缶バッジ 「テスト」"
    assert product["price"] == 4400
    assert product["image_urls"] == [
        "https://shop.example.com/img/a.jpg",
        "https://cdn.example.com/b.jpg",
    ]
    assert product["source_url"] == "/pd/x/"


def test_normalize_product_requires_name():
    assert normalize_product({"price": 100}, URL) is None
    assert normalize_product("文字列", URL) is None
    assert normalize_product({"name": "x", "price": True, "price_text": ""}, URL)["price"] is None


def test_read_products_object_and_list(tmp_path):
    (tmp_path / "products.json").write_text(
        json.dumps(
            {"title": "童話フェア", "products": [{"name": "A"}, {"name": ""}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    title, products = read_products(tmp_path, URL)
    assert title == "童話フェア"
    assert [p["name"] for p in products] == ["A"]

    (tmp_path / "products.json").write_text('[{"name": "B"}]', encoding="utf-8")
    title, products = read_products(tmp_path, URL)
    assert title == "" and products[0]["name"] == "B"


def test_read_products_rejects_missing_and_broken(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_products(tmp_path, URL)
    (tmp_path / "products.json").write_text("{不是 json", encoding="utf-8")
    with pytest.raises(ValueError):
        read_products(tmp_path, URL)


# --------------------------------------------------------------------------- #
# 会话编排（假 ACP 客户端）
# --------------------------------------------------------------------------- #
def fake_factory(
    *,
    products=None,
    session="sess-new",
    writes_products=True,
    publish_result=None,
    calls_out=None,
):
    """构造一个假 ACP 工厂；每次实例化都会走完整协议并（可选）写 products.json。"""

    class FakeAcp:
        def __init__(self, cwd, *, patch_path=None, api_key="", on_event=None, **kwargs):
            self.cwd = Path(cwd)
            self.on_event = on_event or (lambda kind, payload: None)
            self.calls: list = []
            if calls_out is not None:
                calls_out.append(self.calls)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def initialize(self):
            self.calls.append("initialize")
            return {}

        def new_session(self):
            self.calls.append("new_session")
            return session

        def resume_session(self, session_id):
            self.calls.append(("resume", session_id))
            return session_id

        def prompt(self, session_id, text):
            self.calls.append(("prompt", session_id, text))
            self.on_event(
                "update",
                {"update": {"sessionUpdate": "agent_thought_chunk", "content": {"text": "先抓入口页"}}},
            )
            self.on_event(
                "update",
                {"update": {"sessionUpdate": "tool_call_update", "title": "./fetch", "status": "completed"}},
            )
            self.on_event(
                "update",
                {"update": {"sessionUpdate": "agent_message_chunk", "content": {"text": "找到 1 件"}}},
            )
            if publish_result is not None:
                (Path(self.cwd) / "publish_result.json").write_text(
                    json.dumps(publish_result, ensure_ascii=False), encoding="utf-8"
                )
            elif writes_products:
                (Path(self.cwd) / "products.json").write_text(
                    json.dumps(products or {"title": "フェア", "products": [{"name": "缶バッジ"}]}, ensure_ascii=False),
                    encoding="utf-8",
                )
            return "end_turn"

    return FakeAcp


def run(tmp_path, *, acp_factory=None, **overrides):
    logs: list[tuple[str, str]] = []
    events: list[dict] = []
    result = run_task(
        URL,
        tmp_path,
        emit=lambda level, text: logs.append((level, text)),
        emit_event=events.append,
        acp_factory=acp_factory or fake_factory(),
        **overrides,
    )
    return result, logs, events


def test_run_task_collects_products_and_streams_updates(tmp_path):
    calls: list = []
    result, logs, events = run(tmp_path, acp_factory=fake_factory(calls_out=calls))

    assert result["error"] == ""
    assert result["session_id"] == "sess-new"
    assert result["reply"] == "找到 1 件"
    assert result["title"] == "フェア"
    assert [p["name"] for p in result["products"]] == ["缶バッジ"]
    assert events[-1]["type"] == "result"

    levels = {level for level, _ in logs}
    assert {"think", "tool", "agent", "info"} <= levels
    assert calls[0][:2] == ["initialize", "new_session"]
    prompt_call = next(call for call in calls[0] if isinstance(call, tuple) and call[0] == "prompt")
    assert URL in prompt_call[2]


def test_run_task_reports_session_token_usage(tmp_path, monkeypatch):
    """harness 跑完从 dsh 会话日志里取整个会话的累计 token，写进 result 和日志。"""
    usage = {"input": 47810, "output": 12449, "cache_read": 796544, "cache_write": 0, "total": 856803}
    monkeypatch.setattr(harness_module, "read_session_usage", lambda session_id: dict(usage))

    result, logs, events = run(tmp_path)

    assert result["usage"] == usage
    assert events[-1]["usage"] == usage
    assert any("856.8k" in text for _, text in logs)


def test_run_task_without_usage_still_succeeds(tmp_path, monkeypatch):
    """dsh 换了存储格式读不到 token：任务结果不受影响。"""
    monkeypatch.setattr(harness_module, "read_session_usage", lambda session_id: None)

    result, logs, _ = run(tmp_path)

    assert result["error"] == ""
    assert result["usage"] == {}


def test_run_task_resume_sends_user_prompt_verbatim(tmp_path):
    calls: list = []
    result, logs, _ = run(
        tmp_path,
        acp_factory=fake_factory(calls_out=calls),
        session_id="sess-old",
        prompt="少了 2 件，把套装补上",
    )

    assert result["session_id"] == "sess-old"
    assert ("resume", "sess-old") in calls[0]
    prompt_call = next(call for call in calls[0] if isinstance(call, tuple) and call[0] == "prompt")
    assert prompt_call[2] == "少了 2 件，把套装补上"  # 续聊时原样发用户的话
    assert any("续聊会话" in text for _, text in logs)


def test_run_task_first_round_appends_extra_instructions(tmp_path):
    calls: list = []
    run(tmp_path, acp_factory=fake_factory(calls_out=calls), extra="只抓 Blu-ray，价格换算成人民币")
    prompt_call = next(call for call in calls[0] if isinstance(call, tuple) and call[0] == "prompt")
    text = prompt_call[2]
    assert "自己判断" in text  # 默认提示词还在
    assert "用户补充要求" in text
    assert "只抓 Blu-ray，价格换算成人民币" in text


def test_run_task_chat_without_session_adds_context(tmp_path):
    calls: list = []
    run(tmp_path, acp_factory=fake_factory(calls_out=calls), prompt="再核对一遍")
    prompt_call = next(call for call in calls[0] if isinstance(call, tuple) and call[0] == "prompt")
    assert "products.json" in prompt_call[2] and "再核对一遍" in prompt_call[2]
    assert "new_session" in calls[0]


def test_run_task_reports_missing_products_json(tmp_path):
    result, logs, events = run(tmp_path, acp_factory=fake_factory(writes_products=False))
    assert result["products"] == []
    assert "products.json" in result["error"]
    assert any(level == "error" for level, _ in logs)
    assert events[-1]["type"] == "result"


def test_run_task_reports_missing_dsh(tmp_path):
    class MissingAcp:
        def __init__(self, *args, **kwargs):
            raise AcpNotFound("找不到 dsh：npm install -g @deepseek-ai/dsh")

    result, logs, _ = run(tmp_path, acp_factory=MissingAcp)
    assert "npm install" in result["error"]
    assert any(level == "error" and "dsh" in text for level, text in logs)


# --------------------------------------------------------------------------- #
# 淘宝上架（浏览器自动化）
# --------------------------------------------------------------------------- #
def test_publish_task_prepares_workdir_and_reads_result(tmp_path):
    calls: list = []
    result, logs, events = run(
        tmp_path,
        acp_factory=fake_factory(
            calls_out=calls,
            publish_result={
                "ok": True,
                "message": "已提交 1 个，等待平台审核",
                "need_human": "",
                "items": [{"name": "A", "status": "pending_review"}],
            },
        ),
        kind="taobao_publish",
        payload={"items": [{"name": "A", "price": 9.9, "images": ["https://x/a.jpg"]}]},
    )

    assert result["kind"] == "taobao_publish"
    assert result["title"] == "淘宝上架（1 件）"
    assert result["report"]["ok"] is True
    assert result["products"] == []
    assert events[-1]["type"] == "result"
    assert any("上架结果" in text for _, text in logs)

    # 工作目录里三件套齐全（agent 的工具 + 商品数据 + 启动 Chrome 的脚本）
    assert (tmp_path / "publish_payload.json").exists()
    assert (tmp_path / "browser.py").exists()
    assert os.access(tmp_path / "chrome_debug.sh", os.X_OK)

    # 首次任务的提示词带着实战要点（9222 / 真实键盘 / 错误(N) / 真人闸门）
    prompt_call = next(call for call in calls[0] if isinstance(call, tuple) and call[0] == "prompt")
    for needle in ("9222", "真实键盘", "错误(N)", "需要真人"):
        assert needle in prompt_call[2]


def test_publish_chat_without_session_mentions_payload(tmp_path):
    calls: list = []
    run(
        tmp_path,
        acp_factory=fake_factory(calls_out=calls, publish_result={"ok": True, "message": "ok"}),
        kind="taobao_publish",
        payload={"items": [{"name": "A"}]},
        prompt="卡在图片上传了，帮我看下",
    )
    prompt_call = next(call for call in calls[0] if isinstance(call, tuple) and call[0] == "prompt")
    assert "publish_payload.json" in prompt_call[2]
    assert "卡在图片上传了，帮我看下" in prompt_call[2]


def test_publish_reports_missing_result_file(tmp_path):
    result, logs, _ = run(
        tmp_path,
        acp_factory=fake_factory(writes_products=False),
        kind="taobao_publish",
        payload={"items": [{"name": "A"}]},
    )
    assert "publish_result.json" in result["error"]
    assert any(level == "error" for level, _ in logs)


def test_run_task_passes_model_and_thinking(tmp_path):
    seen: dict = {}

    class ModelAcp(fake_factory()):
        def __init__(self, cwd, **kwargs):
            super().__init__(cwd, **kwargs)
            seen["patch"] = Path(cwd, "dsh.patch.yml").read_text(encoding="utf-8")

    run(tmp_path, acp_factory=ModelAcp, model="deepseek-v4-pro", thinking="high")
    assert "model: deepseek-v4-pro" in seen["patch"]
    assert "reasoningEffort: high" in seen["patch"]
