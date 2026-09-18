import { useEffect, useRef, useState } from 'react'
import type { AgentJob } from '../types'
import { hostOf } from '../lib/agent'
import { IconCheckCircle, IconChevronDown, IconSpark, IconSpinner, IconX, IconXCircle } from './Icons'

type Props = {
  job: AgentJob | null
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 追问：接着当前会话继续聊（自由输入） */
  onChat: (message: string) => Promise<void>
}

const LEVEL_STYLE: Record<string, string> = {
  error: 'text-rose-600',
  user: 'text-brand-700 font-medium',
  agent: 'text-slate-800',
  think: 'text-slate-400 italic',
  tool: 'text-violet-500',
  info: 'text-slate-600',
  'agent-chunk': 'text-slate-800',
}

function levelPrefix(level: string): string {
  if (level === 'user') return '我：'
  if (level === 'agent') return 'AI：'
  return ''
}

/**
 * 右下角 popup：AI 抓取的实时日志。
 * 收起时留一个小胶囊（还在跑就带转圈），点开继续看。
 */
export function AgentLogPanel({ job, open, onOpenChange, onChat }: Props) {
  const scroller = useRef<HTMLDivElement>(null)
  const [chatText, setChatText] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const lineCount = job?.log.length ?? 0

  useEffect(() => {
    if (open && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight
  }, [lineCount, open])

  if (!job) return null

  const running = job.status === 'running'
  const title = job.title || hostOf(job.url)

  const sendChat = async () => {
    const text = chatText.trim()
    if (!text || running || chatBusy) return
    setChatBusy(true)
    try {
      await onChat(text)
      setChatText('')
    } finally {
      setChatBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => onOpenChange(true)}
        className="fixed right-4 bottom-4 z-40 flex items-center gap-2 rounded-full bg-slate-900 py-2.5 pr-4 pl-3 text-xs font-medium text-white shadow-lg transition hover:bg-slate-800"
        title="打开 AI 抓取日志"
      >
        {running ? <IconSpinner size={14} /> : <IconSpark size={14} />}
        {running ? 'AI 抓取中…' : `AI 抓取结果（${job.product_count}）`}
      </button>
    )
  }

  return (
    <section className="fixed right-4 bottom-4 z-40 flex max-h-[60vh] w-[420px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
      <header className="flex items-center gap-2 border-b border-slate-100 px-3 py-2.5">
        <span className={running ? 'text-brand-500' : 'text-slate-400'}>
          {running ? <IconSpinner size={16} /> : <IconSpark size={16} />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-slate-800" title={job.title || job.url}>
            {title}
          </p>
          <p className="truncate text-[10px] text-slate-400" title={job.url}>
            {hostOf(job.url)}
          </p>
        </div>
        <StatusChip job={job} />
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          className="rounded p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          title="收起"
        >
          <IconChevronDown size={15} />
        </button>
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          className="rounded p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          title="收起（日志还在，点右下角胶囊可以再打开）"
        >
          <IconX size={15} />
        </button>
      </header>

      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto bg-slate-50/70 px-3 py-2">
        {job.log.length === 0 && <p className="py-4 text-center text-[11px] text-slate-400">等待启动…</p>}
        {job.log.map((line, index) => (
          <p
            key={`${index}-${line.at ?? ''}`}
            className={`font-mono text-[11px] leading-relaxed break-words ${LEVEL_STYLE[line.level] ?? 'text-slate-600'}`}
          >
            {levelPrefix(line.level)}
            {line.text}
          </p>
        ))}
        {job.status === 'done' && job.product_count === 0 && (
          <p className="py-2 text-[11px] text-amber-600">
            这个页面没抽到商品 —— 有的活动页要先进子页才有商品，换一个更靠里的 URL 试试。
          </p>
        )}
        {job.error && <p className="py-2 text-[11px] text-rose-600">{job.error}</p>}
      </div>

      <footer className="border-t border-slate-100 px-3 py-2">
        <div className="flex gap-2">
          <input
            value={chatText}
            onChange={(e) => setChatText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void sendChat()
            }}
            disabled={running || chatBusy}
            placeholder="接着跟 AI 说：少了哪几件 / 价格不对 / 补充字段…"
            className="min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-400"
          />
          <button
            type="button"
            onClick={() => void sendChat()}
            disabled={running || chatBusy || !chatText.trim()}
            className="shrink-0 rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
          >
            {chatBusy ? '…' : '发送'}
          </button>
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-400">
          <span>商品 {job.product_count} 件</span>
          {job.status === 'done' && <span className="text-emerald-600">已入库 · 左栏可回看</span>}
          {job.status === 'error' && <span className="text-rose-600">抓取失败</span>}
          {running && <span className="text-brand-500">抓取中，跑完再追问</span>}
        </div>
      </footer>
    </section>
  )
}

function StatusChip({ job }: { job: AgentJob }) {
  if (job.status === 'running') {
    return (
      <span className="flex shrink-0 items-center gap-1 rounded bg-brand-50 px-1.5 py-0.5 text-[10px] text-brand-600 ring-1 ring-brand-200 ring-inset">
        <IconSpinner size={10} />
        抓取中
      </span>
    )
  }
  if (job.status === 'error') {
    return (
      <span className="flex shrink-0 items-center gap-1 rounded bg-rose-50 px-1.5 py-0.5 text-[10px] text-rose-600 ring-1 ring-rose-200 ring-inset">
        <IconXCircle size={10} />
        失败
      </span>
    )
  }
  return (
    <span className="flex shrink-0 items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-600 ring-1 ring-emerald-200 ring-inset">
      <IconCheckCircle size={10} />
      完成
    </span>
  )
}
