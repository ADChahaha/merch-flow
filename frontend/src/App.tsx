import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { AgentJobList } from './components/AgentJobList'
import { AgentLogPanel } from './components/AgentLogPanel'
import { AgentPanel } from './components/AgentPanel'
import { IconRail } from './components/IconRail'
import { SourceFrame } from './components/SourceFrame'
import { ListingPage } from './components/listing/ListingPage'
import { SettingsPage } from './components/SettingsPage'
import { agentProductToOffer, agentSummaryOf } from './lib/agent'
import { cartItemFromOffer, type CartItem } from './lib/cart'
import type {
  AgentJob,
  AgentJobSummary,
  AgentProductInput,
  CategoryNode,
  FreightTemplate,
  Offer,
} from './types'

/**
 * AI 商品聚合 / 上架助手。
 * 唯一的数据入口是「给一个 URL」：deepseek harness 自主翻页抽商品（落库），
 * 左栏是抓取记录，中间是商品卡片，右下角是 agent 日志。上架吃上架清单里的卡片。
 */
export default function App() {
  const [view, setView] = useState<'products' | 'listing' | 'settings'>('products')
  const [cart, setCart] = useState<CartItem[]>([])
  const [categories, setCategories] = useState<CategoryNode[]>([])
  const [freights, setFreights] = useState<FreightTemplate[]>([])
  const [notice, setNotice] = useState<{ kind: 'error' | 'info'; text: string } | null>(null)

  // ---- AI 抓取 ----
  const [agentUrl, setAgentUrl] = useState('')
  /** 首轮自定义要求（可选） */
  const [agentExtra, setAgentExtra] = useState('')
  const [agentBusy, setAgentBusy] = useState(false)
  const [agentJobs, setAgentJobs] = useState<AgentJobSummary[]>([])
  const [jobsLoading, setJobsLoading] = useState(true)
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
  const [activeJob, setActiveJob] = useState<AgentJob | null>(null)
  const [logOpen, setLogOpen] = useState(false)
  /** 停在「新建会话」页：中间只显示 URL 输入 */
  const [draft, setDraft] = useState(false)
  /** 商品页左边的「原始页面」iframe 开关；默认值来自设置（默认打开），页内切换只影响本次会话 */
  const [sourceOpen, setSourceOpen] = useState(true)

  const toggleSource = () => setSourceOpen((prev) => !prev)

  useEffect(() => {
    void (async () => {
      try {
        const [categoryInfo, freightInfo, jobList, appSettings] = await Promise.all([
          api.listingCategories(),
          api.freightTemplates(),
          api.agentJobs(),
          api.settings(),
        ])
        setCategories(categoryInfo.tree)
        setFreights(freightInfo.templates)
        setSourceOpen(appSettings.ui.source_open)
        setAgentJobs(jobList)
        if (jobList[0]) {
          setActiveJobId(jobList[0].id)
          setActiveJob(await api.agentJob(jobList[0].id))
        } else {
          setDraft(true) // 一条记录都没有：直接停在新建会话页
        }
      } catch (error) {
        setNotice({ kind: 'error', text: `无法连接后端：${(error as Error).message}` })
      } finally {
        setJobsLoading(false)
      }
    })()
  }, [])

  const refreshAgentJobs = async () => {
    try {
      setAgentJobs(await api.agentJobs())
    } catch {
      // 列表刷新不是关键路径，失败就算了
    }
  }

  const startAgentJob = async () => {
    const url = agentUrl.trim()
    if (!url || agentBusy) return
    setAgentBusy(true)
    setNotice(null)
    try {
      const job = await api.startAgentJob(url, agentExtra.trim() || undefined)
      setActiveJob(job)
      setActiveJobId(job.id)
      setLogOpen(true)
      setAgentUrl('')
      setAgentExtra('')
      setDraft(false)
      setAgentJobs((prev) => [agentSummaryOf(job), ...prev.filter((item) => item.id !== job.id)])
    } catch (error) {
      setNotice({ kind: 'error', text: `AI 抓取启动失败：${(error as Error).message}` })
    } finally {
      setAgentBusy(false)
    }
  }

  const startNewSession = () => {
    setDraft(true)
    setActiveJobId(null)
    setActiveJob(null)
    setLogOpen(false)
  }

  const selectAgentJob = async (summary: AgentJobSummary, openLog = true) => {
    setDraft(false)
    setActiveJobId(summary.id)
    setActiveJob(null)
    setLogOpen(openLog)
    try {
      setActiveJob(await api.agentJob(summary.id))
    } catch (error) {
      setNotice({ kind: 'error', text: `读取抓取记录失败：${(error as Error).message}` })
    }
  }

  const deleteAgentJob = async (job: AgentJobSummary) => {
    try {
      await api.deleteAgentJob(job.id)
      const rest = agentJobs.filter((item) => item.id !== job.id)
      setAgentJobs(rest)
      if (activeJobId === job.id) {
        setActiveJobId(null)
        setActiveJob(null)
        setLogOpen(false)
        if (rest[0]) void selectAgentJob(rest[0], false)
        else setDraft(true)
      }
      setNotice({ kind: 'info', text: '已删除抓取记录' })
    } catch (error) {
      setNotice({ kind: 'error', text: `删除失败：${(error as Error).message}` })
    }
  }

  /** 手动补/删商品（人工对照原始页面） */
  const addAgentProduct = async (payload: AgentProductInput) => {
    if (activeJobId === null) return
    try {
      await api.addAgentJobProduct(activeJobId, payload)
      setActiveJob(await api.agentJob(activeJobId))
      setNotice({ kind: 'info', text: `已补充商品：${payload.name.slice(0, 20)}` })
    } catch (error) {
      setNotice({ kind: 'error', text: `添加失败：${(error as Error).message}` })
    }
  }

  const deleteAgentProduct = async (productId: number) => {
    if (activeJobId === null) return
    try {
      await api.deleteAgentJobProduct(activeJobId, productId)
      setActiveJob(await api.agentJob(activeJobId))
    } catch (error) {
      setNotice({ kind: 'error', text: `删除失败：${(error as Error).message}` })
    }
  }

  /** 追问：接着当前会话继续聊（同一 job，agent 带着上下文改 products.json） */
  /** 淘宝浏览器上架任务起来后，接到同一套 job 状态里（popup/左栏/轮询都能用） */
  const handlePublishJobStarted = (job: AgentJob) => {
    setActiveJob(job)
    setActiveJobId(job.id)
    setLogOpen(true)
    setDraft(false)
    setAgentJobs((prev) => [agentSummaryOf(job), ...prev.filter((item) => item.id !== job.id)])
  }

  const chatAgentJob = async (message: string) => {
    if (activeJobId === null) return
    try {
      const job = await api.chatAgentJob(activeJobId, message)
      setActiveJob(job)
      setLogOpen(true)
    } catch (error) {
      setNotice({ kind: 'error', text: `追问失败：${(error as Error).message}` })
    }
  }

  /** 全选：把当前任务的商品都加进上架清单；全取消：把它们都移出 */
  const addAllToCart = () => {
    if (agentOffers.length === 0) return
    setCart((prev) => {
      const have = new Set(prev.map((item) => item.id))
      const additions = agentOffers.filter((offer) => !have.has(offer.id)).map(cartItemFromOffer)
      return additions.length ? [...prev, ...additions] : prev
    })
  }

  const removeAllFromCart = () => {
    const ids = new Set(agentOffers.map((offer) => offer.id))
    setCart((prev) => prev.filter((item) => !ids.has(item.id)))
  }

  /** 任务跑着就每 1.5s 轮一次，日志和商品跟着进度长出来；结束后刷新左栏计数 */
  useEffect(() => {
    if (activeJobId === null) return
    if (activeJob?.status !== 'running') return
    let cancelled = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const job = await api.agentJob(activeJobId)
        if (cancelled) return
        setActiveJob(job)
        setAgentJobs((prev) => prev.map((item) => (item.id === job.id ? agentSummaryOf(job) : item)))
        if (job.status === 'running') {
          timer = window.setTimeout(tick, 1500)
        } else {
          void refreshAgentJobs()
        }
      } catch {
        if (!cancelled) timer = window.setTimeout(tick, 3000)
      }
    }
    timer = window.setTimeout(tick, 200)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJobId, activeJob?.status])

  /** 提示条过一会儿自动消失（错误多停一会儿），不用手动点关闭 */
  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), notice.kind === 'error' ? 5000 : 2500)
    return () => window.clearTimeout(timer)
  }, [notice])

  const agentOffers = useMemo(
    () => (activeJob ? activeJob.products.map((product) => agentProductToOffer(product, activeJob)) : []),
    [activeJob],
  )

  // ---- 上架清单：点商品图片加入 / 移除，上架清单内容就是上架的素材 ----
  const toggleCart = (offer: Offer) => {
    setCart((prev) => {
      const exists = prev.some((item) => item.id === offer.id)
      if (exists) return prev.filter((item) => item.id !== offer.id)
      setNotice({ kind: 'info', text: `已加入上架清单：${offer.listing.title.slice(0, 24)}` })
      return [...prev, cartItemFromOffer(offer)]
    })
  }

  return (
    <div className="flex h-full">
      <IconRail
        active={view}
        cartCount={cart.length}
        onSelect={(key) => {
          if (key === 'settings') setView('settings')
          else if (key === 'listing') setView('listing')
          else setView('products')
        }}
      />

      {view === 'products' && (
        <>
          <AgentJobList
            jobs={agentJobs}
            activeJobId={activeJobId}
            onSelect={(job) => void selectAgentJob(job)}
            onDelete={(job) => deleteAgentJob(job)}
            onNewSession={startNewSession}
            draft={draft}
            loading={jobsLoading}
          />
          <div className="flex min-h-0 min-w-0 flex-1">
            {!draft && activeJob && sourceOpen && (
              <SourceFrame url={activeJob.url} title={activeJob.title} />
            )}
            <AgentPanel
              draft={draft}
              agentUrl={agentUrl}
              onAgentUrlChange={setAgentUrl}
              agentExtra={agentExtra}
              onAgentExtraChange={setAgentExtra}
              onAgentStart={() => void startAgentJob()}
              onAddProduct={addAgentProduct}
              onDeleteProduct={deleteAgentProduct}
              agentBusy={agentBusy}
              agentJob={activeJob}
              agentOffers={agentOffers}
              cartIds={cart.map((item) => item.id)}
              onToggleCart={toggleCart}
              hasJobs={agentJobs.length > 0}
              sourceOpen={sourceOpen}
              onToggleSource={toggleSource}
              onAddAll={addAllToCart}
              onRemoveAll={removeAllFromCart}
            />
          </div>
        </>
      )}

      {view === 'listing' && (
        <ListingPage
          cart={cart}
          onRemoveFromCart={(id) => setCart((prev) => prev.filter((item) => item.id !== id))}
          onClearCart={() => setCart([])}
          categories={categories}
          freights={freights}
          onPublishJobStarted={handlePublishJobStarted}
        />
      )}

      {view === 'settings' && <SettingsPage />}

      <AgentLogPanel
        job={activeJob}
        open={logOpen}
        onOpenChange={setLogOpen}
        onChat={chatAgentJob}
      />

      {notice && (
        <div
          className={`fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg px-3 py-2 text-xs text-white shadow-lg ${
            notice.kind === 'error' ? 'bg-rose-600' : 'bg-slate-800'
          }`}
        >
          <span>{notice.text}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="ml-3 text-white/70 hover:text-white"
          >
            关闭
          </button>
        </div>
      )}
    </div>
  )
}
