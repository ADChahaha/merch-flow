import { useMemo, useState } from 'react'
import type { AgentJobSummary } from '../types'
import { formatTokens, hostOf } from '../lib/agent'
import { IconPlus, IconSearch, IconSpark, IconSpinner, IconTrash, IconXCircle } from './Icons'

type Props = {
  jobs: AgentJobSummary[]
  activeJobId: number | null
  onSelect: (job: AgentJobSummary) => void
  onDelete: (job: AgentJobSummary) => Promise<void> | void
  /** 新建会话（像 New chat：点了才出现输入框） */
  onNewSession: () => void
  /** 当前是不是停在新建会话页 */
  draft: boolean
  loading?: boolean
}

/** 左栏：新建会话入口 + AI 抓取记录（落库的），点开回看商品。 */
export function AgentJobList({
  jobs,
  activeJobId,
  onSelect,
  onDelete,
  onNewSession,
  draft,
  loading,
}: Props) {
  const [filter, setFilter] = useState('')
  const [pendingDelete, setPendingDelete] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)

  const visible = useMemo(() => {
    const text = filter.trim().toLowerCase()
    if (!text) return jobs
    return jobs.filter(
      (job) =>
        (job.title || '').toLowerCase().includes(text) || job.url.toLowerCase().includes(text),
    )
  }, [jobs, filter])

  const confirmDelete = async (job: AgentJobSummary) => {
    setDeleting(true)
    try {
      await onDelete(job)
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  return (
    <section className="flex h-full w-[260px] flex-col border-r border-slate-200 bg-white">
      <header className="flex items-center justify-between px-4 pt-4 pb-2">
        <h1 className="flex items-center gap-1.5 text-[15px] font-semibold text-slate-800">
          <IconSpark size={15} className="text-brand-500" />
          AI 抓取
        </h1>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] text-slate-500 tabular-nums">
          {jobs.length} 条
        </span>
      </header>

      <div className="px-3 pb-2">
        <button
          type="button"
          onClick={onNewSession}
          className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2.5 text-[13px] font-medium transition ${
            draft
              ? 'border-brand-300 bg-brand-50 text-brand-700 ring-1 ring-brand-200'
              : 'border-slate-200 bg-white text-slate-700 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
          }`}
        >
          <IconPlus size={15} />
          新建会话
          <span className="ml-auto text-[10px] font-normal text-slate-400">粘 URL 开始抓取</span>
        </button>
      </div>

      <div className="px-4 pb-2">
        <label className="flex items-center gap-2 rounded-md bg-slate-50 px-2.5 py-1.5 ring-1 ring-slate-200 focus-within:ring-brand-500">
          <IconSearch size={14} className="text-slate-400" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="搜索标题或 URL…"
            className="w-full bg-transparent text-xs outline-none placeholder:text-slate-400"
          />
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loading && <p className="px-3 py-4 text-xs text-slate-400">加载中…</p>}
        {!loading && jobs.length === 0 && (
          <p className="px-3 py-6 text-center text-xs leading-relaxed text-slate-400">
            还没有抓取记录
            <br />
            在中间粘一个 URL 开始
          </p>
        )}
        {!loading && jobs.length > 0 && visible.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-slate-400">没有匹配的记录</p>
        )}

        {visible.map((job) => {
          const active = job.id === activeJobId
          const pending = pendingDelete === job.id
          return (
            <div
              key={job.id}
              className={`group mb-0.5 flex items-center gap-1 rounded-md pr-1.5 transition ${
                active ? 'bg-brand-50 ring-1 ring-brand-100' : 'hover:bg-slate-50'
              }`}
            >
              <button
                type="button"
                onClick={() => onSelect(job)}
                className="min-w-0 flex-1 px-3 py-2 text-left"
                title={`${job.title || hostOf(job.url)}\n${job.url}`}
              >
                <span className="flex items-center gap-1.5">
                  <span
                    className={`min-w-0 flex-1 truncate text-[13px] ${active ? 'font-medium text-brand-700' : 'text-slate-700'}`}
                  >
                    {job.title || hostOf(job.url)}
                  </span>
                  {job.status === 'running' && (
                    <IconSpinner size={11} className="shrink-0 text-brand-400" />
                  )}
                  {job.status === 'error' && (
                    <IconXCircle size={11} className="shrink-0 text-rose-400" />
                  )}
                </span>
                <span className="mt-0.5 flex items-center gap-1 text-[11px] text-slate-400">
                  <span
                    className={`shrink-0 rounded px-1 py-px text-[9px] ring-1 ring-inset ${
                      job.kind === 'taobao_publish'
                        ? 'bg-orange-50 text-orange-600 ring-orange-200'
                        : 'bg-slate-50 text-slate-500 ring-slate-200'
                    }`}
                  >
                    {job.kind === 'taobao_publish' ? '上架' : '抓取'}
                  </span>
                  <span className="truncate">
                    {job.status === 'running'
                      ? '进行中…'
                      : job.status === 'error'
                        ? '失败'
                        : job.kind === 'taobao_publish'
                          ? '已完成（看截图/日志）'
                          : `${job.product_count} 件商品`}
                  </span>
                  {job.usage?.total ? (
                    <span
                      className="shrink-0 tabular-nums"
                      title="整个会话（含追问/续聊）累计消耗的 token"
                    >
                      · Token {formatTokens(job.usage.total)}
                    </span>
                  ) : null}
                </span>
              </button>

              {pending ? (
                <span className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    disabled={deleting}
                    onClick={() => void confirmDelete(job)}
                    className="rounded bg-rose-600 px-1.5 py-1 text-[10px] font-medium text-white transition hover:bg-rose-700 disabled:opacity-60"
                  >
                    {deleting ? '删除中' : '确认删除'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setPendingDelete(null)}
                    className="rounded border border-slate-200 px-1.5 py-1 text-[10px] text-slate-500 transition hover:text-slate-700"
                  >
                    取消
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  title="删除这条记录（含入库商品）"
                  onClick={() => setPendingDelete(job.id)}
                  className="shrink-0 rounded p-1 text-slate-300 opacity-0 transition group-hover:opacity-100 hover:bg-white hover:text-rose-600 focus:opacity-100"
                >
                  <IconTrash size={14} />
                </button>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
