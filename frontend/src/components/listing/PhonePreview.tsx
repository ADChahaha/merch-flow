import { useEffect, useState } from 'react'
import type { ListingForm } from '../../lib/listingDefaults'
import { IconHeart, IconStar } from '../Icons'

/** 上传后效果模拟（手机端）。照着 B 站商品详情页的样子做的预览：轮播图会自动播。 */
export function PhonePreview({ form }: { form: ListingForm }) {
  const prices = form.skus.map((s) => Number(s.priceYuan || 0)).filter((n) => n > 0)
  const minPrice = prices.length ? Math.min(...prices) : 0
  const preorder = form.tags.includes('预售')

  const slides = (form.carousel.length > 0 ? form.carousel : [form.mainImage]).filter(Boolean)
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)

  // 轮播图变了（加/删商品）就回到第一张
  const key = slides.join('|')
  useEffect(() => setIndex(0), [key])

  useEffect(() => {
    if (paused || slides.length <= 1) return
    const timer = window.setInterval(() => setIndex((n) => (n + 1) % slides.length), 3000)
    return () => window.clearInterval(timer)
  }, [paused, slides.length, key])

  const cover = slides[Math.min(index, Math.max(0, slides.length - 1))] ?? ''

  return (
    <div className="mx-auto w-[360px] rounded-[28px] border border-slate-200 bg-white p-3 shadow-sm">
      <div className="overflow-hidden rounded-[22px] bg-white ring-1 ring-slate-100">
        <div
          className="relative aspect-square bg-slate-100"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
        >
          {cover ? (
            <img src={cover} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-slate-400">主图预览</div>
          )}
          <span className="absolute right-2 bottom-2 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-white">
            {Math.min(index + 1, Math.max(1, slides.length))}/{Math.max(1, slides.length)}
          </span>
          {slides.length > 1 && (
            <div className="absolute inset-x-0 bottom-2 flex justify-center gap-1">
              {slides.map((src, i) => (
                <button
                  key={`${src}-${i}`}
                  type="button"
                  onClick={() => setIndex(i)}
                  aria-label={`第 ${i + 1} 张`}
                  className={`h-1.5 rounded-full transition-all ${
                    i === index ? 'w-3 bg-white' : 'w-1.5 bg-white/50 hover:bg-white/80'
                  }`}
                />
              ))}
            </div>
          )}
        </div>

        <div className="px-3 pt-3">
          <div className="flex items-start gap-2">
            <h3 className="line-clamp-2 flex-1 text-[15px] leading-snug font-semibold text-slate-900">
              {form.name || '商品名称'}
            </h3>
            {form.returnSupported && (
              <span className="mt-0.5 shrink-0 rounded bg-emerald-50 px-1.5 py-0.5 text-[9px] text-emerald-600">
                官方正版
              </span>
            )}
          </div>

          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-[22px] font-bold text-[#fb7299]">
              ¥<span className="text-[24px]">{minPrice || '—'}</span>
            </span>
            <span className="text-[11px] text-slate-400">起</span>
            {preorder && (
              <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[10px] text-rose-500">预约中</span>
            )}
            <span className="ml-auto flex items-center gap-1 text-[11px] text-slate-400">
              <IconHeart size={13} />
              1.2万
            </span>
          </div>

          {form.saleStart && (
            <p className="mt-2 rounded-md bg-rose-50 px-2 py-1 text-[11px] text-rose-500">
              🕐 预计开售：{form.saleStart}
            </p>
          )}

          {form.summary && (
            <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-slate-500">{form.summary}</p>
          )}

          {form.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {form.tags.map((tag) => (
                <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">
                  {tag}
                </span>
              ))}
            </div>
          )}

          <p className="mt-3 mb-1.5 text-[12px] font-medium text-slate-700">选择款式</p>
          <div className="flex flex-wrap gap-1.5 pb-3">
            {form.skus.map((sku) => (
              <span
                key={sku.key}
                className="rounded-md border border-slate-200 px-2 py-1 text-[10px] text-slate-600"
              >
                {sku.name}
                {sku.priceYuan && <span className="ml-1 text-rose-500">¥{sku.priceYuan}</span>}
              </span>
            ))}
            {form.skus.length === 0 && <span className="text-[11px] text-slate-400">还没有 SKU</span>}
          </div>

          <div className="flex items-center justify-between border-t border-slate-100 py-2 text-[11px] text-slate-500">
            <span>购买数量</span>
            <span className="text-slate-400">1</span>
            <span>每人限购 {form.limitPerBuyer || 0} 件</span>
          </div>

          <div className="flex items-center gap-3 border-t border-slate-100 py-2 text-[10px] text-slate-500">
            <span className="flex items-center gap-1">
              <IconStar size={12} /> 客服
            </span>
            <span className="flex items-center gap-1">
              <IconStar size={12} /> 收藏
            </span>
            <span className="ml-auto flex-1 rounded-full bg-[#fb7299] py-2 text-center text-[13px] font-medium text-white">
              {preorder ? '立即预约' : '立即购买'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
