import type { DouyinHotRankResponse } from './api'

const CACHE_KEY = 'editorial-hot-rank-v1'
const MAX_AGE = 7 * 24 * 3600 * 1000

export function readHotRankCache(storage: Pick<Storage, 'getItem'>, now = Date.now()): DouyinHotRankResponse | undefined {
  try {
    const cached = JSON.parse(storage.getItem(CACHE_KEY) || 'null')
    if (!cached || !Number.isFinite(cached.savedAt) || cached.savedAt > now || now - cached.savedAt > MAX_AGE) return
    const data = cached.data
    if (!data || typeof data.generated_at !== 'string' || !Number.isFinite(Date.parse(data.generated_at))
      || !Array.isArray(data.items) || !data.items.length || data.items.length > 100) return
    if (now - Date.parse(data.generated_at) > MAX_AGE || Date.parse(data.generated_at) > now + 60000) return
    if (!data.items.every((row: Record<string, unknown>) => row && typeof row.word === 'string'
      && typeof row.search_url === 'string' && /^https:\/\/www\.douyin\.com\/search(?:\/|\?)/.test(row.search_url)
      && typeof row.hot_value === 'number' && Number.isFinite(row.hot_value) && row.hot_value >= 0)) return
    return { ...data, cached: true, stale: true, warning: '正在显示上次成功保存的热榜，等待更新。' }
  } catch { return }
}

export function saveHotRankCache(storage: Pick<Storage, 'setItem'>, data: DouyinHotRankResponse, now = Date.now()) {
  if (!data.items.length || data.stale) return
  try { storage.setItem(CACHE_KEY, JSON.stringify({ savedAt: now, data: { ...data, items: data.items.slice(0, 100) } })) } catch { /* Storage restrictions must not break the feed. */ }
}

export function hotRankAge(generatedAt: string | undefined, now = Date.now()) {
  const timestamp = Date.parse(generatedAt || '')
  if (!Number.isFinite(timestamp)) return '更新时间未知'
  const minutes = Math.max(0, Math.floor((now - timestamp) / 60000))
  if (minutes < 1) return '刚刚更新'
  if (minutes < 60) return `${minutes}分钟前更新`
  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `${hours}小时前更新` : `${Math.floor(hours / 24)}天前更新`
}
