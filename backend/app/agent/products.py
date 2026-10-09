"""跨续聊保留商品身份；不把被复用的 SQLite 行号当作商品身份。"""
from __future__ import annotations


def match_product(product: dict, available: dict):
    uid = product.get("uid")
    if uid in available:
        return available.pop(uid)
    candidates = [row for row in available.values()
                  if row.name == product.get("name") and row.source_url == (product.get("source_url") or "")]
    exact = [row for row in candidates if list(row.image_urls or []) == list(product.get("image_urls") or [])]
    if len(exact) == 1:
        row = exact[0]
    elif len(candidates) == 1:
        row = candidates[0]
    else:
        return None  # 无法判定时创建新身份，不能把另一个商品的勾选转移过来。
    return available.pop(row.uid)
