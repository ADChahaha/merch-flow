import { useEffect, useState } from 'react'
import { api } from '../api'
import type { AgentSettings, AppSettings, BilibiliSettings, UiSettings } from '../types'

const REASONING_OPTIONS = [
  { value: 'off', label: '关闭（最快，默认）' },
  { value: 'low', label: '低（low）' },
  { value: 'high', label: '高（high）' },
  { value: 'max', label: '最高（max，最慢最贵）' },
]

/** 设置页：AI 抓取（DeepSeek）+ B 站上架凭证。凭证只存本地 backend/.env。 */
export function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [error, setError] = useState('')

  const reload = async () => {
    try {
      setSettings(await api.settings())
    } catch (err) {
      setError((err as Error).message)
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  return (
    <div className="flex h-full min-w-0 flex-1 bg-slate-50">
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-2xl space-y-6">
          <header>
            <h2 className="text-[20px] font-semibold text-slate-900">设置</h2>
            <p className="mt-0.5 text-[12px] text-slate-400">
              保存会写入 backend/.env 并即时生效（无需重启后端）
            </p>
          </header>

          {settings ? (
            <>
              <section>
                <h3 className="mb-2 text-[13px] font-semibold text-slate-700">AI 抓取</h3>
                <AgentSection settings={settings.agent} onSaved={reload} onError={setError} />
              </section>

              <section>
                <h3 className="mb-2 text-[13px] font-semibold text-slate-700">界面</h3>
                <UiSection settings={settings.ui} onSaved={reload} onError={setError} />
              </section>

              <section>
                <h3 className="mb-2 text-[13px] font-semibold text-slate-700">Bilibili 上架凭证</h3>
                <BilibiliSection
                  settings={settings.bilibili}
                  onSaved={reload}
                  onError={setError}
                />
              </section>
            </>
          ) : (
            !error && <p className="text-[12px] text-slate-400">加载中…</p>
          )}

          {error && <p className="text-[11px] text-rose-500">读取/保存失败：{error}</p>}
        </div>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// 通用小组件
// --------------------------------------------------------------------------- //
function Group({ children }: { children: React.ReactNode }) {
  return (
    <section className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
      {children}
    </section>
  )
}

function Row({
  title,
  desc,
  children,
}: {
  title: string
  desc: string
  children?: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-6 px-4 py-3.5">
      <div className="min-w-0">
        <p className="text-[13px] text-slate-800">{title}</p>
        <p className="mt-0.5 text-[11px] leading-relaxed text-slate-400">{desc}</p>
      </div>
      <div className="shrink-0 pt-0.5">{children}</div>
    </div>
  )
}

function StatusChip({ configured, hint }: { configured: boolean; hint: string }) {
  return (
    <span
      className={`rounded-md px-2 py-1 text-[11px] ring-1 ring-inset ${
        configured
          ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
          : 'bg-amber-50 text-amber-700 ring-amber-200'
      }`}
    >
      {configured ? `已配置 ${hint}` : '未配置'}
    </span>
  )
}

function SecretInput({
  value,
  onChange,
  onEnter,
  placeholder,
  width = 'w-56',
}: {
  value: string
  onChange: (v: string) => void
  onEnter?: () => void
  placeholder: string
  width?: string
}) {
  return (
    <input
      type="password"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && onEnter) onEnter()
      }}
      placeholder={placeholder}
      spellCheck={false}
      autoComplete="off"
      className={`${width} rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-brand-500`}
    />
  )
}

function SaveButton({
  busy,
  disabled,
  onClick,
  label = '保存',
}: {
  busy: boolean
  disabled: boolean
  onClick: () => void
  label?: string
}) {
  return (
    <button
      type="button"
      disabled={busy || disabled}
      onClick={onClick}
      className="rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
    >
      {label}
    </button>
  )
}

function ClearButton({ busy, onClick, title }: { busy: boolean; onClick: () => void; title: string }) {
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onClick}
      title={title}
      className="rounded-md border border-slate-200 px-2.5 py-1.5 text-xs text-slate-500 transition hover:border-rose-200 hover:text-rose-600 disabled:opacity-50"
    >
      清除
    </button>
  )
}

// --------------------------------------------------------------------------- //
// AI 抓取
// --------------------------------------------------------------------------- //
function AgentSection({
  settings,
  onSaved,
  onError,
}: {
  settings: AgentSettings
  onSaved: () => void
  onError: (message: string) => void
}) {
  const [keyInput, setKeyInput] = useState('')
  const [model, setModel] = useState(settings.model || 'deepseek-v4-flash')
  const [reasoning, setReasoning] = useState(settings.reasoning || 'off')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const save = async (payload: Parameters<typeof api.saveSettings>[0]) => {
    setBusy(true)
    setMessage('')
    try {
      await api.saveSettings(payload)
      setKeyInput('')
      setMessage('已保存')
      onSaved()
    } catch (err) {
      onError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const runtimeDirty = model !== settings.model || reasoning !== settings.reasoning

  return (
    <div className="space-y-2">
      <Group>
        <Row
          title="DeepSeek API Key"
          desc="AI 抓取走 dsh（deepseek harness）跑，用它调模型。key 只写不读，界面只显示配没配和末尾 4 位"
        >
          <StatusChip configured={!!settings.has_key} hint={settings.key_hint ?? ''} />
        </Row>

        <Row title="设置 / 更换 Key" desc="填新的保存即覆盖；输入框里的内容不会回显到界面上">
          <div className="flex items-center gap-2">
            <SecretInput
              value={keyInput}
              onChange={setKeyInput}
              onEnter={() => keyInput.trim() && void save({ deepseek_api_key: keyInput.trim() })}
              placeholder="sk-…"
            />
            <SaveButton
              busy={busy}
              disabled={!keyInput.trim()}
              onClick={() => void save({ deepseek_api_key: keyInput.trim() })}
            />
            {settings.has_key && (
              <ClearButton
                busy={busy}
                onClick={() => void save({ deepseek_api_key: '' })}
                title="从 backend/.env 里清掉 key"
              />
            )}
          </div>
        </Row>

        <Row
          title="运行参数"
          desc="模型：flash 快且便宜（默认）/ pro 更聪明。推理强度：开 thinking 会更准但更慢更贵"
        >
          <div className="flex items-center gap-2">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 outline-none focus:border-brand-500"
            >
              <option value="deepseek-v4-flash">deepseek-v4-flash</option>
              <option value="deepseek-v4-pro">deepseek-v4-pro</option>
            </select>
            <select
              value={reasoning}
              onChange={(e) => setReasoning(e.target.value)}
              title="推理强度（Thinking 模式）"
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 outline-none focus:border-brand-500"
            >
              {REASONING_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  推理：{item.label}
                </option>
              ))}
            </select>
            <SaveButton
              busy={busy}
              disabled={!runtimeDirty}
              onClick={() => void save({ agent_model: model, agent_reasoning: reasoning })}
              label="保存参数"
            />
          </div>
        </Row>
      </Group>
      {message && <p className="text-[11px] text-emerald-600">{message}</p>}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// 界面
// --------------------------------------------------------------------------- //
function UiSection({
  settings,
  onSaved,
  onError,
}: {
  settings: UiSettings
  onSaved: () => void
  onError: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)

  const save = async (value: boolean) => {
    setBusy(true)
    try {
      await api.saveSettings({ ui_source_open: value })
      onSaved()
    } catch (err) {
      onError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Group>
      <Row
        title="默认打开原始页面"
        desc="商品页左侧的「原始页面」iframe（对照 AI 抽取结果核对用）。页内右上角的开关只影响本次会话"
      >
        <Toggle
          checked={settings.source_open}
          disabled={busy}
          onChange={(value) => void save(value)}
        />
      </Row>
    </Group>
  )
}

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-5 w-9 rounded-full transition disabled:opacity-50 ${
        checked ? 'bg-brand-600' : 'bg-slate-300'
      }`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${
          checked ? 'left-4.5' : 'left-0.5'
        }`}
      />
    </button>
  )
}

// --------------------------------------------------------------------------- //
// Bilibili 凭证
// --------------------------------------------------------------------------- //
function BilibiliSection({
  settings,
  onSaved,
  onError,
}: {
  settings: BilibiliSettings
  onSaved: () => void
  onError: (message: string) => void
}) {
  const [tokenInput, setTokenInput] = useState('')
  const [clientId, setClientId] = useState(settings.client_id || '')
  const [secretInput, setSecretInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const save = async (payload: Parameters<typeof api.saveSettings>[0]) => {
    setBusy(true)
    setMessage('')
    try {
      await api.saveSettings(payload)
      setTokenInput('')
      setSecretInput('')
      setMessage('已保存')
      onSaved()
    } catch (err) {
      onError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const appDirty = clientId !== (settings.client_id || '') || secretInput.trim().length > 0

  return (
    <div className="space-y-2">
      <Group>
        <Row
          title="Access-Token"
          desc="B 站开放平台的商品发布凭证（请求头 Access-Token）。只写不读，只显示末尾 4 位"
        >
          <StatusChip configured={!!settings.has_token} hint={settings.token_hint ?? ''} />
        </Row>

        <Row title="上传 / 更换 Access-Token" desc="粘贴开放平台后台签发的 Access-Token，保存后写入 backend/.env">
          <div className="flex items-center gap-2">
            <SecretInput
              value={tokenInput}
              onChange={setTokenInput}
              onEnter={() => tokenInput.trim() && void save({ bilibili_access_token: tokenInput.trim() })}
              placeholder="粘贴 Access-Token…"
              width="w-72"
            />
            <SaveButton
              busy={busy}
              disabled={!tokenInput.trim()}
              onClick={() => void save({ bilibili_access_token: tokenInput.trim() })}
            />
            {settings.has_token && (
              <ClearButton
                busy={busy}
                onClick={() => void save({ bilibili_access_token: '' })}
                title="从 backend/.env 里清掉 Access-Token"
              />
            )}
          </div>
        </Row>

        <Row title="Client ID / Client Secret" desc="开放平台应用的 client_id 与 client_secret（换来 Access-Token 用）">
          <div className="flex items-center gap-2">
            <input
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder="client_id"
              spellCheck={false}
              autoComplete="off"
              className="w-40 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-brand-500"
            />
            <SecretInput
              value={secretInput}
              onChange={setSecretInput}
              onEnter={() =>
                appDirty &&
                void save({
                  bilibili_client_id: clientId.trim(),
                  ...(secretInput.trim() ? { bilibili_client_secret: secretInput.trim() } : {}),
                })
              }
              placeholder={settings.has_client_secret ? '••••（已配置，留空不改）' : 'client_secret'}
              width="w-48"
            />
            <SaveButton
              busy={busy}
              disabled={!appDirty}
              onClick={() =>
                void save({
                  bilibili_client_id: clientId.trim(),
                  ...(secretInput.trim() ? { bilibili_client_secret: secretInput.trim() } : {}),
                })
              }
            />
          </div>
        </Row>
      </Group>
      {message && <p className="text-[11px] text-emerald-600">{message}</p>}
      <p className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-2.5 text-[11px] leading-relaxed text-slate-400">
        凭证只存在本机 backend/.env，后端不代持、不会回显明文。上架页目前只组装符合 B 站 product_add
        契约的请求体，真正发布时由你带着 Access-Token 调接口。
      </p>
    </div>
  )
}
