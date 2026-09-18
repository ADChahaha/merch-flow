"""取页面：先直连（curl_cffi 指纹伪装），撞上 CF 盾再退到浏览器通道。

这正是「复杂情况怎么办」的落地版：
  * 普通站点    → HttpTransport（带的还是项目的代理配置 EC_PROXY）
  * CF 盾站点   → StealthyTransport（patchright + solve_cloudflare），
                  复用骏河屋那套已经调通的通道，不另造轮子。

数据源不固定，所以这里不认站点，只认「这个页面能不能读」。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import Settings, settings as default_settings
from ..scrapers.transport import (
    CHALLENGE_MARKERS,
    HttpTransport,
    StealthyTransport,
    TransportError,
)

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class FetchError(RuntimeError):
    """这个页面拿不到（网络 / HTTP 错误 / 盾）。"""


def is_challenge_page(html: str) -> bool:
    """CF 挑战页的决定性特征（和 ChromeCdpTransport 用的是同一套判据）。"""
    lowered = html[:200_000].lower()
    return any(marker.lower() in lowered for marker in CHALLENGE_MARKERS)


@dataclass
class Fetcher:
    settings: Settings = field(default_factory=lambda: default_settings)
    browser_fallback: bool = True

    _http: HttpTransport | None = None
    _stealthy: StealthyTransport | None = None

    @property
    def http(self) -> HttpTransport:
        if self._http is None:
            self._http = HttpTransport(self.settings)
        return self._http

    @property
    def stealthy(self) -> StealthyTransport:
        if self._stealthy is None:
            self._stealthy = StealthyTransport(self.settings)
        return self._stealthy

    def get_html(self, url: str) -> str:
        """返回页面 HTML；失败抛 FetchError。"""
        direct_error: Exception | None = None
        try:
            html = self.http.get_text(url, headers=BROWSER_HEADERS)
            if is_challenge_page(html):
                raise TransportError("页面是 Cloudflare 挑战页（直连没过）")
            return html
        except (TransportError, OSError) as exc:
            direct_error = exc
            logger.info("直连失败，准备走浏览器通道：%s（%s）", url, exc)

        if not self.browser_fallback:
            raise FetchError(f"直连抓取失败：{direct_error}")

        try:
            html = self.stealthy.fetch_html(url)
        except Exception as exc:  # noqa: BLE001  scrapling 会抛各种底层异常
            raise FetchError(f"直连 + 浏览器通道都失败：{direct_error} / {exc}") from exc
        if is_challenge_page(html):
            raise FetchError("浏览器通道拿到的仍是 Cloudflare 挑战页")
        if not html.strip():
            raise FetchError("浏览器通道返回了空页面")
        return html

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None
        if self._stealthy is not None:
            self._stealthy.close()
            self._stealthy = None
