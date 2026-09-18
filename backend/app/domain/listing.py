"""上架内容（ListingContent）—— 与「搜索/爬取」完全隔离的最小单位。

设计约定（重要，别破坏）：

* 本模块 **只依赖 pydantic**，不 import 任何 ORM / scraper / service。
  这样右边「上架」界面可以独立演进，爬虫侧改版永远不会波及上架侧。
* 一个 `ListingContent` 就是一次上架/一条商品信息的最小单位：
  名字、图片、价格、可预约时间、评论。
* 「搜索」域把它当作一条 offer 的内容载体（外加站点、商品 FK 等爬取态字段）；
  将来的「上架」域把它整块拿去当草稿，两者共用形状、不共享逻辑。
* 落库时用 `ListingContentMixin` 把这 5 个字段铺成列，
  于是「搜索结果表」和将来的「上架草稿表」字段完全一致。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

CURRENCY_JPY = "JPY"

# 全角/半角符号、分隔符统一
_PRICE_JUNK = re.compile(r"[￥¥\\,\s]")
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def normalize_text(value: str | None) -> str:
    """统一空白 + 全角数字 + 去零宽字符。

    骏河屋的 `get_all_text()` 会在节点间插入换行，ブランド 还会带 `[ ]`，
    所以所有文本进库前都过这一道。
    """
    if not value:
        return ""
    text = value.replace("\u3000", " ").replace("\u200b", "")
    text = text.translate(_FULLWIDTH_DIGITS)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_price(value: str | int | None) -> int | None:
    """从任意价格文本里抠出日元整数。

    能吃下：`中古：￥2,100` / `¥2100` / `1,980円` / `２１００` / `-`(None)
    吃不下（如 `品切れ`）返回 None —— 调用方需要自己走 makeple / 特卖分支。
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = normalize_text(value).translate(_FULLWIDTH_DIGITS)
    match = re.search(r"([\d][\d,]*)", _PRICE_JUNK.sub("", text))
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_japanese_date(value: str | None) -> date | None:
    """解析 `2026-06-30` / `2026/06/30` / `2026年6月30日` / `2026年6月`。"""
    if not value:
        return None
    text = normalize_text(value)
    m = re.search(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})", text)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        m = re.search(r"(\d{4})\s*[-/年]\s*(\d{1,2})", text)
        if not m:
            return None
        y, mo = int(m.group(1)), int(m.group(2))
        d = 1
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ReserveWindow(BaseModel):
    """可预约时间。爬到的 offer 常常只知道一头（发售日 = 预约截止 / 受付开始）。"""

    model_config = ConfigDict(frozen=True)

    start: date | None = None
    end: date | None = None

    @property
    def is_open_ended(self) -> bool:
        return self.start is None and self.end is None

    def is_open_at(self, moment: date | None = None) -> bool:
        """预约窗口是否还没关。没填窗口 = 不限制。"""
        today = moment or utcnow().date()
        if self.start and today < self.start:
            return False
        return not (self.end and today > self.end)

    def display(self) -> str:
        if self.is_open_ended:
            return ""
        fmt = "%Y-%m-%d"
        left = self.start.strftime(fmt) if self.start else "即時"
        right = self.end.strftime(fmt) if self.end else "无期限"
        return f"{left} ~ {right}"


class ListingContent(BaseModel):
    """上架/商品信息最小单位。字段顺序即界面顺序（名字→价格→可预约时间→图片→评论）。"""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    price: int | None = None
    currency: str = CURRENCY_JPY
    reserve: ReserveWindow = Field(default_factory=ReserveWindow)
    images: list[str] = Field(default_factory=list)
    comment: str = ""

    _norm = field_validator("title", "comment", mode="before")(normalize_text)
    _imgs = field_validator("images", mode="before")(
        lambda v: [] if not v else [normalize_text(i) for i in v if i and normalize_text(i)]
    )

    @property
    def price_display(self) -> str:
        if self.price is None:
            return "价格未定"
        symbol = "￥" if self.currency == CURRENCY_JPY else f"{self.currency} "
        return f"{symbol}{self.price:,}"

    @property
    def cover(self) -> str | None:
        return self.images[0] if self.images else None

    def is_complete(self) -> bool:
        """够不够格拿去上架：名字 + 价格 + 至少一张图。"""
        return bool(self.title) and self.price is not None and bool(self.images)
