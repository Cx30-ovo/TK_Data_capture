import { useDeferredValue, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowUpRight, Clock3, Flame, Pin, RefreshCw, Search, TrendingUp, Video } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { StatePanel } from '@/components/ui/state-panel'
import { monitorApi, type DouyinHotRankItem, type DouyinHotRankResponse } from '@/lib/api'

function formatCompact(value: number): string {
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function formatTime(value?: string | number): string {
  if (!value) return '-'
  const normalized = typeof value === 'number' ? (value > 10 ** 12 ? value : value * 1000) : value
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString()
}

function errorMessage(error: unknown): string {
  const responseError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = responseError.response?.data?.detail
  return typeof detail === 'string' && detail.trim()
    ? detail
    : String(error instanceof Error ? error.message : error || '')
}

function rankTone(rank: number | null): string {
  if (rank === 1) return 'border-status-danger/30 bg-status-danger/[0.06] text-status-danger'
  if (rank === 2) return 'border-status-warning/30 bg-status-warning/[0.06] text-status-warning'
  if (rank === 3) return 'border-status-info/30 bg-status-info/[0.06] text-status-info'
  return 'border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-secondary'
}

function RankedItem({ item, maxHeat }: { item: DouyinHotRankItem; maxHeat: number }) {
  const { t } = useTranslation('config')
  const heatPercent = item.hot_value > 0 ? Math.max(3, item.hot_value / maxHeat * 100) : 0

  return (
    <li className="group min-w-0 overflow-hidden rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel transition-colors hover:border-primary/35 hover:bg-cyber-bg-tertiary/35">
      <a href={item.search_url} target="_blank" rel="noopener noreferrer" className="flex min-h-[108px] items-start gap-3 p-3.5 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/50">
        <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl border text-sm font-bold tabular-nums ${rankTone(item.rank)}`}>{item.rank}</span>
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-start gap-2">
            <span className="line-clamp-2 flex-1 text-sm font-semibold leading-5 text-cyber-text-primary transition-colors group-hover:text-primary">{item.word}</span>
            {item.label ? <Badge variant="secondary" className="shrink-0">{item.label}</Badge> : null}
            <ArrowUpRight aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-cyber-text-muted transition-colors group-hover:text-primary" />
          </span>
          <span className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-cyber-text-muted">
            <span className="inline-flex items-center gap-1.5"><TrendingUp aria-hidden="true" className="h-3.5 w-3.5 text-status-danger" />{t('hotRank.heat')} <b className="tabular-nums text-cyber-text-primary">{formatCompact(item.hot_value)}</b></span>
            {item.video_count > 0 ? <span className="inline-flex items-center gap-1.5"><Video aria-hidden="true" className="h-3.5 w-3.5" />{t('hotRank.videos', { value: formatCompact(item.video_count) })}</span> : null}
            {item.event_time > 0 ? <span>{formatTime(item.event_time)}</span> : null}
          </span>
          <span aria-hidden="true" className="mt-2.5 block h-1.5 overflow-hidden rounded-full bg-cyber-bg-tertiary"><span className="block h-full rounded-full bg-status-danger/80" style={{ width: `${heatPercent}%` }} /></span>
        </span>
      </a>
    </li>
  )
}

export function MonitorHotRank() {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['douyinHotRank'],
    queryFn: async () => (await monitorApi.getHotRank()).data,
    refetchInterval: 120000,
    retry: 1,
  })
  const refreshMutation = useMutation({
    mutationFn: async () => (await monitorApi.getHotRank(true)).data,
    onSuccess: (response) => queryClient.setQueryData<DouyinHotRankResponse>(['douyinHotRank'], response),
  })
  const keyword = deferredSearch.trim().toLowerCase()
  const items = useMemo(
    () => (data?.items || []).filter((item) => !keyword || item.word.toLowerCase().includes(keyword)),
    [data?.items, keyword],
  )
  const pinnedItems = items.filter((item) => item.is_pinned)
  const rankedItems = items.filter((item) => !item.is_pinned)
  const maxHeat = Math.max(...(data?.items || []).filter((item) => !item.is_pinned).map((item) => item.hot_value), 1)
  const busy = isFetching || refreshMutation.isPending

  if (isLoading) return <StatePanel variant="loading" title={t('hotRank.loading')} description={t('hotRank.loadingHint')} />
  if (error && !data) return (
    <StatePanel
      variant="error"
      title={t('hotRank.loadFailed')}
      description={errorMessage(error)}
      action={<Button type="button" variant="outline" size="sm" onClick={() => refreshMutation.mutate()} disabled={refreshMutation.isPending}><RefreshCw aria-hidden="true" className={refreshMutation.isPending ? 'animate-spin motion-reduce:animate-none' : ''} />{t('hotRank.retry')}</Button>}
    />
  )

  return (
    <section className="overview-panel overflow-hidden" aria-labelledby="douyin-hot-rank-title">
      <header className="overview-panel-header min-h-0 flex-col items-stretch gap-4 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3.5">
          <span className="relative grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-status-danger/20 bg-status-danger/10 text-status-danger">
            <Flame aria-hidden="true" className="h-5 w-5" />
            <span aria-hidden="true" className="absolute right-1 top-1 h-2 w-2 rounded-full border-2 border-cyber-bg-panel bg-status-success" />
          </span>
          <div className="min-w-0">
            <h2 id="douyin-hot-rank-title" className="overview-panel-title">{t('hotRank.title')}</h2>
            <p className="overview-panel-description max-w-2xl">{t('hotRank.description')}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="tabular-nums">{t('hotRank.itemCount', { count: data?.items.length || 0 })}</Badge>
          {data?.cached ? <Badge variant="outline">{t('hotRank.cached')}</Badge> : <Badge variant="outline" className="border-status-success/30 text-status-success">{t('hotRank.realtime')}</Badge>}
          {data?.stale ? <Badge variant="destructive">{t('hotRank.stale')}</Badge> : null}
          <Button type="button" variant="outline" size="sm" onClick={() => refreshMutation.mutate()} disabled={busy} className="min-h-9"><RefreshCw aria-hidden="true" className={busy ? 'animate-spin motion-reduce:animate-none' : ''} />{t('hotRank.refresh')}</Button>
        </div>
      </header>

      <div className="border-b border-cyber-border-subtle bg-cyber-bg-tertiary/15 p-3 sm:px-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-md"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cyber-text-muted" /><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('hotRank.searchPlaceholder')} aria-label={t('hotRank.searchLabel')} className="h-10 bg-cyber-bg-panel pl-9" /></div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-cyber-text-muted"><span className="inline-flex items-center gap-1.5"><Clock3 aria-hidden="true" className="h-3.5 w-3.5" />{t('hotRank.updatedAt')}: {formatTime(data?.generated_at)}</span><span className="tabular-nums">{t('hotRank.resultCount', { count: items.length })}</span></div>
        </div>
        {data?.warning || refreshMutation.error ? <p role="status" className="mt-2 rounded-lg border border-status-warning/25 bg-status-warning/10 px-3 py-2 text-xs text-status-warning">{data?.warning || errorMessage(refreshMutation.error)}</p> : null}
      </div>

      {items.length ? (
        <div className="max-h-[680px] overflow-y-auto overscroll-contain">
          {pinnedItems.map((item) => (
            <a key={`pinned-${item.sentence_id || item.word}`} href={item.search_url} target="_blank" rel="noopener noreferrer" className="group m-3 flex min-h-[92px] items-center gap-3 rounded-xl border border-primary/25 bg-primary/[0.06] p-4 outline-none transition-colors hover:border-primary/45 hover:bg-primary/[0.09] focus-visible:ring-2 focus-visible:ring-primary/50 sm:mx-4">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm"><Pin aria-hidden="true" className="h-5 w-5" /></span>
              <span className="min-w-0 flex-1">
                <span className="mb-1 flex flex-wrap items-center gap-2"><Badge>{t('hotRank.pinned')}</Badge><span className="text-xs text-cyber-text-muted">{t('hotRank.pinnedHint')}</span></span>
                <span className="flex items-center gap-2 text-base font-semibold leading-6 text-cyber-text-primary group-hover:text-primary"><span className="min-w-0 flex-1">{item.word}</span><ArrowUpRight aria-hidden="true" className="h-4 w-4 shrink-0" /></span>
                {item.video_count > 0 ? <span className="mt-1 inline-flex items-center gap-1.5 text-xs text-cyber-text-muted"><Video aria-hidden="true" className="h-3.5 w-3.5" />{t('hotRank.videos', { value: formatCompact(item.video_count) })}</span> : null}
              </span>
            </a>
          ))}

          {rankedItems.length ? (
            <div className="border-t border-cyber-border-subtle/70 px-3 pb-3 pt-3 sm:px-4 sm:pb-4">
              <div className="mb-2.5 flex items-center justify-between gap-3"><h3 className="text-sm font-semibold text-cyber-text-primary">{t('hotRank.rankingTitle')}</h3><span className="text-xs tabular-nums text-cyber-text-muted">{t('hotRank.rankingCount', { count: rankedItems.length })}</span></div>
              <ol className="grid gap-2 lg:grid-cols-2" aria-label={t('hotRank.listLabel')}>
                {rankedItems.map((item) => <RankedItem key={`${item.rank}-${item.sentence_id || item.word}`} item={item} maxHeat={maxHeat} />)}
              </ol>
            </div>
          ) : null}
        </div>
      ) : <StatePanel variant="empty" title={t('hotRank.empty')} description={search ? t('hotRank.emptySearch') : t('hotRank.emptyHint')} />}

      <footer className="border-t border-cyber-border-subtle bg-cyber-bg-tertiary/15 px-4 py-3 text-xs leading-5 text-cyber-text-muted">{t('hotRank.disclaimer')}</footer>
    </section>
  )
}
