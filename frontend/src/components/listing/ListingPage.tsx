import { useState } from 'react'
import type { CartItem } from '../../lib/cart'
import type { AgentJob, CategoryNode, FreightTemplate } from '../../types'
import { IconCart, IconTrash } from '../Icons'
import { BilibiliForm } from './BilibiliForm'
import { TaobaoForm } from './TaobaoForm'

type Props = {
  cart: CartItem[]
  onRemoveFromCart: (id: string) => void
  onClearCart: () => void
  categories: CategoryNode[]
  freights: FreightTemplate[]
  /** 淘宝浏览器上架任务起来后交给 App（日志 popup / 左栏都认它） */
  onPublishJobStarted: (job: AgentJob) => void
}

const CLEAR_KEY = 'ec-listing-clear-cart'

/**
 * 上架页外壳：Bilibili / 淘宝两个平台分 Tab，上架清单共享。
 * 默认上架成功后**不清空**上架清单（想清空在上架清单右上角勾选）。
 */
export function ListingPage({ cart, onRemoveFromCart, onClearCart, categories, freights, onPublishJobStarted }: Props) {
  const [platform, setPlatform] = useState<'bilibili' | 'taobao'>('bilibili')
  const [clearAfterPublish, setClearAfterPublish] = useState(() => {
    try {
      return localStorage.getItem(CLEAR_KEY) === '1'
    } catch {
      return false
    }
  })

  const toggleClear = (value: boolean) => {
    setClearAfterPublish(value)
    try {
      localStorage.setItem(CLEAR_KEY, value ? '1' : '0')
    } catch {
      // 隐私模式写不了就算了，当前会话内照样生效
    }
  }

  /** 子表单组装/发布成功后调用；清不清上架清单由上面的开关决定 */
  const handlePublished = () => {
    if (clearAfterPublish) onClearCart()
  }

  const cartNode = (
    <section className="mb-4 rounded-xl border border-slate-200 bg-white p-4">
      <header className="mb-2 flex items-center gap-2">
        <IconCart size={16} className="text-brand-600" />
        <h2 className="text-[14px] font-semibold text-slate-800">上架清单</h2>
        <span className="text-[11px] text-slate-400">{cart.length} 个商品 · 两个平台共用</span>
        <label
          className="ml-auto flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-500 select-none"
          title="默认不勾选：上架成功后上架清单保留，方便再发另一平台"
        >
          <input
            type="checkbox"
            checked={clearAfterPublish}
            onChange={(e) => toggleClear(e.target.checked)}
            className="h-3 w-3 accent-[var(--color-brand-600)]"
          />
          上架后清空
        </label>
        <button
          type="button"
          onClick={onClearCart}
          disabled={cart.length === 0}
          className="rounded-md border border-slate-200 px-2 py-1 text-[11px] text-slate-500 transition hover:border-slate-300 disabled:opacity-40"
        >
          清空
        </button>
      </header>
      {cart.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-200 px-3 py-5 text-center text-[12px] leading-relaxed text-slate-400">
          还没有商品。去「商品」里点搜索结果里的图片就能放进上架清单。
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {cart.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/60 p-1.5 pr-2"
            >
              <div className="h-10 w-10 overflow-hidden rounded bg-white ring-1 ring-slate-200">
                {item.images[0] ? <img src={item.images[0]} alt="" className="h-full w-full object-cover" /> : null}
              </div>
              <div className="min-w-0 max-w-[180px]">
                <p className="truncate text-[11px] text-slate-700" title={item.title}>
                  {item.title}
                </p>
                <p className="text-[11px] font-semibold text-rose-600">
                  {item.price === null ? '价格未定' : `￥${item.price.toLocaleString()}`}
                  <span className="ml-1 font-normal text-slate-400">{item.site}</span>
                </p>
              </div>
              <button
                type="button"
                onClick={() => onRemoveFromCart(item.id)}
                className="rounded p-1 text-slate-300 transition hover:bg-white hover:text-rose-600"
              >
                <IconTrash size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-slate-100">
      <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1">
          <TabButton active={platform === 'bilibili'} onClick={() => setPlatform('bilibili')}>
            Bilibili 上架
          </TabButton>
          <TabButton active={platform === 'taobao'} onClick={() => setPlatform('taobao')}>
            淘宝上架
          </TabButton>
        </div>
        <span className="text-[11px] text-slate-400">
          {platform === 'bilibili'
            ? '契约：B 站开放平台 product_add'
            : '契约：淘宝开放平台 alibaba.item.publish.submit'}
        </span>
      </header>

      {platform === 'bilibili' ? (
        <BilibiliForm
          cart={cart}
          cartNode={cartNode}
          categories={categories}
          freights={freights}
          onPublished={handlePublished}
        />
      ) : (
        <TaobaoForm cart={cart} cartNode={cartNode} onJobStarted={onPublishJobStarted} />
      )}
    </div>
  )
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-3.5 py-1.5 text-[12.5px] transition ${
        active ? 'bg-white font-medium text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
      }`}
    >
      {children}
    </button>
  )
}
