from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .domain.listing import utcnow


class AgentJob(Base):
    """一次「输入 URL → AI 递归抓商品」的任务。

    和现搜不同：AI 抓取的结果**落库**，因为 agent 跑一轮很贵，
    历史要能回看（左栏的 AI 记录就是这张表）。
    """

    __tablename__ = "agent_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # scrape = URL 抓商品；taobao_publish = 浏览器自动上架
    kind: Mapped[str] = mapped_column(String(32), default="scrape", nullable=False)
    # running | done | error
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    pages_visited: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # dsh 的会话 id：续聊（用户追问）靠它恢复上下文
    agent_session: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # agent 的完整执行日志（一行一条，前端右下角 popup 回放用）
    log: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # 整个会话（含续聊）累计 token：{input, output, cache_read, cache_write, total}
    usage: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    products: Mapped[list["AgentProduct"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="AgentProduct.position",
    )


class AgentProduct(Base):
    """AI 从抓取页面里抽出来的一条商品。

    字段比现搜的 Offer 少：agent 是按页面内容自由抽取的，
    这里只存「确定为上线素材」的公共部分（名字/价格/图片/描述/日期/来源）。
    """

    __tablename__ = "agent_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("agent_jobs.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 价格原文（西日本: "550円(税込)" / "$12.99"），站点怎么写就怎么留
    price_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 发售日 / 举办日期等日期原文
    date_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 商品详情（规格、尺寸、备注……agent 整理后的文本）
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 商品图 URL 列表（绝对地址，第一张当封面）
    image_urls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # 商品自己的页面（详情页链接），抽不到就空
    source_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    job: Mapped[AgentJob] = relationship(back_populates="products")
