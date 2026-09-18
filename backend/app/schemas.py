"""API 契约（AI 抓取）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .models import AgentJob, AgentProduct


class AgentJobCreate(BaseModel):
    url: str = Field(min_length=4, max_length=2000)
    # 首轮的自定义要求：拼在默认抓取提示词后面（例：只抓 Blu-ray / 价格换算成人民币）
    prompt: str = Field(default="", max_length=2000)


class AgentProductCreate(BaseModel):
    """手动添加一条商品（人工发现 AI 漏掉/需要补充的）。"""

    name: str = Field(min_length=1, max_length=500)
    price: int | None = Field(default=None, ge=0)
    price_text: str = Field(default="", max_length=200)
    date_text: str = Field(default="", max_length=300)
    detail: str = Field(default="", max_length=2000)
    image_urls: list[str] = Field(default_factory=list, max_length=50)
    source_url: str = Field(default="", max_length=2000)


class AgentChatRequest(BaseModel):
    """用户追问：接着这个任务原来的会话继续聊（自由输入）。"""

    message: str = Field(min_length=1, max_length=4000)


class TaobaoPublishItem(BaseModel):
    """浏览器自动上架的一件商品（从上架清单来）。"""

    name: str = Field(min_length=1, max_length=500)
    price: float | None = Field(default=None, ge=0)
    stock: int = Field(default=100, ge=0)
    images: list[str] = Field(default_factory=list)
    detail: str = ""


class TaobaoPublishJobRequest(BaseModel):
    """淘宝上架（浏览器自动化）：不依赖开放平台 API，agent 操作卖家中心网页。"""

    items: list[TaobaoPublishItem] = Field(min_length=1, max_length=20)
    category_url: str = Field(default="", max_length=2000, description="可选：直连类目 URL 或 catId")
    note: str = Field(default="", max_length=2000)


class AgentSettingsOut(BaseModel):
    """AI 抓取设置：key 只给状态和掩码，绝不回明文。"""

    has_key: bool = False
    key_hint: str = ""
    model: str = ""
    reasoning: str = "off"


class BilibiliSettingsOut(BaseModel):
    """B 站上架凭证：同样只给状态和掩码。"""

    has_token: bool = False
    token_hint: str = ""
    client_id: str = ""
    has_client_secret: bool = False
    secret_hint: str = ""


class UiSettingsOut(BaseModel):
    """界面默认值（在设置里配，页面加载时用）。"""

    source_open: bool = True


class SettingsOut(BaseModel):
    agent: AgentSettingsOut
    bilibili: BilibiliSettingsOut
    ui: UiSettingsOut


class SettingsUpdate(BaseModel):
    """None = 不改；空字符串 = 清除。"""

    deepseek_api_key: str | None = Field(default=None, max_length=500)
    agent_model: str | None = Field(default=None, max_length=100)
    agent_reasoning: str | None = Field(default=None, max_length=20)
    bilibili_access_token: str | None = Field(default=None, max_length=2000)
    bilibili_client_id: str | None = Field(default=None, max_length=200)
    bilibili_client_secret: str | None = Field(default=None, max_length=500)
    ui_source_open: bool | None = None


class AgentProductOut(BaseModel):
    """AI 抽出来的一条商品。id 在任务还在跑时是 None（还没落库）。"""

    id: int | None = None
    name: str
    price: int | None = None
    price_text: str = ""
    date_text: str = ""
    detail: str = ""
    image_urls: list[str] = Field(default_factory=list)
    source_url: str = ""

    @classmethod
    def of_live(cls, data: dict) -> "AgentProductOut":
        return cls(
            id=data.get("id"),
            name=str(data.get("name") or ""),
            price=data.get("price"),
            price_text=str(data.get("price_text") or ""),
            date_text=str(data.get("date_text") or ""),
            detail=str(data.get("detail") or ""),
            image_urls=list(data.get("image_urls") or []),
            source_url=str(data.get("source_url") or ""),
        )

    @classmethod
    def of_row(cls, row: AgentProduct) -> "AgentProductOut":
        return cls(
            id=row.id,
            name=row.name,
            price=row.price,
            price_text=row.price_text,
            date_text=row.date_text,
            detail=row.detail,
            image_urls=list(row.image_urls or []),
            source_url=row.source_url,
        )


class AgentJobSummaryOut(BaseModel):
    """左栏 AI 记录用的摘要（不带日志和商品，列表轻一点）。"""

    id: int
    url: str
    kind: str = "scrape"
    title: str = ""
    status: str = "running"
    error: str = ""
    pages_visited: int = 0
    product_count: int = 0
    created_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def of_row(cls, job: AgentJob) -> "AgentJobSummaryOut":
        return cls(
            id=job.id,
            url=job.url,
            kind=job.kind or "scrape",
            title=job.title,
            status=job.status,
            error=job.error,
            pages_visited=job.pages_visited,
            product_count=len(job.products),
            created_at=job.created_at,
            finished_at=job.finished_at,
        )


class AgentJobOut(AgentJobSummaryOut):
    log: list[dict] = Field(default_factory=list)
    products: list[AgentProductOut] = Field(default_factory=list)

    @classmethod
    def of_row(cls, job: AgentJob) -> "AgentJobOut":
        return cls(
            id=job.id,
            url=job.url,
            kind=job.kind or "scrape",
            title=job.title,
            status=job.status,
            error=job.error,
            pages_visited=job.pages_visited,
            product_count=len(job.products),
            created_at=job.created_at,
            finished_at=job.finished_at,
            log=list(job.log or []),
            products=[AgentProductOut.of_row(row) for row in job.products],
        )

    @classmethod
    def of_live(cls, live) -> "AgentJobOut":
        return cls(
            id=live.id,
            url=live.url,
            kind=getattr(live, "kind", "scrape") or "scrape",
            title=live.title,
            status=live.status,
            error=live.error,
            pages_visited=live.pages_visited,
            product_count=len(live.products),
            log=list(live.log),
            products=[AgentProductOut.of_live(item) for item in live.products],
        )
