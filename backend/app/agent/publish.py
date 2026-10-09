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
import shlex
import sys

from ..config import BASE_DIR
from pathlib import Path

# --------------------------------------------------------------------------- #
# 提示词
# --------------------------------------------------------------------------- #
PUBLISH_PROMPT = """你是淘宝店铺上架 agent。任务：把工作目录 `publish_payload.json` 里的商品，通过**卖家中心网页**上架。

工作目录里给了你工具：
- `python browser.py launch`：用专用 profile 启动带调试端口 9222 的 Chrome（会弹出窗口）。
- `browser.py`：CDP 挂接那个 Chrome 的工具（check / goto / shot / text / html / click / type / eval / wait）。
  浏览器依赖由内置工具提供，优先使用该工具，不要假设外部 Python 已装 playwright。
- `shots/`：截图统一放这里，每完成一小步截一张，供用户核对。

上架实战要点（来自真实跑通过的流程，务必照做）：
1. 先 `python browser.py check`。连不上就运行 `python browser.py launch` 把 Chrome 打开，
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
def _browser_script() -> str:
    """脚本只分发到内置浏览器工具；打包版不要求外部 Python 安装 playwright。"""
    if getattr(sys, "frozen", False):
        return ("import subprocess, sys\n"
                f"sys.exit(subprocess.call([{sys.executable!r}, '--browser', *sys.argv[1:]]))\n")
    return ("import sys\n"
            f"sys.path.insert(0, {str(BASE_DIR)!r})\n"
            "from app.agent.browser_cli import main\n"
            "sys.exit(main())\n")


def write_publish_workdir(out_dir: Path, payload: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "publish_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "browser.py").write_text(_browser_script(), encoding="utf-8")
    chrome = out_dir / "chrome_debug.sh"
    command = ([sys.executable, "--browser", "launch"] if getattr(sys, "frozen", False)
               else [sys.executable, str(out_dir / "browser.py"), "launch"])
    chrome.write_text("#!/bin/sh\nexec " + shlex.join(command) + "\n", encoding="utf-8")
    (out_dir / "chrome_debug.cmd").write_text(
        "@" + " ".join('"' + part + '"' for part in command) + "\r\n", encoding="utf-8"
    )
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
