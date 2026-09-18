"""页面解析：正文 / 图片 / 链接 的净化与绝对化。

模型看不到原始 HTML，这些函数就是它的「眼睛」——按这里的行为写死。
"""

from __future__ import annotations

from app.agent.page import (
    clean_url,
    extract_images,
    extract_links,
    extract_text,
    parse_html,
    render_for_model,
    same_site,
)

HTML = """
<html><head><title> テスト イベント </title>
<style>.a{color:red}</style><script>var x = "商品";</script></head>
<body>
  <nav><a href="/guide">ご利用ガイド</a></nav>
  <h1>商品一覧</h1>
  <img src="/img/main.jpg" alt="メイン画像">
  <img data-src="/img/lazy.png" alt="遅延画像">
  <img src="data:image/gif;base64,xxx" alt="inline">
  <a href="/pd/12345/">アクリルスタンド</a>
  <a href="/pd/12345#gallery">アクリルスタンド（重复）</a>
  <a href="https://twitter.com/share">シェア</a>
  <a href="/files/price.pdf">価格表</a>
  <a href="https://other.example.com/pd/1">外部サイト</a>
  <a href="mailto:info@example.jp">メール</a>
</body></html>
"""


def parse():
    return parse_html(HTML)


def test_title_is_whitespace_normalized():
    doc = parse()
    assert doc.find(".//title").text_content().strip().startswith("テスト")


def test_text_drops_script_and_style():
    text = extract_text(parse())
    assert "商品一覧" in text
    assert "var x" not in text
    assert "color:red" not in text


def test_text_respects_limit():
    text = extract_text(parse(), limit=10)
    suffix = "\n…（正文已截断）"
    assert text.endswith("…（正文已截断）")
    assert len(text) == 10 + len(suffix)  # 原文严格砍到 10 字符再挂尾巴


def test_images_are_absolute_deduped_and_lazy_aware():
    images = extract_images(parse(), "https://shop.example.com/fair/")
    urls = [img.url for img in images]
    assert urls == ["https://shop.example.com/img/main.jpg", "https://shop.example.com/img/lazy.png"]
    assert images[0].alt == "メイン画像"


def test_links_filter_junk_external_and_fragments():
    links = extract_links(parse(), "https://shop.example.com/fair/", same_site_only=True)
    urls = [link.url for link in links]
    assert "https://shop.example.com/pd/12345/" in urls
    assert all("twitter.com" not in url for url in urls)
    assert all(not url.endswith(".pdf") for url in urls)
    assert all("other.example.com" not in url for url in urls)  # 只跟同站
    assert all("#" not in url for url in urls)  # fragment 去掉后同行只留一条


def test_product_like_links_come_first():
    links = extract_links(parse(), "https://shop.example.com/fair/", same_site_only=True)
    assert links[0].looks_like_product is True
    assert links[0].url.endswith("/pd/12345/")


def test_cross_site_allowed_when_configured():
    links = extract_links(parse(), "https://shop.example.com/fair/", same_site_only=False)
    assert any("other.example.com" in link.url for link in links)


def test_same_site_matches_subdomains_only():
    assert same_site("https://shop.example.com/a", "https://www.example.com/b") is True
    assert same_site("https://evil-example.com/a", "https://example.com/b") is False


def test_clean_url_keeps_query_drops_fragment():
    assert clean_url("https://a.com/pd/1?x=2#top") == "https://a.com/pd/1?x=2"


def test_render_for_model_has_all_sections():
    doc = parse()
    content = render_for_model(
        "https://shop.example.com/fair/",
        title="テスト",
        text=extract_text(doc),
        images=extract_images(doc, "https://shop.example.com/fair/"),
        links=extract_links(doc, "https://shop.example.com/fair/"),
        depth=1,
    )
    assert "【正文】" in content and "【页面图片】" in content and "【页面链接】" in content
    assert "https://shop.example.com/img/main.jpg | メイン画像" in content


def test_invalid_html_returns_none():
    assert parse_html("") is None  # 空文档
    assert parse_html("ただのテキスト") is not None  # lxml 会包成 span，不炸就行
