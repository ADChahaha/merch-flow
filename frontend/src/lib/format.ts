export function yen(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `￥${value.toLocaleString('ja-JP')}`
}

export function dateLabel(value: string | null | undefined): string {
  if (!value) return ''
  return value.replaceAll('-', '/')
}

export function shortMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return ''
  return `￥${value.toLocaleString('ja-JP')}`
}

/** 站点配色 */
export const SITE_COLORS: Record<string, { bg: string; text: string; ring: string }> = {
  agent: { bg: 'bg-violet-100', text: 'text-violet-700', ring: 'ring-violet-200' },
}

export function siteColor(siteKey: string) {
  return SITE_COLORS[siteKey] ?? { bg: 'bg-slate-100', text: 'text-slate-700', ring: 'ring-slate-200' }
}

export function stockStyle(status: string): string {
  if (status.includes('予約')) return 'bg-violet-50 text-violet-700 ring-violet-200'
  if (status.includes('マケプレ')) return 'bg-amber-50 text-amber-700 ring-amber-200'
  if (status.includes('在庫')) return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  return 'bg-slate-100 text-slate-500 ring-slate-200'
}

export function conditionStyle(label: string): string {
  return label === '中古'
    ? 'bg-amber-50 text-amber-700 ring-amber-200'
    : 'bg-teal-50 text-teal-700 ring-teal-200'
}
