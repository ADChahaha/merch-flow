"""全局配置。所有开关都可用环境变量覆盖，方便在「真实抓取」与「Mock」之间切换。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# 数据目录：.env / 数据库 / agent_jobs 都放这。打包版由 Electron 指到系统应用数据目录
# （EC_DATA_DIR），源码运行时就是 backend/。基线值在后文 DATA_DIR 定义。


def _load_dotenv(path: Path) -> None:
    """把 backend/.env 读进环境变量（已存在的真环境变量优先）。

    不引第三方依赖：只认 KEY=VALUE / # 注释 / 引号可有可无。
    DEEPSEEK_API_KEY 这类密钥就放这里，不要提交到仓库。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _resolve_data_dir() -> Path:
    value = (os.getenv("EC_DATA_DIR") or "").strip()
    return Path(value).expanduser() if value else BASE_DIR


DATA_DIR = _resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

_load_dotenv(DATA_DIR / ".env")


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return int(raw)


@dataclass
class Settings:
    # ---- 数据目录 ----
    data_dir: Path = DATA_DIR

    # ---- 数据库 ----
    db_url: str = os.getenv("EC_DB_URL", f"sqlite:///{DATA_DIR / 'data' / 'ec.db'}")

    # ---- 反爬（AI 抓取的页面获取用：直连失败退到浏览器通道） ----
    # Chrome 可执行文件。留空 = 按平台自动探测（macOS / Windows / Linux 的常见安装路径）
    chrome_path: str = os.getenv("EC_CHROME_PATH", "")
    cdp_port: int = _env_int("EC_CDP_PORT", 9333)
    challenge_wait_seconds: float = float(os.getenv("EC_CHALLENGE_WAIT", "12"))

    # 有界面浏览器（headless 过不了 CF，必须 headed）
    headless: bool = _env_bool("EC_HEADLESS", False)
    # 每次冷启动浏览器太贵：会话在进程内复用（一个进程只起一次浏览器）
    session_reuse: bool = _env_bool("EC_SESSION_REUSE", True)
    # 别让抓取用的浏览器抢焦点：
    #   macOS   → `open -g` 后台启动，窗口不跳到最前面
    #   Windows → STARTUPINFO(SW_SHOWMINNOACTIVE) 最小化且不激活
    #   Linux   → 只能靠 EC_BROWSER_OFFSCREEN
    browser_background: bool = _env_bool("EC_BROWSER_BACKGROUND", True)
    # 浏览器空闲多久后自动关掉（秒）。0 = 不自动关。
    # 默认 1 小时：回收太急（原 180s）会让隔几分钟的每次搜索都变成冷启动
    # —— 就算不抢焦点，Dock / 窗口层也会闪一下。代价是后台常驻一只 Chrome。
    browser_idle_timeout: float = float(os.getenv("EC_BROWSER_IDLE_TIMEOUT", "3600"))
    # 把抓取窗口挪到屏幕外（默认开）。`open -g` / SW_SHOWMINNOACTIVE 只能保证
    # 「启动时不激活」，CDP 点击或新开标签页仍可能把窗口顶到最前面，
    # 挪出屏幕才是彻底不打扰。想看窗口排查问题就设 EC_BROWSER_OFFSCREEN=0。
    browser_offscreen: bool = _env_bool("EC_BROWSER_OFFSCREEN", True)
    browser_timeout_ms: int = _env_int("EC_BROWSER_TIMEOUT_MS", 45_000)

    # 地区封锁的站点挂代理直连即可（EC_PROXY）
    proxy: str | None = os.getenv("EC_PROXY") or None

    # 直连超时（秒）
    request_timeout: float = float(os.getenv("EC_REQUEST_TIMEOUT", "25"))

    # ---- 界面默认值 ----
    # 商品页默认是否打开左边的「原始页面」iframe（核对用）
    ui_source_open: bool = _env_bool("EC_UI_SOURCE_OPEN", True)

    # ---- AI 抓取（deepseek harness） ----
    # 密钥放 backend/.env 的 DEEPSEEK_API_KEY=...（见 .env.example），不要写进代码
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    # dsh（DeepSeek Harness）的模型：deepseek-v4-flash（快/便宜，默认）或 deepseek-v4-pro
    agent_model: str = os.getenv("EC_AGENT_MODEL", "deepseek-v4-flash")
    # 思考/推理强度：off（默认，不开 thinking）/ low / high / max（传给 dsh 的 thinking + reasoningEffort）
    agent_reasoning: str = os.getenv("EC_AGENT_REASONING", "off")
    # 单个任务总超时（秒），超了直接杀子进程（唯一的硬保险，防跑飞）
    agent_total_timeout: float = float(os.getenv("EC_AGENT_TOTAL_TIMEOUT", "900"))
    # 喂给模型的正文截断长度（字符），控制 token
    agent_page_text_limit: int = _env_int("EC_AGENT_TEXT_LIMIT", 20_000)

    # ---- Bilibili 开放平台凭证（上架用，不代持，只存本地） ----
    bilibili_access_token: str = os.getenv("BILIBILI_ACCESS_TOKEN", "")
    bilibili_client_id: str = os.getenv("BILIBILI_CLIENT_ID", "")
    bilibili_client_secret: str = os.getenv("BILIBILI_CLIENT_SECRET", "")



    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("EC_CORS_ORIGINS", "http://localhost:5173").split(",")
            if o.strip()
        ]
    )


settings = Settings()
