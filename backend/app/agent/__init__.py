"""AI 抓取：输入一个 URL，交给官方 DeepSeek Harness（dsh）agent 自主抓商品。

链路：routers/agent → jobs（起子进程 / 日志 / 落库）→ harness（准备任务目录 + 调 dsh）
→ dsh（模型自己决定翻哪些页、怎么抽）→ products.json。
fetch/page 是给 agent 用的抓取小工具（直连 + CF 兜底 + 正文/链接提取）。
"""
