"""跨平台浏览器定位 / 启动 用例。

这台机器只能真跑 macOS 分支，Windows 分支用 monkeypatch 把 subprocess 换掉，
把「发了什么命令、带了什么标志」钉住 —— 换平台时至少逻辑是先验证过的。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.scrapers import browser
from app.scrapers.browser import bundle_path, find_chrome, launch_detached, window_flags


class FakePopen:
    """记录调用参数的 Popen 替身。

    returncode=0 同时被 `pgrep`（0 = 进程还在）和 `pkill` 复用，
    所以默认语义是「一直杀不掉」—— 专门用来验证 -9 升级逻辑。
    """

    calls: list[tuple] = []
    returncode = 0

    def __init__(self, cmd, **kwargs):
        FakePopen.calls.append((cmd, kwargs))
        self.cmd = cmd
        self.kwargs = kwargs
        self.terminated = False

    def terminate(self):
        self.terminated = True


@pytest.fixture(autouse=True)
def clean_calls():
    FakePopen.calls = []
    yield
    FakePopen.calls = []


# --------------------------------------------------------------------------- #
# 定位
# --------------------------------------------------------------------------- #
def test_explicit_path_wins(monkeypatch, tmp_path):
    fake = tmp_path / "chrome"
    fake.write_text("#!/bin/sh\n")
    assert find_chrome(str(fake)) == str(fake)


def test_explicit_path_that_does_not_exist_is_not_silently_replaced():
    assert find_chrome("/no/such/chrome-binary") is None


@pytest.mark.parametrize(
    ("platform", "env", "expected"),
    [
        (
            "darwin",
            {},
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ),
        (
            "win32",
            {"PROGRAMFILES": r"C:\Program Files"},
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ),
    ],
)
def test_picks_first_available_candidate_per_platform(monkeypatch, platform, env, expected):
    monkeypatch.setattr(browser, "platform_key", lambda: platform)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(browser, "_is_browser", lambda path: path == expected)
    assert find_chrome() == expected


def test_linux_falls_back_to_path_lookup(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "linux")
    monkeypatch.setattr(browser, "_is_browser", lambda path: path == "chromium")
    assert find_chrome() == "chromium"


def test_windows_candidates_expand_env_vars(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"D:\Users\me\AppData\Local")
    seen: list[str] = []

    def spy(path):
        seen.append(path)
        return False

    monkeypatch.setattr(browser, "_is_browser", spy)
    find_chrome()
    assert any(p.startswith(r"D:\Users\me\AppData\Local") for p in seen), "Windows 的 %LOCALAPPDATA% 必须展开"


# --------------------------------------------------------------------------- #
# macOS .app 推导
# --------------------------------------------------------------------------- #
def test_bundle_path_extracts_app():
    assert (
        bundle_path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        == "/Applications/Google Chrome.app"
    )
    assert bundle_path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge") == (
        "/Applications/Microsoft Edge.app"
    )


def test_bundle_path_returns_none_for_plain_binary():
    assert bundle_path("/usr/bin/chromium") is None


# --------------------------------------------------------------------------- #
# 窗口标志
# --------------------------------------------------------------------------- #
def test_offscreen_uses_negative_position():
    flags = window_flags(background=True, offscreen=True)
    assert "--window-position=-32000,-32000" in flags
    assert any(f.startswith("--window-size=") for f in flags)


def test_anti_throttle_flags_are_always_there_when_background():
    """后台模式必须带防节流参数，否则被遮挡的窗口会被降级、CF 挑战过不去。"""
    flags = window_flags(background=True, offscreen=False)
    assert "--disable-backgrounding-occluded-windows" in flags
    assert "--disable-renderer-backgrounding" in flags
    assert "--disable-background-timer-throttling" in flags
    assert not any(f.startswith("--window-position") for f in flags)


def test_foreground_mode_adds_nothing():
    assert window_flags(background=False, offscreen=False) == []


# --------------------------------------------------------------------------- #
# 启动：三个平台
# --------------------------------------------------------------------------- #
def test_macos_background_launch_uses_open_dash_g(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "darwin")
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    proc = launch_detached(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ["--remote-debugging-port=9333", "https://example.com"],
        background=True,
    )

    assert proc is None  # 走 `open` 拿不到进程句柄
    cmd = FakePopen.calls[0][0]
    assert cmd[:2] == ["open", "-g"], "-g 是关键：启动但不激活，窗口不抢焦点"
    assert "-n" in cmd and "-a" in cmd
    assert "/Applications/Google Chrome.app" in cmd
    assert "--args" in cmd
    assert "https://example.com" in cmd


def test_macos_foreground_launch_runs_binary_directly(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "darwin")
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    proc = launch_detached("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["-x"], background=False)

    assert proc is not None
    assert FakePopen.calls[0][0][0].endswith("Google Chrome")


def test_windows_background_launch_minimizes_without_activating(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "win32")

    class FakeStartupInfo:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None

    monkeypatch.setattr(subprocess, "STARTUPINFO", FakeStartupInfo, raising=False)
    monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    launch_detached(r"C:\Program Files\Google\Chrome\Application\chrome.exe", ["-x"], background=True)

    _, kwargs = FakePopen.calls[0]
    assert kwargs["startupinfo"].wShowWindow == 7, "SW_SHOWMINNOACTIVE：最小化且不激活"
    assert kwargs["startupinfo"].dwFlags & 1
    assert kwargs["creationflags"] == 0x200
    assert kwargs["stdout"] is subprocess.DEVNULL


def test_windows_foreground_launch_is_normal_window(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "win32")

    class FakeStartupInfo:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None

    monkeypatch.setattr(subprocess, "STARTUPINFO", FakeStartupInfo, raising=False)
    monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    launch_detached("chrome.exe", ["-x"], background=False)
    assert FakePopen.calls[0][1]["startupinfo"].wShowWindow == 1


def test_linux_launch_is_plain_popen(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "linux")
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    launch_detached("/usr/bin/chromium", ["--remote-debugging-port=9333"], background=True)

    cmd, kwargs = FakePopen.calls[0]
    assert cmd == ["/usr/bin/chromium", "--remote-debugging-port=9333"]
    assert "startupinfo" not in kwargs


# --------------------------------------------------------------------------- #
# 回收：只杀临时 profile 的那只，不动用户自己的 Chrome
# --------------------------------------------------------------------------- #
def test_terminate_on_macos_kills_only_temp_profile(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "darwin")
    monkeypatch.setattr(subprocess, "run", FakePopen)

    from app.scrapers.browser import terminate_chrome_for_profile

    terminate_chrome_for_profile("/tmp/ec-chrome-abc123")
    cmd = FakePopen.calls[0][0]
    assert cmd == ["pkill", "-f", "user-data-dir=/tmp/ec-chrome-abc123"]


def test_terminate_on_windows_filters_by_command_line(monkeypatch):
    monkeypatch.setattr(browser, "platform_key", lambda: "win32")
    monkeypatch.setattr(subprocess, "run", FakePopen)

    from app.scrapers.browser import terminate_chrome_for_profile

    terminate_chrome_for_profile(r"C:\Temp\ec-chrome-abc")
    cmd = FakePopen.calls[0][0]
    assert cmd[0] == "powershell"
    assert any("CommandLine" in part for part in cmd)
    assert any(r"C:\Temp\ec-chrome-abc" in part for part in cmd)
    assert any("Stop-Process" in part for part in cmd)


def test_terminate_escalates_to_sigkill_when_stubborn(monkeypatch):
    """SIGTERM 送不走就 -9：临时 Chrome 不能留下来占着端口和内存。"""
    monkeypatch.setattr(browser, "platform_key", lambda: "darwin")
    monkeypatch.setattr(browser.time, "sleep", lambda _s: None)
    monkeypatch.setattr(subprocess, "run", FakePopen)

    from app.scrapers.browser import terminate_chrome_for_profile

    terminate_chrome_for_profile("/tmp/ec-chrome-stubborn")

    signals = [c[0][1] for c in FakePopen.calls if c[0][0] == "pkill"]
    assert signals == ["-f", "-9"]


# --------------------------------------------------------------------------- #
# 关闭清理：不能因为 playright 跨线程炸掉就跳过杀 Chrome
# --------------------------------------------------------------------------- #
def test_transport_close_escalates_and_never_skips_kill(monkeypatch, tmp_path):
    from app.scrapers import browser as browser_module
    from app.scrapers.transport import ChromeCdpTransport

    killed: list[str] = []
    monkeypatch.setattr(
        browser_module, "terminate_chrome_for_profile", lambda profile: killed.append(profile)
    )
    monkeypatch.setattr("app.scrapers.transport.terminate_chrome_for_profile", killed.append)

    transport = ChromeCdpTransport()
    transport.profile_dir = str(tmp_path / "ec-chrome-x")

    class ExplodingBrowser:
        def close(self):  # 模拟 greenlet.error: Cannot switch to a different thread
            raise RuntimeError("Cannot switch to a different thread")

    class FakeExecutor:
        alive = True

        def call(self, func, timeout=None):
            return func()

        def shutdown(self, timeout=10.0):
            pass

    transport._browser = ExplodingBrowser()
    transport._ex = FakeExecutor()

    transport.close()

    assert killed == [str(tmp_path / "ec-chrome-x")], "断开 CDP 失败也必须继续回收临时 Chrome"
    assert transport.profile_dir is None
    assert transport._browser is None


# --------------------------------------------------------------------------- #
# 并发安全：macOS 下 `open` 拿不到句柄，不能靠 _proc 判断「已启动」
# --------------------------------------------------------------------------- #
def test_launch_is_idempotent_even_without_process_handle(monkeypatch, tmp_path):
    from app.scrapers.transport import ChromeCdpTransport

    launches: list[list[str]] = []

    def fake_launch(chrome, args, *, background):
        launches.append(args)
        return None  # 模拟 macOS 的 `open -g`：没有进程句柄

    monkeypatch.setattr("app.scrapers.transport.find_chrome", lambda explicit=None: "/chrome")
    monkeypatch.setattr("app.scrapers.transport.launch_detached", fake_launch)
    monkeypatch.setattr("app.scrapers.transport.time.sleep", lambda _s: None)
    monkeypatch.setattr(ChromeCdpTransport, "_wait_for_debug_port", lambda self, timeout=20: None)
    monkeypatch.setattr(ChromeCdpTransport, "_attach", lambda self: None)  # 不真连 CDP
    monkeypatch.setattr(ChromeCdpTransport, "_debug_port_alive", lambda self: True)

    transport = ChromeCdpTransport()
    transport._ensure_session("https://a.test/1")  # 会真的去 attach，先让 attach 失败也无妨
    assert len(launches) == 1

    # 再调一次也不该重复起浏览器（_proc 是 None，必须靠 _launched 标志）
    transport._ensure_session("https://a.test/2")
    assert len(launches) == 1

    class FakeBrowser:
        contexts: list = []

        def is_connected(self) -> bool:
            return True

    transport._browser = FakeBrowser()
    transport._ensure_session("https://a.test/3")
    assert len(launches) == 1


# 用户手动把后台 Chrome 关掉后（实测踩过）：连接断了要能自愈，不能一直报
# 「Target page, context or browser has been closed」
# 浏览器被关掉重开后，R18 这类会话标志必须作废（新 profile 里 cookie 全没了），
# 否则新会话会以为已经放行过 —— 实测少了成人向商品（2,216 → 1,262）
def test_relaunch_forgets_session_flags(monkeypatch):
    from app.scrapers.transport import ChromeCdpTransport, set_session_flag

    monkeypatch.setattr("app.scrapers.transport.find_chrome", lambda explicit=None: "/chrome")
    monkeypatch.setattr("app.scrapers.transport.launch_detached", lambda *a, **k: None)
    monkeypatch.setattr("app.scrapers.transport.time.sleep", lambda _s: None)
    monkeypatch.setattr(ChromeCdpTransport, "_wait_for_debug_port", lambda self, timeout=20: None)
    monkeypatch.setattr(ChromeCdpTransport, "_attach", lambda self: None)

    transport = ChromeCdpTransport()
    set_session_flag("surugaya", "chrome_cdp", "adult_ready", True) if False else None
    transport.adult_ready = True  # set_session_flag 就是 setattr 到 transport 上
    transport._detach()
    assert not hasattr(transport, "adult_ready"), "断开连接时必须把会话标志清掉"

    transport.adult_ready = True
    transport._launch_chrome("https://a.test/1")
    assert not hasattr(transport, "adult_ready"), "重新起 Chrome 时必须把会话标志清掉"


# 会话还挂着但已经死了的时候，会话标志（R18 已放行）不能算数
def test_session_flag_ignored_when_browser_is_dead():
    import time as _time

    from app.scrapers import transport as T

    class FakeBrowser:
        def __init__(self, connected: bool) -> None:
            self.contexts = [object()] if connected else []
            self._connected = connected

        def is_connected(self) -> bool:
            return self._connected

    tr = T.ChromeCdpTransport()
    tr.adult_ready = True
    key = "surugaya:chrome_cdp"
    with T._CACHE_LOCK:
        T._TRANSPORT_CACHE[key] = tr
        T._LAST_USED[key] = _time.monotonic()
    try:
        tr._browser = FakeBrowser(connected=False)
        assert T.get_session_flag("surugaya", "chrome_cdp", "adult_ready", False) is False, "会话死了，标志不能算数"

        tr._browser = FakeBrowser(connected=True)
        assert T.get_session_flag("surugaya", "chrome_cdp", "adult_ready", False) is True, "会话活着，标志照常"

        tr._browser = None
        assert T.get_session_flag("surugaya", "chrome_cdp", "adult_ready", False) is False
    finally:
        with T._CACHE_LOCK:
            T._TRANSPORT_CACHE.pop(key, None)
            T._LAST_USED.pop(key, None)


def test_reconnects_when_browser_was_closed(monkeypatch):
    from app.scrapers.transport import ChromeCdpTransport

    launches: list = []
    attaches: list = []

    monkeypatch.setattr("app.scrapers.transport.find_chrome", lambda explicit=None: "/chrome")
    monkeypatch.setattr("app.scrapers.transport.launch_detached", lambda *a, **k: launches.append(a) or None)
    monkeypatch.setattr("app.scrapers.transport.time.sleep", lambda _s: None)
    monkeypatch.setattr(ChromeCdpTransport, "_wait_for_debug_port", lambda self, timeout=20: None)
    monkeypatch.setattr(ChromeCdpTransport, "_attach", lambda self: attaches.append(1))

    class FakeBrowser:
        def __init__(self, connected: bool) -> None:
            self.contexts: list = []
            self._connected = connected

        def is_connected(self) -> bool:
            return self._connected

        def close(self) -> None:
            self._connected = False

    transport = ChromeCdpTransport()
    # 端口还活着（Chrome 进程在，只是 CDP 连接断了）→ 重挂即可，不用重开
    monkeypatch.setattr(ChromeCdpTransport, "_debug_port_alive", lambda self: True)
    transport._browser = FakeBrowser(connected=False)
    transport._launched = True
    transport._ensure_session("https://a.test/1")
    assert len(launches) == 0, "端口还活着就不该再起一个 Chrome"
    assert attaches == [1], "断线后必须重新 attach"

    # 端口也没了（浏览器被整个关掉）→ 重新起一个
    monkeypatch.setattr(ChromeCdpTransport, "_debug_port_alive", lambda self: False)
    transport._browser = FakeBrowser(connected=False)
    transport._ensure_session("https://a.test/2")
    assert len(launches) == 1
