import type { AgentJob, AgentJobSummary, AgentProduct, Offer } from '../types'
import { yen } from './format'

export function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

export function agentSummaryOf(job: AgentJob | AgentJobSummary): AgentJobSummary {
  return {
    id: job.id,
    url: job.url,
    kind: job.kind,
    title: job.title,
    status: job.status,
    error: job.error,
    pages_visited: job.pages_visited,
    product_count: job.product_count,
    created_at: job.created_at,
    finished_at: job.finished_at,
  }
}

/**
 * AI 抽的商品 → 现搜的 Offer 形状，直接复用 OfferCard 和上架清单。
 * 站点固定是「AI 抓取」，来源挂在 shop_name 上（列表里能看到抓的是哪个站）。
 */
export function agentProductToOffer(product: AgentProduct, job: AgentJob | AgentJobSummary): Offer {
  return {
    id: `agent:${job.id}:${product.id ?? product.name}`,
    site_key: 'agent',
    site: 'AI 抓取',
    url: product.source_url || job.url,
    listing: {
      title: product.name,
      price: product.price,
      price_display: product.price_text || (product.price !== null ? yen(product.price) : '—'),
      currency: 'JPY',
      reserve: { start: null, end: null, display: '' },
      images: product.image_urls,
      comment: product.detail,
    },
    condition_label: '',
    stock_status: '',
    release_date: null,
    release_text: product.date_text,
    shipping: '',
    shop_name: hostOf(job.url),
    price_original: null,
    is_buyable: true,
    not_buyable_reason: '',
  }
}
