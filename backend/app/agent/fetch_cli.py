"""页面抓取小工具（CLI）：`./fetch` / `./fetch_raw` 和打包版的 `--fetch` 都走这里。

两种输出：
  json <url> [text_limit]   抓页面 → JSON（标题 / 正文 / 图片 / 链接）打到 stdout
  raw  <url> [out.html]     抓原始 HTML 存文件，打印保存路径和大小

逻辑统一放这里，避免「开发版模板脚本」和「打包版内置工具」两份实现漂移。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..config import settings
from .fetch import Fetcher
from .page import extract_images, extract_links, extract_text, page_title, parse_html


def json_main(argv: list[str]) -> int:
    if not argv:
        print("用法: fetch <url> [text_limit]", file=sys.stderr)
        return 2
    url = argv[0]
    limit = int(argv[1]) if len(argv) > 1 else settings.agent_page_text_limit
    fetcher = Fetcher(settings)
    try:
        html = fetcher.get_html(url)
    finally:
        fetcher.close()
    doc = parse_html(html)
    payload = {
        "url": url,
        "title": page_title(doc),
        "text": extract_text(doc, limit=limit),
        "images": [{"url": image.url, "alt": image.alt} for image in extract_images(doc, url)],
        "links": [
            {"url": link.url, "text": link.text}
            for link in extract_links(doc, url, same_site_only=False)
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0


def raw_main(argv: list[str]) -> int:
    if not argv:
        print("用法: fetch_raw <url> [out.html]", file=sys.stderr)
        return 2
    url = argv[0]
    out = Path(argv[1]) if len(argv) > 1 else Path("raw_page.html")
    fetcher = Fetcher(settings)
    try:
        html = fetcher.get_html(url)
    finally:
        fetcher.close()
    out.write_text(html, encoding="utf-8")
    print(f"{out}（{len(html)} 字符）")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"json", "raw"}:
        print("用法: fetch json|raw <url> [...]", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    return json_main(rest) if command == "json" else raw_main(rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
