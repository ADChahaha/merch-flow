/**
 * Electron 壳（最小版）：把本仓库当成一个本地桌面应用跑起来。
 *
 *   1. 用仓库里的 venv 起 Python 后端（uvicorn），监听一个随机空闲端口；
 *   2. 轮询 /api/health，就绪后窗口加载 http://127.0.0.1:<port>
 *      （后端顺带 serve frontend/dist，所以只有一个进程、没有 CORS 问题）；
 *   3. 退出时把后端连同它的子进程（dsh / 抓取用的 Chrome）一起收走。
 *
 * 环境变量：
 *   EC_PYTHON         指定 python 解释器（默认仓库 .venv）
 *   EC_BACKEND_DIR    后端目录（默认 ../backend）
 *   EC_DESKTOP_URL    直接加载这个 URL（开发时指到 vite dev server，不起后端）
 *   EC_DESKTOP_SMOKE  1 = 页面加载完成后自动退出（自检/CI 用）
 */

const { app, BrowserWindow, dialog } = require('electron')
const { spawn, spawnSync } = require('node:child_process')
const net = require('node:net')
const path = require('node:path')
const fs = require('node:fs')

const REPO_ROOT = path.resolve(__dirname, '..')
const BACKEND_DIR = process.env.EC_BACKEND_DIR ?? path.join(REPO_ROOT, 'backend')
const DEV_URL = process.env.EC_DESKTOP_URL ?? ''
const SMOKE = process.env.EC_DESKTOP_SMOKE === '1'
const IS_PACKAGED = app.isPackaged

let backend = null
let backendPort = 0
let quitting = false

// --------------------------------------------------------------------------- //
// 后端：起进程 / 等就绪 / 退出时清理
// --------------------------------------------------------------------------- //
function pythonPath() {
  if (process.env.EC_PYTHON) return process.env.EC_PYTHON
  const venv = path.join(REPO_ROOT, '.venv')
  const candidates =
    process.platform === 'win32'
      ? [path.join(venv, 'Scripts', 'python.exe')]
      : [path.join(venv, 'bin', 'python3'), path.join(venv, 'bin', 'python')]
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate
  }
  return process.platform === 'win32' ? 'python' : 'python3'
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
  })
}

function logBackend(line) {
  const text = String(line).trimEnd()
  if (text) console.log(`[backend] ${text}`)
}

/** 后端命令：打包版用内置的 merch-backend；开发版用仓库 venv 跑 backend/run.py。 */
function backendCommand(port) {
  if (IS_PACKAGED) {
    const exe = process.platform === 'win32' ? 'merch-backend.exe' : 'merch-backend'
    return {
      cmd: path.join(process.resourcesPath, 'backend', exe),
      args: [],
      cwd: process.resourcesPath,
    }
  }
  return {
    cmd: pythonPath(),
    args: [path.join(BACKEND_DIR, 'run.py')],
    cwd: BACKEND_DIR,
  }
}

async function startBackend() {
  backendPort = await freePort()
  const { cmd, args, cwd } = backendCommand(backendPort)
  console.log(`[desktop] 启动后端：${cmd}（端口 ${backendPort}${IS_PACKAGED ? '，打包版' : ''}）`)

  const env = { ...process.env, EC_PORT: String(backendPort), PYTHONUNBUFFERED: '1' }
  if (IS_PACKAGED) {
    // 数据（.env / 数据库 / agent_jobs）写到系统应用数据目录；前端 dist 在 resources 里
    env.EC_DATA_DIR = app.getPath('userData')
    env.EC_FRONTEND_DIST = path.join(process.resourcesPath, 'frontend-dist')
  }

  backend = spawn(cmd, args, {
    cwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    // unix 下单独进程组，退出时能整组带走（dsh、Chrome 都在里面）
    detached: process.platform !== 'win32',
  })
  backend.stdout.on('data', (chunk) => logBackend(chunk))
  backend.stderr.on('data', (chunk) => logBackend(chunk))
  backend.on('exit', (code, signal) => {
    backend = null
    if (!quitting) {
      dialog.showErrorBox('后端退出了', `Python 后端意外退出（code=${code} signal=${signal}），看终端日志定位原因。`)
      app.quit()
    }
  })
  backend.on('error', (error) => {
    dialog.showErrorBox(
      '后端起不来',
      IS_PACKAGED
        ? `内置后端启动失败：${error.message}`
        : `启动 ${cmd} 失败：${error.message}\n\n先在仓库根目录建好 .venv 并装依赖。`,
    )
  })

  const root = `http://127.0.0.1:${backendPort}/`
  const deadline = Date.now() + 40_000
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${root}api/health`, { signal: AbortSignal.timeout(1500) })
      if (response.ok) return root
    } catch {
      // 还没起来，继续等
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
  throw new Error(`等待后端就绪超时（40s）：${root}api/health`)
}

function killBackend() {
  if (!backend || backend.pid === undefined) return
  quitting = true
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(backend.pid), '/T', '/F'], { stdio: 'ignore' })
  } else {
    try {
      process.kill(-backend.pid, 'SIGTERM')
    } catch {
      // 进程组可能已经没了
    }
  }
  backend = null
}

// --------------------------------------------------------------------------- //
// 窗口
// --------------------------------------------------------------------------- //
async function createWindow(url) {
  const win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1080,
    minHeight: 700,
    title: 'AI 商品聚合 / 上架助手',
    backgroundColor: '#f8fafc',
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  })
  win.on('closed', () => {
    if (process.platform === 'darwin') app.quit()
  })
  await win.loadURL(url)
  console.log(`[desktop] 界面已加载：${url}`)
  if (SMOKE) {
    const title = await win.webContents.executeJavaScript('document.title')
    const rootChildren = await win.webContents.executeJavaScript(
      'document.getElementById("root")?.childElementCount ?? 0',
    )
    if (!rootChildren) throw new Error('页面加载了但没渲染出内容（#root 是空的）')
    console.log(`[desktop] smoke ok：${title}（#root 子节点 ${rootChildren}）`)
    setTimeout(() => app.quit(), 300)
  }
  return win
}

// --------------------------------------------------------------------------- //
// 入口
// --------------------------------------------------------------------------- //
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    const [win] = BrowserWindow.getAllWindows()
    if (win) {
      if (win.isMinimized()) win.restore()
      win.focus()
    }
  })

  app.on('before-quit', killBackend)
  app.on('window-all-closed', () => app.quit())

  app.whenReady().then(async () => {
    try {
      const url = DEV_URL || (await startBackend())
      await createWindow(url)
    } catch (error) {
      console.error('[desktop] 启动失败：', error)
      dialog.showErrorBox('启动失败', String(error?.stack ?? error))
      app.exit(1)
    }
  })
}
