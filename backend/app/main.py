from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers import agent, listings, settings as settings_router

logging.basicConfig(
    level=os.getenv("EC_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    # 关掉会话缓存里的浏览器（抓取用的临时 Chrome / StealthySession）
    from .scrapers.transport import close_all_transports

    close_all_transports()
    # 杀掉还在跑的 AI 抓取子进程
    from .agent.jobs import manager

    manager.shutdown()


app = FastAPI(
    title="AI 商品聚合 / 上架助手",
    version="0.3.0",
    description=(
        "给一个 URL，deepseek harness 自己递归翻页把商品抽出来（app/agent/），"
        "结果落库；上架接口见 app/routers/listings.py。"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent.router)
app.include_router(listings.router)
app.include_router(settings_router.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "db": settings.db_url,
        "agent_model": settings.agent_model,
        "agent_key_configured": bool(settings.deepseek_api_key),
    }


# 前端构建产物存在时直接由后端 serve（Electron 壳只开一个 URL，也不用 CORS）。
# 挂在最后：/api/* 已经先注册，不会挡到接口。
_FRONTEND_DIST = Path(
    os.getenv("EC_FRONTEND_DIST") or Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
