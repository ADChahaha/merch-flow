"""抓取传输层：把「怎么拿到一个页面」和「页面怎么解析」彻底解耦。

三种 transport，对应三类实测结论：

* `HttpTransport`  —— curl_cffi 指纹伪装直连。Melonbooks / Sofmap 走这条，
  它们没有 CF，只有地区封锁（直连 403，挂 EC_PROXY 即可），连浏览器都不用开。
* `StealthyTransport` —— Scrapling StealthySession(camoufox) + solve_cloudflare=True，
  稳定过骏河屋的 managed Turnstile，固定脚本用这条。
* `ChromeCdpTransport` —— 有界面真实 Chrome + 临时 profile：
  **先只开页面让挑战自然通过，之后才挂 CDP 读取**。
  实测这是唯一能过的 CDP 方案；「先 CDP 附加再导航」和「headless + CDP 注入
  webdriver 伪装」都过不了（challenge 永远不消，CDP 本身会被 CF 检测到）。

编码问题（Sofmap 为主）单独在 `decode_body` 里处理：壳页声明 Shift_JIS 实为 UTF-8，
parts 页真是 Shift_JIS —— 一律按响应字节嗅探，不信 header/meta 声明。
"""

from __future__ import annotations

import atexit
import logging
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import quote

from ..config import Settings, settings as default_settings
from .session_thread import SessionThread, safe_close
from .browser import (
    chrome_not_found_hint,
    find_chrome,
    launch_detached,
    terminate_chrome_for_profile,
    window_flags,
)

logger = logging.getLogger(__name__)

_SHIFT_JIS = "cp932"


# --------------------------------------------------------------------------- #
# 编码
# --------------------------------------------------------------------------- #
def decode_body(body: bytes, declared: str | None = None, *, hint: str = "") -> str:
    """按响应字节嗅探编码，不信声明。

    顺序：BOM → 严格 UTF-8 → 声明 → cp932 → 兜底。
    壳页声明 Shift_JIS 实为 UTF-8，parts 页真是 Shift_JIS（hint="shift_jis" 时优先 cp932）。
    """
    if not body:
        return ""
    if body.startswith(b"\xef\xbb\xbf"):
        return body.decode("utf-8-sig", errors="replace")

    order: list[str] = []
    if hint in {"cp932", "shift_jis", "sjis"}:
        order.append(_SHIFT_JIS)
    order.append("utf-8")
    if declared:
        order.append(declared.lower())
    order.extend(["cp932" if hint != "shift_jis" else "utf-8", "euc-jp"])

    for enc in order:
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


def encode_keyword(keyword: str, encoding: str | None = None) -> str:
    """Sofmap 的关键词必须按页面真实编码送（Shift_JIS），否则搜不到东西。"""
    if not encoding:
        return quote(keyword, safe="")
    try:
        return quote(keyword.encode(encoding), safe="")
    except UnicodeEncodeError:
        return quote(keyword, safe="")


# --------------------------------------------------------------------------- #
# 表单流程（跨站点通用）
# --------------------------------------------------------------------------- #
@dataclass
class FormStep:
    """一步表单提交。

    Drupal 的年龄确认是**两步**：`/config` 填完提交 → `/config/confirm` 再点「はい」。
    第二步的表单没有 action（POST 到当前 URL），而且选择项由服务端表单状态带过去，
    所以必须「在同一个会话里、按顺序、在落地的页面上继续操作」——
    单独 POST 第二步是无效的。`url=None` 就表示「在当前页面继续」。
    """

    url: str | None = None
    radios: dict[str, str] = field(default_factory=dict)  # name -> value
    selects: dict[str, str] = field(default_factory=dict)  # name -> value
    submit_value: str = ""  # 提交按钮的 value，如 設定する / はい


# --------------------------------------------------------------------------- #
# HTTP（curl_cffi）
# --------------------------------------------------------------------------- #
@dataclass
class HttpTransport:
    """直连。地区封锁站点请把 EC_PROXY 打开，We're not a browser, no CF here."""

    settings: Settings = field(default_factory=lambda: default_settings)

    def __post_init__(self) -> None:
        self._session = None

    @property
    def session(self):
        if self._session is None:
            from curl_cffi import requests as curl_requests

            proxies = (
                {"http": self.settings.proxy, "https": self.settings.proxy}
                if self.settings.proxy
                else None
            )
            self._session = curl_requests.Session(
                impersonate="chrome",
                proxies=proxies,
                timeout=self.settings.request_timeout,
            )
        return self._session

    def get_text(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        hint: str = "",
        encoding: str | None = None,
    ) -> str:
        resp = self.session.get(url, headers=headers or {})
        raw = resp.content
        body = decode_body(raw, getattr(resp, "encoding", None), hint=hint)
        if resp.status_code >= 400:
            raise TransportError(f"HTTP {resp.status_code} for {url}")
        return body

    def post_text(
        self,
        url: str,
        *,
        data: dict | None = None,
        headers: dict[str, str] | None = None,
        hint: str = "",
    ) -> str:
        resp = self.session.post(url, data=data or {}, headers=headers or {})
        body = decode_body(resp.content, getattr(resp, "encoding", None), hint=hint)
        if resp.status_code >= 400:
            raise TransportError(f"HTTP {resp.status_code} for {url}")
        return body

    def submit_form_flow(self, steps: list[FormStep]) -> str:
        """按顺序在同一会话（cookie）里走完多步表单，返回最后一页 HTML。"""
        current_url = steps[0].url if steps else ""
        html = ""
        for index, step in enumerate(steps):
            if step.url:
                current_url = step.url
                html = self.get_text(current_url, headers={"Accept-Language": "ja"})
            if not current_url:
                raise TransportError("第一步必须给 url")
            data = _form_payload(html, step)
            resp = self.session.post(current_url, data=data, headers={"Accept-Language": "ja"})
            html = decode_body(resp.content, getattr(resp, "encoding", None), hint="")
            current_url = getattr(resp, "url", None) or current_url  # 跟着重定向走
            if resp.status_code >= 400:
                raise TransportError(f"表单第 {index + 1} 步失败 HTTP {resp.status_code}")
        return html

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


class TransportError(RuntimeError):
    pass


def _form_payload(html: str, step: FormStep) -> dict[str, str]:
    """把页面上的隐藏字段（form_build_id/form_id…）原样带上，再覆盖我们要选的项。

    隐藏字段一个都不能少也不能改：Drupal 的表单状态全挂在 form_build_id 上。
    """
    from scrapling.parser import Selector

    data: dict[str, str] = {}
    for field in Selector(html or "").css("form input[type=hidden]"):
        name = field.attrib.get("name")
        if name:
            data[name] = field.attrib.get("value") or ""
    data.update(step.radios)
    data.update(step.selects)
    if step.submit_value:
        data["op"] = step.submit_value
    return data


# --------------------------------------------------------------------------- #
# Stealthy（Scrapling / camoufox + solve_cloudflare）
# --------------------------------------------------------------------------- #
@dataclass
class StealthyTransport:
    """固定脚本过 CF 首选。headed + solve_cloudflare=True。"""

    settings: Settings = field(default_factory=lambda: default_settings)
    _session = None
    _owns_session = False
    _ex: SessionThread | None = None

    @property
    def executor(self) -> SessionThread:
        """Scrapling 也是同步 playwright，必须固定线程（见 session_thread.py）。"""
        if self._ex is None:
            self._ex = SessionThread("ec-stealthy")
        return self._ex

    def ensure_session(self):
        if self._session is not None:
            return self._session

        def build():
            from scrapling.fetchers import StealthySession

            flags = window_flags(
                background=self.settings.browser_background,
                offscreen=self.settings.browser_offscreen,
            )
            session = StealthySession(
                headless=self.settings.headless,  # CF 挑战在 headless 下过不了，默认 headed
                solve_cloudflare=True,
                timeout=self.settings.browser_timeout_ms,
                proxy=self.settings.proxy,
                retries=2,
                # 这条通道由 Scrapling 自己 launch（必抢焦点），只能用屏幕外兜底
                extra_flags=flags or None,
                # 临时 profile：挑战通过后的 cookie 留在盘上，本次进程复用
                user_data_dir=tempfile.mkdtemp(prefix="ec-stealthy-"),
            )
            # Scrapling 的 Session 需要显式 start()，否则 fetch 会报
            # "Context manager has been closed"（不是 camoufox 缺失）
            session.start()
            return session

        self._session = self.executor.call(build)
        self._owns_session = True
        return self._session

    def fetch_html(self, url: str, *, wait_selector: str | None = None, page_action=None) -> str:
        session = self.ensure_session()
        kwargs: dict = {}
        if wait_selector:
            kwargs["wait_selector"] = wait_selector
            kwargs["wait_selector_state"] = "attached"
        if page_action is not None:
            kwargs["page_action"] = page_action

        def do_fetch():
            return session.fetch(url, **kwargs)

        response = self.executor.call(do_fetch, timeout=self.settings.browser_timeout_ms / 1000 + 60)
        status = getattr(response, "status", 200)
        if status and status >= 400:
            raise TransportError(f"HTTP {status} for {url}")
        return str(response.html_content)

    def is_session_alive(self) -> bool:
        return self._session is not None

    def submit_form_flow(self, steps: list[FormStep]) -> str:
        """Scrapling 的 page_action 只在导航后跑一次，所以把多步表单都塞进这一个回调。"""
        session = self.ensure_session()
        if not steps or not steps[0].url:
            raise TransportError("第一步必须给 url")

        def page_action(page) -> None:
            _run_steps_in_browser(page, steps)

        def do_fetch():
            return session.fetch(steps[0].url, page_action=page_action, wait=None)

        response = self.executor.call(do_fetch, timeout=self.settings.browser_timeout_ms / 1000 + 120)
        return str(response.html_content)

    def close(self) -> None:
        clear_session_flags(self)
        session, self._session = self._session, None
        if session is not None and self._owns_session and self._ex is not None and self._ex.alive:
            safe_close(("stealthy session", lambda: self._ex.call(session.close, timeout=15)))
        if self._ex is not None:
            self._ex.shutdown()
            self._ex = None
        self._owns_session = False


# --------------------------------------------------------------------------- #
# Chrome over CDP（有界面 Chrome + 临时 profile，挑战自然过完再挂 CDP）
# --------------------------------------------------------------------------- #
# CF 挑战页的**决定性**特征。
# 注意别把 "challenge-platform" / "Turnstile" 放进来：正常受 CF 保护的页面里
# 也带这些脚本片段，加了就会误判成挑战没过、白等几十秒（实测踩过）。
CHALLENGE_MARKERS = (
    "cf-mitigated",
    "Just a moment",
    "Checking your browser before accessing",
    "cf_chl_opt",
    "__cf_chl",
    "challenge-form",
    "しばらくお待ちください",
)

# 正常页面的兜底判据：够大且没有决定性挑战特征
NORMAL_PAGE_MIN_BYTES = 15_000


@dataclass
class ChromeCdpTransport:
    """有界面 Chrome + 临时 profile：先让挑战自然过，之后再挂 CDP 读。

    顺序是全部要点（实测结论）：
      1. 用**临时 profile** 起有界面 Chrome，`--remote-debugging-port` 开着但**先不连 CDP**；
      2. 让 Chrome 自己打开目标页，等挑战自然通过（此时没有任何 CDP 流量）；
      3. 挑战过了再 `connect_over_cdp` 去读 DOM，之后同 profile 内正常翻页。

    启动不抢焦点：macOS 走 `open -g`，Windows 走 STARTUPINFO(SW_SHOWMINNOACTIVE)。

    并发上的两个坑（都踩过）：
      * macOS 下 `open` 拿不到进程句柄，用 `_proc is None` 当「已启动」的条件会重复起浏览器
        → 必须用独立的 `_launched` 标志；
      * `sync_playwright().start()` 在同一个线程里调第二次会直接报
        「Playwright Sync API inside the asyncio loop」
        → 启动、挂 CDP、翻页、关闭**全部**丢进同一个 SessionThread，并且幂等。
    """

    settings: Settings = field(default_factory=lambda: default_settings)
    profile_dir: str | None = None
    _proc: subprocess.Popen | None = None
    _browser = None
    _playwright = None
    _launched: bool = False
    _first_page_consumed: bool = False
    _ex: SessionThread | None = None

    @property
    def cdp_url(self) -> str:
        return f"http://127.0.0.1:{self.settings.cdp_port}"

    @property
    def executor(self) -> SessionThread:
        if self._ex is None:
            self._ex = SessionThread("ec-chrome-cdp")
        return self._ex

    # ------------------------------------------------------------------ #
    # 全部浏览器操作都在会话线程里跑
    # ------------------------------------------------------------------ #
    def fetch_html(self, url: str, *, wait_selector: str | None = None) -> str:
        timeout = self.settings.challenge_wait_seconds * 5 + self.settings.browser_timeout_ms / 1000 + 60

        def job() -> str:
            self._ensure_session(url)
            # 第一次：直接读 Chrome 自己开的那个标签页（挑战就是在这里过的）
            if not self._first_page_consumed:
                self._first_page_consumed = True
                html = self._read_first_page(wait_selector)
                if html and not _looks_like_challenge(html):
                    return html
            return self._navigate(url, wait_selector)

        return self.executor.call(job, timeout=timeout)

    def _ensure_session(self, first_url: str) -> None:
        """幂等：起 Chrome + 挂 CDP。只在会话线程里被调用。

        自愈：用户可能手动把后台那个 Chrome 关掉（实测踩过），
        这时 `_browser` 还在但连接已经断了 —— 必须重挂，必要时重开。
        """
        if self._browser is not None:
            if self._browser.is_connected() and self._browser.contexts:
                return
            logger.info("CDP 连接已断（浏览器被关了？），重新挂一次")
            self._detach()
        if not self._launched or not self._debug_port_alive():
            self._launch_chrome(first_url)
            self._launched = True
        self._attach()

    def is_session_alive(self) -> bool:
        """CDP 会话活着 = 连接在 + 还有 context（连接断了 contexts 会变空）。"""
        browser = self._browser
        return browser is not None and browser.is_connected() and bool(browser.contexts)

    def _detach(self) -> None:
        """丢掉旧的 Playwright 句柄（保留 profile，Chrome 还活着就直接重挂）。"""
        clear_session_flags(self)  # 连接断了 = 站点侧状态不可信，R18 等标志作废
        browser, playwright = self._browser, self._playwright
        self._browser, self._playwright = None, None
        for close in (
            lambda: browser.close() if browser is not None else None,
            lambda: playwright.stop() if playwright is not None else None,
        ):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    def _debug_port_alive(self) -> bool:
        import urllib.request

        try:
            with urllib.request.urlopen(f"{self.cdp_url}/json/version", timeout=1):
                return True
        except Exception:  # noqa: BLE001
            return False

    def _launch_chrome(self, first_url: str) -> None:
        clear_session_flags(self)  # 新 Chrome = 新 profile，会话标志全部作废
        chrome = find_chrome(self.settings.chrome_path)
        if not chrome:
            raise TransportError(chrome_not_found_hint())
        self.profile_dir = self.profile_dir or tempfile.mkdtemp(prefix="ec-chrome-")
        args = [
            f"--remote-debugging-port={self.settings.cdp_port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
            *window_flags(
                background=self.settings.browser_background,
                offscreen=self.settings.browser_offscreen,
            ),
            first_url,
        ]
        self._proc = launch_detached(chrome, args, background=self.settings.browser_background)
        logger.info(
            "Chrome 已启动（%s，等挑战自然通过）：%s",
            "后台不抢焦点" if self.settings.browser_background else "普通窗口",
            first_url,
        )
        self._wait_for_debug_port()
        time.sleep(self.settings.challenge_wait_seconds)

    def _attach(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)

    def _wait_for_debug_port(self, timeout: float = 20.0) -> None:
        """等 DevTools 端口起来（Chrome 冷启动要几秒）。"""
        import urllib.request

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{self.cdp_url}/json/version", timeout=1) as resp:
                    if resp.status == 200:
                        return
            except Exception:  # noqa: BLE001
                time.sleep(0.3)
        raise TransportError(f"Chrome 的 DevTools 端口没起来（{self.cdp_url}）")

    def _read_first_page(self, wait_selector: str | None) -> str:
        """读启动时那个已经过了挑战的标签页。

        优先用**正向信号**（结果容器出现了没）判断挑战过没过：
        光看挑战特征词会误判 —— 骏河屋正常页面里也带着 Turnstile 的脚本片段，
        于是白等 36 秒。等不到结果容器再退回特征词启发式。
        """
        contexts = self._browser.contexts
        if not contexts or not contexts[0].pages:
            raise TransportError("CDP 已连上但找不到标签页")
        page = contexts[0].pages[-1]

        if wait_selector:
            try:
                page.wait_for_selector(
                    wait_selector, timeout=self.settings.challenge_wait_seconds * 1000
                )
                return page.content()
            except Exception:  # noqa: BLE001
                logger.info("等 %s 超时，退回挑战特征词判断", wait_selector)

        html = page.content()
        for attempt in range(3):
            if not _looks_like_challenge(html):
                return html
            logger.info("挑战还没过完，继续等（第 %d 次）", attempt + 1)
            page.wait_for_timeout(self.settings.challenge_wait_seconds * 1000)
            html = page.content()
        return html

    # 偶发但会真实发生的导航错误，重试一般就好
    RETRYABLE_NAV_ERRORS = (
        "ERR_ABORTED",
        "ERR_CONNECTION",
        "ERR_NETWORK",
        "ERR_TIMED_OUT",
        "frame was detached",
        "Target page, context or browser has been closed",
        "Target closed",
    )

    def _reuse_page(self):
        """拿一个可复用的标签页。

        每次导航都 new_page() 的话，新标签页激活会把 Chrome 窗口顶到最前面
        （实测踩过）—— 所以优先复用已经开着的标签页，一个都不在才新开。
        已经被关掉的页不能复用（用户手动关标签页时 Playwright 的列表会滞后）。
        """
        context = self._browser.contexts[0]
        alive = [page for page in context.pages if not page.is_closed()]
        return alive[-1] if alive else context.new_page()

    def _navigate(self, url: str, wait_selector: str | None, attempts: int = 3) -> str:
        """翻页。要重试：`Page.goto: net::ERR_ABORTED; maybe frame was detached?`
        是 CDP 附加模式下偶发的竞态（实测翻第 2 页时碰到过），重试一次基本就好。
        """
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                # 浏览器可能中途被关掉：重试前重新确认会话（断了会重挂/重开）
                self._ensure_session(url)
                page = self._reuse_page()
                page.goto(url, timeout=self.settings.browser_timeout_ms, wait_until="domcontentloaded")
                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=self.settings.browser_timeout_ms)
                return page.content()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == attempts or not any(k in str(exc) for k in self.RETRYABLE_NAV_ERRORS):
                    raise
                logger.info("导航失败（第 %d 次），重试：%s", attempt, str(exc).splitlines()[0][:90])
                # 竞态里标签页可能已经废了（frame was detached），换一个再试
                try:
                    page.close()
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1.0)
        raise TransportError(f"导航失败：{last_error}")

    # ------------------------------------------------------------------ #
    def submit_form_flow(self, steps: list[FormStep]) -> str:
        executor = self.executor
        timeout = self.settings.browser_timeout_ms / 1000 * len(steps) + 90

        def job() -> str:
            if not steps or not steps[0].url:
                raise TransportError("第一步必须给 url")
            self._ensure_session(steps[0].url)
            # 表单流程已经把浏览器开走过了：启动时那个标签页不再是「当前页」，
            # 否则随后 fetch 会去读它，读到的还是设置前的旧内容（踩过）
            self._first_page_consumed = True
            page = self._reuse_page()
            _run_steps_in_browser(page, steps)
            return page.content()

        return executor.call(job, timeout=timeout)

    def close(self) -> None:
        """每一步独立兜底：任何一步失败都不能影响「杀掉临时 Chrome」。"""
        browser, self._browser = self._browser, None
        playwright, self._playwright = self._playwright, None
        ex, self._ex = self._ex, None

        steps = []
        if ex is not None and ex.alive:
            if browser is not None:
                steps.append(("断开 CDP", lambda: ex.call(browser.close, timeout=15)))
            if playwright is not None:
                steps.append(("停 playwright", lambda: ex.call(playwright.stop, timeout=15)))
        safe_close(*steps)
        if ex is not None:
            ex.shutdown()

        if self._proc is not None:
            proc, self._proc = self._proc, None
            safe_close(("终止 Chrome 进程", proc.terminate))
        elif self.profile_dir:
            profile, self.profile_dir = self.profile_dir, None
            # macOS 用 `open` 启动拿不到句柄：按临时 profile 精确回收（SIGTERM→SIGKILL）
            safe_close(("回收临时 Chrome", lambda: terminate_chrome_for_profile(profile)))
        self._launched = False
        self._first_page_consumed = False


def _run_steps_in_browser(page, steps: list[FormStep]) -> None:
    """在 playwright page 上按顺序填表并提交。

    两个细节：radio 常常被 CSS 藏起来（样式化的选择项），直接 check() 会失败，
    这时要点它对应的 <label>；Drupal 确认页没 action，点完就落在同一路径上。
    """
    for index, step in enumerate(steps):
        if step.url:
            page.goto(step.url, wait_until="domcontentloaded")
        for name, value in step.radios.items():
            _check_in_browser(page, name, value)
        for name, value in step.selects.items():
            page.select_option(f'select[name="{name}"]', value)
        submit_selector = (
            f'input[type=submit][value="{step.submit_value}"]'
            if step.submit_value
            else "input[type=submit], button[type=submit]"
        )
        # 有的分支没有确认页（比如骏河屋把限制调「強/中」是即时生效、直接跳首页），
        # 这时第 2 步没有按钮可点 —— 跳过，由调用方回读页面核对真实结果。
        if page.locator(submit_selector).count() == 0:
            logger.info("表单第 %d 步没有「%s」按钮，跳过（该分支无需确认）", index + 1, step.submit_value)
            continue
        try:
            with page.expect_navigation(timeout=30_000):
                page.click(submit_selector)
        except Exception:  # noqa: BLE001  有些表单是 AJAX，不跳转也算成功
            page.click(submit_selector)
        logger.debug("表单第 %d 步已提交", index + 1)


def _check_in_browser(page, name: str, value: str) -> None:
    selector = f'input[name="{name}"][value="{value}"]'
    element = page.locator(selector).first
    if element.count() == 0:
        raise TransportError(f"页面上找不到 {name}={value}")
    try:
        if element.is_visible():
            element.check(timeout=5000)
        else:
            element_id = element.get_attribute("id")
            if element_id:
                page.click(f'label[for="{element_id}"]')  # 藏起来的 radio 点 label
            else:
                element.check(force=True)
    except Exception:  # noqa: BLE001
        element_id = element.get_attribute("id")
        if element_id:
            page.click(f'label[for="{element_id}"]')
        else:
            element.check(force=True)
    if not element.is_checked():
        raise TransportError(f"{name}={value} 没勾上")


def _looks_like_challenge(html: str) -> bool:
    """判断当前页面还是不是 CF 挑战页。

    只用决定性特征，并且「页面够大且没有这些特征」就算正常 —— 宁可早一点收手，
    也不要在这里空转几十秒（挑战真没过的话，后面的解析会自己报出来）。
    """
    if not html:
        return True
    if any(marker in html for marker in CHALLENGE_MARKERS):
        return True
    return len(html) < NORMAL_PAGE_MIN_BYTES




# --------------------------------------------------------------------------- #
# 会话缓存：同一个站点在整个进程内只起一次浏览器
# --------------------------------------------------------------------------- #
_TRANSPORT_CACHE: dict[str, object] = {}
_LAST_USED: dict[str, float] = {}
_CACHE_LOCK = threading.Lock()
_REAPER: threading.Thread | None = None


def get_transport(site_key: str, kind: str, settings: Settings | None = None):
    """按站点复用 transport。

    没有这个缓存时每次搜索都会新建 scraper → 新建 StealthySession → 重新冷启动
    Chrome（窗口又弹一次）。缓存之后一个进程只起一次，搜索只是翻页。
    空闲超过 `browser_idle_timeout` 会被回收线程自动关掉（见 _ensure_reaper）。
    """
    cfg = settings or default_settings
    if not cfg.session_reuse:
        return _build_transport(kind, cfg)
    key = f"{site_key}:{kind}"
    with _CACHE_LOCK:
        cached = _TRANSPORT_CACHE.get(key)
        if cached is None:
            cached = _build_transport(kind, cfg)
            _TRANSPORT_CACHE[key] = cached
        _LAST_USED[key] = time.monotonic()
    _ensure_reaper(cfg)
    return cached


# 会话级标志：挂在 transport 上（scraper 每轮重建，挂实例上会每轮重跑 R18 表单）。
# 浏览器被关掉 / 重新起一个之后，这些状态必须作废 —— 新 profile 里 cookie 全没了。
SESSION_FLAG_NAMES = ("adult_ready",)


def clear_session_flags(transport) -> None:
    for name in SESSION_FLAG_NAMES:
        if hasattr(transport, name):
            try:
                delattr(transport, name)
            except Exception:  # noqa: BLE001
                pass


def get_session_flag(site_key: str, kind: str, name: str, default=None):
    """读会话级标志（如 R18 已放开）。

    会话被回收时标志一起消失；**会话还挂着但已经死了**（浏览器被关、连接断）时
    也要当成没有 —— 否则会跳过 R18 表单，搜出来的结果少一截（实测 2,216 → 1,262）。
    """
    with _CACHE_LOCK:
        transport = _TRANSPORT_CACHE.get(f"{site_key}:{kind}")
    if transport is None:
        return default
    alive = getattr(transport, "is_session_alive", None)
    if alive is not None and not alive():
        return default
    return getattr(transport, name, default)


def set_session_flag(site_key: str, kind: str, name: str, value) -> None:
    with _CACHE_LOCK:
        transport = _TRANSPORT_CACHE.get(f"{site_key}:{kind}")
        if transport is not None:
            setattr(transport, name, value)


def touch_transport(site_key: str, kind: str) -> None:
    """每取一次页面刷新一次活跃时间，免得抓到一半被回收。"""
    _LAST_USED[f"{site_key}:{kind}"] = time.monotonic()


def _ensure_reaper(cfg: Settings) -> None:
    """空闲回收线程：抓完 N 秒没人用就把浏览器关掉，不留孤儿窗口。"""
    global _REAPER
    if cfg.browser_idle_timeout <= 0 or _REAPER is not None:
        return
    with _CACHE_LOCK:
        if _REAPER is not None:
            return
        _REAPER = threading.Thread(
            target=_reap_idle_transports, args=(cfg.browser_idle_timeout,), name="ec-reaper", daemon=True
        )
        _REAPER.start()


def _reap_idle_transports(idle_timeout: float) -> None:
    interval = max(5.0, min(idle_timeout / 3, 30.0))
    while True:
        time.sleep(interval)
        _reap_once(idle_timeout)


def _reap_once(idle_timeout: float) -> list[str]:
    """把空闲超过阈值的会话关掉。返回被回收的 key（测试直接调它）。"""
    now = time.monotonic()
    with _CACHE_LOCK:
        idle_keys = [
            key for key in _TRANSPORT_CACHE if now - _LAST_USED.get(key, now) >= idle_timeout
        ]
    for key in idle_keys:
        logger.info("会话 %s 空闲超过 %.0fs，关掉浏览器", key, idle_timeout)
        _close_cached(key)
    return idle_keys


def _close_cached(key: str) -> None:
    with _CACHE_LOCK:
        transport = _TRANSPORT_CACHE.pop(key, None)
        _LAST_USED.pop(key, None)
    closer = getattr(transport, "close", None)
    if closer:
        try:
            closer()
        except Exception:  # noqa: BLE001
            logger.debug("回收会话 %s 失败", key, exc_info=True)


def _build_transport(kind: str, cfg: Settings):
    if kind == "stealthy":
        return StealthyTransport(settings=cfg)
    if kind == "chrome_cdp":
        return ChromeCdpTransport(settings=cfg)
    return HttpTransport(settings=cfg)


def close_all_transports() -> None:
    with _CACHE_LOCK:
        keys = list(_TRANSPORT_CACHE)
    if keys:
        logger.info("关闭 %d 个抓取会话", len(keys))
    for key in keys:
        _close_cached(key)


@atexit.register
def _close_on_exit() -> None:
    """进程退出兜底。

    FastAPI 走 lifespan shutdown 会主动关；但脚本 / 调试 CLI / 一次性抓取
    跑完直接退出时，Chrome 是被 `open -g` 拉起来的独立进程，不会跟着死 ——
    不注册这个就会留下一堆孤儿浏览器（实测残留过 30 个进程）。"""
    close_all_transports()
