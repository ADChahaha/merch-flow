// 与 backend/app/schemas.py 一一对应。

export type ReserveWindow = {
  start: string | null
  end: string | null
  display: string
}

/** 展示/上架内容最小单位：名字 / 价格 / 可预约时间 / 图片 / 评论 */
export type ListingContent = {
  title: string
  price: number | null
  price_display: string
  currency: string
  reserve: ReserveWindow
  images: string[]
  comment: string
}

/** AI 抓出来的商品映射成的卡片数据（购物车/上架直接吃它） */
export type Offer = {
  id: string
  site: string
  site_key: string
  url: string
  listing: ListingContent
  condition_label: string
  stock_status: string
  release_date: string | null
  /** 发售日 / 举办日期**原文**，有就显示这个 */
  release_text: string
  shipping: string
  shop_name: string
  price_original: number | null
  is_buyable: boolean
  not_buyable_reason: string
}

/** AI 抓取（deepseek harness）：一条抽出来的商品 */
export type AgentProduct = {
  id: number | null
  name: string
  price: number | null
  price_text: string
  date_text: string
  detail: string
  image_urls: string[]
  source_url: string
}

/** 手动添加商品（人工补 AI 的漏） */
export type AgentProductInput = {
  name: string
  price: number | null
  price_text: string
  date_text: string
  detail: string
  image_urls: string[]
  source_url: string
}

export type AgentLogLine = {
  level: 'info' | 'error' | string
  text: string
  at?: string
}

export type AgentJobStatus = 'running' | 'done' | 'error'

/** 左栏 AI 记录（列表轻量版，不含日志/商品） */
export type AgentJobSummary = {
  id: number
  url: string
  /** scrape = URL 抓商品；taobao_publish = 浏览器自动上架 */
  kind: 'scrape' | 'taobao_publish' | string
  title: string
  status: AgentJobStatus
  error: string
  pages_visited: number
  product_count: number
  created_at: string | null
  finished_at: string | null
}

export type AgentJob = AgentJobSummary & {
  log: AgentLogLine[]
  products: AgentProduct[]
}

/** 设置页：密钥只给状态和掩码，明文只在保存时上行 */
export type AgentSettings = {
  has_key: boolean
  key_hint: string
  model: string
  /** off / low / high / max */
  reasoning: string
}

export type BilibiliSettings = {
  has_token: boolean
  token_hint: string
  client_id: string
  has_client_secret: boolean
  secret_hint: string
}

export type UiSettings = {
  /** 商品页默认是否打开「原始页面」iframe（设置里配，默认打开） */
  source_open: boolean
}

export type AppSettings = {
  agent: AgentSettings
  bilibili: BilibiliSettings
  ui: UiSettings
}

export type SettingsUpdate = {
  deepseek_api_key?: string
  agent_model?: string
  agent_reasoning?: string
  bilibili_access_token?: string
  bilibili_client_id?: string
  bilibili_client_secret?: string
  ui_source_open?: boolean
}

/** 上架：类目 / 运费模板 */
export type CategoryNode = { id: number; name: string; children: CategoryNode[] }
export type FreightTemplate = { freight_id: number; name: string }

export type ProductAddResponse = {
  ok: boolean
  endpoint: string
  request: Record<string, unknown>
  warnings: string[]
  note: string
}

/** 淘宝上架（浏览器自动化）：商品数据 + 可选类目 URL/备注 */
export type TaobaoPublishItem = {
  name: string
  price: number | null
  stock: number
  images: string[]
  detail: string
}

export type TaobaoPublishJobRequest = {
  items: TaobaoPublishItem[]
  category_url?: string
  note?: string
}

export type JobFile = {
  name: string
  url: string
  mtime: number
}
