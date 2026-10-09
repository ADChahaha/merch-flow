import { expect, test } from 'vitest'
import { buildForm, toProductAddRequest, validateForm } from './listingDefaults'
import type { CartItem } from './cart'
const item = (id: string): CartItem => ({ id, site: '', url: '', title: '相同名称的不同商品', price: 12.99, images: ['https://example.com/a.jpg'], stockStatus: '', conditionLabel: '', reserveStart: null, reserveEnd: null, releaseDate: null, comment: '' })
const form = () => buildForm([item('a')], { categoryLeafId: 2301, freightId: 1004258 })
test('selected main image leads exported carousel and keeps old image', () => {
  const draft = form()
  draft.mainImage = 'https://example.com/new.jpg'
  const request = toProductAddRequest(draft, false)
  expect(request.pic.split('\n')).toEqual([draft.mainImage, ...draft.carousel])
  expect(request.spec_prices[0].price).toBe(1299)
})
test('same titles still get distinct default SKU names', () => {
  const draft = buildForm([item('a'), item('b')], { categoryLeafId: 2301, freightId: 1004258 })
  expect(new Set(draft.skus.map((sku) => sku.name)).size).toBe(2)
  expect(validateForm(draft)).toEqual([])
})
test('reject invalid price and fractional stock before export', () => {
  const draft = form()
  draft.skus[0].priceYuan = 'NaN'
  draft.skus[0].stock = '1.5'
  expect(validateForm(draft)).toHaveLength(2)
})
