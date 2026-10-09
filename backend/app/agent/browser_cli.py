#!/usr/bin/env python3
"""淘宝上架浏览器工具：CDP 挂接 9222 上的 Chrome。

用法：
  python browser.py check                 # 端口/页面列表
  python browser.py goto <url>            # 打开/复用页面
  python browser.py shot <name>          # 截图到 shots/<name>.png
  python browser.py text [max_chars]      # 当前页可见文本
  python browser.py html [selector]       # 当前页/元素 HTML 摘要
  python browser.py click <selector>
  python browser.py type <selector> <text> [--enter]   # 真实键盘输入
  python browser.py eval "<js>"
  python browser.py wait <ms>
"""
import argparse
import json
import os
import subprocess
from urllib.request import urlopen
import sys
import time
from pathlib import Path

CDP = "http://127.0.0.1:9222"
SHOTS = Path("shots")


def fail(msg: str, code: int = 2):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(code)


def connect():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        fail("playwright 没装：python -m pip install playwright")
    play = sync_playwright().start()
    try:
        browser = play.chromium.connect_over_cdp(CDP)
    except Exception as exc:  # noqa: BLE001
        play.stop()
        fail(f"连不上 Chrome（{CDP}）：{exc}。先运行 ./chrome_debug.sh")
    return play, browser


def pick_page(browser, url_hint: str = ""):
    contexts = browser.contexts
    context = contexts[0] if contexts else browser.new_context()
    pages = list(context.pages)
    if url_hint:
        for page in pages:
            if url_hint in page.url:
                return page
    if pages:
        return pages[-1]
    return context.new_page()


def out(payload: dict):
    print(json.dumps(payload, ensure_ascii=False))


def launch() -> int:
    # 这个浏览器供用户登录与后续确认，必须独立于单轮 agent 的进程组。
    from ..scrapers.browser import find_chrome
    from ..config import settings
    try:
        with urlopen(f"{CDP}/json/version", timeout=2) as response:
            if json.load(response).get("webSocketDebuggerUrl"):
                out({"ok": True, "message": "CDP 9222 已在运行"})
                return 0
    except (OSError, ValueError):
        pass
    executable = find_chrome(settings.chrome_path)
    if not executable:
        fail("找不到 Chrome / Edge，请安装浏览器或设置 EC_CHROME_PATH")
    profile = Path(os.getenv("EC_TAOBAO_PROFILE") or Path.home() / ".ec-taobao-profile")
    args = [executable, "--remote-debugging-port=9222", f"--user-data-dir={profile}",
            "--no-first-run", "https://myseller.taobao.com/"]
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)
    out({"ok": True, "message": "已启动浏览器，请扫码登录后继续", "profile": str(profile)})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--enter", action="store_true")
    options = parser.parse_args(argv)
    cmd, args = options.command, options.args

    if cmd == "launch":
        return launch()
    play, browser = connect()
    try:
        if cmd == "check":
            context = browser.contexts[0] if browser.contexts else None
            pages = [{"url": p.url, "title": p.title()} for p in (context.pages if context else [])]
            out({"ok": True, "cdp": CDP, "pages": pages})
            return 0

        page = pick_page(browser, args[0] if cmd == "goto" and args else "")
        page.bring_to_front()

        if cmd == "goto":
            page.goto(args[0], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)
            out({"ok": True, "url": page.url, "title": page.title()})
        elif cmd == "shot":
            SHOTS.mkdir(exist_ok=True)
            name = args[0] if args else f"shot-{int(time.time())}"
            path = SHOTS / f"{name}.png"
            page.screenshot(path=str(path), full_page=True)
            out({"ok": True, "path": str(path)})
        elif cmd == "text":
            limit = int(args[0]) if args else 4000
            body = page.evaluate("document.body ? document.body.innerText : ''")
            out({"ok": True, "text": body[:limit]})
        elif cmd == "html":
            selector = args[0] if args else "body"
            node = page.query_selector(selector)
            if node is None:
                fail(f"选择器没找到：{selector}")
            html = node.evaluate("el => el.outerHTML")
            out({"ok": True, "html": html[:4000]})
        elif cmd == "click":
            page.click(args[0], timeout=15000)
            page.wait_for_timeout(800)
            out({"ok": True, "clicked": args[0]})
        elif cmd == "type":
            # 真实键盘：click 聚焦 + keyboard.type（set value 在淘宝不生效）
            text = args[1]
            page.click(args[0], timeout=15000)
            page.keyboard.press("Meta+A" if sys.platform == "darwin" else "Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(text, delay=60)
            if options.enter:
                page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            out({"ok": True, "typed": text[:80]})
        elif cmd == "eval":
            out({"ok": True, "result": page.evaluate(args[0])})
        elif cmd == "wait":
            page.wait_for_timeout(int(args[0]))
            out({"ok": True})
        else:
            fail(f"不认识命令：{cmd}")
    finally:
        play.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
