"""AI 抓取接口：起任务 / 轮询 / 落库 / 删除。

子进程换成假的（按行回放 NDJSON），不联网、不调模型；真实 harness 在
test_agent_harness.py 里用注入的假抓取 + 假模型覆盖。
"""

from __future__ import annotations

import functools
import json
import time
from pathlib import Path
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

URL = "https://shop.example.com/fair/"

RESULT = {
    "url": URL,
    "title": "童話フェア",
    "products": [
        {
            "name": "缶バッジ「テスト」",
            "price": 550,
            "price_text": "550円(税込)",
            "date_text": "2026年10月23日(金)～11月8日(日)",
            "detail": "全8種",
            "image_urls": ["https://shop.example.com/img/badge.jpg"],
            "source_url": "https://shop.example.com/pd/badge/",
        }
    ],
    "pages_visited": 2,
    "error": "",
}


class FakePopen:
    """按类属性 lines 回放 stdout，模拟 harness 子进程。"""

    lines: list[dict] = []
    returncode = 0

    def __init__(self, cmd, **kwargs):  # noqa: ANN001
        self.cmd = cmd
        self.stdout = iter(_dump(line) for line in type(self).lines)
        self.returncode = type(self).returncode

    def wait(self, timeout=None):  # noqa: ANN001
        return self.returncode

    def poll(self):  # noqa: ANN001
        return self.returncode

    def kill(self):  # noqa: ANN001
        self.returncode = -9


def _dump(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


@pytest.fixture
def agent_client(monkeypatch, tmp_path):
    import app.agent.jobs as jobs_module
    import app.main as main
    from app.db import Base, get_session

    # 用临时文件库而不是内存 StaticPool：后台的落库线程和断言线程要各自拿连接，
    # 共用一条内存连接时并发写会偶发 database is locked（测试就会随机超时）。
    engine = create_engine(
        f"sqlite:///{tmp_path / 'agent_test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @contextmanager
    def test_scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(jobs_module, "session_scope", test_scope)
    monkeypatch.setattr(jobs_module, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs_module.subprocess, "Popen", FakePopen)

    main.app.dependency_overrides[get_session] = functools.partial(_session_gen, factory)
    FakePopen.lines = []
    FakePopen.returncode = 0
    with TestClient(main.app) as client:
        yield client, factory
    main.app.dependency_overrides.clear()
    engine.dispose()


def _session_gen(factory):
    session = factory()
    try:
        yield session
    finally:
        session.close()


def wait_done(client, job_id: int, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/agent/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("任务没有在超时前结束")


def wait_persisted(factory, job_id: int, timeout: float = 15.0) -> dict:
    """等任务落库，返回快照（session 关了就 lazy load 不了，进 session 里取完）。"""
    from app.models import AgentJob

    deadline = time.time() + timeout
    while time.time() < deadline:
        with factory() as session:
            job = session.get(AgentJob, job_id)
            if job is not None and job.status != "running":
                return {
                    "status": job.status,
                    "error": job.error,
                    "agent_session": job.agent_session,
                    "usage": dict(job.usage or {}),
                    "products": [
                        {"name": p.name, "price": p.price, "price_text": p.price_text}
                        for p in job.products
                    ],
                }
        time.sleep(0.05)
    raise AssertionError("任务没有落库")


def test_create_job_rejects_bad_url(agent_client):
    client, _ = agent_client
    assert client.post("/api/agent/jobs", json={"url": "不是链接"}).status_code == 400
    assert client.post("/api/agent/jobs", json={"url": "ftp://a.com/x"}).status_code == 400


def test_job_runs_and_persists_products(agent_client):
    client, factory = agent_client
    FakePopen.lines = [
        {"type": "log", "level": "info", "text": "任务：https://shop.example.com/fair/"},
        {"type": "log", "level": "info", "text": "思考：先抓入口页，再进商品详情"},
        {"type": "page", "url": URL, "title": "テスト", "products": 1, "queued": 1, "index": 1},
        {"type": "result", **RESULT},
    ]

    created = client.post("/api/agent/jobs", json={"url": URL})
    assert created.status_code == 201
    job_id = created.json()["id"]

    body = wait_done(client, job_id)
    assert body["status"] == "done"
    assert body["title"] == "童話フェア"
    assert body["pages_visited"] == 2
    assert body["product_count"] == 1
    product = body["products"][0]
    assert product["name"] == "缶バッジ「テスト」"
    assert product["price"] == 550
    assert product["image_urls"] == ["https://shop.example.com/img/badge.jpg"]
    assert len(body["log"]) >= 3  # 两条 agent 日志 + 任务结束

    job = wait_persisted(factory, job_id)
    assert job["status"] == "done"
    assert [p["name"] for p in job["products"]] == ["缶バッジ「テスト」"]
    assert job["products"][0]["price_text"] == "550円(税込)"
    assert job["usage"] == {}


def test_job_persists_token_usage(agent_client):
    """整个会话的 token 用量跟着任务落库，列表/详情都能看到。"""
    client, factory = agent_client
    usage = {"input": 31710, "output": 11971, "cache_read": 431488, "cache_write": 0, "total": 475169}
    FakePopen.lines = [{"type": "result", **RESULT, "usage": usage}]

    job_id = client.post("/api/agent/jobs", json={"url": URL}).json()["id"]
    body = wait_done(client, job_id)
    assert body["usage"] == usage

    summary = client.get("/api/agent/jobs").json()[0]
    assert summary["usage"]["total"] == 475169

    job = wait_persisted(factory, job_id)
    assert job["usage"] == usage


def test_backfill_job_usage_for_old_jobs(agent_client, tmp_path, monkeypatch):
    """上线前跑的老任务（没存过 usage）从 dsh 会话日志里补一次。"""
    import app.agent.jobs as jobs_module
    from app.models import AgentJob

    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh"))
    session_dir = tmp_path / "dsh" / "sessions" / "--x--" / "sess-old"
    session_dir.mkdir(parents=True)
    (session_dir / "session.v3.jsonl").write_text(
        json.dumps(
            {
                "data": {
                    "usage": {
                        "inputTokens": 100,
                        "outputTokens": 20,
                        "cacheReadTokens": 3000,
                        "cacheWriteTokens": 0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    _, factory = agent_client
    with factory() as session:
        session.add(AgentJob(url=URL, status="done", agent_session="sess-old"))
        session.commit()

    assert jobs_module.backfill_job_usage(factory) == 1
    with factory() as session:
        job = session.query(AgentJob).filter_by(agent_session="sess-old").one()
        assert job.usage["total"] == 3120
    # 再补一次不重复算
    assert jobs_module.backfill_job_usage(factory) == 0


def test_chat_continues_session_and_updates_products(agent_client):
    client, factory = agent_client
    FakePopen.lines = [{"type": "result", **RESULT, "session_id": "sess-1"}]
    job_id = client.post("/api/agent/jobs", json={"url": URL}).json()["id"]
    wait_done(client, job_id)

    FakePopen.lines = [
        {"type": "log", "level": "info", "text": "续聊会话 sess-1…"},
        {"type": "log", "level": "agent", "text": "补上了：套装款和隐藏款"},
        {
            "type": "result",
            **{
                **RESULT,
                "session_id": "sess-1",
                "products": [
                    RESULT["products"][0],
                    {
                        "name": "アクリルスタンド「テスト」",
                        "price": 1870,
                        "price_text": "1,870円(税込)",
                        "image_urls": [],
                        "source_url": URL,
                    },
                ],
            },
        },
    ]

    response = client.post(f"/api/agent/jobs/{job_id}/chat", json={"message": "少了 2 件，补上"})
    assert response.status_code == 200

    body = wait_done(client, job_id)
    assert body["product_count"] == 2
    assert any(line["level"] == "user" and "少了" in line["text"] for line in body["log"])
    assert any(line["level"] == "agent" for line in body["log"])

    job = wait_persisted(factory, job_id)
    assert job["agent_session"] == "sess-1"  # 会话 id 落库，重启后还能续聊
    assert len(job["products"]) == 2


def test_manual_add_and_delete_product(agent_client):
    client, factory = agent_client
    FakePopen.lines = [{"type": "result", **RESULT}]
    job_id = client.post("/api/agent/jobs", json={"url": URL}).json()["id"]
    wait_done(client, job_id)

    created = client.post(
        f"/api/agent/jobs/{job_id}/products",
        json={
            "name": "手动补充的亚克力立牌",
            "price": 1870,
            "price_text": "1,870円(税込)",
            "date_text": "2026年11月上旬发售",
            "detail": "全1种",
            "image_urls": ["https://shop.example.com/img/stand.jpg"],
            "source_url": URL,
        },
    )
    assert created.status_code == 201
    product_id = created.json()["id"]

    body = client.get(f"/api/agent/jobs/{job_id}").json()
    assert body["product_count"] == 2
    assert any(p["name"] == "手动补充的亚克力立牌" for p in body["products"])

    # 落库了（刷新/重启后还在）
    job = wait_persisted(factory, job_id)
    assert "手动补充的亚克力立牌" in [p["name"] for p in job["products"]]

    assert client.delete(f"/api/agent/jobs/{job_id}/products/{product_id}").status_code == 200
    body = client.get(f"/api/agent/jobs/{job_id}").json()
    assert body["product_count"] == 1
    assert client.delete(f"/api/agent/jobs/{job_id}/products/{product_id}").status_code == 404


def test_create_job_accepts_first_round_prompt(agent_client):
    client, _ = agent_client
    FakePopen.lines = [{"type": "result", **RESULT}]
    created = client.post("/api/agent/jobs", json={"url": URL, "prompt": "只抓 Blu-ray"})
    assert created.status_code == 201
    assert created.json()["status"] == "running"
    wait_done(client, created.json()["id"])


def test_taobao_browser_publish_job(agent_client, tmp_path):
    """淘宝浏览器上架：起任务 → 日志/结果落库 → 截图列表可读。"""
    client, factory = agent_client
    FakePopen.lines = [
        {"type": "log", "level": "info", "text": "新建会话 · 模型 deepseek-v4-flash"},
        {"type": "log", "level": "info", "text": "上架结果：已提交 1 个"},
        {
            "type": "result",
            "url": "taobao://publish",
            "kind": "taobao_publish",
            "title": "淘宝上架（1 件）",
            "products": [],
            "session_id": "publish-sess",
            "reply": "",
            "error": "",
        },
    ]

    response = client.post(
        "/api/listings/taobao/browser",
        json={"items": [{"name": "测试商品", "price": 9.9, "images": ["https://x/a.jpg"], "stock": 10}]},
    )
    assert response.status_code == 200
    created = response.json()
    assert created["kind"] == "taobao_publish"
    job_id = created["id"]

    body = wait_done(client, job_id)
    assert body["title"] == "淘宝上架（1 件）"
    assert body["kind"] == "taobao_publish"

    listed = client.get("/api/agent/jobs").json()
    assert any(item["id"] == job_id and item["kind"] == "taobao_publish" for item in listed)

    # 模拟 agent 截了图 → files 接口能列出来、能取到
    # （router 用的是它自己模块里 import 的 BASE_DIR，测试就写到那个位置）
    from app.routers import agent as agent_router

    shots = Path(agent_router.BASE_DIR) / "data" / "agent_jobs" / str(job_id) / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "step1.png").write_bytes(b"\x89PNG\r\n")
    files = client.get(f"/api/agent/jobs/{job_id}/files").json()["files"]
    assert any(item["name"] == "shots/step1.png" for item in files)
    shot = client.get(f"/api/agent/jobs/{job_id}/files/shots/step1.png")
    assert shot.status_code == 200

    # 目录穿越/非图片要被挡掉
    assert client.get(f"/api/agent/jobs/{job_id}/files/../../ec.db").status_code in (400, 404, 422)
    (shots / "note.txt").write_text("x", encoding="utf-8")
    assert client.get(f"/api/agent/jobs/{job_id}/files/shots/note.txt").status_code == 400


def test_taobao_browser_publish_requires_items(agent_client):
    client, _ = agent_client
    assert client.post("/api/listings/taobao/browser", json={"items": []}).status_code == 422


def test_chat_rejects_unknown_job(agent_client):
    client, _ = agent_client
    assert client.post("/api/agent/jobs/999999/chat", json={"message": "在吗"}).status_code == 404
    assert client.post("/api/agent/jobs/999999/chat", json={"message": ""}).status_code == 422


def test_job_list_and_delete(agent_client):
    client, factory = agent_client
    FakePopen.lines = [{"type": "result", **RESULT}]

    job_id = client.post("/api/agent/jobs", json={"url": URL}).json()["id"]
    wait_persisted(factory, job_id)

    listed = client.get("/api/agent/jobs").json()
    assert any(item["id"] == job_id and item["product_count"] == 1 for item in listed)
    assert "log" not in listed[0]  # 摘要不背日志

    assert client.delete(f"/api/agent/jobs/{job_id}").json()["ok"] is True
    assert client.get(f"/api/agent/jobs/{job_id}").status_code == 404
    assert client.delete(f"/api/agent/jobs/{job_id}").status_code == 404


def test_settings_masks_secrets_and_writes_env(agent_client, monkeypatch, tmp_path):
    client, _ = agent_client
    import app.agent.env_store as env_store
    from app.config import settings

    env_path = tmp_path / ".env"
    monkeypatch.setattr(env_store, "ENV_PATH", env_path)
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "agent_model", "deepseek-v4-flash")
    monkeypatch.setattr(settings, "agent_reasoning", "off")
    monkeypatch.setattr(settings, "bilibili_access_token", "")
    monkeypatch.setattr(settings, "bilibili_client_id", "")
    monkeypatch.setattr(settings, "bilibili_client_secret", "")

    body = client.get("/api/settings").json()
    assert body["agent"]["has_key"] is False
    assert body["bilibili"]["has_token"] is False

    saved = client.put(
        "/api/settings",
        json={
            "deepseek_api_key": "sk-test-1234abcd",
            "agent_model": "deepseek-v4-pro",
            "agent_reasoning": "max",
            "bilibili_access_token": "bili-token-9999wxyz",
            "bilibili_client_id": "app-123",
            "bilibili_client_secret": "secret-abcd",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["agent"]["has_key"] is True
    assert body["agent"]["key_hint"].endswith("abcd")
    assert body["agent"]["reasoning"] == "max"
    assert body["bilibili"]["has_token"] is True
    assert body["bilibili"]["token_hint"].endswith("wxyz")
    assert body["bilibili"]["client_id"] == "app-123"
    assert body["bilibili"]["has_client_secret"] is True
    dump = json.dumps(body)
    assert "sk-test" not in dump and "secret-abcd" not in dump  # 明文绝不出后端

    text = env_path.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-test-1234abcd" in text
    assert "BILIBILI_ACCESS_TOKEN=bili-token-9999wxyz" in text
    assert "EC_AGENT_REASONING=max" in text

    # 只改推理强度：key 不动
    body = client.put("/api/settings", json={"agent_reasoning": "low"}).json()
    assert body["agent"]["has_key"] is True and body["agent"]["reasoning"] == "low"

    # 非法值拒绝
    assert client.put("/api/settings", json={"agent_model": "gpt-9"}).status_code == 400
    assert client.put("/api/settings", json={"agent_reasoning": "ultra"}).status_code == 400

    # 空串 = 清除
    body = client.put("/api/settings", json={"deepseek_api_key": "", "bilibili_access_token": ""}).json()
    assert body["agent"]["has_key"] is False
    assert body["bilibili"]["has_token"] is False

    # 界面默认值：原始页面默认打开，可关
    assert client.get("/api/settings").json()["ui"]["source_open"] is True
    assert client.put("/api/settings", json={"ui_source_open": False}).json()["ui"]["source_open"] is False
    assert "EC_UI_SOURCE_OPEN=0" in env_path.read_text(encoding="utf-8")


def test_failed_harness_marks_job_error(agent_client):
    client, factory = agent_client
    FakePopen.lines = [
        {"type": "log", "level": "error", "text": "模型分析失败"},
        {"type": "result", **{**RESULT, "products": [], "error": "模型分析失败"}},
    ]
    FakePopen.returncode = 1

    job_id = client.post("/api/agent/jobs", json={"url": URL}).json()["id"]
    body = wait_done(client, job_id)

    assert body["status"] == "error"
    assert body["error"]
    assert body["products"] == []
    job = wait_persisted(factory, job_id)
    assert job["status"] == "error"
