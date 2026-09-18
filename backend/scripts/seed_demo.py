"""灌入几个演示关键词（只加壳，不抓取）。

    .venv/bin/python scripts/seed_demo.py

点开哪个关键词就现搜哪个，数量永远和站点一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db, session_scope  # noqa: E402
from app.services import catalog  # noqa: E402

KEYWORDS = [
    "ブルーアーカイブ",
    "勝利の女神：NIKKE",
    "ホロライブ",
    "原神",
    "ゼルダの伝説",
]


def main() -> int:
    init_db()
    with session_scope() as session:
        for keyword in KEYWORDS:
            product = catalog.create_product(session, keyword)
            print(f"  {product.name}")
    print("完成，启动后端即可看到左栏关键词（点开才现搜）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
