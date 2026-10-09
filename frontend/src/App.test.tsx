// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'
import { api } from './api'
import type { AgentJob } from './types'

vi.mock('./api', () => ({ api: {
  listingCategories: vi.fn(), freightTemplates: vi.fn(), agentJobs: vi.fn(), settings: vi.fn(),
  agentJob: vi.fn(), addAgentJobProduct: vi.fn(),
} }))
vi.mock('./components/AgentLogPanel', () => ({ AgentLogPanel: () => null }))

const job = (id: number): AgentJob => ({
  id, url: `https://example.com/${id}`, kind: 'scrape', title: `Job ${id}`, status: 'done',
  error: '', created_at: null, finished_at: null, pages_visited: 1, product_count: 0, usage: { input: 0, output: 0, cache_read: 0, cache_write: 0, total: 0 }, log: [], products: [],
})
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.listingCategories).mockResolvedValue({ tree: [], note: '' })
  vi.mocked(api.freightTemplates).mockResolvedValue({ templates: [], note: '' })
  vi.mocked(api.settings).mockResolvedValue({ ui: { source_open: false }, agent: { has_key: false, key_hint: '', model: '', reasoning: 'off' }, bilibili: { has_token: false, token_hint: '', client_id: '', has_client_secret: false, secret_hint: '' } })
  vi.mocked(api.agentJobs).mockResolvedValue([job(1), job(2), job(3)])
  vi.mocked(api.agentJob).mockImplementation(async (id) => job(id))
})
afterEach(cleanup)

test('late response cannot replace the currently selected job', async () => {
  render(<App />)
  await screen.findByRole('heading', { name: 'Job 1' })
  const slow = deferred<AgentJob>()
  vi.mocked(api.agentJob).mockImplementation((id) => id === 2 ? slow.promise : Promise.resolve(job(id)))
  fireEvent.click(screen.getByRole('button', { name: /^Job 2/ }))
  fireEvent.click(screen.getByRole('button', { name: /^Job 3/ }))
  await screen.findByRole('heading', { name: 'Job 3' })
  await act(async () => slow.resolve(job(2)))
  expect(screen.queryByRole('heading', { name: 'Job 2' })).toBeNull()
  expect(screen.getByRole('heading', { name: 'Job 3' })).toBeTruthy()
})

test('failed manual add keeps the form and its input, even with no scraped products', async () => {
  vi.mocked(api.addAgentJobProduct).mockRejectedValue(new Error('offline'))
  render(<App />)
  await screen.findByRole('heading', { name: 'Job 1' })
  fireEvent.click(screen.getByRole('button', { name: '手动加商品' }))
  const name = screen.getByPlaceholderText('商品名 *（原文，别翻译）') as HTMLInputElement
  fireEvent.change(name, { target: { value: 'manual A' } })
  fireEvent.click(screen.getByRole('button', { name: '保存商品' }))
  await waitFor(() => expect(screen.getByText('添加失败：offline')).toBeTruthy())
  expect(name.value).toBe('manual A')
  expect(screen.getByRole('button', { name: '保存商品' })).toBeTruthy()
})

test('successful manual add does not depend on a second GET or invite duplicate retries', async () => {
  vi.mocked(api.addAgentJobProduct).mockResolvedValue({ id: 1, uid: 'new', name: 'manual A', price: 12.99, price_text: '', date_text: '', detail: '', image_urls: [], source_url: '' })
  render(<App />)
  await screen.findByRole('heading', { name: 'Job 1' })
  vi.mocked(api.agentJob).mockRejectedValue(new Error('refresh offline'))
  fireEvent.click(screen.getByRole('button', { name: '手动加商品' }))
  fireEvent.change(screen.getByPlaceholderText('商品名 *（原文，别翻译）'), { target: { value: 'manual A' } })
  fireEvent.click(screen.getByRole('button', { name: '保存商品' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: '保存商品' })).toBeNull())
  expect(screen.getByText('manual A')).toBeTruthy()
  expect(api.addAgentJobProduct).toHaveBeenCalledTimes(1)
  expect(api.agentJob).toHaveBeenCalledTimes(1)
})
