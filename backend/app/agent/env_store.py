"""把设置写回 backend/.env（不想手改文件时的保存口）。

只动它认识的键，别的行原样保留；写文件后顺手 chmod 600。
进程内 settings 是另一回事：路由保存后会同步热更新（不用重启）。
"""

from __future__ import annotations

import os
from pathlib import Path

from ..config import BASE_DIR

ENV_PATH = Path(BASE_DIR) / ".env"


def update_env_file(updates: dict[str, str], path: Path | None = None) -> Path:
    target = path or ENV_PATH
    lines: list[str] = []
    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                continue
        out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def mask_key(key: str) -> str:
    """只回末尾 4 位，界面用来显示「配过没有」。"""
    if not key:
        return ""
    tail = key[-4:] if len(key) > 4 else ""
    return f"••••{tail}"
