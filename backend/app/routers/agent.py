"""AI 抓取接口：给一个 URL，agent 自己去递归翻页找商品。

任务在后台线程里跑（子进程是 deepseek harness），前端轮询拿日志和结果。
和现搜不同：这里的结果**落库**，左栏能回看历史。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.jobs import manager
from ..config import BASE_DIR
from ..db import get_session
from ..models import AgentJob
from ..schemas import (
    AgentChatRequest,
    AgentJobCreate,
    AgentJobOut,
    AgentJobSummaryOut,
    AgentProductCreate,
    AgentProductOut,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _job_workdir(job_id: int) -> Path:
    return Path(BASE_DIR) / "data" / "agent_jobs" / str(job_id)


def _validate_url(raw: str) -> str:
    url = (raw or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HTTPException(status_code=400, detail="请输入完整的 http(s) URL")
    return url


@router.post("/jobs", response_model=AgentJobOut, status_code=201)
def create_job(payload: AgentJobCreate) -> AgentJobOut:
    """起一个 AI 抓取任务。立即返回，日志靠轮询 GET /api/agent/jobs/{id} 拿。

    prompt 是首轮的自定义要求，拼在默认抓取提示词后面（不覆盖）。
    """
    live = manager.start(_validate_url(payload.url), extra=payload.prompt or None)
    return AgentJobOut.of_live(live)


@router.get("/jobs", response_model=list[AgentJobSummaryOut])
def list_jobs(session: Session = Depends(get_session)) -> list[AgentJobSummaryOut]:
    stmt = select(AgentJob).order_by(AgentJob.id.desc()).limit(200)
    return [AgentJobSummaryOut.of_row(job) for job in session.scalars(stmt).all()]


@router.get("/jobs/{job_id}", response_model=AgentJobOut)
def get_job(job_id: int, session: Session = Depends(get_session)) -> AgentJobOut:
    """任务详情：进程内存里有就优先用它（实时日志）；重启后再看走库里的历史。"""
    live = manager.get(job_id)
    if live is not None:
        return AgentJobOut.of_live(live)
    job = session.get(AgentJob, job_id)
    if job is not None:
        return AgentJobOut.of_row(job)
    raise HTTPException(status_code=404, detail="任务不存在")


@router.get("/jobs/{job_id}/files")
def list_job_files(job_id: int, session: Session = Depends(get_session)) -> dict:
    """任务目录里的截图/图片（agent 每步截图，用来核对上架/抓取过程）。"""
    if manager.get(job_id) is None and session.get(AgentJob, job_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    root = _job_workdir(job_id)
    files: list[dict] = []
    if root.exists():
        for path in sorted(root.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            rel = path.relative_to(root).as_posix()
            files.append(
                {
                    "name": rel,
                    "url": f"/api/agent/jobs/{job_id}/files/{rel}",
                    "mtime": int(path.stat().st_mtime),
                }
            )
            if len(files) >= 60:
                break
    return {"files": files}


@router.get("/jobs/{job_id}/files/{name:path}")
def get_job_file(job_id: int, name: str) -> FileResponse:
    root = _job_workdir(job_id).resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if target.suffix.lower() not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="只支持图片文件")
    return FileResponse(target)


@router.post("/jobs/{job_id}/products", response_model=AgentProductOut, status_code=201)
def add_job_product(job_id: int, payload: AgentProductCreate) -> AgentProductOut:
    """手动补一条商品（对照原始页面发现 AI 漏了时用）。"""
    try:
        product = manager.add_product(job_id, payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if product is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return AgentProductOut.of_live(product)


@router.delete("/jobs/{job_id}/products/{product_id}")
def delete_job_product(job_id: int, product_id: int) -> dict:
    if not manager.delete_product(job_id, product_id):
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"ok": True}


@router.post("/jobs/{job_id}/chat", response_model=AgentJobOut)
def chat_job(
    job_id: int, payload: AgentChatRequest, session: Session = Depends(get_session)
) -> AgentJobOut:
    """追问：接着这个任务的 dsh 会话继续聊，agent 带着上下文和 products.json 继续改。"""
    if manager.get(job_id) is None and session.get(AgentJob, job_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        live = manager.chat(job_id, payload.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if live is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return AgentJobOut.of_live(live)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, session: Session = Depends(get_session)) -> dict:
    """删任务：跑着就先杀进程，再删库（agent_products 跟着级联删）。"""
    job = session.get(AgentJob, job_id)
    if job is None and manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    manager.delete(job_id)
    return {"ok": True, "job_id": job_id}
