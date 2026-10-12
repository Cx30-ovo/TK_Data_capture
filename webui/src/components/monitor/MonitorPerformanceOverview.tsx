import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, ArrowDown, ArrowUp, ArrowUpDown, BarChart3, Bookmark, ChevronLeft, ChevronRight, Clock3, ExternalLink, Flame, Gauge, Heart, ImageIcon, MessageSquare, Search, Share2, TrendingUp } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { MonitorDashboardPost, MonitorSnapshot } from '@/lib/api'
import { firstSeenDelayHours, latestSnapshot, mean, median } from '@/lib/monitorMetrics'


function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
}


function formatPublishedAt(value: number): string {
  const date = new Date(value * 1000)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat(undefined, {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}


function stageBadgeClass(stage?: string): string {
  if (stage === '1h') return 'border-status-info/25 bg-status-info/10 text-status-info'
  if (stage === '6h') return 'border-status-success/25 bg-status-success/10 text-status-success'
  if (stage === '24h') return 'border-status-purple/25 bg-status-purple/10 text-status-purple'
  if (stage === '72h') return 'border-status-warning/25 bg-status-warning/10 text-status-warning'
  if (stage === '7d') return 'border-status-danger/25 bg-status-danger/10 text-status-danger'
  if (stage === 'first_seen') return 'border-cyber-border-default bg-cyber-bg-tertiary text-cyber-text-secondary'
  return 'border-cyber-border-subtle bg-cyber-bg-tertiary/60 text-cyber-text-muted'
}


type OverviewSort = 'publishDesc' | 'publishAsc' | 'likesDesc' | 'likesAsc' | 'collectionsDesc' | 'collectionsAsc' | 'commentsDesc' | 'commentsAsc' | 'sharesDesc' | 'sharesAsc' | 'interactionDesc' | 'interactionAsc' | 'growthDesc' | 'growthAsc'
type LifecycleStage = 'latest' | '24h' | '72h' | '7d'
type PerformanceState = 'all' | 'comparable' | 'burst' | 'zero' | 'notReached' | 'missing' | 'deleted'
type CoverFilter = 'all' | 'withCover' | 'withoutCover'


const LIFECYCLE_SECONDS: Record<Exclude<LifecycleStage, 'latest'>, number> = {
  '24h': 24 * 60 * 60,
  '72h': 72 * 60 * 60,
  '7d': 7 * 24 * 60 * 60,
}


function stageSnapshot(post: MonitorDashboardPost, stage: LifecycleStage): MonitorSnapshot | undefined {
  if (stage === 'latest') return latestSnapshot(post)
  return [...post.snapshots]
    .filter((snapshot) => snapshot.stage === stage)
    .sort((left, right) => right.captured_at - left.captured_at)[0]
}


function interactionScore(snapshot: MonitorSnapshot | undefined): number {
  if (!snapshot) return 0
  return snapshot.liked_count + snapshot.comment_count + snapshot.collected_count + snapshot.share_count
}


function percentile(values: number[], ratio: number): number {
  if (!values.length) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const position = Math.min(sorted.length - 1, Math.max(0, (sorted.length - 1) * ratio))
  const lower = Math.floor(position)
  const upper = Math.ceil(position)
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower)
}


function lifecycleState(post: MonitorDashboardPost, stage: LifecycleStage, snapshot: MonitorSnapshot | undefined): Exclude<PerformanceState, 'all' | 'burst' | 'zero'> | 'noSnapshot' {
  if (post.status === 'deleted') return 'deleted'
  if (snapshot) return 'comparable'
  if (stage === 'latest') return 'noSnapshot'
  const ageSeconds = Date.now() / 1000 - post.create_time
  return ageSeconds < LIFECYCLE_SECONDS[stage] ? 'notReached' : 'missing'
}


function SortableHeader({ label, active, direction, numeric = false, sticky = false, toneClass = '', icon: Icon, onClick }: { label: string; active: boolean; direction: 'asc' | 'desc'; numeric?: boolean; sticky?: boolean; toneClass?: string; icon?: typeof Activity; onClick: () => void }) {
  const aligned = numeric
  return <th scope="col" aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'} data-numeric={numeric ? 'true' : undefined} className={`post-overview-head-cell px-3 py-2 ${sticky ? 'sticky left-0 z-30 min-w-[360px]' : ''} ${aligned ? '!text-center' : 'text-left'}`}><button type="button" data-active={active ? 'true' : 'false'} onClick={onClick} className={`post-overview-sort-button ${aligned ? 'mx-auto' : ''} ${active ? 'text-primary' : toneClass}`}><span aria-hidden="true" className="post-overview-header-icon">{Icon ? <Icon className="h-3.5 w-3.5" /> : null}</span><span>{label}</span>{active ? direction === 'desc' ? <ArrowDown aria-hidden="true" className="h-3 w-3" /> : <ArrowUp aria-hidden="true" className="h-3 w-3" /> : <ArrowUpDown aria-hidden="true" className="h-3 w-3 opacity-40" />}</button></th>
}


function MetricValue({ label, value, max, textClass, barClass }: { label: string; value: number | null; max: number; textClass: string; barClass: string }) {
  const width = value === null || max <= 0 ? 0 : Math.max(value > 0 ? 4 : 0, Math.min(100, value / max * 100))
  return (
    <div className="post-overview-metric" data-empty={value === null ? 'true' : 'false'} aria-label={`${label}: ${value === null ? '-' : formatNumber(value)}`}>
      <span className={`numeric-value text-sm font-semibold ${value === null ? 'text-cyber-text-muted' : textClass}`}>{value === null ? '-' : formatNumber(value)}</span>
      <span aria-hidden="true" className="post-overview-metric-track"><span className={`post-overview-metric-fill ${barClass}`} style={{ width: `${width}%` }} /></span>
    </div>
  )
}


function PostCover({ post }: { post: MonitorDashboardPost }) {
  const { t } = useTranslation('config')
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [post.cover_url])
  const image = post.cover_url && !failed ? (
    <img
      src={post.cover_url}
      alt={t('performance.coverAlt', { title: post.title || post.aweme_id })}
      width={64}
      height={48}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="h-full w-full object-cover transition-transform duration-200 motion-reduce:transition-none group-hover/cover:scale-[1.03]"
    />
  ) : (
    <span className="grid h-full w-full place-items-center bg-cyber-bg-tertiary text-cyber-text-muted" aria-label={t('performance.noCover')}>
      <ImageIcon aria-hidden="true" className="h-4 w-4" />
    </span>
  )

  return post.cover_url && !failed ? (
    <a
      href={post.cover_url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={t('performance.openCover', { title: post.title || post.aweme_id })}
      className="group/cover block h-12 w-16 shrink-0 overflow-hidden rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary shadow-sm outline-none transition-colors hover:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      {image}
    </a>
  ) : <span className="block h-12 w-16 shrink-0 overflow-hidden rounded-md border border-cyber-border-subtle">{image}</span>
}


export function MonitorPerformanceOverview({ posts, focusAwemeId, focusToken }: { posts: MonitorDashboardPost[]; focusAwemeId?: string; focusToken?: number }) {
  const { t } = useTranslation('config')
  const [activeStructureMetric, setActiveStructureMetric] = useState<'liked' | 'collected' | 'comment' | 'share' | null>(null)
  const [overviewSearch, setOverviewSearch] = useState('')
  const [overviewSort, setOverviewSort] = useState<OverviewSort>('publishDesc')
  const [lifecycleStage, setLifecycleStage] = useState<LifecycleStage>('latest')
  const [performanceState, setPerformanceState] = useState<PerformanceState>('all')
  const [coverFilter, setCoverFilter] = useState<CoverFilter>('all')
  const [overviewPage, setOverviewPage] = useState(1)
  const [detailPost, setDetailPost] = useState<MonitorDashboardPost>()
  const [detailCoverFailed, setDetailCoverFailed] = useState(false)
  const [highlightedAwemeId, setHighlightedAwemeId] = useState<string>()
  const handledFocusToken = useRef<number | undefined>()
  const analysisRows = posts.map((post) => {
    const snapshot = stageSnapshot(post, lifecycleStage)
    const state = lifecycleState(post, lifecycleStage, snapshot)
    return { post, snapshot, state, score: snapshot && state === 'comparable' ? interactionScore(snapshot) : null }
  })
  const comparableRows = analysisRows.filter((row) => row.state === 'comparable' && row.snapshot && row.score !== null)
  const interactions = comparableRows.map((row) => Number(row.score))
  const average = mean(interactions)
  const middle = median(interactions)
  const deviation = interactions.length > 1 ? Math.sqrt(interactions.reduce((sum, value) => sum + (value - average) ** 2, 0) / interactions.length) : 0
  const burstThreshold = Math.max(percentile(interactions, 0.9), average + deviation * 2, 1)
  const burstRows = comparableRows.filter((row) => Number(row.score) >= burstThreshold)
  const burstIds = new Set(burstRows.map((row) => row.post.aweme_id))
  const zeroRows = comparableRows.filter((row) => row.score === 0)
  const missingCount = analysisRows.filter((row) => row.state === 'missing' || row.state === 'noSnapshot').length
  const notReachedCount = analysisRows.filter((row) => row.state === 'notReached').length
  const deletedCount = analysisRows.filter((row) => row.state === 'deleted').length
  const delays = comparableRows.map((row) => firstSeenDelayHours(row.post))
  const selectedSnapshots = comparableRows.map((row) => row.snapshot)
  const structure = {
    liked: selectedSnapshots.reduce((sum, snapshot) => sum + (snapshot?.liked_count || 0), 0),
    collected: selectedSnapshots.reduce((sum, snapshot) => sum + (snapshot?.collected_count || 0), 0),
    comment: selectedSnapshots.reduce((sum, snapshot) => sum + (snapshot?.comment_count || 0), 0),
    share: selectedSnapshots.reduce((sum, snapshot) => sum + (snapshot?.share_count || 0), 0),
  }
  const structureTotal = structure.liked + structure.collected + structure.comment + structure.share
  const structureShares = {
    liked: structureTotal ? structure.liked / structureTotal * 100 : 0,
    collected: structureTotal ? structure.collected / structureTotal * 100 : 0,
    comment: structureTotal ? structure.comment / structureTotal * 100 : 0,
    share: structureTotal ? structure.share / structureTotal * 100 : 0,
  }
  const structureItems = [
    { key: 'liked' as const, label: t('monitorDashboard.metricLikes'), value: structure.liked, percent: structureShares.liked, barClass: 'bg-cyber-neon-cyan', borderClass: 'border-cyber-neon-cyan' },
    { key: 'collected' as const, label: t('monitorDashboard.metricCollections'), value: structure.collected, percent: structureShares.collected, barClass: 'bg-cyber-neon-purple', borderClass: 'border-cyber-neon-purple' },
    { key: 'comment' as const, label: t('monitorDashboard.metricComments'), value: structure.comment, percent: structureShares.comment, barClass: 'bg-cyber-neon-pink', borderClass: 'border-cyber-neon-pink' },
    { key: 'share' as const, label: t('monitorDashboard.metricShares'), value: structure.share, percent: structureShares.share, barClass: 'bg-cyber-neon-orange', borderClass: 'border-cyber-neon-orange' },
  ]
  const dominantStructure = structureItems.reduce((best, item) => item.value > best.value ? item : best, structureItems[0])
  const growthForPost = (post: MonitorDashboardPost) => {
    const snapshot24h = stageSnapshot(post, '24h')
    const snapshot72h = stageSnapshot(post, '72h')
    return snapshot24h && snapshot72h ? interactionScore(snapshot72h) - interactionScore(snapshot24h) : null
  }
  const overviewRows = useMemo(() => {
    const keyword = overviewSearch.trim().toLowerCase()
    const rows = posts.map((post) => {
      const snapshot = stageSnapshot(post, lifecycleStage)
      const state = lifecycleState(post, lifecycleStage, snapshot)
      const total = snapshot && state === 'comparable' ? interactionScore(snapshot) : null
      const growth = growthForPost(post)
      return { post, snapshot, state, total, growth }
    })
    const metricValue = (row: typeof rows[number], metric: 'liked_count' | 'collected_count' | 'comment_count' | 'share_count' | 'interaction' | 'growth') => {
      const { snapshot } = row
      if (metric === 'growth') return row.growth ?? Number.NEGATIVE_INFINITY
      if (metric === 'interaction') return row.total ?? Number.NEGATIVE_INFINITY
      if (!snapshot) return 0
      return snapshot[metric]
    }
    return rows
      .filter(({ post, state, total }) => {
        if (keyword && !(post.title || '').toLowerCase().includes(keyword) && !post.aweme_id.toLowerCase().includes(keyword)) return false
        if (coverFilter === 'withCover' && !post.cover_url) return false
        if (coverFilter === 'withoutCover' && post.cover_url) return false
        if (performanceState === 'comparable' && state !== 'comparable') return false
        if (performanceState === 'burst' && !burstIds.has(post.aweme_id)) return false
        if (performanceState === 'zero' && !(state === 'comparable' && total === 0)) return false
        if (performanceState === 'notReached' && state !== 'notReached') return false
        if (performanceState === 'missing' && state !== 'missing' && state !== 'noSnapshot') return false
        if (performanceState === 'deleted' && state !== 'deleted') return false
        return true
      })
      .sort((left, right) => {
        if (overviewSort === 'publishAsc') return left.post.create_time - right.post.create_time
        if (overviewSort === 'publishDesc') return right.post.create_time - left.post.create_time
        const metric = overviewSort.startsWith('likes') ? 'liked_count' : overviewSort.startsWith('collections') ? 'collected_count' : overviewSort.startsWith('comments') ? 'comment_count' : overviewSort.startsWith('shares') ? 'share_count' : overviewSort.startsWith('growth') ? 'growth' : 'interaction'
        const difference = metricValue(right, metric) - metricValue(left, metric)
        return overviewSort.endsWith('Asc') ? -difference : difference
      })
  }, [burstThreshold, coverFilter, lifecycleStage, overviewSearch, overviewSort, performanceState, posts])
  const metricMaximums = useMemo(() => ({
    likes: Math.max(1, percentile(overviewRows.map((row) => row.snapshot?.liked_count || 0), 0.95)),
    collections: Math.max(1, percentile(overviewRows.map((row) => row.snapshot?.collected_count || 0), 0.95)),
    comments: Math.max(1, percentile(overviewRows.map((row) => row.snapshot?.comment_count || 0), 0.95)),
    shares: Math.max(1, percentile(overviewRows.map((row) => row.snapshot?.share_count || 0), 0.95)),
    total: Math.max(1, percentile(overviewRows.map((row) => row.total || 0), 0.95)),
    growth: Math.max(1, percentile(overviewRows.map((row) => Math.max(0, row.growth || 0)), 0.95)),
  }), [overviewRows])
  const pageSize = 50
  const pageCount = Math.max(1, Math.ceil(overviewRows.length / pageSize))
  const currentPage = Math.min(overviewPage, pageCount)
  const displayedRows = overviewRows.slice((currentPage - 1) * pageSize, currentPage * pageSize)

  const toggleOverviewSort = (group: 'publish' | 'likes' | 'collections' | 'comments' | 'shares' | 'interaction' | 'growth') => {
    setOverviewSort((current) => {
      const desc = `${group}Desc` as OverviewSort
      const asc = `${group}Asc` as OverviewSort
      return current === desc ? asc : desc
    })
  }

  useEffect(() => setOverviewPage(1), [coverFilter, lifecycleStage, overviewSearch, overviewSort, performanceState])

  useEffect(() => setDetailCoverFailed(false), [detailPost?.aweme_id, detailPost?.cover_url])

  useEffect(() => {
    if (!focusAwemeId || focusToken === undefined || handledFocusToken.current === focusToken) return
    handledFocusToken.current = focusToken
    setOverviewSearch(focusAwemeId)
    setHighlightedAwemeId(focusAwemeId)
    const scrollTimer = window.setTimeout(() => {
      const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
      Array.from(document.querySelectorAll<HTMLElement>('[data-aweme-id]'))
        .find((element) => element.dataset.awemeId === focusAwemeId)
        ?.scrollIntoView({ block: 'center', behavior })
    }, 80)
    const highlightTimer = window.setTimeout(() => setHighlightedAwemeId(undefined), 3200)
    return () => {
      window.clearTimeout(scrollTimer)
      window.clearTimeout(highlightTimer)
    }
  }, [focusAwemeId, focusToken])

  const meanMedianRatio = middle > 0 ? average / middle : 0
  const topTenInteraction = [...comparableRows].sort((left, right) => Number(right.score) - Number(left.score)).slice(0, 10).reduce((sum, row) => sum + Number(row.score), 0)
  const totalInteraction = interactions.reduce((sum, value) => sum + value, 0)
  const concentration = totalInteraction > 0 ? topTenInteraction / totalInteraction * 100 : 0
  const kpis = [
    { label: t('performance.comparablePosts'), value: formatNumber(comparableRows.length), icon: BarChart3, tone: 'text-cyber-neon-cyan' },
    { label: t('performance.medianInteraction'), value: formatNumber(middle), icon: Gauge, tone: 'text-cyber-neon-purple' },
    { label: t('performance.burstRate'), value: `${comparableRows.length ? (burstRows.length / comparableRows.length * 100).toFixed(1) : '0.0'}%`, icon: Flame, tone: 'text-cyber-neon-pink' },
    { label: t('performance.topTenConcentration'), value: `${concentration.toFixed(1)}%`, icon: TrendingUp, tone: 'text-cyber-neon-green' },
  ]
  const detailSnapshot = detailPost ? stageSnapshot(detailPost, lifecycleStage) : undefined
  const detailState = detailPost ? lifecycleState(detailPost, lifecycleStage, detailSnapshot) : undefined
  const detailSnapshots = detailPost ? [...detailPost.snapshots].sort((left, right) => left.actual_age_seconds - right.actual_age_seconds) : []
  const detailGrowth = detailPost ? growthForPost(detailPost) : null

  return (
    <div className="flex flex-col space-y-3">
      <section className="overview-panel p-3" aria-label={t('performance.comparisonSettings')}>
        <div className="grid gap-3 md:grid-cols-[minmax(16rem,0.7fr)_minmax(0,1.3fr)] md:items-end">
          <div className="grid gap-1 text-xs font-medium text-cyber-text-secondary"><span id="performance-lifecycle-label">{t('performance.lifecycleLabel')}</span><Select value={lifecycleStage} onValueChange={(value) => setLifecycleStage(value as LifecycleStage)}><SelectTrigger aria-labelledby="performance-lifecycle-label" className="h-10"><SelectValue /></SelectTrigger><SelectContent>{(['24h', '72h', '7d', 'latest'] as const).map((stage) => <SelectItem key={stage} value={stage}>{t(`performance.lifecycle.${stage}`)}</SelectItem>)}</SelectContent></Select></div>
          <p className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary/35 px-3 py-2 text-xs leading-5 text-cyber-text-muted">{t('performance.rawFormula')}</p>
        </div>
      </section>
      <section className={`rounded-lg border p-4 ${meanMedianRatio >= 1.5 ? 'border-cyber-neon-orange/35 bg-cyber-neon-orange/5' : 'border-cyber-neon-cyan/30 bg-cyber-neon-cyan/5'}`}>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="text-sm font-semibold text-cyber-text-primary">{t(meanMedianRatio >= 1.5 ? 'performance.meanMedianAlert' : 'performance.distributionStable')}</div>
          <div className="flex flex-wrap gap-4 text-xs text-cyber-text-secondary">
            <span>{t('performance.averageInteraction')}: <b className="numeric-value">{formatNumber(average)}</b></span>
            <span>{t('performance.medianInteraction')}: <b className="numeric-value">{formatNumber(middle)}</b></span>
            <span>{t('performance.meanMedianRatio')}: <b className="numeric-value">{meanMedianRatio.toFixed(2)}x</b></span>
            <span>{t('performance.topTenConcentration')}: <b className="numeric-value">{concentration.toFixed(1)}%</b></span>
          </div>
        </div>
        <p className="mt-2 text-xs text-cyber-text-muted">{t('performance.concentrationHint')}</p>
      </section>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {kpis.map((item) => (
          <div key={item.label} className="metric-surface-card p-3">
            <div className="flex items-center gap-2 text-xs text-cyber-text-muted"><item.icon aria-hidden="true" className="h-3.5 w-3.5" />{item.label}</div>
            <div className={`mt-2 text-xl font-semibold numeric-value ${item.tone}`}>{item.value}</div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2 rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel px-4 py-3 text-xs text-cyber-text-secondary"><span>{t('performance.allPosts')}: <b className="numeric-value text-cyber-text-primary">{posts.length}</b></span><span>{t('performance.notReached')}: <b className="numeric-value text-status-info">{notReachedCount}</b></span><span>{t('performance.missingSnapshot')}: <b className="numeric-value text-status-warning">{missingCount}</b></span><span>{t('performance.zeroInteraction')}: <b className="numeric-value text-cyber-text-primary">{zeroRows.length}</b></span><span>{t('performance.deletedPosts')}: <b className="numeric-value text-status-danger">{deletedCount}</b></span><span>{t('performance.firstSeenDelay')}: <b className="numeric-value text-cyber-text-primary">{formatNumber(median(delays))}h</b></span></div>

      <section className="overview-panel post-overview-panel order-3 overflow-hidden">
        <div className="overview-panel-header min-h-0 flex-col items-stretch gap-3 py-3 2xl:flex-row 2xl:items-end 2xl:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary"><BarChart3 aria-hidden="true" className="h-4 w-4" /></span>
            <div className="min-w-0"><div className="overview-panel-title">{t('performance.postOverview')}</div><div className="overview-panel-description">{t('performance.postOverviewHint')}</div></div>
            <div className="ml-auto flex shrink-0 flex-col items-end gap-1 xl:ml-2"><Badge variant="secondary">{t('performance.postOverviewCount', { count: overviewRows.length })}</Badge><span className="hidden text-[10px] text-cyber-text-muted sm:block">{t('performance.metricScaleHint')}</span></div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <label className="grid gap-1 text-[11px] font-medium text-cyber-text-secondary">
              {t('performance.searchLabel')}
              <span className="relative"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cyber-text-muted" /><Input type="search" aria-label={t('performance.searchLabel')} value={overviewSearch} onChange={(event) => setOverviewSearch(event.target.value)} placeholder={t('performance.postSearchPlaceholder')} className="h-9 pl-9 text-xs" /></span>
            </label>
            <div className="grid gap-1 text-[11px] font-medium text-cyber-text-secondary">
              <span id="post-overview-sort-label">{t('performance.sortLabel')}</span>
              <Select value={overviewSort} onValueChange={(value) => setOverviewSort(value as OverviewSort)}><SelectTrigger aria-labelledby="post-overview-sort-label" className="h-9 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="publishDesc">{t('performance.sort.publishDesc')}</SelectItem><SelectItem value="publishAsc">{t('performance.sort.publishAsc')}</SelectItem><SelectItem value="likesDesc">{t('performance.sort.likesDesc')}</SelectItem><SelectItem value="likesAsc">{t('performance.sort.likesAsc')}</SelectItem><SelectItem value="collectionsDesc">{t('performance.sort.collectionsDesc')}</SelectItem><SelectItem value="collectionsAsc">{t('performance.sort.collectionsAsc')}</SelectItem><SelectItem value="commentsDesc">{t('performance.sort.commentsDesc')}</SelectItem><SelectItem value="commentsAsc">{t('performance.sort.commentsAsc')}</SelectItem><SelectItem value="sharesDesc">{t('performance.sort.sharesDesc')}</SelectItem><SelectItem value="sharesAsc">{t('performance.sort.sharesAsc')}</SelectItem><SelectItem value="interactionDesc">{t('performance.sort.interactionDesc')}</SelectItem><SelectItem value="interactionAsc">{t('performance.sort.interactionAsc')}</SelectItem><SelectItem value="growthDesc">{t('performance.sort.growthDesc')}</SelectItem><SelectItem value="growthAsc">{t('performance.sort.growthAsc')}</SelectItem></SelectContent></Select>
            </div>
            <div className="grid gap-1 text-[11px] font-medium text-cyber-text-secondary"><span id="post-overview-state-label">{t('performance.stateFilter')}</span><Select value={performanceState} onValueChange={(value) => setPerformanceState(value as PerformanceState)}><SelectTrigger aria-labelledby="post-overview-state-label" className="h-9 text-xs"><SelectValue /></SelectTrigger><SelectContent>{(['all', 'comparable', 'burst', 'zero', 'notReached', 'missing', 'deleted'] as const).map((state) => <SelectItem key={state} value={state}>{t(`performance.state.${state}`)}</SelectItem>)}</SelectContent></Select></div>
            <div className="grid gap-1 text-[11px] font-medium text-cyber-text-secondary"><span id="post-overview-cover-label">{t('performance.coverFilter')}</span><Select value={coverFilter} onValueChange={(value) => setCoverFilter(value as CoverFilter)}><SelectTrigger aria-labelledby="post-overview-cover-label" className="h-9 text-xs"><SelectValue /></SelectTrigger><SelectContent>{(['all', 'withCover', 'withoutCover'] as const).map((value) => <SelectItem key={value} value={value}>{t(`performance.coverState.${value}`)}</SelectItem>)}</SelectContent></Select></div>
          </div>
        </div>

        <div className="hidden lg:block">
          <div className="data-table-frame post-overview-frame max-h-[540px] rounded-none border-0 shadow-none">
            <table className="data-table post-overview-table w-full min-w-[1120px] text-xs">
              <caption className="sr-only">{t('performance.tableCaption')}</caption>
              <colgroup><col className="w-[34%]" /><col className="w-[11%]" /><col className="w-[11%]" /><col className="w-[11%]" /><col className="w-[11%]" /><col className="w-[11%]" /><col className="w-[11%]" /></colgroup>
              <thead className="sticky top-0 z-20 text-left backdrop-blur">
                <tr><SortableHeader label={t('performance.postAndPublish')} active={overviewSort.startsWith('publish')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} sticky icon={Clock3} onClick={() => toggleOverviewSort('publish')} /><SortableHeader label={t('monitorDashboard.metricLikes')} active={overviewSort.startsWith('likes')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Heart} toneClass="text-status-info" onClick={() => toggleOverviewSort('likes')} /><SortableHeader label={t('monitorDashboard.metricCollections')} active={overviewSort.startsWith('collections')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Bookmark} toneClass="text-status-purple" onClick={() => toggleOverviewSort('collections')} /><SortableHeader label={t('monitorDashboard.metricComments')} active={overviewSort.startsWith('comments')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={MessageSquare} toneClass="text-cyber-neon-pink" onClick={() => toggleOverviewSort('comments')} /><SortableHeader label={t('monitorDashboard.metricShares')} active={overviewSort.startsWith('shares')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Share2} toneClass="text-status-warning" onClick={() => toggleOverviewSort('shares')} /><SortableHeader label={t('performance.totalInteraction')} active={overviewSort.startsWith('interaction')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Activity} toneClass="text-status-success" onClick={() => toggleOverviewSort('interaction')} /><SortableHeader label={t('performance.growth24to72')} active={overviewSort.startsWith('growth')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={TrendingUp} toneClass="text-primary" onClick={() => toggleOverviewSort('growth')} /></tr>
              </thead>
              <tbody>
                {displayedRows.map(({ post, snapshot, state, total, growth }, index) => (
                  <tr key={post.aweme_id} data-aweme-id={post.aweme_id} data-selected={highlightedAwemeId === post.aweme_id ? 'true' : undefined} className="group">
                    <td className="post-overview-primary-cell sticky left-0 z-10 max-w-[420px] px-4 py-3">
                      <div className="flex min-w-0 items-start gap-3"><span aria-hidden="true" className="post-overview-index font-mono">{String((currentPage - 1) * pageSize + index + 1).padStart(2, '0')}</span><PostCover post={post} /><div className="min-w-0 flex-1"><div className="flex min-w-0 items-center gap-2"><button type="button" onClick={() => setDetailPost(post)} title={post.title || post.aweme_id} className="min-w-0 flex-1 cursor-pointer truncate text-left text-sm font-semibold text-cyber-text-primary outline-none transition-colors hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-primary/40">{post.title || post.aweme_id}</button>{post.canonical_url ? <a href={post.canonical_url} target="_blank" rel="noopener noreferrer" aria-label={t('performance.openPost', { title: post.title || post.aweme_id })} className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-cyber-text-muted hover:bg-cyber-bg-tertiary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"><ExternalLink aria-hidden="true" className="h-3.5 w-3.5" /></a> : null}<span className={`status-chip shrink-0 ${stageBadgeClass(snapshot?.stage)}`}>{snapshot?.stage || t(`performance.rowState.${state}`)}</span></div><div className="mt-1.5 flex min-w-0 items-center gap-3 text-[11px] text-cyber-text-muted"><span className="inline-flex shrink-0 items-center gap-1"><Clock3 aria-hidden="true" className="h-3 w-3" />{formatPublishedAt(post.create_time)}</span><span title={post.aweme_id} className="truncate font-mono">ID {post.aweme_id}</span></div></div></div>
                    </td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('monitorDashboard.metricLikes')} value={snapshot?.liked_count ?? null} max={metricMaximums.likes} textClass="text-status-info" barClass="bg-status-info" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('monitorDashboard.metricCollections')} value={snapshot?.collected_count ?? null} max={metricMaximums.collections} textClass="text-status-purple" barClass="bg-status-purple" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('monitorDashboard.metricComments')} value={snapshot?.comment_count ?? null} max={metricMaximums.comments} textClass="text-cyber-neon-pink" barClass="bg-cyber-neon-pink" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('monitorDashboard.metricShares')} value={snapshot?.share_count ?? null} max={metricMaximums.shares} textClass="text-status-warning" barClass="bg-status-warning" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell post-overview-total-cell px-3 py-3"><MetricValue label={t('performance.totalInteraction')} value={total} max={metricMaximums.total} textClass="text-status-success" barClass="bg-status-success" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('performance.growth24to72')} value={growth} max={metricMaximums.growth} textClass={Number(growth || 0) >= 0 ? 'text-primary' : 'text-status-danger'} barClass={Number(growth || 0) >= 0 ? 'bg-primary' : 'bg-status-danger'} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="max-h-[540px] space-y-3 overflow-y-auto overscroll-contain p-3 lg:hidden" tabIndex={0} role="region" aria-label={t('performance.postOverview')}>
          {displayedRows.map(({ post, snapshot, state, total, growth }, index) => (
            <article key={post.aweme_id} data-aweme-id={post.aweme_id} data-selected={highlightedAwemeId === post.aweme_id ? 'true' : undefined} className="metric-surface-card post-overview-card p-3 data-[selected=true]:border-primary/50 data-[selected=true]:ring-2 data-[selected=true]:ring-primary/15">
              <div className="flex min-w-0 items-start gap-2"><span aria-hidden="true" className="post-overview-index font-mono">{String((currentPage - 1) * pageSize + index + 1).padStart(2, '0')}</span><PostCover post={post} /><button type="button" onClick={() => setDetailPost(post)} className="min-w-0 flex-1 cursor-pointer text-left text-sm font-semibold leading-5 text-cyber-text-primary hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">{post.title || post.aweme_id}</button><span className={`status-chip shrink-0 ${stageBadgeClass(snapshot?.stage)}`}>{snapshot?.stage || t(`performance.rowState.${state}`)}</span></div>
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-cyber-text-muted"><span className="inline-flex items-center gap-1"><Clock3 aria-hidden="true" className="h-3 w-3" />{formatPublishedAt(post.create_time)}</span><span className="break-all font-mono">ID {post.aweme_id}</span></div>
              <dl className="mt-3 grid grid-cols-2 gap-2">
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricLikes')}</dt><dd><MetricValue label={t('monitorDashboard.metricLikes')} value={snapshot?.liked_count ?? null} max={metricMaximums.likes} textClass="text-status-info" barClass="bg-status-info" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricCollections')}</dt><dd><MetricValue label={t('monitorDashboard.metricCollections')} value={snapshot?.collected_count ?? null} max={metricMaximums.collections} textClass="text-status-purple" barClass="bg-status-purple" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricComments')}</dt><dd><MetricValue label={t('monitorDashboard.metricComments')} value={snapshot?.comment_count ?? null} max={metricMaximums.comments} textClass="text-cyber-neon-pink" barClass="bg-cyber-neon-pink" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricShares')}</dt><dd><MetricValue label={t('monitorDashboard.metricShares')} value={snapshot?.share_count ?? null} max={metricMaximums.shares} textClass="text-status-warning" barClass="bg-status-warning" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('performance.totalInteraction')}</dt><dd><MetricValue label={t('performance.totalInteraction')} value={total} max={metricMaximums.total} textClass="text-status-success" barClass="bg-status-success" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('performance.growth24to72')}</dt><dd><MetricValue label={t('performance.growth24to72')} value={growth} max={metricMaximums.growth} textClass="text-primary" barClass="bg-primary" /></dd></div>
              </dl>
            </article>
          ))}
        </div>
        {overviewRows.length === 0 ? <div className="px-4 py-12 text-center text-sm text-cyber-text-muted">{t('performance.noMatchingPosts')}</div> : null}
        {overviewRows.length > 0 ? <div className="flex items-center justify-between gap-3 border-t border-cyber-border-subtle px-4 py-3"><span className="text-xs text-cyber-text-muted">{t('performance.pageInfo', { page: currentPage, total: pageCount, count: overviewRows.length })}</span><div className="flex gap-2"><Button type="button" variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setOverviewPage((page) => Math.max(1, page - 1))} className="min-h-9"><ChevronLeft aria-hidden="true" className="h-4 w-4" />{t('performance.previousPage')}</Button><Button type="button" variant="outline" size="sm" disabled={currentPage >= pageCount} onClick={() => setOverviewPage((page) => Math.min(pageCount, page + 1))} className="min-h-9">{t('performance.nextPage')}<ChevronRight aria-hidden="true" className="h-4 w-4" /></Button></div></div> : null}
      </section>

      <div className="order-2 space-y-3">
        <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold text-cyber-text-primary">{t('performance.structure')}</div>
              <div className="mt-1 text-[9px] text-cyber-text-muted">{t('performance.structureHint')}</div>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px] text-cyber-text-secondary">
              <span>{t('performance.totalInteraction')}: <b className="numeric-value text-cyber-text-primary">{formatNumber(structureTotal)}</b></span>
              {structureTotal > 0 ? <span>{t('performance.structureDominant', { metric: dominantStructure.label, percent: dominantStructure.percent.toFixed(1) })}</span> : null}
            </div>
          </div>

          <div className="mt-4 flex h-7 overflow-hidden rounded-md bg-cyber-bg-tertiary" onMouseLeave={() => setActiveStructureMetric(null)}>
            {structureItems.map((item) => (
              <div
                key={item.key}
                className={`relative flex min-w-0 items-center justify-center transition-opacity ${item.barClass} ${activeStructureMetric && activeStructureMetric !== item.key ? 'opacity-40' : 'opacity-100'}`}
                style={{ width: `${item.percent}%` }}
                title={`${item.label}: ${formatNumber(item.value)} (${item.percent.toFixed(1)}%)`}
                onMouseEnter={() => setActiveStructureMetric(item.key)}
              >
                {item.percent >= 10 ? <span className="truncate px-2 text-[9px] font-semibold text-cyber-bg-primary">{item.label} {item.percent.toFixed(1)}%</span> : null}
              </div>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 lg:grid-cols-4">
            {structureItems.map((item) => (
              <button
                key={item.key}
                type="button"
                aria-pressed={activeStructureMetric === item.key}
                className={`min-h-14 rounded-sm border-t-2 px-1 pt-2 text-left outline-none transition-all focus-visible:ring-2 focus-visible:ring-primary/40 ${item.borderClass} ${activeStructureMetric && activeStructureMetric !== item.key ? 'opacity-40' : 'opacity-100'} ${activeStructureMetric === item.key ? 'bg-cyber-bg-tertiary/25' : ''}`}
                onMouseEnter={() => setActiveStructureMetric(item.key)}
                onMouseLeave={() => setActiveStructureMetric(null)}
                onFocus={() => setActiveStructureMetric(item.key)}
                onBlur={() => setActiveStructureMetric(null)}
                onClick={() => setActiveStructureMetric((current) => current === item.key ? null : item.key)}
              >
                <div className="text-[10px] text-cyber-text-muted">{item.label}</div>
                <div className="mt-1 text-sm font-semibold numeric-value text-cyber-text-primary">{formatNumber(item.value)}</div>
                <div className="mt-0.5 text-[10px] font-medium numeric-value text-cyber-text-secondary">{item.percent.toFixed(1)}%</div>
              </button>
            ))}
          </div>
        </section>

      </div>

      <Dialog open={Boolean(detailPost)} onOpenChange={(open) => !open && setDetailPost(undefined)}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto border-cyber-border-subtle bg-cyber-bg-panel">
          <DialogHeader>
            <DialogTitle className="pr-8 text-left text-cyber-text-primary">{detailPost?.title || detailPost?.aweme_id}</DialogTitle>
            <DialogDescription className="text-left text-cyber-text-muted">{detailPost ? `${formatPublishedAt(detailPost.create_time)} · ID ${detailPost.aweme_id}` : ''}</DialogDescription>
          </DialogHeader>
          {detailPost ? <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-[13rem_minmax(0,1fr)]"><div className="aspect-video overflow-hidden rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary">{detailPost.cover_url && !detailCoverFailed ? <img src={detailPost.cover_url} alt={t('performance.coverAlt', { title: detailPost.title || detailPost.aweme_id })} width={208} height={117} className="h-full w-full object-cover" decoding="async" referrerPolicy="no-referrer" onError={() => setDetailCoverFailed(true)} /> : <div className="grid h-full place-items-center gap-2 text-xs text-cyber-text-muted"><ImageIcon aria-hidden="true" className="h-6 w-6" /><span>{t('performance.noCover')}</span></div>}</div><div className="grid grid-cols-2 gap-2"><div className="metric-surface-card p-3"><span className="text-xs text-cyber-text-muted">{t('performance.currentState')}</span><b className="mt-2 block text-sm text-cyber-text-primary">{detailSnapshot?.stage || (detailState ? t(`performance.rowState.${detailState}`) : '—')}</b></div><div className="metric-surface-card p-3"><span className="text-xs text-cyber-text-muted">{t('performance.totalInteraction')}</span><b className="mt-2 block text-lg numeric-value text-status-success">{detailSnapshot ? formatNumber(interactionScore(detailSnapshot)) : '—'}</b></div><div className="metric-surface-card p-3"><span className="text-xs text-cyber-text-muted">{t('performance.growth24to72')}</span><b className="mt-2 block text-lg numeric-value text-primary">{detailGrowth == null ? '—' : formatNumber(detailGrowth)}</b></div><div className="metric-surface-card p-3"><span className="text-xs text-cyber-text-muted">{t('performance.firstSeenDelay')}</span><b className="mt-2 block text-lg numeric-value text-cyber-text-primary">{formatNumber(firstSeenDelayHours(detailPost))}h</b></div></div></div>
            {detailPost.canonical_url ? <a href={detailPost.canonical_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"><ExternalLink aria-hidden="true" className="h-4 w-4" />{t('performance.openPostAction')}</a> : <Badge variant="outline">{t('performance.noPostLink')}</Badge>}
            <div><h3 className="text-sm font-semibold text-cyber-text-primary">{t('performance.snapshotHistory')}</h3>{detailSnapshots.length ? <div className="mt-2 overflow-x-auto rounded-lg border border-cyber-border-subtle"><table className="w-full min-w-[620px] text-xs"><thead className="bg-cyber-bg-tertiary/50 text-cyber-text-secondary"><tr><th className="px-3 py-2 text-left">{t('performance.latestStage')}</th><th className="px-3 py-2 text-right">{t('monitorDashboard.metricLikes')}</th><th className="px-3 py-2 text-right">{t('monitorDashboard.metricCollections')}</th><th className="px-3 py-2 text-right">{t('monitorDashboard.metricComments')}</th><th className="px-3 py-2 text-right">{t('monitorDashboard.metricShares')}</th><th className="px-3 py-2 text-right">{t('performance.totalInteraction')}</th></tr></thead><tbody className="divide-y divide-cyber-border-subtle">{detailSnapshots.map((snapshot) => <tr key={`${snapshot.stage}-${snapshot.captured_at}`}><td className="px-3 py-2 text-cyber-text-primary">{snapshot.stage}</td><td className="px-3 py-2 text-right numeric-value">{formatNumber(snapshot.liked_count)}</td><td className="px-3 py-2 text-right numeric-value">{formatNumber(snapshot.collected_count)}</td><td className="px-3 py-2 text-right numeric-value">{formatNumber(snapshot.comment_count)}</td><td className="px-3 py-2 text-right numeric-value">{formatNumber(snapshot.share_count)}</td><td className="px-3 py-2 text-right font-semibold numeric-value text-status-success">{formatNumber(interactionScore(snapshot))}</td></tr>)}</tbody></table></div> : <div className="mt-2 rounded-lg border border-dashed border-cyber-border-subtle px-4 py-8 text-center text-xs text-cyber-text-muted">{t('performance.noSnapshotHistory')}</div>}</div>
          </div> : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}
