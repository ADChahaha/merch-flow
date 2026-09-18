"""任务管理：起 harness 子进程、收集日志、落库。

前端轮询拿到的是这里的内存状态（跑的时候日志是实时的），
任务结束再一次性写进 agent_jobs / agent_products —— agent 跑一轮很贵，
历史结果必须能回看。
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import settings
from ..db import session_scope
from ..domain.listing import utcnow
from ..models import AgentJob, AgentProduct
from .tokens import read_session_usage

logger = logging.getLogger(__name__)

# 内存里保留的日志行数（写库时也按这个上限，别让一个跑飞的 agent 把库撑爆）
MAX_LOG_LINES = 600


@dataclass
class LiveJob:
    """任务的内存态：日志和产物在子进程活着的时候就实时可见。"""

    id: int
    url: str
    kind: str = "scrape"  # scrape | taobao_publish
    status: str = "running"  # running | done | error
    title: str = ""
    error: str = ""
    pages_visited: int = 0
    # dsh 会话 id：用户追问（续聊）靠它恢复上下文
    agent_session: str = ""
    # 最近一轮 agent 的回复
    reply: str = ""
    # 整个会话（含续聊）累计 token：{input, output, cache_read, cache_write, total}
    usage: dict = field(default_factory=dict)
    log: list[dict] = field(default_factory=list)
    products: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "kind": self.kind,
            "status": self.status,
            "title": self.title,
            "error": self.error,
            "pages_visited": self.pages_visited,
            "agent_session": self.agent_session,
            "reply": self.reply,
            "usage": self.usage,
            "log": self.log,
            "products": self.products,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[int, LiveJob] = {}
        self._procs: dict[int, subprocess.Popen] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def start(
        self,
        url: str,
        *,
        kind: str = "scrape",
        payload: dict | None = None,
        extra: str | None = None,
    ) -> LiveJob:
        with session_scope() as session:
            job = AgentJob(url=url, kind=kind, status="running", log=[])
            session.add(job)
            session.flush()
            job_id = job.id

        live = LiveJob(id=job_id, url=url, kind=kind)
        with self._lock:
            self._jobs[job_id] = live
            # 内存只留最近 50 个任务的实时态，更早的走库里的历史
            for old_id in sorted(self._jobs):
                if len(self._jobs) <= 50:
                    break
                if old_id != job_id and self._jobs[old_id].status != "running":
                    del self._jobs[old_id]

        thread = threading.Thread(
            target=self._run,
            args=(job_id,),
            kwargs={"payload": payload, "extra": extra},
            name=f"agent-job-{job_id}",
            daemon=True,
        )
        thread.start()
        return live

    def get(self, job_id: int) -> LiveJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _restore(self, job_id: int) -> LiveJob | None:
        """进程重启后从库里恢复内存态（追问要接着原来的会话）。"""
        with session_scope() as session:
            job = session.get(AgentJob, job_id)
            if job is None:
                return None
            live = LiveJob(
                id=job.id,
                url=job.url,
                kind=job.kind,
                status=job.status,
                title=job.title,
                error=job.error,
                pages_visited=job.pages_visited,
                agent_session=job.agent_session or "",
                usage=dict(job.usage or {}),
                log=list(job.log or []),
                products=[
                    {
                        "id": row.id,
                        "name": row.name,
                        "price": row.price,
                        "price_text": row.price_text,
                        "date_text": row.date_text,
                        "detail": row.detail,
                        "image_urls": list(row.image_urls or []),
                        "source_url": row.source_url,
                    }
                    for row in job.products
                ],
            )
        with self._lock:
            self._jobs[job_id] = live
        return live

    def add_product(self, job_id: int, data: dict) -> dict | None:
        """手动添加一条商品（人工对比原始页面后补 AI 的漏）。"""
        live = self.get(job_id) or self._restore(job_id)
        if live is None:
            return None
        if live.status == "running":
            raise RuntimeError("任务进行中，跑完再手动加商品")

        with session_scope() as session:
            job = session.get(AgentJob, job_id)
            if job is None:
                return None
            position = max((row.position for row in job.products), default=-1) + 1
            row = AgentProduct(
                job_id=job_id,
                position=position,
                name=str(data.get("name") or "")[:2000],
                price=data.get("price"),
                price_text=str(data.get("price_text") or "")[:500],
                date_text=str(data.get("date_text") or "")[:500],
                detail=str(data.get("detail") or ""),
                image_urls=[str(url) for url in data.get("image_urls") or []],
                source_url=str(data.get("source_url") or "")[:2000],
            )
            session.add(row)
            session.flush()
            product_id = row.id

        product = {
            "id": product_id,
            "name": data.get("name") or "",
            "price": data.get("price"),
            "price_text": data.get("price_text") or "",
            "date_text": data.get("date_text") or "",
            "detail": data.get("detail") or "",
            "image_urls": list(data.get("image_urls") or []),
            "source_url": data.get("source_url") or "",
        }
        live.products.append(product)
        return product

    def delete_product(self, job_id: int, product_id: int) -> bool:
        """删掉一条商品（手动加错了、或人工确认是误抓）。"""
        with session_scope() as session:
            row = session.get(AgentProduct, product_id)
            if row is None or row.job_id != job_id:
                return False
            session.delete(row)

        live = self.get(job_id)
        if live is not None:
            live.products = [item for item in live.products if item.get("id") != product_id]
        return True

    def chat(self, job_id: int, message: str) -> LiveJob | None:
        """用户在同一个任务上追问：续聊原来的 dsh 会话，让它继续改 products.json。"""
        live = self.get(job_id) or self._restore(job_id)
        if live is None:
            return None
        if live.status == "running":
            raise RuntimeError("任务还在跑，等它结束再追问")
        live.status = "running"
        live.error = ""
        self._append_log(live, "user", message)
        thread = threading.Thread(
            target=self._run,
            args=(job_id,),
            kwargs={"prompt": message, "resume": True},
            name=f"agent-chat-{job_id}",
            daemon=True,
        )
        thread.start()
        return live

    def delete(self, job_id: int) -> bool:
        """删任务：跑着就先杀，然后连同落库的商品一起删。"""
        self._kill(job_id)
        with self._lock:
            self._jobs.pop(job_id, None)
        from ..models import AgentJob as _AgentJob

        with session_scope() as session:
            job = session.get(_AgentJob, job_id)
            if job is None:
                return False
            session.delete(job)
        return True

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._procs)
        for job_id in ids:
            self._kill(job_id)

    # ------------------------------------------------------------------ #
    def _kill(self, job_id: int) -> None:
        with self._lock:
            proc = self._procs.get(job_id)
        if proc is None or proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                proc.kill()
            except OSError:
                pass

    def _append_log(self, live: LiveJob, level: str, text: str) -> None:
        live.log.append({"level": level, "text": text, "at": datetime.now().isoformat(timespec="seconds")})
        if len(live.log) > MAX_LOG_LINES:
            del live.log[: len(live.log) - MAX_LOG_LINES]

    def _handle_event(self, live: LiveJob, event: dict) -> None:
        kind = event.get("type")
        if kind == "log":
            self._append_log(live, str(event.get("level") or "info"), str(event.get("text") or ""))
        elif kind == "page":
            live.pages_visited = max(live.pages_visited, int(event.get("index") or 0))
            if not live.title:
                live.title = str(event.get("title") or "")
        elif kind == "result":
            live.products = list(event.get("products") or [])
            live.pages_visited = max(live.pages_visited, int(event.get("pages_visited") or 0))
            live.title = str(event.get("title") or live.title)
            live.agent_session = str(event.get("session_id") or live.agent_session)
            live.reply = str(event.get("reply") or live.reply)
            if isinstance(event.get("usage"), dict):
                live.usage = dict(event["usage"])
            if event.get("error"):
                live.error = str(event["error"])

    # ------------------------------------------------------------------ #
    def _run(
        self,
        job_id: int,
        *,
        prompt: str | None = None,
        resume: bool = False,
        payload: dict | None = None,
        extra: str | None = None,
    ) -> None:
        live = self.get(job_id)
        if live is None:
            return

        out_dir = Path(settings.data_dir) / "data" / "agent_jobs" / str(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        # 打包版（PyInstaller）：sys.executable 是后端本体，用 --harness 分发到同一份代码
        harness_cmd = [sys.executable, "--harness"] if getattr(sys, "frozen", False) else [
            sys.executable,
            "-m",
            "app.agent.harness",
        ]
        cmd = harness_cmd + [
            "--url",
            live.url,
            "--out",
            str(out_dir),
            "--kind",
            live.kind,
        ]
        if payload is not None:
            payload_path = out_dir / "payload.json"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            cmd += ["--payload", str(payload_path)]
        if resume and live.agent_session:
            cmd += ["--resume", live.agent_session]
        if prompt:
            cmd += ["--prompt", prompt]
        elif extra and extra.strip():
            cmd += ["--extra", extra.strip()]

        env = os.environ.copy()
        if settings.deepseek_api_key:
            env["DEEPSEEK_API_KEY"] = settings.deepseek_api_key
        if not env.get("DEEPSEEK_API_KEY"):
            self._append_log(
                live, "error", "没有 DEEPSEEK_API_KEY：在「设置 → AI 抓取」里填上再重试"
            )

        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(settings.data_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                # 单独进程组：超时/删除时把 dsh、它的 bash 子进程一起带走，别留孤儿
                start_new_session=True,
            )
        except OSError as exc:
            live.status = "error"
            live.error = f"起 harness 失败：{exc}"
            self._append_log(live, "error", live.error)
            self._persist(live)
            return

        with self._lock:
            self._procs[job_id] = proc

        timer = threading.Timer(settings.agent_total_timeout, self._on_timeout, args=(job_id,))
        timer.daemon = True
        timer.start()

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                text = line.strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    self._append_log(live, "info", text[:500])
                    continue
                if isinstance(event, dict):
                    self._handle_event(live, event)
            proc.wait()
            if live.status == "running":
                live.status = "done" if proc.returncode == 0 else "error"
                if proc.returncode != 0 and not live.error:
                    live.error = f"harness 退出码 {proc.returncode}"
        except Exception as exc:  # noqa: BLE001 读流里出什么都不该把线程带走
            live.status = "error"
            live.error = f"任务异常：{exc}"
            self._append_log(live, "error", live.error)
        finally:
            timer.cancel()
            with self._lock:
                self._procs.pop(job_id, None)
            if live.status == "running":
                live.status = "error"
                live.error = live.error or "任务意外结束"
            elapsed = time.monotonic() - started
            self._append_log(live, "info", f"任务结束（{elapsed:.1f}s，状态 {live.status}）")
            self._persist(live)

    def _on_timeout(self, job_id: int) -> None:
        live = self.get(job_id)
        if live is None or live.status != "running":
            return
        live.status = "error"
        live.error = f"总超时（{settings.agent_total_timeout:.0f}s），已终止"
        self._append_log(live, "error", live.error)
        self._kill(job_id)

    def _persist(self, live: LiveJob) -> None:
        try:
            with session_scope() as session:
                job = session.get(AgentJob, live.id)
                if job is None:
                    return
                job.title = live.title or job.url
                job.kind = live.kind
                job.status = live.status
                job.error = live.error
                job.pages_visited = live.pages_visited
                job.agent_session = live.agent_session
                job.usage = live.usage or {}
                job.log = live.log[-MAX_LOG_LINES:]
                job.finished_at = utcnow()
                for existing in list(job.products):
                    session.delete(existing)
                session.flush()
                for position, product in enumerate(live.products):
                    job.products.append(
                        AgentProduct(
                            position=position,
                            name=str(product.get("name") or "")[:2000],
                            price=product.get("price"),
                            price_text=str(product.get("price_text") or "")[:500],
                            date_text=str(product.get("date_text") or "")[:500],
                            detail=str(product.get("detail") or ""),
                            image_urls=list(product.get("image_urls") or []),
                            source_url=str(product.get("source_url") or "")[:2000],
                        )
                    )
        except Exception:  # noqa: BLE001 落库失败只记日志，任务状态保持内存里的
            logger.exception("AI 抓取任务 %s 落库失败", live.id)


manager = JobManager()


def backfill_job_usage(factory=None) -> int:
    """给上线前跑的老任务补 token 统计：从 dsh 会话日志读一次写库，返回补了几条。

    init_db 里调一次。读不到（dsh 清过日志/换了存储格式）就跳过，不影响启动。
    """
    from sqlalchemy import select

    from ..db import SessionLocal

    factory = factory or SessionLocal
    filled = 0
    with factory() as session:
        rows = session.scalars(select(AgentJob).where(AgentJob.agent_session != "")).all()
        for row in rows:
            if row.usage:
                continue
            usage = read_session_usage(row.agent_session)
            if usage:
                row.usage = usage
                filled += 1
        if filled:
            session.commit()
    return filled
