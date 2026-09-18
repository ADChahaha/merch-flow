import type { Offer } from '../types'

/** 上架清单里的一个商品（从上架内容最小单位抽出来的，跟搜索域解耦） */
export type CartItem = {
  id: string
  site: string
  /** 来源页面（上架页左边 iframe 核对用） */
  url: string
  title: string
  price: number | null
  images: string[]
  stockStatus: string
  conditionLabel: string
  reserveStart: string | null
  reserveEnd: string | null
  releaseDate: string | null
  comment: string
}

export function cartItemFromOffer(offer: Offer): CartItem {
  return {
    id: offer.id,
    site: offer.site,
    url: offer.url,
    title: offer.listing.title,
    price: offer.listing.price,
    images: offer.listing.images.filter(Boolean),
    stockStatus: offer.stock_status,
    conditionLabel: offer.condition_label,
    reserveStart: offer.listing.reserve.start,
    reserveEnd: offer.listing.reserve.end,
    releaseDate: offer.release_date,
    comment: offer.listing.comment,
  }
}

export function primaryImage(item: CartItem): string {
  return item.images[0] ?? ''
}
