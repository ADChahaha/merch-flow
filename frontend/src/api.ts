import type {
  AgentJob,
  AgentJobSummary,
  AppSettings,
  CategoryNode,
  FreightTemplate,
  ProductAddResponse,
  SettingsUpdate,
  AgentProduct,
  AgentProductInput,
  JobFile,
  TaobaoPublishJobRequest,
} from './types'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const text = await res.text()
  const body = text ? JSON.parse(text) : null
  if (!res.ok) {
    const detail = body?.detail ?? res.statusText
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return body as T
}

export const api = {
  /** AI 抓取：给一个 URL 起任务；prompt 是首轮自定义要求（拼在默认提示词后） */
  startAgentJob: (url: string, prompt?: string) =>
    request<AgentJob>('/api/agent/jobs', {
      method: 'POST',
      body: JSON.stringify({ url, ...(prompt ? { prompt } : {}) }),
    }),

  /** 左栏 AI 记录（不含日志/商品） */
  agentJobs: () => request<AgentJobSummary[]>('/api/agent/jobs'),

  /** 任务详情：跑着的时候轮询它拿实时日志和商品 */
  agentJob: (id: number) => request<AgentJob>(`/api/agent/jobs/${id}`),

  /** 手动补一条商品（对照原始页面发现 AI 漏了时用） */
  addAgentJobProduct: (id: number, payload: AgentProductInput) =>
    request<AgentProduct>(`/api/agent/jobs/${id}/products`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteAgentJobProduct: (id: number, productId: number) =>
    request<{ ok: boolean }>(`/api/agent/jobs/${id}/products/${productId}`, { method: 'DELETE' }),

  /** 追问：接着这个任务原来的会话继续聊（自由输入，agent 带着上下文改 products.json） */
  chatAgentJob: (id: number, message: string) =>
    request<AgentJob>(`/api/agent/jobs/${id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  deleteAgentJob: (id: number) =>
    request<{ ok: boolean; job_id: number }>(`/api/agent/jobs/${id}`, { method: 'DELETE' }),

  /** 全局设置：AI 抓取（DeepSeek）+ B 站上架凭证 */
  settings: () => request<AppSettings>('/api/settings'),

  /** 保存设置：写入 backend/.env 并即时生效（字段省略 = 不改，空串 = 清除） */
  saveSettings: (payload: SettingsUpdate) =>
    request<AppSettings>('/api/settings', { method: 'PUT', body: JSON.stringify(payload) }),

  /** 类目 / 运费模板（示例数据，真实 ID 走 B 站接口） */
  listingCategories: () =>
    request<{ tree: CategoryNode[]; note: string }>('/api/listings/categories'),

  freightTemplates: () =>
    request<{ templates: FreightTemplate[]; note: string }>('/api/listings/freight-templates'),

  /**
   * B 站上架：请求体按 product_add 契约组装。
   * 后端只做校验 + 组装（不代持 Access-Token），返回可直接发给 B 站的 request。
   */
  createBilibiliListing: (payload: Record<string, unknown>) =>
    request<ProductAddResponse>('/api/listings/bilibili', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /**
   * 淘宝上架（浏览器自动化）：起一个 agent 任务，
   * 它用 CDP 操作本机 Chrome 的卖家中心网页（开放平台 API 申请不到）。
   */
  publishTaobaoBrowser: (payload: TaobaoPublishJobRequest) =>
    request<AgentJob>('/api/listings/taobao/browser', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** 任务目录里的截图（agent 每步截图，核对用） */
  agentJobFiles: (id: number) => request<{ files: JobFile[] }>(`/api/agent/jobs/${id}/files`),
}

export { ApiError }
