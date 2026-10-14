# MerchFlow · 跨站商品聚合 / 上架助手

给一个 URL，AI（deepseek harness）自己递归翻页把商品抽出来、落库回看；
抽到的商品一键加入上架清单，走 Bilibili 接口上架，或让 agent 打开卖家中心**浏览器自动化上架**（淘宝）。

- 前端：React + Vite + Tailwind（`frontend/`）
- 后端：FastAPI + SQLite（`backend/`）
- 桌面壳：Electron（`desktop/`，内置打包好的后端，双击即用）

## 下载安装（macOS / Windows）

到 [Releases](../../releases) 下载对应安装包：

| 平台 | 文件 | 说明 |
| --- | --- | --- |
| macOS（Apple Silicon） | `MerchFlow-x.y.z-mac-arm64.dmg` | 打开 dmg 拖进「应用程序」 |
| Windows（x64） | `MerchFlow-x.y.z-win-x64.exe` | NSIS 安装包，一路下一步 |

安装包**未签名**，首次打开会被系统拦一下：

- macOS：按住 Control 点图标 → 「打开」；或 `xattr -dr com.apple.quarantine /Applications/MerchFlow.app`
- Windows：SmartScreen 里点「更多信息 → 仍要运行」

## 外部依赖（AI 抓取 / 上架自动化要用）

应用本体（界面、回看记录、上架清单）不需要这些；但「AI 抓取」和「淘宝上架」在本地起
agent 干活，依赖下面三样（都不随安装包分发）：

| 依赖 | 用途 | 安装 |
| --- | --- | --- |
| **Node.js ≥ 18 + dsh** | AI 抓取 / 上架的 agent 本体 | `npm install -g @deepseek-ai/dsh`（[deepseek-harness](https://deepseek-harness.github.io/deepseek-harness/)） |
| **Python 3.10+** | agent 现场写的抓取/解析脚本要跑它 | macOS 自带或 [python.org](https://www.python.org/downloads/)，Windows 装时勾选 Add to PATH |
| **Chrome / Edge** | 过 Cloudflare 兜底、淘宝卖家中心自动化 | 装任意一个即可，路径会自动探测（特殊路径用 `EC_CHROME_PATH` 指） |

装完在应用里打开「设置 → AI 抓取」，填 `DEEPSEEK_API_KEY`。

## 源码运行（开发）

```bash
# 后端
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
backend 目录放 .env（参考 backend/.env.example），至少填 DEEPSEEK_API_KEY
cd backend && ../.venv/bin/python run.py          # http://127.0.0.1:8000

# 前端（开发服务器，/api 代理到 8000）
cd frontend && npm install && npm run dev          # http://localhost:5173

# 桌面壳（自动起后端 + 打包好的前端）
cd frontend && npm run build
cd desktop && npm install && npm start
```

`desktop` 的两种模式：

- `npm start`：起仓库 `.venv` 里的后端，窗口指向它（开发用）
- `npm run dev`：窗口指向 vite dev server（改前端热更新）
- `npm run smoke`：加载后自检渲染并退出（CI/自测用）

## 打包发版

后端用 PyInstaller 冻成单目录可执行文件，Electron 用 electron-builder 出安装包：

```bash
# 1. 后端（必须在目标平台构建：mac 产物只能 mac 上打，win 只能 windows 上打）
cd backend && pyinstaller --noconfirm --clean merch-backend.spec   # → backend/dist/merch-backend/

# 2. 前端 + 桌面壳
cd frontend && npm run build
cd desktop && npx electron-builder --mac   # 或 --win

# 3. 发版：打 tag 推上去，GitHub Actions 双端构建并挂到 Release
git tag v0.3.4 && git push origin v0.3.4
```

`.github/workflows/ci.yml`：每次 main 推送和 PR 均在 Windows(x64) / macOS(arm64)
运行后端与前端测试、构建后端、验证真实冻结产物并生成安装包。测试还会再次运行 Electron 包内的后端。
CP936/CP1252 回归测试强制旧编码标准流；打包测试通过真实进程管道验证中文、日文、emoji 和商品入库，
不依赖付费模型（外部 ACP 服务用离线 fixture 替代）。Windows runner 本身不必改成中文系统区域。

`.github/workflows/release.yml`：tag 推送复用上述 CI，**双平台全部通过才发布**。
发布说明放在 `docs/releases/<tag>.md`。Actions 页也可手动运行 CI。

本地验证冻结产物（先完成 PyInstaller 构建）：

```powershell
# Windows PowerShell
$env:MERCH_TEST_BACKEND = (Resolve-Path backend/dist/merch-backend/merch-backend.exe).Path
python -m pytest -q backend/tests/test_packaged_encoding.py -k frozen
```

v0.3.4 起标准输入输出和打包解释器均固定 UTF-8，不需要更改系统编码或关闭沙箱。

## 目录一览

```
backend/          FastAPI：抓取/上架接口、AI 任务管理、SQLite、run.py 统一入口
  app/agent/      dsh(ACP) 桥、抓取工具（fetch_cli）、token 统计、上架 agent
  merch-backend.spec  PyInstaller 配置
frontend/         React 界面（Agent 会话、商品、上架、设置）
desktop/          Electron 壳：起内置后端、窗口加载、退出清理
```
