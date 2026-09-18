import { useState } from 'react'
import type { AgentJob, AgentProductInput, Offer } from '../types'
import { hostOf } from '../lib/agent'
import { IconCheckCircle, IconPlus, IconSpark, IconSpinner, IconTrash, IconXCircle } from './Icons'
import { OfferCard } from './OfferCard'

type Props = {
  /** 停在「新建会话」页（只显示一个 URL 输入） */
  draft: boolean
  agentUrl: string
  onAgentUrlChange: (value: string) => void
  /** 首轮自定义要求（可选，拼在默认提示词后） */
  agentExtra: string
  onAgentExtraChange: (value: string) => void
  onAgentStart: () => void
  agentBusy: boolean
  /** 手动加/删商品 */
  onAddProduct: (payload: AgentProductInput) => Promise<void>
  onDeleteProduct: (productId: number) => Promise<void>
  /** 当前查看的任务（跑着的时候由 App 轮询刷新） */
  agentJob: AgentJob | null
  /** 当前任务的商品（已映射成卡片数据） */
  agentOffers: Offer[]
  cartIds: string[]
  onToggleCart: (offer: Offer) => void
  /** 左栏有没有历史记录（决定空状态的文案） */
  hasJobs: boolean
  /** 左侧「原始页面」iframe 开关 */
  sourceOpen: boolean
  onToggleSource: () => void
  /** 上架清单批量操作（作用于当前任务的商品） */
  onAddAll: () => void
  onRemoveAll: () => void
}

/**
 * 中间面板：AI 抓取的唯一入口和结果区。
 * 粘一个 URL → deepseek harness 自己决定怎么翻怎么抽 → 商品按卡片列在这里。
 */
export function AgentPanel({
  draft,
  agentUrl,
  onAgentUrlChange,
  agentExtra,
  onAgentExtraChange,
  onAgentStart,
  agentBusy,
  onAddProduct,
  onDeleteProduct,
  agentJob,
  agentOffers,
  cartIds,
  onToggleCart,
  hasJobs,
  sourceOpen,
  onToggleSource,
  onAddAll,
  onRemoveAll,
}: Props) {
  const running = agentJob?.status === 'running'
  const inCartCount = agentOffers.filter((offer) => cartIds.includes(offer.id)).length

  // 手动添加商品
  const [addOpen, setAddOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    name: '',
    price: '',
    priceText: '',
    dateText: '',
    detail: '',
    images: '',
    sourceUrl: '',
  })
  const patchForm = (next: Partial<typeof form>) => setForm((prev) => ({ ...prev, ...next }))

  const submitAdd = async () => {
    if (!form.name.trim() || saving) return
    setSaving(true)
    try {
      await onAddProduct({
        name: form.name.trim(),
        price: form.price ? Number(form.price) : null,
        price_text: form.priceText.trim(),
        date_text: form.dateText.trim(),
        detail: form.detail.trim(),
        image_urls: form.images
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        source_url: form.sourceUrl.trim(),
      })
      setForm({ name: '', price: '', priceText: '', dateText: '', detail: '', images: '', sourceUrl: '' })
      setAddOpen(false)
    } finally {
      setSaving(false)
    }
  }

  if (draft) {
    return (
      <section className="flex h-full min-w-0 flex-1 items-center justify-center bg-slate-50 px-6">
        <div className="w-full max-w-2xl">
          <h2 className="text-[20px] font-semibold text-slate-800">新建抓取会话</h2>
          <p className="mt-1 text-[12px] leading-relaxed text-slate-400">
            粘一个商品页 / 活动页 URL。deepseek harness 会自己去翻页、判断怎么抽取，商品实时出现在这里。
          </p>
          <div className="mt-5 flex gap-2">
            <label className="flex flex-1 items-center gap-2 rounded-lg bg-white px-4 py-3 ring-1 ring-slate-200 focus-within:ring-brand-500">
              <IconSpark size={16} className="shrink-0 text-brand-500" />
              <input
                autoFocus
                value={agentUrl}
                onChange={(e) => onAgentUrlChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onAgentStart()
                }}
                placeholder="https://…（商品页 / 活动页 / 任意页面）"
                spellCheck={false}
                className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
              />
            </label>
            <button
              type="button"
              onClick={onAgentStart}
              disabled={agentBusy || !agentUrl.trim()}
              className="flex shrink-0 items-center gap-1.5 rounded-lg bg-brand-600 px-5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
            >
              {agentBusy ? <IconSpinner size={14} /> : <IconSpark size={14} />}
              {agentBusy ? '启动中…' : '开始抓取'}
            </button>
          </div>
          <textarea
            value={agentExtra}
            onChange={(e) => onAgentExtraChange(e.target.value)}
            rows={3}
            placeholder="补充要求（可选）：比如「只抓 Blu-ray」「价格换算成人民币」「忽略中古」… 会拼在默认提示词后面"
            className="mt-3 w-full resize-none rounded-lg border border-slate-200 bg-white px-4 py-3 text-[12px] leading-relaxed text-slate-700 outline-none placeholder:text-slate-400 focus:border-brand-500"
          />
          <p className="mt-3 text-[11px] text-slate-400">
            想回看以前的抓取，点左边列表里的记录。
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="flex h-full min-w-0 flex-1 flex-col bg-slate-50">
      <header className="flex min-h-[42px] items-center gap-2 px-5 pt-4 pb-2">
        <h2 className="min-w-0 truncate text-[17px] font-semibold text-slate-800">
          {agentJob ? agentJob.title || hostOf(agentJob.url) : 'AI 商品抓取'}
        </h2>
        {agentJob && <AgentStatusChip job={agentJob} />}
        {agentJob && (
          <button
            type="button"
            onClick={onToggleSource}
            title={sourceOpen ? '收起原始页面' : '对照原始页面核对'}
            className={`ml-auto hidden shrink-0 rounded-md border px-2.5 py-1.5 text-[11px] transition lg:block ${
              sourceOpen
                ? 'border-brand-200 bg-brand-50 text-brand-700'
                : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300'
            }`}
          >
            原始页面 {sourceOpen ? '开' : '关'}
          </button>
        )}
      </header>

      {agentJob && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 pb-1 text-[11px] text-slate-400">
          <span className="flex items-center gap-1 text-brand-500">
            <IconSpark size={12} />
            deepseek harness 自主抓取
          </span>
          <a
            href={agentJob.url}
            target="_blank"
            rel="noreferrer"
            className="max-w-[460px] truncate underline decoration-slate-300 underline-offset-2 hover:text-slate-600"
            title={agentJob.url}
          >
            {agentJob.url}
          </a>
          <span>商品随进度写入</span>
        </div>
      )}

      {agentJob && agentOffers.length > 0 && (
        <div className="flex items-center gap-2 px-5 pt-1.5 pb-1 text-[11px] text-slate-400">
          <span>
            共 {agentOffers.length} 件 · 已加入上架清单 {inCartCount}
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              onClick={onAddAll}
              disabled={running || inCartCount === agentOffers.length}
              className="rounded-md border border-brand-200 bg-white px-2.5 py-1 text-[11px] text-brand-700 transition hover:bg-brand-50 disabled:opacity-40"
            >
              全选加入清单
            </button>
            <button
              type="button"
              onClick={onRemoveAll}
              disabled={running || inCartCount === 0}
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-500 transition hover:border-slate-300 hover:text-slate-700 disabled:opacity-40"
            >
              全取消
            </button>
            <button
              type="button"
              onClick={() => setAddOpen((prev) => !prev)}
              disabled={running}
              className={`flex items-center gap-0.5 rounded-md border px-2.5 py-1 text-[11px] transition disabled:opacity-40 ${
                addOpen
                  ? 'border-brand-300 bg-brand-50 text-brand-700'
                  : 'border-slate-200 bg-white text-slate-500 hover:border-brand-200 hover:text-brand-700'
              }`}
            >
              <IconPlus size={11} />
              手动加商品
            </button>
          </div>
        </div>
      )}

      {agentJob && addOpen && (
        <div className="mx-5 mb-2 rounded-lg border border-brand-200 bg-white p-3">
          <div className="grid grid-cols-2 gap-2">
            <input
              value={form.name}
              onChange={(e) => patchForm({ name: e.target.value })}
              placeholder="商品名 *（原文，别翻译）"
              className="col-span-2 rounded-md border border-slate-200 px-2.5 py-1.5 text-[12px] outline-none focus:border-brand-500"
            />
            <input
              value={form.price}
              onChange={(e) => patchForm({ price: e.target.value.replace(/\D/g, '') })}
              placeholder="价格（数字，可选）"
              className="rounded-md border border-slate-200 px-2.5 py-1.5 text-[12px] outline-none focus:border-brand-500"
            />
            <input
              value={form.priceText}
              onChange={(e) => patchForm({ priceText: e.target.value })}
              placeholder="价格原文（可选，如 550円(税込)）"
              className="rounded-md border border-slate-200 px-2.5 py-1.5 text-[12px] outline-none focus:border-brand-500"
            />
            <input
              value={form.dateText}
              onChange={(e) => patchForm({ dateText: e.target.value })}
              placeholder="发售日/日期原文（可选）"
              className="rounded-md border border-slate-200 px-2.5 py-1.5 text-[12px] outline-none focus:border-brand-500"
            />
            <input
              value={form.sourceUrl}
              onChange={(e) => patchForm({ sourceUrl: e.target.value })}
              placeholder="来源 URL（可选，不填用任务入口 URL）"
              className="rounded-md border border-slate-200 px-2.5 py-1.5 text-[12px] outline-none focus:border-brand-500"
            />
            <textarea
              value={form.detail}
              onChange={(e) => patchForm({ detail: e.target.value })}
              rows={2}
              placeholder="详情（可选：规格/备注/特典…）"
              className="col-span-2 resize-none rounded-md border border-slate-200 px-2.5 py-1.5 text-[12px] outline-none focus:border-brand-500"
            />
            <textarea
              value={form.images}
              onChange={(e) => patchForm({ images: e.target.value })}
              rows={2}
              placeholder="图片 URL，一行一个（可选）"
              className="col-span-2 resize-none rounded-md border border-slate-200 px-2.5 py-1.5 text-[12px] outline-none focus:border-brand-500"
            />
          </div>
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              className="rounded-md border border-slate-200 px-2.5 py-1.5 text-[11px] text-slate-500 transition hover:text-slate-700"
            >
              取消
            </button>
            <button
              type="button"
              disabled={!form.name.trim() || saving}
              onClick={() => void submitAdd()}
              className="rounded-md bg-brand-600 px-3 py-1.5 text-[11px] font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
            >
              {saving ? '保存中…' : '保存商品'}
            </button>
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
        {!agentJob && (
          <p className="mt-10 text-center text-sm leading-relaxed text-slate-400">
            {hasJobs
              ? '左栏选一条抓取记录回看结果，或在上面粘一个新 URL 开始抓取'
              : '把商品页 / 活动页 URL 粘到上面，AI 会自己递归翻页找出所有商品'}
          </p>
        )}
        {agentJob && running && agentOffers.length === 0 && (
          <p className="mt-10 flex items-center justify-center gap-2 text-center text-sm text-brand-500">
            <IconSpinner size={14} />
            AI 正在递归抓取，商品会随进度陆续出现…
          </p>
        )}
        {agentJob && !running && agentOffers.length === 0 && (
          <p className="mt-10 text-center text-sm leading-relaxed text-rose-500">
            {agentJob.error || (agentJob.kind === 'taobao_publish' ? '这是浏览器上架任务：日志/截图看右下角 popup 和「上架」页' : '没有抽到商品')}
          </p>
        )}
        {agentJob
          ? agentJob.products.map((product, index) => {
              const offer = agentOffers[index]
              if (!offer) return null
              return (
                <div key={offer.id} className="group/item relative">
                  <OfferCard
                    offer={offer}
                    inCart={cartIds.includes(offer.id)}
                    onToggleCart={onToggleCart}
                  />
                  {!running && product.id !== null && (
                    <button
                      type="button"
                      title="删除这条商品"
                      onClick={() => void onDeleteProduct(product.id as number)}
                      className="absolute top-2 right-2 hidden rounded-md border border-slate-200 bg-white/95 p-1 text-slate-400 shadow-sm transition hover:border-rose-200 hover:text-rose-600 group-hover/item:block"
                    >
                      <IconTrash size={13} />
                    </button>
                  )}
                </div>
              )
            })
          : null}
      </div>
    </section>
  )
}

function AgentStatusChip({ job }: { job: AgentJob }) {
  if (job.status === 'running') {
    return (
      <span className="flex shrink-0 items-center gap-1 text-[11px] font-normal text-brand-500">
        <IconSpinner size={12} />
        AI 抓取中…
      </span>
    )
  }
  if (job.status === 'error') {
    return (
      <span className="flex shrink-0 items-center gap-1 rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-normal text-rose-600 ring-1 ring-rose-200 ring-inset">
        <IconXCircle size={11} />
        抓取失败
      </span>
    )
  }
  return (
    <span className="flex shrink-0 items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-normal text-emerald-600 ring-1 ring-emerald-200 ring-inset">
      <IconCheckCircle size={11} />
      {job.product_count} 件商品
    </span>
  )
}
