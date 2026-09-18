import { useMemo, useState } from 'react'
import { api } from '../../api'
import type { CartItem } from '../../lib/cart'
import {
  MAX_CAROUSEL,
  MAX_DESCRIPTION,
  buildForm,
  toProductAddRequest,
  validateForm,
  type ListingForm,
  type SkuDraft,
} from '../../lib/listingDefaults'
import type { CategoryNode, FreightTemplate, ProductAddResponse } from '../../types'
import { IconCopy, IconPlus, IconTrash, IconUpload } from '../Icons'
import { CELL, Field, INPUT, Section } from './FormBits'
import { ImageStrip } from './ImageStrip'
import { PhonePreview } from './PhonePreview'

type Props = {
  cart: CartItem[]
  /** 上架清单区块（外壳渲染，放在表单最上面） */
  cartNode: React.ReactNode
  categories: CategoryNode[]
  freights: FreightTemplate[]
  /** 组装成功（commit=true 表示是「发布」而不是只预览） */
  onPublished: (commit: boolean) => void
}

const LEAF = (nodes: CategoryNode[]): { id: number; name: string; parent: string }[] =>
  nodes.flatMap((node) => node.children.map((child) => ({ id: child.id, name: child.name, parent: node.name })))

/** Bilibili 上架表单：契约照 product_add，后端只校验 + 组装。 */
export function BilibiliForm({ cart, cartNode, categories, freights, onPublished }: Props) {
  const leaves = useMemo(() => LEAF(categories), [categories])
  const defaultCategory = leaves[0]?.id ?? 2301
  const defaultFreight = freights[0]?.freight_id ?? 1004258

  const [form, setForm] = useState<ListingForm>(() =>
    buildForm(cart, { categoryLeafId: defaultCategory, freightId: defaultFreight }),
  )
  const [tagDraft, setTagDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ProductAddResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 上架清单变了（加/删商品）就按新内容重算默认值
  const cartKey = cart.map((item) => item.id).join(',')
  const [lastCartKey, setLastCartKey] = useState(cartKey)
  if (cartKey !== lastCartKey) {
    setLastCartKey(cartKey)
    setForm(buildForm(cart, { categoryLeafId: defaultCategory, freightId: defaultFreight }))
    setResult(null)
    setError(null)
  }

  const patch = (next: Partial<ListingForm>) => setForm((prev) => ({ ...prev, ...next }))
  const patchSku = (key: string, next: Partial<SkuDraft>) =>
    setForm((prev) => ({
      ...prev,
      skus: prev.skus.map((sku) => (sku.key === key ? { ...sku, ...next } : sku)),
    }))

  const addSku = () => {
    setForm((prev) => ({
      ...prev,
      skus: [
        ...prev.skus,
        {
          key: `manual-${Date.now()}`,
          itemId: '',
          name: `款式${prev.skus.length + 1}`,
          priceYuan: '',
          stock: '100',
          reserveStart: prev.reserveStart,
          saleStart: prev.saleStart,
          limitPerBuyer: prev.limitPerBuyer,
          image: prev.mainImage,
        },
      ],
    }))
  }

  const duplicateSku = (key: string) =>
    setForm((prev) => {
      const index = prev.skus.findIndex((sku) => sku.key === key)
      if (index < 0) return prev
      const copy: SkuDraft = { ...prev.skus[index], key: `copy-${Date.now()}`, name: `${prev.skus[index].name} 副本` }
      return { ...prev, skus: [...prev.skus.slice(0, index + 1), copy, ...prev.skus.slice(index + 1)] }
    })

  const removeSku = (key: string) =>
    setForm((prev) => ({ ...prev, skus: prev.skus.filter((sku) => sku.key !== key) }))

  const submit = async (commit: boolean) => {
    const problems = validateForm(form)
    if (problems.length > 0) {
      setError(problems.join('；'))
      setResult(null)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const payload = toProductAddRequest(form, commit)
      const response = await api.createBilibiliListing(payload)
      setResult(response)
      if (commit) onPublished(true)
    } catch (err) {
      setError((err as Error).message)
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {cartNode}

        {/* ① 基础信息 */}
        <Section index={1} title="基础信息" hint="填写商品最基本的信息">
          <div className="grid grid-cols-2 gap-5">
            <Field label="商品名称" required counter={`${form.name.length}/60`}>
              <input
                value={form.name}
                maxLength={60}
                onChange={(e) => patch({ name: e.target.value })}
                placeholder="例）限定亚克力立牌（预售）"
                className={INPUT}
              />
            </Field>
            <Field label="商品分类" required>
              <select
                value={form.categoryLeafId ?? ''}
                onChange={(e) => patch({ categoryLeafId: Number(e.target.value) })}
                className={INPUT}
              >
                {leaves.map((leaf) => (
                  <option key={leaf.id} value={leaf.id}>
                    {leaf.parent} / {leaf.name}（{leaf.id}）
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-5">
            <Field label="商品简介" required counter={`${form.summary.length}/200`}>
              <textarea
                value={form.summary}
                rows={3}
                maxLength={200}
                onChange={(e) => patch({ summary: e.target.value })}
                className={`${INPUT} resize-none`}
              />
            </Field>
            <Field label="商品标签">
              <div className="flex flex-wrap items-center gap-1.5">
                {form.tags.map((tag) => (
                  <span
                    key={tag}
                    className="flex items-center gap-1 rounded-full bg-brand-50 px-2 py-1 text-[11px] text-brand-700"
                  >
                    {tag}
                    <button type="button" onClick={() => patch({ tags: form.tags.filter((t) => t !== tag) })}>
                      <IconPlus size={10} className="rotate-45" />
                    </button>
                  </span>
                ))}
                <input
                  value={tagDraft}
                  onChange={(e) => setTagDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== 'Enter' || !tagDraft.trim()) return
                    patch({ tags: [...new Set([...form.tags, tagDraft.trim()])] })
                    setTagDraft('')
                  }}
                  placeholder="+ 添加标签"
                  className="w-24 rounded-full border border-dashed border-slate-300 px-2 py-1 text-[11px] outline-none focus:border-brand-400"
                />
              </div>
            </Field>
          </div>
        </Section>

        {/* ② 图片上传 */}
        <Section index={2} title="图片上传" hint="主图用于商品卡片，轮播图最多 5 张（接口限制），详情图最多 50 张">
          <div className="grid grid-cols-[220px_1fr_1fr] gap-5">
            <Field label="商品主图" required>
              <div className="relative h-[220px] w-[220px] overflow-hidden rounded-lg bg-slate-100 ring-1 ring-slate-200">
                {form.mainImage ? (
                  <img src={form.mainImage} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-slate-400">未设置</div>
                )}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {form.carousel.slice(0, 8).map((src) => (
                  <button
                    key={src}
                    type="button"
                    onClick={() => patch({ mainImage: src })}
                    className={`h-10 w-10 overflow-hidden rounded ring-1 transition ${
                      src === form.mainImage ? 'ring-2 ring-brand-500' : 'ring-slate-200 hover:ring-brand-300'
                    }`}
                  >
                    <img src={src} alt="" className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            </Field>

            <Field label={`商品轮播图（${form.carousel.length}/${MAX_CAROUSEL}）`} required>
              <ImageStrip
                images={form.carousel}
                onRemove={(src) =>
                  patch({
                    carousel: form.carousel.filter((s) => s !== src),
                    mainImage: form.mainImage === src ? '' : form.mainImage,
                  })
                }
                onInsert={(src) =>
                  patch({ carousel: [...form.carousel, src].slice(0, MAX_CAROUSEL + 45), mainImage: form.mainImage || src })
                }
                hint="第一张即主图。超过 5 张的部分提交时会自动挪到详情图，不会丢。"
              />
            </Field>

            <Field label={`详情图文（${form.descriptionImages.length}/${MAX_DESCRIPTION}）`}>
              <ImageStrip
                images={form.descriptionImages.slice(0, 30)}
                compact
                onRemove={(src) => patch({ descriptionImages: form.descriptionImages.filter((s) => s !== src) })}
                onInsert={(src) =>
                  patch({ descriptionImages: [...form.descriptionImages, src].slice(0, MAX_DESCRIPTION) })
                }
                hint={`默认放了上架清单前 ${MAX_DESCRIPTION} 张图，可删可插；与轮播图重复的不会重复提交。`}
              />
            </Field>
          </div>
        </Section>

        {/* ③ 销售信息 */}
        <Section index={3} title="销售信息" hint="设置整体的销售相关信息">
          <div className="grid grid-cols-3 gap-5">
            <Field label="预约开始时间" required>
              <input
                value={form.reserveStart}
                onChange={(e) => patch({ reserveStart: e.target.value })}
                placeholder="2026-09-01 10:00"
                className={INPUT}
              />
            </Field>
            <Field label="开售时间" required>
              <input
                value={form.saleStart}
                onChange={(e) => patch({ saleStart: e.target.value })}
                placeholder="2026-09-20 19:30"
                className={INPUT}
              />
            </Field>
            <Field label="每人限购" required>
              <div className="flex items-center gap-2">
                <input
                  value={form.limitPerBuyer}
                  onChange={(e) => patch({ limitPerBuyer: e.target.value.replace(/\D/g, '') })}
                  className={INPUT}
                />
                <span className="shrink-0 text-xs text-slate-400">件（0 = 不限购）</span>
              </div>
            </Field>
          </div>
        </Section>

        {/* ④ SKU */}
        <Section index={4} title="SKU 规格设置" hint="上架清单里的每个商品默认占一行，可增删改">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-separate border-spacing-0 text-[12px]">
              <thead>
                <tr className="text-left text-slate-500">
                  {['SKU 名称 *', '售价 *', '库存 *', '预约开始时间 *', '开售时间 *', '限购 *', '图片', '操作'].map(
                    (head) => (
                      <th key={head} className="border-b border-slate-200 pb-1.5 font-normal">
                        {head}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {form.skus.map((sku) => (
                  <tr key={sku.key}>
                    <td className="border-b border-slate-100 py-1.5 pr-2">
                      <input
                        value={sku.name}
                        onChange={(e) => patchSku(sku.key, { name: e.target.value })}
                        className={CELL}
                      />
                    </td>
                    <td className="border-b border-slate-100 py-1.5 pr-2">
                      <div className="flex items-center gap-1">
                        <span className="text-slate-400">¥</span>
                        <input
                          value={sku.priceYuan}
                          onChange={(e) => patchSku(sku.key, { priceYuan: e.target.value.replace(/[^\d.]/g, '') })}
                          className={CELL}
                        />
                      </div>
                    </td>
                    <td className="border-b border-slate-100 py-1.5 pr-2">
                      <input
                        value={sku.stock}
                        onChange={(e) => patchSku(sku.key, { stock: e.target.value.replace(/\D/g, '') })}
                        className={CELL}
                      />
                    </td>
                    <td className="border-b border-slate-100 py-1.5 pr-2">
                      <input
                        value={sku.reserveStart}
                        onChange={(e) => patchSku(sku.key, { reserveStart: e.target.value })}
                        className={CELL}
                      />
                    </td>
                    <td className="border-b border-slate-100 py-1.5 pr-2">
                      <input
                        value={sku.saleStart}
                        onChange={(e) => patchSku(sku.key, { saleStart: e.target.value })}
                        className={CELL}
                      />
                    </td>
                    <td className="border-b border-slate-100 py-1.5 pr-2">
                      <input
                        value={sku.limitPerBuyer}
                        onChange={(e) => patchSku(sku.key, { limitPerBuyer: e.target.value.replace(/\D/g, '') })}
                        className={CELL}
                      />
                    </td>
                    <td className="border-b border-slate-100 py-1.5 pr-2">
                      <button
                        type="button"
                        title={sku.image || '设置 SKU 图片 URL'}
                        onClick={() => {
                          const url = window.prompt('SKU 图片 URL', sku.image)
                          if (url !== null) patchSku(sku.key, { image: url.trim() })
                        }}
                        className="h-8 w-8 overflow-hidden rounded ring-1 ring-slate-200"
                      >
                        {sku.image ? <img src={sku.image} alt="" className="h-full w-full object-cover" /> : null}
                      </button>
                    </td>
                    <td className="border-b border-slate-100 py-1.5">
                      <div className="flex items-center gap-2 text-[11px]">
                        <button
                          type="button"
                          onClick={() => duplicateSku(sku.key)}
                          className="flex items-center gap-0.5 text-brand-600 hover:underline"
                        >
                          <IconCopy size={12} /> 复制
                        </button>
                        <button
                          type="button"
                          onClick={() => removeSku(sku.key)}
                          className="flex items-center gap-0.5 text-rose-500 hover:underline"
                        >
                          <IconTrash size={12} /> 删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            onClick={addSku}
            className="mt-3 flex items-center gap-1 rounded-md border border-brand-300 px-2.5 py-1.5 text-[12px] text-brand-700 transition hover:bg-brand-50"
          >
            <IconPlus size={13} /> 添加 SKU
          </button>
          <p className="mt-1 text-[10px] text-slate-400">
            接口要求 SKU 数量 = 规格组合数，所以每个 SKU 会作为「款式」的一个取值提交。
          </p>
        </Section>

        {/* ⑤ 展示与说明 */}
        <Section index={5} title="展示与说明" hint="完善商品说明，帮助用户更好地了解商品">
          <div className="grid grid-cols-2 gap-5">
            <Field label="发货说明" required counter={`${form.shippingNote.length}/200`}>
              <textarea
                value={form.shippingNote}
                rows={4}
                maxLength={200}
                onChange={(e) => patch({ shippingNote: e.target.value })}
                className={`${INPUT} resize-none`}
              />
            </Field>
            <Field label="购买须知" required counter={`${form.purchaseNote.length}/200`}>
              <textarea
                value={form.purchaseNote}
                rows={4}
                maxLength={200}
                onChange={(e) => patch({ purchaseNote: e.target.value })}
                className={`${INPUT} resize-none`}
              />
            </Field>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-5">
            <Field label="运费模板" required>
              <select
                value={form.freightId ?? ''}
                onChange={(e) => patch({ freightId: Number(e.target.value) })}
                className={INPUT}
              >
                {freights.map((template) => (
                  <option key={template.freight_id} value={template.freight_id}>
                    {template.name}（{template.freight_id}）
                  </option>
                ))}
              </select>
            </Field>
            <Field label="承诺发货时间（天）">
              <input
                value={form.deliveryDelayDay}
                onChange={(e) => patch({ deliveryDelayDay: e.target.value.replace(/\D/g, '') })}
                className={INPUT}
              />
            </Field>
            <Field label="售后服务">
              <label className="flex items-center gap-2 pt-2 text-[12px] text-slate-600">
                <input
                  type="checkbox"
                  checked={form.returnSupported}
                  onChange={(e) => patch({ returnSupported: e.target.checked })}
                  className="h-3.5 w-3.5 accent-[var(--color-brand-600)]"
                />
                支持 7 天无理由（7-1）
              </label>
            </Field>
          </div>
        </Section>

        {(error || result) && (
          <div
            className={`mb-4 rounded-xl border px-4 py-3 text-[12px] leading-relaxed ${
              error
                ? 'border-rose-200 bg-rose-50 text-rose-600'
                : 'border-emerald-200 bg-emerald-50 text-emerald-700'
            }`}
          >
            {error && <p>校验没过：{error}</p>}
            {result && (
              <div>
                <p className="font-medium">已按 B 站 product_add 契约组装好请求体</p>
                <p className="mt-1 text-emerald-600/80">{result.note}</p>
                <details className="mt-2">
                  <summary className="cursor-pointer">查看请求体（{result.endpoint}）</summary>
                  <pre className="mt-1 max-h-64 overflow-auto rounded bg-white/70 p-2 text-[10px] text-slate-600">
                    {JSON.stringify(result.request, null, 2)}
                  </pre>
                </details>
              </div>
            )}
          </div>
        )}

        <footer className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-[13px] text-slate-600 transition hover:border-slate-400 disabled:opacity-50"
          >
            保存草稿
          </button>
          <button
            type="button"
            disabled={busy || cart.length === 0}
            onClick={() => void submit(true)}
            className="flex items-center gap-1.5 rounded-md bg-[#fb7299] px-5 py-2 text-[13px] font-medium text-white transition hover:bg-[#e4638a] disabled:opacity-50"
          >
            <IconUpload size={14} />
            {busy ? '提交中…' : '发布到 Bilibili'}
          </button>
          <button
            type="button"
            onClick={() => void submit(false)}
            disabled={busy || cart.length === 0}
            className="text-[11px] text-slate-400 underline-offset-2 hover:underline disabled:opacity-40"
          >
            只校验并预览请求体（commit=false）
          </button>
        </footer>
      </div>

      <aside className="hidden w-[420px] shrink-0 overflow-y-auto border-l border-slate-200 bg-white px-5 py-5 xl:block">
        <header className="mb-3 flex items-center gap-2">
          <h2 className="text-[14px] font-semibold text-slate-800">上传后效果模拟</h2>
          <span className="text-[11px] text-slate-400">以下为 B 站客户端商品详情页的预览效果</span>
        </header>
        <PhonePreview form={form} />
      </aside>
    </div>
  )
}
