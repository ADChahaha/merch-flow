"""跨平台的浏览器定位与「不抢焦点」启动。

macOS / Windows / Linux 三个平台各有一套做法，全部集中在这里，
上层（transport / 配置）只调 `find_chrome` 和 `launch_detached`。

  抢焦点这件事按平台这么解：
    macOS   `open -g -n -a <app> --args …`  → 启动但不激活，窗口留在后面
    Windows STARTUPINFO(SW_SHOWMINNOACTIVE) → 最小化启动且不激活；
            个别版本 Chrome 会无视它，可用 EC_BROWSER_OFFSCREEN 把窗口挪到屏幕外
    Linux   没有通用办法，同样用 EC_BROWSER_OFFSCREEN
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

_WINDOWS_ENV = re.compile(r"%([^%]+)%")

logger = logging.getLogger(__name__)

# 按平台的常见安装路径 / 可执行名（Windows 的 %LOCALAPPDATA% 会展开）
CHROME_CANDIDATES: dict[str, tuple[str, ...]] = {
    "darwin": (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ),
    "win32": (
        r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
        r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
    ),
    "linux": (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "brave-browser",
    ),
}


def platform_key() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if os.name == "nt" or sys.platform.startswith("win"):
        return "win32"
    return "linux"


def _expand(path: str) -> str:
    """展开 %VAR%（Windows 写法）和 $VAR，两个平台都要能展开。

    不能只靠 os.path.expandvars：POSIX 下它不认 %VAR%，Windows 下不认 $VAR，
    而我们希望同一份候选表在三个平台都被正确展开（也才好在别的平台上写测试）。
    """
    expanded = os.path.expandvars(path)
    return _WINDOWS_ENV.sub(lambda m: os.environ.get(m.group(1), m.group(0)), expanded)


def find_chrome(explicit: str | None = None) -> str | None:
    """找到可用的 Chrome/Chromium/Edge。

    `explicit`（EC_CHROME_PATH）优先；填了但不存在返回 None，
    由上层报出「你指的路径不对」而不是悄悄换成别的浏览器。
    """
    if explicit:
        expanded = _expand(explicit)
        return expanded if _is_browser(expanded) else None
    for candidate in CHROME_CANDIDATES[platform_key()]:
        expanded = _expand(candidate)
        if _is_browser(expanded):
            return expanded
    return None


def _is_browser(path: str) -> bool:
    if not path:
        return False
    if Path(path).is_file():
        return True
    return shutil.which(path) is not None


def bundle_path(chrome_binary: str) -> str | None:
    """/Applications/Google Chrome.app/Contents/MacOS/Google Chrome → .app（macOS 专用）。"""
    for parent in Path(chrome_binary).parents:
        if parent.suffix == ".app":
            return str(parent)
    return None


def window_flags(*, background: bool, offscreen: bool) -> list[str]:
    """窗口位置 + 防节流参数。

    背景模式下默认把窗口挪到屏幕外：`open -g` 只保证「启动时不激活」，
    但后面 CDP 的点击（比如 R18 表单）或者新开标签页仍然可能把窗口顶到最前面
    —— 挪到屏幕外才是彻底不打扰（实测 `open -g` 之后仍会偶尔冒出来）。

    屏幕外/最小化的窗口会被 Chromium 判定成「被遮挡」而降级渲染，
    JS 定时器被节流后 Cloudflare 挑战可能永远过不去，所以必须同时带上
    这三个 disable-* 参数（Playwright 自己 launch 时默认就带，我们直接
    launch Chrome 就得自己加）。
    """
    anti_throttle = [
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
    ]
    if offscreen:
        # 屏幕外 + 固定尺寸，保证页面照常渲染（不要用 --headless，CF 过不了）
        return ["--window-position=-32000,-32000", "--window-size=1280,900", *anti_throttle]
    if background:
        # 没有挪出屏幕时也带上防节流：窗口可能被别的窗口盖住
        return anti_throttle
    return []


def launch_detached(
    chrome_binary: str, args: list[str], *, background: bool
) -> subprocess.Popen | None:
    """跨平台启动浏览器。返回 Popen；macOS 走 `open` 时拿不到进程句柄，返回 None。

    调用方拿不到句柄也没关系：`terminate_chrome_for_profile` 能按 profile 目录
    精确回收（不会误杀用户自己开的 Chrome）。
    """
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    key = platform_key()

    if key == "darwin" and background:
        bundle = bundle_path(chrome_binary)
        if bundle:
            subprocess.Popen(["open", "-g", "-n", "-a", bundle, "--args", *args], **kwargs)
            return None
        logger.debug("非 .app 形式的 Chrome，退回直接启动（可能抢焦点）")

    if key == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        # SW_SHOWMINNOACTIVE=7：最小化显示且不激活；SW_SHOWNORMAL=1
        startupinfo.wShowWindow = 7 if background else 1
        return subprocess.Popen(
            [chrome_binary, *args],
            startupinfo=startupinfo,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            **kwargs,
        )

    return subprocess.Popen([chrome_binary, *args], **kwargs)


def terminate_chrome_for_profile(profile_dir: str) -> None:
    """只关掉用这个临时 profile 起的那只 Chrome，不动用户自己的浏览器。"""
    if not profile_dir:
        return
    key = platform_key()
    try:
        if key == "win32":
            script = (
                "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\" | "
                f"Where-Object {{ $_.CommandLine -like '*{profile_dir}*' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            return

        pattern = f"user-data-dir={profile_dir}"
        subprocess.run(
            ["pkill", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20
        )
        # SIGTERM 之后 Chrome 要几秒才退干净；还赖着就直接 -9
        for _ in range(10):
            if not _profile_alive(pattern):
                return
            time.sleep(0.5)
        logger.debug("SIGTERM 没送走临时 Chrome，改用 SIGKILL（profile=%s）", profile_dir)
        subprocess.run(
            ["pkill", "-9", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20
        )
    except Exception:  # noqa: BLE001
        logger.debug("回收临时 Chrome 失败（profile=%s）", profile_dir, exc_info=True)


def _profile_alive(pattern: str) -> bool:
    result = subprocess.run(
        ["pgrep", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
    )
    return result.returncode == 0


def chrome_not_found_hint() -> str:
    return (
        "找不到 Chrome/Chromium/Edge。用 EC_CHROME_PATH 指定可执行文件，"
        "或设 EC_SURUGAYA_BROWSER_MODE=stealthy 改用 patchright 自带内核（需先 "
        "`python -m patchright install chromium`）"
    )
