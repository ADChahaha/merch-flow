"""上架接口的契约 —— 照抄哔哩哔哩开放平台「商品发布」product_add。

  POST https://member.bilibili.com/arcopen/fn/market/common/product_add

字段/限制都是文档里的（见每条注释）。我们这边不代持 Access-Token，
所以 `/api/listings` 的职责是：**校验 + 组装出可直接发给 B 站的请求体**，
真正的发布由调用方拿着请求体去调（或者在设置里配上凭证后再接）。

几个容易踩的硬限制（文档原文）：
  * name    6-60 字
  * pic     轮播图，多张用换行隔，**最多 5 张**，第一张作主图
  * description 图片描述，多张用换行隔，**最多 50 张**
  * text_description 文字描述 ≤500 字
  * spec_prices 数量必须与规格组合数一致
  * price   单位是**分**
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_CAROUSEL_IMAGES = 5
MAX_DESCRIPTION_IMAGES = 50
MAX_TEXT_DESCRIPTION = 500
NAME_MIN, NAME_MAX = 6, 60

PRODUCT_ADD_ENDPOINT = "https://member.bilibili.com/arcopen/fn/market/common/product_add"


def join_images(urls: list[str]) -> str:
    """多张图片用换行符分隔（文档要求）。"""
    return "\n".join(url.strip() for url in urls if url and url.strip())


def split_images(value: str) -> list[str]:
    return [part.strip() for part in (value or "").replace("\r", "\n").split("\n") if part.strip()]


class AfterSaleService(BaseModel):
    """售后服务。7-0 不支持 7 天无理由；7-1 支持。"""

    supply_day_return_selector: str = Field(default="7-1", pattern=r"^7-[01]$")


class SpecValue(BaseModel):
    value_name: str


class SpecValueGroup(BaseModel):
    """一个规格项（如「款式」）及其可选值。"""

    property_name: str
    values: list[SpecValue] = Field(min_length=1)


class SpecInfo(BaseModel):
    spec_values: list[SpecValueGroup] = Field(min_length=1)


class SellProperty(BaseModel):
    """某个 SKU 在某个规格项上取的值。"""

    property_name: str
    value_name: str


class SpecPrice(BaseModel):
    """一个 SKU。"""

    stock_num: int = Field(ge=0)
    price: int = Field(ge=1, description="价格，单位：分")
    code: str | None = None
    sell_properties: list[SellProperty] = Field(min_length=1)


class ProductAddRequest(BaseModel):
    """商品发布请求体。"""

    model_config = ConfigDict(extra="forbid")

    category_leaf_id: int = Field(description="叶子类目 ID，从类目接口获取")
    name: str = Field(min_length=NAME_MIN, max_length=NAME_MAX)
    pic: str = Field(description="轮播图，换行分隔，第一张作主图，最多 5 张")
    description: str = Field(default="", description="图片描述，换行分隔，最多 50 张")
    text_description: str = Field(default="", max_length=MAX_TEXT_DESCRIPTION)
    freight_id: int = Field(description="运费模板 ID")
    delivery_delay_day: int | None = Field(default=None, description="承诺发货时间，现货必填")
    presell_type: int = Field(default=0, description="0-现货发货")
    commit: bool = Field(default=False, description="false-仅保存；true-保存+提审")
    product_type: int | None = Field(default=None, description="0-普通商品 1-虚拟服务")
    operate_status: int | None = Field(default=None, description="0-立即上架 1-定时上架 2-下架")
    scheduled_on_shelf_time: int | None = Field(default=None, description="定时上架时间，毫秒时间戳")
    limit_per_buyer: int = Field(default=0, ge=0, description="每用户累计限购件数，0 不限购")
    product_format: str | None = Field(default=None, description="属性 JSON 字符串")
    after_sale_service: AfterSaleService = Field(default_factory=AfterSaleService)
    spec_info: SpecInfo
    spec_pic: str = Field(default="", description="规格图片")
    spec_prices: list[SpecPrice] = Field(min_length=1)
    ext_property: dict | None = None

    @field_validator("pic")
    @classmethod
    def _check_carousel(cls, value: str) -> str:
        images = split_images(value)
        if not images:
            raise ValueError("轮播图不能为空")
        if len(images) > MAX_CAROUSEL_IMAGES:
            raise ValueError(f"轮播图最多 {MAX_CAROUSEL_IMAGES} 张（当前 {len(images)} 张）")
        return value

    @field_validator("description")
    @classmethod
    def _check_description(cls, value: str) -> str:
        images = split_images(value)
        if len(images) > MAX_DESCRIPTION_IMAGES:
            raise ValueError(f"图片描述最多 {MAX_DESCRIPTION_IMAGES} 张（当前 {len(images)} 张）")
        return value

    @field_validator("scheduled_on_shelf_time")
    @classmethod
    def _check_scheduled(cls, value: int | None) -> int | None:
        return value

    def validate_spec_consistency(self) -> list[str]:
        """文档要求：sku 数量和规格组合数必须一致。返回问题列表（空 = 通过）。"""
        problems: list[str] = []
        combos = 1
        for group in self.spec_info.spec_values:
            combos *= len(group.values)
        if combos != len(self.spec_prices):
            problems.append(
                f"SKU 数量（{len(self.spec_prices)}）必须等于规格组合数（{combos}）"
            )
        if self.operate_status == 1 and not self.scheduled_on_shelf_time:
            problems.append("定时上架（operate_status=1）必须传 scheduled_on_shelf_time")
        if self.presell_type == 0 and self.delivery_delay_day is None:
            problems.append("现货发货（presell_type=0）建议传 delivery_delay_day（承诺发货时间）")
        return problems


class ProductAddResponse(BaseModel):
    """我们返回的是「可直接发给 B 站的请求体」+ 校验结果。"""

    ok: bool
    endpoint: str = PRODUCT_ADD_ENDPOINT
    request: dict
    warnings: list[str] = Field(default_factory=list)
    note: str = ""


class CategoryNode(BaseModel):
    """类目。真实 ID 请走 B 站「查询类目」接口，这里只给一份可用的示例树。"""

    id: int
    name: str
    children: list["CategoryNode"] = Field(default_factory=list)


class FreightTemplate(BaseModel):
    freight_id: int
    name: str


CategoryNode.model_rebuild()
