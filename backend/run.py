"""统一入口（开发 / 打包共用）。

  python run.py [--port 8000]        起 HTTP 服务（端口也可用 EC_PORT）
  python run.py --harness ...        AI 抓取任务（等价 python -m app.agent.harness）
  python run.py --fetch json|raw …   页面抓取小工具（./fetch / ./fetch_raw 用它）

打包成 merch-backend 后：Electron 起服务、dsh 任务、agent 的抓取命令
全部通过这一个可执行文件分发，不需要用户机器上有 Python 仓库。
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--harness":
        from app.agent.harness import main as harness_main

        return harness_main(sys.argv[2:])

    if len(sys.argv) > 1 and sys.argv[1] == "--fetch":
        from app.agent.fetch_cli import main as fetch_main

        return fetch_main(sys.argv[2:])

    import uvicorn

    from app.main import app

    port = int(os.getenv("EC_PORT", "8000"))
    host = os.getenv("EC_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("EC_LOG_LEVEL", "info").lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
