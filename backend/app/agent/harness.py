"""deepseek harness 桥：把 URL 交给 dsh agent，它自己决定怎么抓；之后还能接着聊。

这里**没有递归逻辑**：我们只做四件事——
  1. 准备任务目录：一个 fetch 小工具（直连 + CF 兜底）、TASK.md、dsh patch（模型/推理）；
  2. 起 `dsh --profile acp`（ACP over stdio），流式收它的思考/工具/回复，转成日志事件；
  3. agent 写出的 products.json 收回来，清洗成入库形状；
  4. 续聊：同一个 session 再 prompt（用户自由输入），它带着上下文和 products.json 继续改。

翻几页、跟哪些链接、怎么解析，全是模型自己的判断。

CLI：
  python -m app.agent.harness --url URL --out DIR [--prompt 文本] [--resume SESSION]
输出协议（stdout，NDJSON 一行一个，jobs.py 按行读）：
  {"type": "log", "level": "info|error|think|tool|agent|user", "text": "..."}
  {"type": "result", "url": ..., "title": ..., "products": [...],
   "session_id": ..., "reply": ..., "error": ""}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

from ..config import BASE_DIR, settings
from .acp import AcpClient, AcpError, summarize_update
from .publish import build_publish_prompt, read_publish_result, write_publish_workdir
from .tokens import format_usage, read_session_usage

# --------------------------------------------------------------------------- #
# 给 agent 的提示词（它拿到的全部世界观）
# --------------------------------------------------------------------------- #
PROMPT_TEMPLATE = """你是电商商品抓取 agent。任务：从 {url} 出发，找齐这个页面/站点下的所有商品。

工作目录里准备好了命令，随你使用：
- `./fetch <url>`：抓取页面并输出 JSON（标题 / 正文 / 图片 / 链接）。已处理直连和 Cloudflare 兜底，超时自己加。
- `./fetch_raw <url> [out.html]`：抓原始 HTML 存成文件（正文被截断、需要看原始结构时用）。
{tools}

怎么翻页、递归几层、跟哪些链接、怎么从 HTML 里抽字段——全部自己判断，不需要问我。

省步数（每一步都要把整个上下文重发一遍，很贵，务必照做）：
- 先写一个脚本一次性完成「抓取 → 解析 → 写出 products.json → 自检」，跑通即可；
- 不要用多次小命令逐步探查同一个文件（例如一条命令只 print 一个 key，分四遍看 images / text / links）；
- products.json 写完不要 read 回来看，自检在脚本里做（json.load 后检查字段和数量）。

产出要求：
1. 商品 = 单品级条目（周边、谷子、书籍、CD/Blu-ray、门票、手办……）：名称 / 价格 / 图片 / 发售日或举办日期 / 详情 / 来源 URL。
2. 不要漏、不要编：图片必须是页面里真实出现的绝对 URL（http/https），拿不准就少填。
3. 抓完后把结果写到 `./products.json`（合法 JSON，UTF-8）：
{{
  "title": "站点或活动名",
  "products": [
    {{
      "name": "商品名（原文，别翻译）",
      "price_text": "价格原文，如 550円(税込)；没有就空字符串",
      "price": 550,
      "date_text": "发售日/举办日期原文；没有就空字符串",
      "detail": "规格、尺寸、备注、特典等整理成一小段；没有就空字符串",
      "image_urls": ["https://…"],
      "source_url": "该商品详情页 URL；就是当前页就填当前页"
    }}
  ]
}}
4. 写完自查一遍 products.json 是合法 JSON，然后回复一句话总结（找到多少件商品）。"""


# 开发（源码运行）：工具是 python 脚本，仓库代码可复用、可 import
DEV_TOOLS = """- `TASK.md` 里有任务说明；`fetch_page.py` / `fetch_raw_page.py` 是上面命令的源码，可以改。

仓库里已有的代码优先复用，别重写（脚本开头 `sys.path.insert(0, {backend!r})` 后 import）：
- 抓取：`app.agent.fetch.Fetcher`（直连 + Cloudflare 兜底；`get_html(url)` 就是原始 HTML，别自己写请求）
- 解析：`app.agent.page`：`parse_html` / `extract_text` / `extract_images` / `extract_links` / `page_title`
- python 环境可用（httpx / lxml / curl_cffi 都装了）"""

# 打包版：抓取走内置工具（后端同款代码），不依赖仓库路径
FROZEN_TOOLS = """- 这两个命令由应用内置，直接可用。"""


def build_prompt(url: str, *, frozen: bool | None = None) -> str:
    if frozen is None:
        frozen = is_frozen()
    tools = FROZEN_TOOLS if frozen else DEV_TOOLS.format(backend=str(BASE_DIR))
    return PROMPT_TEMPLATE.format(url=url, tools=tools)


# --------------------------------------------------------------------------- #
# 任务目录
# --------------------------------------------------------------------------- #
def is_frozen() -> bool:
    """是不是 PyInstaller 打包版（没有仓库路径，也没有可跑的 python 脚本）。"""
    return bool(getattr(sys, "frozen", False))


def _fetch_script() -> str:
    """开发模式：生成抓取小工具（薄壳，实现在 app.agent.fetch_cli，源码可看可改）。"""
    return f'''#!/usr/bin/env python3
"""抓一个页面 → JSON（标题 / 正文 / 图片 / 链接）。用法：python fetch_page.py <url> [text_limit]"""
import sys
from pathlib import Path

BACKEND = Path({str(BASE_DIR)!r})
sys.path.insert(0, str(BACKEND))

from app.agent.fetch_cli import json_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(json_main(sys.argv[1:]))
'''


def _fetch_raw_script() -> str:
    """开发模式：抓原始 HTML 的小工具（薄壳，实现在 app.agent.fetch_cli）。"""
    return f'''#!/usr/bin/env python3
"""抓原始 HTML 存文件。用法：python fetch_raw_page.py <url> [out.html]"""
import sys
from pathlib import Path

BACKEND = Path({str(BASE_DIR)!r})
sys.path.insert(0, str(BACKEND))

from app.agent.fetch_cli import raw_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(raw_main(sys.argv[1:]))
'''


def _fetch_wrapper(workdir: Path, script: str = "fetch_page.py") -> str:
    return "#!/bin/sh\n" f'exec "{{sys.executable}}" "{{workdir / script}}" "$@"\n'


def _frozen_wrappers(out_dir: Path) -> None:
    """打包版：./fetch、./fetch_raw 直接转发给内置工具（同一个可执行文件 --fetch）。

    dsh 在 unix 走 bash、Windows 走 pwsh/cmd，所以 sh 和 cmd 两种壳都写。
    """
    exe = Path(sys.executable)
    for command, mode in (("fetch", "json"), ("fetch_raw", "raw")):
        sh = out_dir / command
        sh.write_text(f'#!/bin/sh\nexec "{exe}" --fetch {mode} "$@"\n', encoding="utf-8")
        sh.chmod(0o755)
        (out_dir / f"{command}.cmd").write_text(
            f'@"{exe}" --fetch {mode} %*\r\n', encoding="utf-8"
        )


def _dsh_patch(model: str, thinking: str) -> str:
    """per-run 覆盖：默认模型 + 思考/推理强度（off = 真关掉）。

    不写 llm-deepseek 这一段时，dsh 会用 provider 的默认推理强度（high）——
    所以 off 也必须显式写出来，不然「关闭推理」等于没关，每步都在烧思考 token。
    """
    effort = (thinking or "off").strip().lower()
    if effort not in {"off", "low", "high", "max"}:
        effort = "off"
    lines = [
        "- id: agent-default-model",
        "  config:",
        "    provider: deepseek-official",
        f"    model: {model}",
        "- id: llm-deepseek",
        "  config:",
        f"    thinking: {'disabled' if effort == 'off' else 'enabled'}",
        f"    reasoningEffort: {effort}",
    ]
    return "\n".join(lines) + "\n"


def write_workdir(out_dir: Path, url: str, *, model: str, thinking: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if is_frozen():
        _frozen_wrappers(out_dir)
    else:
        for script in ("fetch_page.py", "fetch_raw_page.py"):
            source = _fetch_script() if script == "fetch_page.py" else _fetch_raw_script()
            (out_dir / script).write_text(source, encoding="utf-8")
        for command in ("fetch", "fetch_raw"):
            wrapper = out_dir / command
            wrapper.write_text(_fetch_wrapper(out_dir, f"{command}_page.py"), encoding="utf-8")
            wrapper.chmod(0o755)
    (out_dir / "TASK.md").write_text(
        f"# 商品抓取任务\n\n入口 URL：{url}\n\n{build_prompt(url)}\n",
        encoding="utf-8",
    )
    (out_dir / "dsh.patch.yml").write_text(_dsh_patch(model, thinking), encoding="utf-8")


# --------------------------------------------------------------------------- #
# products.json 清洗（agent 写的东西要宽容地收）
# --------------------------------------------------------------------------- #
def _clean_text(value: object, limit: int = 2000) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _parse_int(price: object, price_text: str) -> int | None:
    if isinstance(price, bool):
        return None
    if isinstance(price, (int, float)):
        return int(price)
    digits = re.sub(r"[^\d]", "", str(price or ""))
    if digits:
        return int(digits)
    digits = re.sub(r"[^\d]", "", price_text or "")
    return int(digits) if digits else None


def normalize_product(raw: object, page_url: str = "") -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = _clean_text(raw.get("name"), limit=500)
    if not name:
        return None

    price_text = _clean_text(raw.get("price_text"), limit=200)
    images: list[str] = []
    for value in raw.get("image_urls") or []:
        url = _clean_text(value, limit=2000)
        if not url:
            continue
        url = urljoin(page_url, url) if page_url else url
        if url.startswith(("http://", "https://")) and url not in images:
            images.append(url)

    source_url = _clean_text(raw.get("source_url"), limit=2000)
    if not source_url and page_url:
        source_url = page_url

    return {
        "name": name,
        "price": _parse_int(raw.get("price"), price_text),
        "price_text": price_text,
        "date_text": _clean_text(raw.get("date_text"), limit=300),
        "detail": _clean_text(raw.get("detail"), limit=2000),
        "image_urls": images,
        "source_url": source_url,
    }


def read_products(out_dir: Path, entry_url: str) -> tuple[str, list[dict]]:
    """读 agent 写的 products.json；缺文件/坏 JSON 都抛出来让上层记日志。"""
    path = out_dir / "products.json"
    if not path.exists():
        raise FileNotFoundError("agent 没有写 products.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"products.json 不是合法 JSON：{exc}") from exc

    if isinstance(data, list):
        data = {"title": "", "products": data}
    if not isinstance(data, dict):
        raise ValueError("products.json 顶层应该是对象")

    products: list[dict] = []
    for raw in data.get("products") or []:
        product = normalize_product(raw, entry_url)
        if product is not None:
            products.append(product)
    return _clean_text(data.get("title"), limit=300), products


# --------------------------------------------------------------------------- #
# 任务入口（ACP 会话）
# --------------------------------------------------------------------------- #
def run_task(
    url: str,
    out_dir: Path,
    *,
    prompt: str | None = None,
    extra: str | None = None,
    session_id: str | None = None,
    kind: str = "scrape",
    payload: dict | None = None,
    emit=lambda level, text: None,
    emit_event=lambda event: None,
    model: str | None = None,
    thinking: str | None = None,
    acp_factory=AcpClient,
) -> dict:
    """跑一轮：新建会话或续聊。返回 result 字典（含 session_id / reply / kind）。"""
    model = model or settings.agent_model
    thinking = (thinking or settings.agent_reasoning or "off").lower()
    publish = kind == "taobao_publish"

    if publish:
        if payload is None:  # 续聊：沿用工作目录里已有的商品数据
            existing = out_dir / "publish_payload.json"
            payload = json.loads(existing.read_text(encoding="utf-8")) if existing.exists() else {}
        write_publish_workdir(out_dir, payload)
    else:
        write_workdir(out_dir, url, model=model, thinking=thinking)

    result = {
        "url": url,
        "kind": kind,
        "title": "",
        "products": [],
        "session_id": session_id or "",
        "reply": "",
        "error": "",
        "usage": {},
    }
    state = {"reply": ""}

    def handle(kind: str, payload) -> None:
        if kind == "update":
            line = summarize_update(payload.get("update") or {})
            if line is None:
                return
            if line["level"] == "agent-chunk":
                state["reply"] += line["text"]
            else:
                emit(line["level"], line["text"])
        elif kind == "stderr":
            emit("info", f"dsh: {payload}")
        elif kind == "noise":
            emit("info", str(payload)[:300])

    if prompt:
        if session_id:
            task_text = prompt  # 续聊：原样发
        elif publish:
            task_text = (
                f"继续之前的淘宝上架任务（商品数据在 ./publish_payload.json，工具在 ./browser.py）。"
                f"用户说：{prompt}"
            )
        else:
            task_text = f"继续之前的工作（入口 {url}，已有结果在 ./products.json）。用户说：{prompt}"
    elif publish:
        task_text = build_publish_prompt()
    else:
        task_text = build_prompt(url)
        if extra and extra.strip():
            # 首轮的自定义要求：接在默认提示词后面，不覆盖它
            task_text += f"\n\n用户补充要求（优先满足，但不要违反上面的产出要求）：\n{extra.strip()}"

    emit(
        "info",
        f"{'续聊会话 ' + session_id[:8] + '…' if session_id else '新建会话'} · 模型 {model} · 推理 {thinking}",
    )

    try:
        with acp_factory(
            cwd=out_dir,
            patch_path=out_dir / "dsh.patch.yml",
            api_key=settings.deepseek_api_key,
            on_event=handle,
        ) as client:
            client.initialize()
            active_session = client.resume_session(session_id) if session_id else client.new_session()
            result["session_id"] = active_session
            if not session_id:
                emit("info", f"会话已建立：{active_session[:8]}…")
            stop_reason = client.prompt(active_session, task_text)
            if stop_reason and stop_reason != "end_turn":
                emit("info", f"agent 结束：{stop_reason}")
    except AcpError as exc:
        result["error"] = str(exc)
        emit("error", str(exc))
    except Exception as exc:  # noqa: BLE001 dsh 各种异常都收成任务失败
        result["error"] = str(exc)
        emit("error", f"agent 执行失败：{exc}")

    # 整个会话（含之前的续聊）的累计 token：dsh 进程退出后再读，日志才是完整的
    if result["session_id"]:
        try:
            usage = read_session_usage(result["session_id"])
        except Exception as exc:  # noqa: BLE001 统计失败不影响任务结果
            usage = None
            emit("info", f"token 统计失败：{exc}")
        if usage:
            result["usage"] = usage
            emit("info", f"本次会话累计 {format_usage(usage)}")

    reply = state["reply"].strip()
    result["reply"] = reply
    if reply:
        emit("agent", reply)

    if not result["error"]:
        try:
            if publish:
                report = read_publish_result(out_dir)
                count = len(payload.get("items", [])) if payload else 0
                result["title"] = f"淘宝上架（{count} 件）"
                result["report"] = report
                message = str(report.get("message") or "")
                if report.get("ok"):
                    emit("info", f"上架结果：{message or '完成'}")
                else:
                    emit("error", f"上架未完成：{message or report}")
                if report.get("need_human"):
                    emit("info", f"需要真人：{report['need_human']}")
            else:
                title, products = read_products(out_dir, url)
                result["title"] = title or url
                result["products"] = products
                emit("info", f"收到 products.json：{len(products)} 件商品")
        except (FileNotFoundError, ValueError) as exc:
            result["error"] = str(exc)
            emit("error", str(exc))

    emit_event({"type": "result", **result})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 URL / 追问交给 deepseek harness（dsh ACP）")
    parser.add_argument("--url", required=True, help="任务入口 URL（续聊时用于上下文）")
    parser.add_argument("--out", required=True, help="任务目录（agent 在这里工作，products.json 也写这里）")
    parser.add_argument("--prompt", default=None, help="用户追问（续聊）；不填 = 首次任务")
    parser.add_argument("--extra", default=None, help="首轮的自定义要求（拼在默认提示词后）")
    parser.add_argument("--resume", default=None, help="要续聊的 dsh session id")
    parser.add_argument("--kind", default="scrape", choices=["scrape", "taobao_publish"])
    parser.add_argument("--payload", default=None, help="taobao_publish 的商品数据 JSON 路径")
    parser.add_argument("--model", default=None)
    parser.add_argument("--thinking", default=None, choices=["off", "low", "high", "max"])
    args = parser.parse_args(argv)

    payload = None
    if args.payload:
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))

    def emit(level: str, text: str) -> None:
        print(json.dumps({"type": "log", "level": level, "text": text}, ensure_ascii=False), flush=True)

    def emit_event(event: dict) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)

    result = run_task(
        args.url,
        Path(args.out),
        prompt=args.prompt,
        extra=args.extra,
        session_id=args.resume,
        kind=args.kind,
        payload=payload,
        emit=emit,
        emit_event=emit_event,
        model=args.model,
        thinking=args.thinking,
    )
    (Path(args.out) / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if result["products"] or not result["error"] else 1


if __name__ == "__main__":
    sys.exit(main())
