import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import type { CartItem } from '../../lib/cart'
import type { AgentJob, JobFile, TaobaoPublishItem } from '../../types'
import { IconExternal, IconSpinner, IconUpload } from '../Icons'
import { Field, INPUT, Section } from './FormBits'

type Props = {
  cart: CartItem[]
  /** 上架清单区块（外壳渲染，放在表单最上面） */
  cartNode: React.ReactNode
  /** 任务起来后交给 App（右下角日志 popup 接管） */
  onJobStarted: (job: AgentJob) => void
}

type Draft = { price: string; stock: string }

/**
 * 淘宝上架（浏览器自动化）：开放平台 API 申请不到，改成让 dsh agent
 * 用 CDP 操作本机 Chrome 的卖家中心网页上架；这里只准备商品数据 + 盯进度。
 */
export function TaobaoForm({ cart, cartNode, onJobStarted }: Props) {
  const [categoryUrl, setCategoryUrl] = useState('')
  const [note, setNote] = useState('')
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [job, setJob] = useState<AgentJob | null>(null)
  const [shots, setShots] = useState<JobFile[]>([])
  const jobIdRef = useRef<number | null>(null)

  // 购物车变化时补/清理草稿（价格默认取清单里的，库存默认 100）
  useEffect(() => {
    setDrafts((prev) => {
      const next: Record<string, Draft> = {}
      for (const item of cart) {
        next[item.id] = prev[item.id] ?? {
          price: item.price === null ? '' : String(item.price),
          stock: '100',
        }
      }
      return next
    })
  }, [cart])

  // 任务跑着就轮询状态 + 截图（agent 每步截图，用户核对）
  useEffect(() => {
    const id = job?.id
    if (!id || job.status !== 'running') return
    let cancelled = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const [next, files] = await Promise.all([api.agentJob(id), api.agentJobFiles(id)])
        if (cancelled) return
        setJob(next)
        setShots(files.files)
        if (next.status === 'running') timer = window.setTimeout(tick, 2500)
      } catch {
        if (!cancelled) timer = window.setTimeout(tick, 4000)
      }
    }
    timer = window.setTimeout(tick, 800)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [job?.id, job?.status])

  const patchDraft = (id: string, next: Partial<Draft>) =>
    setDrafts((prev) => ({ ...prev, [id]: { ...(prev[id] ?? { price: '', stock: '100' }), ...next } }))

  const submit = async () => {
    if (cart.length === 0) return
    setError(null)
    setBusy(true)
    try {
      const items: TaobaoPublishItem[] = cart.map((item) => {
        const draft = drafts[item.id]
        const price = draft?.price ? Number(draft.price) : null
        const stock = draft?.stock ? Number(draft.stock) : 100
        return {
          name: item.title,
          price: price !== null && Number.isFinite(price) ? price : null,
          stock: Number.isFinite(stock) ? stock : 100,
          images: item.images,
          detail: item.comment || '',
        }
      })
      const created = await api.publishTaobaoBrowser({
        items,
        ...(categoryUrl.trim() ? { category_url: categoryUrl.trim() } : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
      })
      jobIdRef.current = created.id
      setJob(created)
      setShots([])
      onJobStarted(created)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const latest = shots[0]

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      {cartNode}

      <Section
        index={1}
        title="上架方式：浏览器自动化"
        hint="不依赖开放平台 API，agent 直接操作卖家中心网页（CDP 挂接你本机的 Chrome）"
      >
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[11px] leading-relaxed text-amber-800">
          需要本机 Chrome：任务开始后 agent 会自动用专用 profile 启动带调试端口 9222 的
          Chrome（首次要你在窗口里扫码登录卖家中心）。每步操作都会截图给你核对，提交前会停下来等你确认；
          遇到滑块/短信/人脸验证会停下提示真人处理。
        </div>
        <div className="mt-4 grid grid-cols-2 gap-5">
          <Field label="类目 URL 或 catId">
            <input
              value={categoryUrl}
              onChange={(e) => setCategoryUrl(e.target.value.trim())}
              placeholder="可选；不填让 agent 自己找（https://item.upload.taobao.com/sell/v2/publish.htm?catId=…）"
              className={INPUT}
            />
          </Field>
          <Field label="给 agent 的备注">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="可选，例如：价格要含运费 / 先只上传草稿"
              className={INPUT}
            />
          </Field>
        </div>
      </Section>

      <Section index={2} title="待上架商品（来自上架清单）" hint="价格/库存可以直接改；名称和图片按清单里的来">
        {cart.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-200 px-3 py-5 text-center text-[12px] text-slate-400">
            上架清单是空的。去「商品」里把 AI 抓到的商品加进来。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-separate border-spacing-0 text-[12px]">
              <thead>
                <tr className="text-left text-slate-500">
                  {['商品', '价格（元）', '库存', '图片'].map((head) => (
                    <th key={head} className="border-b border-slate-200 pb-1.5 font-normal">
                      {head}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cart.map((item) => {
                  const draft = drafts[item.id] ?? { price: '', stock: '100' }
                  return (
                    <tr key={item.id}>
                      <td className="border-b border-slate-100 py-2 pr-3">
                        <p className="max-w-[420px] truncate text-slate-700" title={item.title}>
                          {item.title}
                        </p>
                      </td>
                      <td className="w-28 border-b border-slate-100 py-2 pr-3">
                        <input
                          value={draft.price}
                          onChange={(e) => patchDraft(item.id, { price: e.target.value.replace(/[^\d.]/g, '') })}
                          placeholder="待定"
                          className={INPUT}
                        />
                      </td>
                      <td className="w-24 border-b border-slate-100 py-2 pr-3">
                        <input
                          value={draft.stock}
                          onChange={(e) => patchDraft(item.id, { stock: e.target.value.replace(/\D/g, '') })}
                          className={INPUT}
                        />
                      </td>
                      <td className="border-b border-slate-100 py-2">
                        <span className="text-slate-400">{item.images.length} 张</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-[12px] text-rose-600">
          {error}
        </div>
      )}

      {job && (
        <Section index={3} title="任务进度" hint="agent 的每一步都会截图；日志在右下角">
          <div className="flex flex-wrap items-center gap-3 text-[12px] text-slate-600">
            <span className="flex items-center gap-1.5">
              {job.status === 'running' && <IconSpinner size={13} className="text-brand-500" />}
              任务 #{job.id} ·{' '}
              {job.status === 'running' ? '进行中' : job.status === 'done' ? '已结束' : '失败'}
            </span>
            {job.status === 'error' && <span className="text-rose-600">{job.error}</span>}
            <a
              href={`/api/agent/jobs/${job.id}/files`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-0.5 text-brand-600 hover:underline"
            >
              <IconExternal size={12} /> 截图列表
            </a>
          </div>
          {latest && (
            <a
              href={latest.url}
              target="_blank"
              rel="noreferrer"
              className="mt-3 block overflow-hidden rounded-lg border border-slate-200"
              title={latest.name}
            >
              <img src={latest.url} alt={latest.name} className="max-h-[320px] w-full object-contain" />
            </a>
          )}
        </Section>
      )}

      <footer className="flex items-center gap-2">
        <button
          type="button"
          disabled={busy || cart.length === 0 || job?.status === 'running'}
          onClick={() => void submit()}
          className="flex items-center gap-1.5 rounded-md bg-[#ff5000] px-5 py-2 text-[13px] font-medium text-white transition hover:bg-[#e64800] disabled:opacity-50"
        >
          {busy ? <IconSpinner size={14} /> : <IconUpload size={14} />}
          {busy ? '启动中…' : job?.status === 'running' ? '任务进行中…' : '浏览器自动上架'}
        </button>
        <span className="text-[11px] text-slate-400">
          上架清单不会自动清空；第二个商品等这次跑完再发（单日建议 ≤2 个）。
        </span>
      </footer>
    </div>
  )
}
