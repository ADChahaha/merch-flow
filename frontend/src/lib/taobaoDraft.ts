import type { CartItem } from './cart'

function esc(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

/**
 * 从上架清单生成一份 itemSchema **草稿**（淘宝要求的格式是 XML）。
 * 正式发布前应该用「拉取发布规则」拿到的类目 schema 替换/补全 —— 这里只是别让输入框空着。
 */
export function buildDraftSchema(items: CartItem[]): string {
  const first = items[0]
  if (!first) return '<itemSchema></itemSchema>'

  const title = items.length > 1 ? `${first.title} 等 ${items.length} 件` : first.title
  const price = first.price === null ? '' : first.price.toFixed(2)
  const images = [...new Set(items.flatMap((item) => item.images))].slice(0, 5)
  const description = items
    .map((item) => `${item.title}${item.price === null ? '' : ` ￥${item.price}`}`)
    .join('；')

  return [
    '<itemSchema>',
    `  <field id="title" name="宝贝标题" type="input"><value>${esc(title)}</value></field>`,
    `  <field id="price" name="价格" type="input"><value>${esc(price)}</value></field>`,
    '  <field id="quantity" name="数量" type="input"><value>100</value></field>',
    '  <field id="itemImages" name="商品图片" type="complex"><values>',
    ...images.map((src) => `    <value>${esc(src)}</value>`),
    '  </values></field>',
    `  <field id="description" name="宝贝描述" type="input"><value>${esc(description)}</value></field>`,
    '</itemSchema>',
  ].join('\n')
}
