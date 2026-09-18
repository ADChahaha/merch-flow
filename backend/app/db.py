from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


IS_SQLITE = settings.db_url.startswith("sqlite")

if IS_SQLITE:
    db_path = settings.db_url.replace("sqlite:///", "", 1)
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.db_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)


if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:
        """SQLite 并发三件套。

        没这些的话，两个请求同时入库就会 `database is locked`（实测 500）：
          * WAL   —— 读不阻塞写、写不阻塞读
          * busy_timeout —— 抢不到写锁时等一会儿，而不是立刻报错
          * foreign_keys —— 让 FK 真正生效
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def _ensure_columns() -> None:
    """给已经存在的表补新列（本地工具不做 Alembic，create_all 不会改旧表）。"""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "agent_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("agent_jobs")}
    additions = {
        "agent_session": "VARCHAR(64) NOT NULL DEFAULT ''",
        "kind": "VARCHAR(32) NOT NULL DEFAULT 'scrape'",
        "usage": "JSON NOT NULL DEFAULT '{}'",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE agent_jobs ADD COLUMN {name} {ddl}"))


def init_db() -> None:
    from . import models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(engine)
    _ensure_columns()

    # 老任务（这个功能上线前跑的）从 dsh 会话日志里补 token 统计
    try:
        from .agent.jobs import backfill_job_usage

        backfill_job_usage()
    except Exception:  # noqa: BLE001 统计补不上不能挡住启动
        logging.getLogger(__name__).exception("token 用量回填失败")


def get_session() -> Iterator[Session]:
    """FastAPI 依赖注入用。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """脚本 / 测试用上下文。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
