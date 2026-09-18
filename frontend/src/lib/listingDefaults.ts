import type { CartItem } from '../lib/cart'
import { primaryImage } from '../lib/cart'

/**
 * 上架清单 → B 站商品发布请求 的默认填充。
 *
 * 规则（按需求）：
 *   * 多个商品：**所有商品都填进 SKU**，其它能填的字段也一起填好；
 *     主图 = 第一个商品的图，轮播图 / 详情图 = 前面那些商品的图（可删可插）。
 *   * 单个商品：主图和轮播图都是这张图，能填的都填上。
 *
 * 硬限制来自 B 站文档：轮播图最多 5 张、图片描述最多 50 张、标题 6-60 字。
 */

export const MAX_CAROUSEL = 5
export const MAX_DESCRIPTION = 50
export const NAME_MIN = 6
export const NAME_MAX = 60

export type SkuDraft = {
  key: string
  name: string
  priceYuan: string
  stock: string
  reserveStart: string
  saleStart: string
  limitPerBuyer: string
  image: string
  itemId: string
}

export type ListingForm = {
  name: string
  categoryLeafId: number | null
  summary: string
  tags: string[]
  mainImage: string
  carousel: string[]
  descriptionImages: string[]
  reserveStart: string
  saleStart: string
  limitPerBuyer: string
  skus: SkuDraft[]
  shippingNote: string
  purchaseNote: string
  freightId: number | null
  deliveryDelayDay: string
  returnSupported: boolean
}

export const DEFAULT_SHIPPING_NOTE =
  '预计在开售后 30 天内按订单顺序发货，具体以官方公告为准。'
export const DEFAULT_PURCHASE_NOTE = [
  '1. 本商品为预售商品，拍下后不可随意退款；',
  '2. 商品可能因生产原因出现轻微差异，介意请谨慎购买；',
  '3. 如有问题请联系官方客服。',
].join('\n')

export function pad(value: string, min = NAME_MIN, suffix = '（预售）'): string {
  return value.length >= min ? value : `${value}${suffix}`
}

function formatDateTime(value: Date): string {
  const pad2 = (n: number) => String(n).padStart(2, '0')
  return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())} ${pad2(value.getHours())}:${pad2(value.getMinutes())}`
}

/** 收集上架清单里所有图片（按商品顺序，去重），第一张 = 第一个商品的主图 */
export function collectImages(items: CartItem[], limit: number): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const item of items) {
    for (const image of item.images) {
      if (!image || seen.has(image)) continue
      seen.add(image)
      out.push(image)
      if (out.length >= limit) return out
    }
  }
  return out
}

export function deriveTags(items: CartItem[]): string[] {
  const tags: string[] = []
  if (items.some((i) => i.stockStatus.includes('予約'))) tags.push('预售')
  else tags.push('现货')
  if (items.some((i) => i.conditionLabel === '新品')) tags.push('新品')
  if (items.some((i) => i.conditionLabel === '中古')) tags.push('二手')
  if (items.some((i) => i.stockStatus.includes('マケプレ'))) tags.push('限量')
  return [...new Set(tags)]
}

function skuName(item: CartItem, index: number): string {
  const title = item.title.replace(/\s+/g, ' ').trim()
  const short = title.length > 24 ? `${title.slice(0, 24)}…` : title
  return short || `款式${index + 1}`
}

function saleStartOf(items: CartItem[]): string {
  const dates = items
    .map((item) => item.reserveEnd || item.releaseDate)
    .filter((d): d is string => !!d)
    .sort()
  if (dates[0]) return `${dates[0]} 19:30`
  const fallback = new Date()
  fallback.setDate(fallback.getDate() + 7)
  return formatDateTime(fallback)
}

/** 用上架清单内容生成一份填好的上架表单 */
export function buildForm(
  items: CartItem[],
  options: { categoryLeafId: number | null; freightId: number | null },
): ListingForm {
  const now = new Date()
  const reserveStart = formatDateTime(now)
  const saleStart = saleStartOf(items)
  const limit = '2'

  const images = collectImages(items, MAX_DESCRIPTION)
  const mainImage = images[0] ?? ''
  const carousel = items.length <= 1 ? images.slice(0, 1) : images.slice(0, MAX_CAROUSEL)

  const name =
    items.length <= 1
      ? pad(items[0]?.title?.trim() || '未命名商品')
      : pad(`${items[0].title.trim()} 等 ${items.length} 件`)
  const summary = items
    .map((item) => item.title.trim())
    .join(' / ')
    .slice(0, 200)

  return {
    name: name.slice(0, NAME_MAX),
    categoryLeafId: options.categoryLeafId,
    summary,
    tags: deriveTags(items),
    mainImage,
    carousel,
    descriptionImages: items.length <= 1 ? images.slice(0, 1) : images,
    reserveStart,
    saleStart,
    limitPerBuyer: limit,
    skus: items.map((item, index) => ({
      key: `${item.id}-${index}`,
      itemId: item.id,
      name: skuName(item, index),
      priceYuan: item.price === null ? '' : String(item.price),
      stock: '100',
      reserveStart,
      saleStart,
      limitPerBuyer: limit,
      image: primaryImage(item),
    })),
    shippingNote: DEFAULT_SHIPPING_NOTE,
    purchaseNote: DEFAULT_PURCHASE_NOTE,
    freightId: options.freightId,
    deliveryDelayDay: '30',
    returnSupported: true,
  }
}

/** 表单 → B 站 product_add 请求体（这里就是后端 /api/listings 的入参） */
export function toProductAddRequest(form: ListingForm, commit: boolean) {
  const specName = '款式'
  const values = form.skus.map((sku) => ({ value_name: sku.name }))
  const carousel = form.carousel.filter(Boolean)
  // 接口硬限制：pic 最多 5 张。超出的自动挪到详情图，别丢
  const pic = carousel.slice(0, MAX_CAROUSEL)
  const overflow = carousel.slice(MAX_CAROUSEL)
  const description = [...overflow, ...form.descriptionImages.filter((i) => !pic.includes(i))].slice(
    0,
    MAX_DESCRIPTION,
  )

  return {
    category_leaf_id: form.categoryLeafId ?? 2301,
    name: form.name.slice(0, NAME_MAX),
    pic: pic.join('\n'),
    description: description.join('\n'),
    text_description: [form.summary, form.shippingNote, form.purchaseNote]
      .filter(Boolean)
      .join('\n')
      .slice(0, 500),
    freight_id: form.freightId ?? 1004258,
    delivery_delay_day: form.deliveryDelayDay ? Number(form.deliveryDelayDay) : undefined,
    presell_type: 0,
    commit,
    operate_status: 0,
    limit_per_buyer: Number(form.limitPerBuyer || 0),
    after_sale_service: {
      supply_day_return_selector: form.returnSupported ? '7-1' : '7-0',
    },
    spec_info: { spec_values: [{ property_name: specName, values }] },
    spec_pic: form.mainImage || pic[0] || '',
    spec_prices: form.skus.map((sku) => ({
      stock_num: Number(sku.stock || 0),
      // 文档：price 单位是**分**
      price: Math.max(1, Math.round(Number(sku.priceYuan || 0) * 100)),
      code: sku.itemId,
      sell_properties: [{ property_name: specName, value_name: sku.name }],
    })),
  }
}

export function validateForm(form: ListingForm): string[] {
  const problems: string[] = []
  if (form.name.length < NAME_MIN) problems.push(`商品名称至少 ${NAME_MIN} 字`)
  if (form.name.length > NAME_MAX) problems.push(`商品名称最多 ${NAME_MAX} 字`)
  if (!form.categoryLeafId) problems.push('请选择商品分类')
  if (!form.mainImage) problems.push('请上传商品主图')
  if (form.carousel.length === 0) problems.push('请至少放一张轮播图')
  if (form.skus.length === 0) problems.push('至少添加一个 SKU')
  form.skus.forEach((sku, index) => {
    if (!sku.name.trim()) problems.push(`第 ${index + 1} 个 SKU 缺名称`)
    if (!sku.priceYuan || Number(sku.priceYuan) <= 0) problems.push(`第 ${index + 1} 个 SKU 缺售价`)
    if (sku.stock === '' || Number(sku.stock) < 0) problems.push(`第 ${index + 1} 个 SKU 缺库存`)
  })
  if (!form.shippingNote.trim()) problems.push('请填写发货说明')
  if (!form.purchaseNote.trim()) problems.push('请填写购买须知')
  return problems
}
