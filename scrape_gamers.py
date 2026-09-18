#!/usr/bin/env python3
"""Scrape a GAMERS event/fair detail page into structured data.

Usage:
    python scrape_gamers.py [event_id] [--out DIR]

Example:
    python scrape_gamers.py 7910 --out gamers_7910
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html

BASE = "https://www.gamers.co.jp"
DETAIL_URL = BASE + "/contents/event_fair/detail.php?id={event_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.8",
}

PRICE_RE = re.compile(r"価格[:：]\s*([\d,]+円\(税込\))")
SET_PRICE_RE = re.compile(r"(コンプリートセット|セット価格)[:：]\s*([\d,]+円\(税込\))")
PERIOD_RE = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日\(([^)]*)\)"
    r"\s*[～~\-]\s*"
    r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\(([^)]*)\)"
)


def fetch(url: str) -> str:
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def abs_url(src: str) -> str:
    return urljoin(BASE, src)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def text_of(node) -> str:
    return clean(node.text_content())


def section_html(doc, heading: str):
    """Return the content block that follows an <h3> with the given heading."""
    for h3 in doc.xpath("//h3"):
        if clean(h3.text_content()) == heading:
            node = h3.getnext()
            while node is not None and node.tag not in ("div", "section"):
                node = node.getnext()
            return node
    return None


def parse_page(page_html: str, event_id: str) -> dict:
    doc = lxml_html.fromstring(page_html)

    data: dict = {"source_url": DETAIL_URL.format(event_id=event_id)}

    title_node = doc.xpath("//h2[contains(@class,'ttl')]")
    data["title"] = text_of(title_node[0]) if title_node else None

    data["main_image_url"] = None
    og = doc.xpath("//meta[@property='og:image']/@content")
    if og:
        data["main_image_url"] = og[0]

    page_text = doc.text_content()
    m = re.search(r"(\d{4}年\d{2}月\d{2}日)\s*公開", page_text)
    data["published_at"] = m.group(1) if m else None

    store_info = section_html(doc, "開催概要")
    data["overview_text"] = text_of(store_info) if store_info is not None else None
    data["periods"] = []
    if store_info is not None:
        for y1, m1, d1, w1, y2, m2, d2, w2 in PERIOD_RE.findall(
            text_of(store_info)
        ):
            year2 = y2 or y1
            data["periods"].append(
                {
                    "start": f"{y1}年{int(m1):02d}月{int(d1):02d}日({w1})",
                    "end": f"{year2}年{int(m2):02d}月{int(d2):02d}日({w2})",
                }
            )

    bonuses = []
    for heading in ("店頭購入特典", "ゲーマーズオンラインショップ購入特典"):
        sec = section_html(doc, heading)
        if sec is None:
            continue
        images = [
            {"alt": clean(img.get("alt") or ""), "url": abs_url(img.get("src"))}
            for img in sec.xpath(".//img")
            if img.get("src")
        ]
        bonuses.append(
            {"name": heading, "description": text_of(sec), "images": images}
        )
    data["purchase_bonuses"] = bonuses

    products = []
    goods = section_html(doc, "販売商品")
    if goods is not None:
        for p in goods.xpath(".//p[contains(@class,'box')]"):
            img = p.xpath(".//img")
            img_url = abs_url(img[0].get("src")) if img else None
            img_alt = clean(img[0].get("alt") or "") if img else None

            lines = [clean(x) for x in p.itertext()]
            lines = [x for x in lines if x]

            name = img_alt
            for line in lines:
                if line.startswith("■"):
                    name = line.lstrip("■").strip()
                    break

            price = None
            price_match = PRICE_RE.search(text_of(p))
            if price_match:
                price = price_match.group(1)

            set_price = None
            set_match = SET_PRICE_RE.search(text_of(p))
            if set_match:
                set_price = f"{set_match.group(1)}：{set_match.group(2)}"

            notes = [
                x
                for x in lines
                if not x.startswith("■")
                and not x.startswith("価格")
                and not re.match(r"^(コンプリートセット|セット価格)", x)
                and x != name
            ]

            products.append(
                {
                    "name": name,
                    "price": price,
                    "set_price": set_price,
                    "image_url": img_url,
                    "image_alt": img_alt,
                    "notes": notes,
                }
            )
    data["products"] = products

    stores = []
    sec = section_html(doc, "開催店舗")
    if sec is not None:
        stores = [
            {"name": clean(a.text_content()), "url": abs_url(a.get("href"))}
            for a in sec.xpath(".//a[@href]")
        ]
    data["stores"] = stores

    sec = section_html(doc, "関連語句")
    data["related_keywords"] = (
        [
            {"name": clean(a.text_content()), "url": abs_url(a.get("href"))}
            for a in sec.xpath(".//a[@href]")
        ]
        if sec is not None
        else []
    )

    return data


def write_outputs(data: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "event.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with (out_dir / "products.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["No.", "商品名", "价格", "套装价", "图片URL", "备注"]
        )
        for i, p in enumerate(data["products"], 1):
            writer.writerow(
                [
                    i,
                    p["name"],
                    p["price"] or "",
                    p["set_price"] or "",
                    p["image_url"] or "",
                    " / ".join(p["notes"]),
                ]
            )

    lines = [
        f"# {data['title']}",
        "",
        f"- 来源: {data['source_url']}",
        f"- 公开日期: {data['published_at']}",
        f"- 主图: {data['main_image_url']}",
        "",
    ]
    if data["periods"]:
        lines.append("## 举办期间")
        for period in data["periods"]:
            lines.append(f"- {period['start']} ~ {period['end']}")
        lines.append("")
    if data["purchase_bonuses"]:
        lines.append("## 购买特典")
        for bonus in data["purchase_bonuses"]:
            lines.append(f"### {bonus['name']}")
            for img in bonus["images"]:
                lines.append(f"- ![{(img['alt'] or '')}]({img['url']})")
            lines.append("")
    lines.append(f"## 商品 ({len(data['products'])})")
    lines.append("")
    for i, p in enumerate(data["products"], 1):
        lines.append(f"### {i}. {p['name']}")
        if p["price"]:
            lines.append(f"- 价格: {p['price']}")
        if p["set_price"]:
            lines.append(f"- {p['set_price']}")
        if p["image_url"]:
            lines.append(f"- 图片: {p['image_url']}")
        lines.append("")
    if data["stores"]:
        lines.append("## 举办店铺")
        for store in data["stores"]:
            lines.append(f"- [{store['name']}]({store['url']})")
        lines.append("")
    (out_dir / "event.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_id", nargs="?", default="7910")
    parser.add_argument("--out", default=None, help="output directory")
    args = parser.parse_args()

    out_dir = Path(args.out or f"gamers_{args.event_id}")
    page_html = fetch(DETAIL_URL.format(event_id=args.event_id))
    data = parse_page(page_html, args.event_id)
    (out_dir).mkdir(parents=True, exist_ok=True)
    (out_dir / "page.html").write_text(page_html, encoding="utf-8")
    write_outputs(data, out_dir)

    print(f"title      : {data['title']}")
    print(f"published  : {data['published_at']}")
    print(f"products   : {len(data['products'])}")
    print(f"output dir : {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
