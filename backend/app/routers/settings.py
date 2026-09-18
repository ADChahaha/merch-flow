"""设置接口：AI 抓取（DeepSeek）+ B 站上架凭证。

保存写 backend/.env 并同步热更新进程内 settings —— 不用重启。
密钥只写不读：GET 只回「配没配 + 末尾 4 位」。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..agent.env_store import mask_key, update_env_file
from ..config import settings
from ..schemas import (
    AgentSettingsOut,
    BilibiliSettingsOut,
    SettingsOut,
    SettingsUpdate,
    UiSettingsOut,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}
ALLOWED_REASONING = {"off", "low", "high", "max"}


def _out() -> SettingsOut:
    return SettingsOut(
        agent=AgentSettingsOut(
            has_key=bool(settings.deepseek_api_key),
            key_hint=mask_key(settings.deepseek_api_key),
            model=settings.agent_model,
            reasoning=settings.agent_reasoning or "off",
        ),
        bilibili=BilibiliSettingsOut(
            has_token=bool(settings.bilibili_access_token),
            token_hint=mask_key(settings.bilibili_access_token),
            client_id=settings.bilibili_client_id,
            has_client_secret=bool(settings.bilibili_client_secret),
            secret_hint=mask_key(settings.bilibili_client_secret),
        ),
        ui=UiSettingsOut(source_open=settings.ui_source_open),
    )


@router.get("", response_model=SettingsOut)
def get_settings() -> SettingsOut:
    return _out()


@router.put("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate) -> SettingsOut:
    updates: dict[str, str] = {}

    if payload.deepseek_api_key is not None:
        key = payload.deepseek_api_key.strip()
        updates["DEEPSEEK_API_KEY"] = key
        settings.deepseek_api_key = key

    if payload.agent_model is not None and payload.agent_model.strip():
        model = payload.agent_model.strip()
        if model not in ALLOWED_MODELS:
            raise HTTPException(status_code=400, detail=f"模型只支持 {' / '.join(sorted(ALLOWED_MODELS))}")
        updates["EC_AGENT_MODEL"] = model
        settings.agent_model = model

    if payload.agent_reasoning is not None:
        reasoning = payload.agent_reasoning.strip().lower()
        if reasoning not in ALLOWED_REASONING:
            raise HTTPException(
                status_code=400, detail=f"推理强度只支持 {' / '.join(sorted(ALLOWED_REASONING))}"
            )
        updates["EC_AGENT_REASONING"] = reasoning
        settings.agent_reasoning = reasoning

    if payload.bilibili_access_token is not None:
        token = payload.bilibili_access_token.strip()
        updates["BILIBILI_ACCESS_TOKEN"] = token
        settings.bilibili_access_token = token

    if payload.bilibili_client_id is not None:
        client_id = payload.bilibili_client_id.strip()
        updates["BILIBILI_CLIENT_ID"] = client_id
        settings.bilibili_client_id = client_id

    if payload.bilibili_client_secret is not None:
        secret = payload.bilibili_client_secret.strip()
        updates["BILIBILI_CLIENT_SECRET"] = secret
        settings.bilibili_client_secret = secret

    if payload.ui_source_open is not None:
        value = bool(payload.ui_source_open)
        updates["EC_UI_SOURCE_OPEN"] = "1" if value else "0"
        settings.ui_source_open = value

    if updates:
        update_env_file(updates)
    return _out()
