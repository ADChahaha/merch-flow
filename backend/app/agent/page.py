"""把 HTML 压成「给模型看」的紧凑结构：标题 / 正文 / 图片 / 链接。

模型看不到原始 HTML，所以这里要做到两件事：
  * 正文只留可见文本（script/style/nav 里的不算），并截断控制 token；
  * 图片和链接都转成绝对 URL，附上 alt / 锚文本，模型才知道哪条值得跟。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

from lxml import etree
from lxml import html as lxml_html

# 这些域名和扩展名的链接跟下去没意义（社交 / 广告 / 文件）
JUNK_HOSTS = (
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "line.me",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "pinterest.com",
    "google.com",
    "apple.com",
    "doubleclick.net",
    "googletagmanager.com",
    "google-analytics.com",
)

JUNK_EXTENSIONS = (
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".mp4",
    ".mp3",
    ".css",
    ".js",
    ".ico",
    ".xml",
)

# URL / 锚文本里出现这些词，多半是商品或活动子页 → 排序时优先、提示模型优先跟
PRODUCT_HINTS = (
    "detail",
    "item",
    "product",
    "goods",
    "pd/",
    "pn/pd",
    "shop/",
    "event",
    "fair",
    "popup",
    "特典",
    "商品",
    "グッズ",
    "フェア",
)

_WS_RE = re.compile(r"[ \t\u3000]+")
_LINES_RE = re.compile(r"\n{3,}")
_DROP_TAGS = ("script", "style", "noscript", "svg", "template", "iframe")
_IMG_ATTRS = ("src", "data-src", "data-original", "data-lazy-src")


@dataclass(frozen=True)
class Link:
    url: str
    text: str

    @property
    def looks_like_product(self) -> bool:
        haystack = f"{self.url} {self.text}".lower()
        return any(hint in haystack for hint in PRODUCT_HINTS)


@dataclass(frozen=True)
class Image:
    url: str
    alt: str


def clean_url(url: str) -> str:
    """去掉 fragment（#...），保留 query —— 有些站点靠 query 定位商品。"""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def host_of(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def same_site(url: str, base_url: str) -> bool:
    """同站判断：裸域名相同就算（都去掉 www.，允许子域）。"""
    a, b = host_of(url), host_of(base_url)
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def page_title(doc) -> str:
    if doc is None:
        return ""
    title = doc.find(".//title")
    text = title.text_content() if title is not None else ""
    return _WS_RE.sub(" ", text).strip()[:300]


def extract_text(doc, *, limit: int = 20_000) -> str:
    """可见正文：丢掉 script/style 之类的噪音，压平空白，超长截断。"""
    if doc is None:
        return ""
    for tag in _DROP_TAGS:
        for node in doc.xpath(f"//{tag}"):
            node.getparent().remove(node)
    body = doc.find(".//body")
    text = (body if body is not None else doc).text_content()
    text = _WS_RE.sub(" ", text)
    text = _LINES_RE.sub("\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    if len(text) > limit:
        text = text[:limit] + "\n…（正文已截断）"
    return text.strip()


def extract_images(doc, base_url: str, *, limit: int = 150) -> list[Image]:
    """页面上的图片（含懒加载的 data-src），转绝对地址、去重。"""
    if doc is None:
        return []
    seen: set[str] = set()
    images: list[Image] = []
    for img in doc.xpath("//img"):
        raw = ""
        for attr in _IMG_ATTRS:
            value = (img.get(attr) or "").strip()
            if value and not value.startswith("data:"):
                raw = value
                break
        if not raw:
            continue
        url = clean_url(urljoin(base_url, raw))
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        alt = _WS_RE.sub(" ", (img.get("alt") or "")).strip()[:200]
        images.append(Image(url=url, alt=alt))
        if len(images) >= limit:
            break
    return images


def _is_junk_link(link: Link, base_url: str, *, same_site_only: bool) -> bool:
    if not link.url.startswith(("http://", "https://")):
        return True
    if link.url.lower().split("?")[0].endswith(JUNK_EXTENSIONS):
        return True
    host = urlsplit(link.url).netloc.lower()
    if any(host == junk or host.endswith("." + junk) for junk in JUNK_HOSTS):
        return True
    if same_site_only and not same_site(link.url, base_url):
        return True
    return False


def extract_links(
    doc,
    base_url: str,
    *,
    same_site_only: bool = True,
    limit: int = 200,
) -> list[Link]:
    """页面里的可跟链接。商品味的（detail/goods/…）排前面，方便模型挑。"""
    if doc is None:
        return []
    seen: set[str] = set()
    links: list[Link] = []
    for anchor in doc.xpath("//a[@href]"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        url = clean_url(urljoin(base_url, href))
        link = Link(url=url, text=_WS_RE.sub(" ", anchor.text_content()).strip()[:120])
        if url in seen or _is_junk_link(link, base_url, same_site_only=same_site_only):
            continue
        seen.add(url)
        links.append(link)
    links.sort(key=lambda link: not link.looks_like_product)  # 商品味优先
    return links[:limit]


def render_for_model(
    url: str,
    *,
    title: str,
    text: str,
    images: list[Image],
    links: list[Link],
    depth: int,
) -> str:
    """拼成喂给模型的「页面内容」文本。"""
    chunks = [
        f"URL: {url}",
        f"深度: {depth}",
        f"标题: {title}",
        "",
        "【正文】",
        text or "（没有可读文本）",
        "",
        "【页面图片】（绝对 URL | alt）",
    ]
    chunks += [f"{img.url} | {img.alt}" for img in images] or ["（无）"]
    chunks += ["", "【页面链接】（锚文本 | URL）"]
    chunks += [f"{link.text or '(无文本)'} | {link.url}" for link in links] or ["（无）"]
    return "\n".join(chunks)


def parse_html(raw: str) -> lxml_html.HtmlElement | None:
    try:
        return lxml_html.fromstring(raw)
    except (etree.LxmlError, ValueError, TypeError):
        return None
