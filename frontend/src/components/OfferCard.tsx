import type { Offer } from '../types'
import { conditionStyle, dateLabel, siteColor, stockStyle, yen } from '../lib/format'
import { IconExternal } from './Icons'

type Props = {
  offer: Offer
  inCart: boolean
  onToggleCart: (offer: Offer) => void
}

/** 一张搜索结果卡片。上架内容（名字/图片/价格）只从 offer.listing 读；点图片加入上架清单。 */
export function OfferCard({ offer, inCart, onToggleCart }: Props) {
  const { listing } = offer
  const color = siteColor(offer.site_key)
  const cover = listing.images[0]

  const unbuyable = !offer.is_buyable

  return (
    <article
      className={`mb-2.5 flex gap-3 rounded-lg border p-3 transition hover:shadow-sm ${
        unbuyable ? 'border-dashed border-slate-200 bg-slate-50/70' : 'border-slate-200 bg-white hover:border-slate-300'
      }`}
    >
      <button
        type="button"
        onClick={() => onToggleCart(offer)}
        title={inCart ? '从上架清单移除' : '点图片加入上架清单'}
        className="group/cart relative h-[92px] w-[92px] shrink-0 overflow-hidden rounded-md bg-slate-100 ring-1 ring-slate-200"
      >
        {cover ? (
          <img src={cover} alt="" loading="lazy" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-[10px] text-slate-400">No Image</div>
        )}
        <span
          className={`absolute inset-x-0 bottom-0 flex items-center justify-center gap-0.5 py-1 text-[10px] text-white transition ${
            inCart ? 'bg-emerald-600/85 opacity-100' : 'bg-black/55 opacity-0 group-hover/cart:opacity-100'
          }`}
        >
          {inCart ? '已在上架清单' : '+ 加入上架清单'}
        </span>
        {inCart && (
          <span className="absolute top-0.5 right-0.5 rounded bg-emerald-600 px-1 text-[9px] text-white">✓</span>
        )}
      </button>

      <div className="flex min-w-0 flex-1 flex-col">
        <h3
          className={`line-clamp-2 text-[13.5px] leading-snug font-medium ${unbuyable ? 'text-slate-500' : 'text-slate-800'}`}
          title={listing.title}
        >
          {listing.title}
        </h3>

        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span
            className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${color.bg} ${color.text} ${color.ring}`}
          >
            {offer.site}
          </span>
          {offer.condition_label && (
            <span
              className={`rounded px-1.5 py-0.5 text-[11px] ring-1 ring-inset ${conditionStyle(offer.condition_label)}`}
            >
              {offer.condition_label}
            </span>
          )}
          {offer.stock_status && (
            <span className={`rounded px-1.5 py-0.5 text-[11px] ring-1 ring-inset ${stockStyle(offer.stock_status)}`}>
              {offer.stock_status}
            </span>
          )}
          {unbuyable && (
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[11px] text-slate-600">
              不可买{offer.not_buyable_reason ? ` · ${offer.not_buyable_reason}` : ''}
            </span>
          )}
        </div>

        <div className="mt-auto flex items-end justify-between gap-2 pt-2">
          <div className="min-w-0">
            <p className="flex items-baseline gap-1.5">
              <span
                className={`text-[17px] font-semibold tabular-nums ${unbuyable ? 'text-slate-400 line-through' : 'text-rose-600'}`}
              >
                {listing.price_display}
              </span>
              {offer.price_original !== null && (
                <span className="text-[11px] text-slate-400 line-through tabular-nums">
                  {yen(offer.price_original)}
                </span>
              )}
            </p>
            <p className="mt-0.5 flex flex-wrap gap-x-3 text-[11px] text-slate-400">
              {offer.shop_name && <span>{offer.shop_name}</span>}
              {offer.shipping && <span>{offer.shipping}</span>}
              {(offer.release_text || offer.release_date) && (
                <span>发售日: {offer.release_text || dateLabel(offer.release_date as string)}</span>
              )}
              {listing.reserve.display && <span>可预约: {listing.reserve.display}</span>}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <a
              href={offer.url}
              target="_blank"
              rel="noreferrer"
              title="打开原站页面"
              className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
            >
              <IconExternal size={15} />
            </a>
            <button
              type="button"
              onClick={() => onToggleCart(offer)}
              className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition ${
                inCart
                  ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                  : 'border border-brand-200 bg-white text-brand-700 hover:bg-brand-50'
              }`}
            >
              {inCart ? '移出上架清单' : '加入上架清单'}
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}
