"""上架接口。

Bilibili：校验 + 组装 product_add 请求体（不代持 Access-Token，也不代为发送）。
淘宝：开放平台 API 申请不到，改成**浏览器自动化**——起一个 dsh agent 任务，
它用 CDP 挂接用户本机开着调试端口的 Chrome，自己操作卖家中心网页上架。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..agent.jobs import manager
from ..domain.bilibili import (
    PRODUCT_ADD_ENDPOINT,
    CategoryNode,
    FreightTemplate,
    ProductAddRequest,
    ProductAddResponse,
)
from ..schemas import AgentJobOut, TaobaoPublishJobRequest

router = APIRouter(prefix="/api/listings", tags=["listings"])

# 示例类目树（真实 ID 需要走 B 站「查询类目」接口获取）
CATEGORY_TREE = [
    CategoryNode(
        id=2,
        name="周边",
        children=[
            CategoryNode(id=2301, name="手办"),
            CategoryNode(id=2302, name="徽章"),
            CategoryNode(id=2303, name="立牌"),
            CategoryNode(id=2304, name="挂件"),
            CategoryNode(id=2305, name="文具"),
            CategoryNode(id=2306, name="服饰"),
        ],
    ),
    CategoryNode(
        id=3,
        name="模玩",
        children=[
            CategoryNode(id=3101, name="拼装模型"),
            CategoryNode(id=3102, name="成品模型"),
            CategoryNode(id=3103, name="扭蛋"),
        ],
    ),
    CategoryNode(
        id=4,
        name="图书",
        children=[
            CategoryNode(id=4101, name="画集"),
            CategoryNode(id=4102, name="漫画"),
            CategoryNode(id=4103, name="杂志"),
        ],
    ),
    CategoryNode(
        id=5,
        name="影音",
        children=[
            CategoryNode(id=5101, name="蓝光"),
            CategoryNode(id=5102, name="CD"),
        ],
    ),
]

# 示例运费模板（真实 ID 需要走 B 站「运费模板」接口获取）
FREIGHT_TEMPLATES = [
    FreightTemplate(freight_id=1004258, name="默认运费模板（包邮）"),
    FreightTemplate(freight_id=1004259, name="全国 12 元"),
    FreightTemplate(freight_id=1004260, name="港澳台/海外"),
]


@router.get("/categories")
def categories() -> dict:
    return {
        "tree": [node.model_dump() for node in CATEGORY_TREE],
        "note": "示例类目树，真实的 category_leaf_id 请走 B 站「查询类目」接口。",
    }


@router.get("/freight-templates")
def freight_templates() -> dict:
    return {
        "templates": [t.model_dump() for t in FREIGHT_TEMPLATES],
        "note": "示例运费模板，真实 freight_id 请走 B 站「运费模板」接口。",
    }


@router.post("/bilibili", response_model=ProductAddResponse)
def create_bilibili_listing(payload: ProductAddRequest) -> ProductAddResponse:
    """校验并组装 B 站商品发布请求体。

    - 校验不过返回 422（Pydantic 自动）；
    - 规格数对不上等业务问题返回 400；
    - 通过则回传 `request`：可直接作为 body 发到 `endpoint`。
    """
    problems = payload.validate_spec_consistency()
    if problems:
        raise HTTPException(status_code=400, detail={"problems": problems})

    body = payload.model_dump(exclude_none=True)
    return ProductAddResponse(
        ok=True,
        endpoint=PRODUCT_ADD_ENDPOINT,
        request=body,
        warnings=[],
        note=(
            "请求体已按 B 站 product_add 组装完成。实际发布需要 Access-Token 与签名"
            "（x-bili-* 请求头），本服务不代持凭证，所以没有代为发送。"
        ),
    )


# --------------------------------------------------------------------------- #
# 淘宝：浏览器自动化上架（开放平台 API 申请不到，改由 dsh agent 操作网页）
# --------------------------------------------------------------------------- #
@router.post("/taobao/browser", response_model=AgentJobOut)
def create_taobao_browser_job(payload: TaobaoPublishJobRequest) -> AgentJobOut:
    """起一个浏览器上架任务（后台 dsh agent 用 CDP 操作本机 Chrome 的卖家中心）。

    返回任务对象；进度看日志（右下角 popup），截图在 `/api/agent/jobs/{id}/files`。
    """
    job = manager.start(
        "taobao://publish",
        kind="taobao_publish",
        payload=payload.model_dump(),
    )
    return AgentJobOut.of_live(job)
