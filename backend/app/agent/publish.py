"""淘宝上架（浏览器自动化）任务：任务目录、提示词、浏览器工具、结果收集。

思路来自 victorytianyi-dev/taobao-shop-automation 的实战经验：
  * CDP 挂接用户自己开着调试端口的 Chrome（9222），**绝不由我们重启浏览器**；
  * 登录靠用户在那个 Chrome 里扫码一次，长期保持；
  * 直连类目 URL、真实键盘输入、品牌「无品牌」/型号「通用」、iframe 主图、
    运费模板、提交后按「错误(N)」逐项补；
  * 低频操作（间隔 30-90s 随机、单日 ≤2 个）、遇到滑块/短信/人脸立即停下叫人。

我们只负责把 ①商品数据 ②浏览器小工具 ③操作守则 放进工作目录，
具体怎么点、怎么填，由 dsh agent 自己判断。
"""

from __future__ import annotations

import json
from pathlib import Path

# --------------------------------------------------------------------------- #
# 提示词
# --------------------------------------------------------------------------- #
PUBLISH_PROMPT = """你是淘宝店铺上架 agent。任务：把工作目录 `publish_payload.json` 里的商品，通过**卖家中心网页**上架。

工作目录里给了你工具：
- `./chrome_debug.sh`：用专用 profile 启动带调试端口 9222 的 Chrome（会弹出窗口）。
- `browser.py`：CDP 挂接那个 Chrome 的工具（check / goto / shot / text / html / click / type / eval / wait）。
  也可以直接写自己的 python（playwright 已装，用 `p.chromium.connect_over_cdp("http://127.0.0.1:9222")` 挂接）。
- `shots/`：截图统一放这里，每完成一小步截一张，供用户核对。

上架实战要点（来自真实跑通过的流程，务必照做）：
1. 先 `python browser.py check`。连不上就运行 `./chrome_debug.sh` 把 Chrome 打开，
   然后**停下来提示用户扫码登录卖家中心**（这是必须真人的一步），登录完再继续。
2. 直连类目 URL，别去点类目树：`https://item.upload.taobao.com/sell/v2/publish.htm?catId={类目ID}&fromAICategory=true`。
   payload 里没给 catId 时，先用浏览器搜一个同类商品/类目页拿到 catId，再直连。
3. 标题 / 价格 / 库存必须**真实键盘输入**（click 后 `keyboard.type`，直接 set value 不生效）。
4. 品牌/型号用「原生 setter + input/change 事件」；品牌填「无品牌」、型号填「通用」。
5. 主图用 800x800 正方形（免裁剪）；图片空间是 iframe，点击坐标要加 iframe 偏移。
   图片先下载到本地再上传。payload 里给了图片 URL。
6. 运费模板：刷新下拉后选「系统模板-商家默认模板」。
7. 提交前把整页截图存 `shots/`，**先停下来给用户确认这一步**（标题/价格/图片/类目）；用户说继续才提交。
8. 提交后如果有「错误(N)」，逐条补字段直到错误清零；仍卡住就停下报告，不要硬点。
9. 遇到滑块 / 短信 / 人脸验证 → **立即停止**，在回复里明确说「需要真人处理」并说明在哪一步。
10. 低频模拟真人：操作间隔 30-90 秒随机；本次会话最多上架 2 个商品。

结束时把结果写到 `./publish_result.json`（合法 JSON）：
{
  "ok": true/false,
  "message": "一句话结果（上了几个、卡在哪）",
  "need_human": "需要真人做的事；没有就空字符串",
  "items": [{"name": "商品名", "status": "published|pending_review|failed|skipped", "detail": "备注"}]
}
写完回复一句话总结。"""


def build_publish_prompt() -> str:
    return PUBLISH_PROMPT


# --------------------------------------------------------------------------- #
# 工作目录
# --------------------------------------------------------------------------- #
def _chrome_script() -> str:
    """独立 profile + 9222 启动 Chrome（macOS/Linux 通用）。"""
    return """#!/bin/sh
# 启动带调试端口的 Chrome（专用 profile，登录态长期保存）。已在跑就不用重复执行。
PROFILE="${EC_TAOBAO_PROFILE:-$HOME/.ec-taobao-profile}"
URL="https://myseller.taobao.com/"
if curl -s --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo "CDP 9222 已在运行"
  exit 0
fi
for CHROME in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
              "/Applications/Chromium.app/Contents/MacOS/Chromium" \\
              "$(command -v google-chrome)" "$(command -v chromium)" "$(command -v chrome)"; do
  if [ -n "$CHROME" ] && [ -x "$CHROME" ]; then
    "$CHROME" --remote-debugging-port=9222 --user-data-dir="$PROFILE" --no-first-run "$URL" >/dev/null 2>&1 &
    echo "已启动 Chrome（profile: $PROFILE）"
    exit 0
  fi
done
echo "找不到 Chrome，请手动执行：<chrome> --remote-debugging-port=9222 --user-data-dir=$PROFILE"
exit 1
"""


def _browser_script() -> str:
    """CDP 挂接工具：所有子命令都作用于同一个 Chrome，状态自然保持。"""
    return '''#!/usr/bin/env python3
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
import sys
import time
from pathlib import Path

CDP = "http://127.0.0.1:9222"
SHOTS = Path(__file__).parent / "shots"


def fail(msg: str, code: int = 2):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(code)


def connect():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        fail("playwright 没装：python -m playwright install chromium")
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--enter", action="store_true")
    options = parser.parse_args()
    cmd, args = options.command, options.args

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
            page.keyboard.press("Control+A")
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
'''


def write_publish_workdir(out_dir: Path, payload: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "publish_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "browser.py").write_text(_browser_script(), encoding="utf-8")
    chrome = out_dir / "chrome_debug.sh"
    chrome.write_text(_chrome_script(), encoding="utf-8")
    chrome.chmod(0o755)
    (out_dir / "TASK.md").write_text(f"# 淘宝上架任务\n\n{PUBLISH_PROMPT}\n", encoding="utf-8")


def read_publish_result(out_dir: Path) -> dict:
    path = out_dir / "publish_result.json"
    if not path.exists():
        raise FileNotFoundError("agent 没有写 publish_result.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"publish_result.json 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("publish_result.json 顶层应该是对象")
    return data
