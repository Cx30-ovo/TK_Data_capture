import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, ArrowDown, ArrowUp, ArrowUpDown, BarChart3, Bookmark, CalendarRange, ChevronLeft, ChevronRight, Clock3, Crosshair, ExternalLink, Flame, Gauge, Heart, ImageIcon, MessageSquare, Search, Share2, Sparkles, TrendingUp } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { MonitorDashboardPost, MonitorSnapshot } from '@/lib/api'
import { classifyTheme, firstSeenDelayHours, latestSnapshot, mean, median, THEME_COLORS } from '@/lib/monitorMetrics'


function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
}


function logTicks(maxValue: number): number[] {
  const max = Math.max(1, maxValue)
  const ticks: number[] = []
  for (let value = 1; value <= max; value *= 10) {
    ticks.push(value)
    if (ticks.length >= 5) break
  }
  if (ticks[ticks.length - 1] !== max) ticks.push(max)
  return ticks
}


function formatCompactNumber(value: number): string {
  if (value >= 100000000) return `${(value / 100000000).toFixed(1)}亿`
  if (value >= 100000) return `${(value / 10000).toFixed(1)}万`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(Math.round(value))
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
type QuadrantKey = 'highHigh' | 'highLow' | 'lowHigh' | 'lowLow'
type QuadrantTimeRange = '24h' | '7d' | '30d' | 'all'
type LifecycleStage = 'latest' | '24h' | '72h' | '7d'
type InteractionMode = 'raw' | 'weighted'
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


function interactionScore(snapshot: MonitorSnapshot | undefined, mode: InteractionMode): number {
  if (!snapshot) return 0
  if (mode === 'weighted') return snapshot.liked_count + snapshot.comment_count * 2 + snapshot.collected_count * 2 + snapshot.share_count * 3
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


function pearsonCorrelation(points: Array<[number, number]>): number | null {
  if (points.length < 3) return null
  const xs = points.map(([x]) => Math.log10(x + 1))
  const ys = points.map(([, y]) => Math.log10(y + 1))
  const meanX = mean(xs)
  const meanY = mean(ys)
  const numerator = points.reduce((sum, _point, index) => sum + (xs[index] - meanX) * (ys[index] - meanY), 0)
  const denominatorX = Math.sqrt(xs.reduce((sum, value) => sum + (value - meanX) ** 2, 0))
  const denominatorY = Math.sqrt(ys.reduce((sum, value) => sum + (value - meanY) ** 2, 0))
  const denominator = denominatorX * denominatorY
  return denominator > 0 ? numerator / denominator : null
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
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('raw')
  const [performanceState, setPerformanceState] = useState<PerformanceState>('all')
  const [coverFilter, setCoverFilter] = useState<CoverFilter>('all')
  const [overviewPage, setOverviewPage] = useState(1)
  const [detailPost, setDetailPost] = useState<MonitorDashboardPost>()
  const [detailCoverFailed, setDetailCoverFailed] = useState(false)
  const [highlightedAwemeId, setHighlightedAwemeId] = useState<string>()
  const [activeQuadrantPostId, setActiveQuadrantPostId] = useState<string>()
  const [selectedQuadrantKey, setSelectedQuadrantKey] = useState<QuadrantKey>()
  const [highlightedTheme, setHighlightedTheme] = useState<string>()
  const [quadrantTimeRange, setQuadrantTimeRange] = useState<QuadrantTimeRange>('all')
  const handledFocusToken = useRef<number | undefined>()
  const analysisRows = posts.map((post) => {
    const snapshot = stageSnapshot(post, lifecycleStage)
    const state = lifecycleState(post, lifecycleStage, snapshot)
    return { post, snapshot, state, score: snapshot && state === 'comparable' ? interactionScore(snapshot, interactionMode) : null }
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
    return snapshot24h && snapshot72h ? interactionScore(snapshot72h, interactionMode) - interactionScore(snapshot24h, interactionMode) : null
  }
  const overviewRows = useMemo(() => {
    const keyword = overviewSearch.trim().toLowerCase()
    const rows = posts.map((post) => {
      const snapshot = stageSnapshot(post, lifecycleStage)
      const state = lifecycleState(post, lifecycleStage, snapshot)
      const total = snapshot && state === 'comparable' ? interactionScore(snapshot, interactionMode) : null
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
  }, [burstThreshold, coverFilter, interactionMode, lifecycleStage, overviewSearch, overviewSort, performanceState, posts])
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

  useEffect(() => setOverviewPage(1), [coverFilter, interactionMode, lifecycleStage, overviewSearch, overviewSort, performanceState])

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

  const quadrantPosts = useMemo(() => {
    const comparablePosts = posts.filter((post) => lifecycleState(post, lifecycleStage, stageSnapshot(post, lifecycleStage)) === 'comparable')
    if (quadrantTimeRange === 'all') return comparablePosts
    const rangeHours = quadrantTimeRange === '24h' ? 24 : quadrantTimeRange === '7d' ? 24 * 7 : 24 * 30
    const cutoff = Date.now() / 1000 - rangeHours * 60 * 60
    return comparablePosts.filter((post) => post.create_time >= cutoff)
  }, [lifecycleStage, posts, quadrantTimeRange])
  const scoreForPost = (post: MonitorDashboardPost) => interactionScore(stageSnapshot(post, lifecycleStage), interactionMode)
  const quadrantInteractions = quadrantPosts.map(scoreForPost)

  const meanMedianRatio = middle > 0 ? average / middle : 0
  const topTenInteraction = [...comparableRows].sort((left, right) => Number(right.score) - Number(left.score)).slice(0, 10).reduce((sum, row) => sum + Number(row.score), 0)
  const totalInteraction = interactions.reduce((sum, value) => sum + value, 0)
  const concentration = totalInteraction > 0 ? topTenInteraction / totalInteraction * 100 : 0
  const maxLikes = Math.max(...quadrantPosts.map((post) => stageSnapshot(post, lifecycleStage)?.liked_count || 0), 1)
  const maxComments = Math.max(...quadrantPosts.map((post) => stageSnapshot(post, lifecycleStage)?.comment_count || 0), 1)
  const medianLikes = median(quadrantPosts.map((post) => stageSnapshot(post, lifecycleStage)?.liked_count || 0))
  const medianComments = median(quadrantPosts.map((post) => stageSnapshot(post, lifecycleStage)?.comment_count || 0))
  const likesCommentsCorrelation = pearsonCorrelation(quadrantPosts.map((post) => {
    const snapshot = stageSnapshot(post, lifecycleStage)
    return [snapshot?.liked_count || 0, snapshot?.comment_count || 0]
  }))
  const correlationKey = likesCommentsCorrelation == null
    ? 'noData'
    : likesCommentsCorrelation >= 0.7
      ? 'strongPositive'
      : likesCommentsCorrelation >= 0.4
        ? 'moderatePositive'
        : likesCommentsCorrelation >= 0.2
          ? 'weakPositive'
          : likesCommentsCorrelation <= -0.2
            ? 'negative'
            : 'none'
  const logMaxLikes = Math.log10(maxLikes + 1)
  const logMaxComments = Math.log10(maxComments + 1)
  const plotMinimum = 6
  const plotMaximum = 96
  const plotSpan = plotMaximum - plotMinimum
  const xPosition = (likes: number) => plotMinimum + Math.log10(likes + 1) / logMaxLikes * plotSpan
  const yPosition = (comments: number) => plotMinimum + Math.log10(comments + 1) / logMaxComments * plotSpan
  const medianX = xPosition(medianLikes)
  const medianY = yPosition(medianComments)
  const xTicks = logTicks(maxLikes)
  const yTicks = logTicks(maxComments)
  const topRightExtreme = [...quadrantPosts]
    .filter((post) => (stageSnapshot(post, lifecycleStage)?.liked_count || 0) >= medianLikes && (stageSnapshot(post, lifecycleStage)?.comment_count || 0) >= medianComments)
    .sort((left, right) => scoreForPost(right) - scoreForPost(left))[0]
  const bottomRightExtreme = [...quadrantPosts]
    .filter((post) => (stageSnapshot(post, lifecycleStage)?.liked_count || 0) >= medianLikes && (stageSnapshot(post, lifecycleStage)?.comment_count || 0) < medianComments)
    .sort((left, right) => (stageSnapshot(right, lifecycleStage)?.liked_count || 0) - (stageSnapshot(left, lifecycleStage)?.liked_count || 0))[0]
  const visibleThemes = [...new Set(quadrantPosts.map(classifyTheme))]
  const quadrants = useMemo(() => [
    { key: 'highHigh' as const, label: t('performance.quadrants.highHigh'), posts: quadrantPosts.filter((post) => (stageSnapshot(post, lifecycleStage)?.liked_count || 0) >= medianLikes && (stageSnapshot(post, lifecycleStage)?.comment_count || 0) >= medianComments) },
    { key: 'highLow' as const, label: t('performance.quadrants.highLow'), posts: quadrantPosts.filter((post) => (stageSnapshot(post, lifecycleStage)?.liked_count || 0) >= medianLikes && (stageSnapshot(post, lifecycleStage)?.comment_count || 0) < medianComments) },
    { key: 'lowHigh' as const, label: t('performance.quadrants.lowHigh'), posts: quadrantPosts.filter((post) => (stageSnapshot(post, lifecycleStage)?.liked_count || 0) < medianLikes && (stageSnapshot(post, lifecycleStage)?.comment_count || 0) >= medianComments) },
    { key: 'lowLow' as const, label: t('performance.quadrants.lowLow'), posts: quadrantPosts.filter((post) => (stageSnapshot(post, lifecycleStage)?.liked_count || 0) < medianLikes && (stageSnapshot(post, lifecycleStage)?.comment_count || 0) < medianComments) },
  ], [lifecycleStage, medianComments, medianLikes, quadrantPosts, t])
  const quadrantMeta = [
    { key: 'highHigh' as const, label: t('performance.quadrants.highHigh'), description: t('performance.quadrantDescriptions.highHigh'), icon: Sparkles, tone: 'success' },
    { key: 'highLow' as const, label: t('performance.quadrants.highLow'), description: t('performance.quadrantDescriptions.highLow'), icon: Heart, tone: 'info' },
    { key: 'lowHigh' as const, label: t('performance.quadrants.lowHigh'), description: t('performance.quadrantDescriptions.lowHigh'), icon: MessageSquare, tone: 'purple' },
    { key: 'lowLow' as const, label: t('performance.quadrants.lowLow'), description: t('performance.quadrantDescriptions.lowLow'), icon: Gauge, tone: 'muted' },
  ]
  const quadrantKeyForPost = (post: MonitorDashboardPost): QuadrantKey => {
    const snapshot = stageSnapshot(post, lifecycleStage)
    const highLikes = (snapshot?.liked_count || 0) >= medianLikes
    const highComments = (snapshot?.comment_count || 0) >= medianComments
    if (highLikes && highComments) return 'highHigh'
    if (highLikes) return 'highLow'
    if (highComments) return 'lowHigh'
    return 'lowLow'
  }
  const maxPointInteraction = Math.max(...quadrantInteractions, 1)
  const activeQuadrantPost = quadrantPosts.find((post) => post.aweme_id === activeQuadrantPostId) || topRightExtreme || quadrantPosts[0]
  const activeQuadrantSnapshot = activeQuadrantPost ? stageSnapshot(activeQuadrantPost, lifecycleStage) : undefined
  const activeQuadrantTheme = activeQuadrantPost ? classifyTheme(activeQuadrantPost) : undefined
  const activeQuadrantKey = activeQuadrantPost ? quadrantKeyForPost(activeQuadrantPost) : undefined
  const activeQuadrantMeta = quadrantMeta.find((item) => item.key === activeQuadrantKey)
  const corePercent = quadrantPosts.length ? quadrants[0].posts.length / quadrantPosts.length * 100 : 0
  const potentialPercent = quadrantPosts.length ? quadrants[2].posts.length / quadrantPosts.length * 100 : 0
  const activeQuadrantScore = activeQuadrantPost ? scoreForPost(activeQuadrantPost) : 0
  const activeInteractionPercentile = quadrantInteractions.length
    ? quadrantInteractions.filter((value) => value <= activeQuadrantScore).length / quadrantInteractions.length * 100
    : 0

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
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1fr_1fr_auto] xl:items-end">
          <div className="grid gap-1 text-xs font-medium text-cyber-text-secondary"><span id="performance-lifecycle-label">{t('performance.lifecycleLabel')}</span><Select value={lifecycleStage} onValueChange={(value) => setLifecycleStage(value as LifecycleStage)}><SelectTrigger aria-labelledby="performance-lifecycle-label" className="h-10"><SelectValue /></SelectTrigger><SelectContent>{(['24h', '72h', '7d', 'latest'] as const).map((stage) => <SelectItem key={stage} value={stage}>{t(`performance.lifecycle.${stage}`)}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1 text-xs font-medium text-cyber-text-secondary"><span id="performance-interaction-mode-label">{t('performance.interactionModeLabel')}</span><Select value={interactionMode} onValueChange={(value) => setInteractionMode(value as InteractionMode)}><SelectTrigger aria-labelledby="performance-interaction-mode-label" className="h-10"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="raw">{t('performance.interactionMode.raw')}</SelectItem><SelectItem value="weighted">{t('performance.interactionMode.weighted')}</SelectItem></SelectContent></Select></div>
          <p className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary/35 px-3 py-2 text-xs leading-5 text-cyber-text-muted">{t(interactionMode === 'weighted' ? 'performance.weightedFormula' : 'performance.rawFormula')}</p>
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
        <div className="overview-panel-header min-h-0 flex-col items-stretch gap-3 py-3 xl:flex-row xl:items-end xl:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary"><BarChart3 aria-hidden="true" className="h-4 w-4" /></span>
            <div className="min-w-0"><div className="overview-panel-title">{t('performance.postOverview')}</div><div className="overview-panel-description">{t('performance.postOverviewHint')}</div></div>
            <div className="ml-auto flex shrink-0 flex-col items-end gap-1 xl:ml-2"><Badge variant="secondary">{t('performance.postOverviewCount', { count: overviewRows.length })}</Badge><span className="hidden text-[10px] text-cyber-text-muted sm:block">{t('performance.metricScaleHint')}</span></div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 xl:min-w-[760px] xl:grid-cols-4">
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
                <tr><SortableHeader label={t('performance.postAndPublish')} active={overviewSort.startsWith('publish')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} sticky icon={Clock3} onClick={() => toggleOverviewSort('publish')} /><SortableHeader label={t('monitorDashboard.metricLikes')} active={overviewSort.startsWith('likes')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Heart} toneClass="text-status-info" onClick={() => toggleOverviewSort('likes')} /><SortableHeader label={t('monitorDashboard.metricCollections')} active={overviewSort.startsWith('collections')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Bookmark} toneClass="text-status-purple" onClick={() => toggleOverviewSort('collections')} /><SortableHeader label={t('monitorDashboard.metricComments')} active={overviewSort.startsWith('comments')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={MessageSquare} toneClass="text-cyber-neon-pink" onClick={() => toggleOverviewSort('comments')} /><SortableHeader label={t('monitorDashboard.metricShares')} active={overviewSort.startsWith('shares')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Share2} toneClass="text-status-warning" onClick={() => toggleOverviewSort('shares')} /><SortableHeader label={t(interactionMode === 'weighted' ? 'performance.weightedInteraction' : 'performance.totalInteraction')} active={overviewSort.startsWith('interaction')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Activity} toneClass="text-status-success" onClick={() => toggleOverviewSort('interaction')} /><SortableHeader label={t('performance.growth24to72')} active={overviewSort.startsWith('growth')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={TrendingUp} toneClass="text-primary" onClick={() => toggleOverviewSort('growth')} /></tr>
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
                    <td data-numeric="true" className="post-overview-metric-cell post-overview-total-cell px-3 py-3"><MetricValue label={t(interactionMode === 'weighted' ? 'performance.weightedInteraction' : 'performance.totalInteraction')} value={total} max={metricMaximums.total} textClass="text-status-success" barClass="bg-status-success" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('performance.growth24to72')} value={growth} max={metricMaximums.growth} textClass={Number(growth || 0) >= 0 ? 'text-primary' : 'text-status-danger'} barClass={Number(growth || 0) >= 0 ? 'bg-primary' : 'bg-status-danger'} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-3 p-3 lg:hidden">
          {displayedRows.map(({ post, snapshot, state, total, growth }, index) => (
            <article key={post.aweme_id} data-aweme-id={post.aweme_id} data-selected={highlightedAwemeId === post.aweme_id ? 'true' : undefined} className="metric-surface-card post-overview-card p-3 data-[selected=true]:border-primary/50 data-[selected=true]:ring-2 data-[selected=true]:ring-primary/15">
              <div className="flex min-w-0 items-start gap-2"><span aria-hidden="true" className="post-overview-index font-mono">{String((currentPage - 1) * pageSize + index + 1).padStart(2, '0')}</span><PostCover post={post} /><button type="button" onClick={() => setDetailPost(post)} className="min-w-0 flex-1 cursor-pointer text-left text-sm font-semibold leading-5 text-cyber-text-primary hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">{post.title || post.aweme_id}</button><span className={`status-chip shrink-0 ${stageBadgeClass(snapshot?.stage)}`}>{snapshot?.stage || t(`performance.rowState.${state}`)}</span></div>
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-cyber-text-muted"><span className="inline-flex items-center gap-1"><Clock3 aria-hidden="true" className="h-3 w-3" />{formatPublishedAt(post.create_time)}</span><span className="break-all font-mono">ID {post.aweme_id}</span></div>
              <dl className="mt-3 grid grid-cols-2 gap-2">
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricLikes')}</dt><dd><MetricValue label={t('monitorDashboard.metricLikes')} value={snapshot?.liked_count ?? null} max={metricMaximums.likes} textClass="text-status-info" barClass="bg-status-info" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricCollections')}</dt><dd><MetricValue label={t('monitorDashboard.metricCollections')} value={snapshot?.collected_count ?? null} max={metricMaximums.collections} textClass="text-status-purple" barClass="bg-status-purple" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricComments')}</dt><dd><MetricValue label={t('monitorDashboard.metricComments')} value={snapshot?.comment_count ?? null} max={metricMaximums.comments} textClass="text-cyber-neon-pink" barClass="bg-cyber-neon-pink" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricShares')}</dt><dd><MetricValue label={t('monitorDashboard.metricShares')} value={snapshot?.share_count ?? null} max={metricMaximums.shares} textClass="text-status-warning" barClass="bg-status-warning" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t(interactionMode === 'weighted' ? 'performance.weightedInteraction' : 'performance.totalInteraction')}</dt><dd><MetricValue label={t(interactionMode === 'weighted' ? 'performance.weightedInteraction' : 'performance.totalInteraction')} value={total} max={metricMaximums.total} textClass="text-status-success" barClass="bg-status-success" /></dd></div>
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

      <section className="overview-panel order-4 overflow-hidden">
        <div className="overview-panel-header min-h-0 flex-col items-stretch gap-3 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary"><Crosshair aria-hidden="true" className="h-4 w-4" /></span>
            <div className="min-w-0">
              <div className="overview-panel-title">{t('performance.quadrantTitle')}</div>
              <div className="overview-panel-description">{t('performance.quadrantHint')}</div>
            </div>
          </div>
          <div className="flex flex-col gap-2 lg:items-end">
            <div className="flex flex-wrap items-end gap-2">
              <div className="grid gap-1 text-[10px] font-medium text-cyber-text-secondary">
                <span id="quadrant-time-range-label" className="inline-flex items-center gap-1.5"><CalendarRange aria-hidden="true" className="h-3.5 w-3.5" />{t('performance.quadrantTimeFilter')}</span>
                <Select value={quadrantTimeRange} onValueChange={(value) => {
                  setQuadrantTimeRange(value as QuadrantTimeRange)
                  setSelectedQuadrantKey(undefined)
                  setHighlightedTheme(undefined)
                  setActiveQuadrantPostId(undefined)
                }}>
                  <SelectTrigger aria-labelledby="quadrant-time-range-label" className="h-8 w-[168px] text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>{(['24h', '7d', '30d', 'all'] as const).map((range) => <SelectItem key={range} value={range}>{t(`dataCenter.timeRange.${range}`)}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <Badge variant="secondary">{t('performance.quadrantFilteredPosts', { count: quadrantPosts.length, total: comparableRows.length })}</Badge>
              <Badge variant="outline">{t(`performance.lifecycle.${lifecycleStage}`)}</Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{t('performance.medianLikesLine', { value: formatNumber(medianLikes) })}</Badge>
              <Badge variant="outline">{t('performance.medianCommentsLine', { value: formatNumber(medianComments) })}</Badge>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 border-b border-cyber-border-subtle bg-cyber-bg-tertiary/15 p-3 xl:grid-cols-4">
          {quadrantMeta.map((item) => {
            const quadrant = quadrants.find((candidate) => candidate.key === item.key)
            const count = quadrant?.posts.length || 0
            const percent = quadrantPosts.length ? count / quadrantPosts.length * 100 : 0
            return (
              <button
                key={item.key}
                type="button"
                aria-pressed={selectedQuadrantKey === item.key}
                data-active={selectedQuadrantKey === item.key ? 'true' : 'false'}
                data-tone={item.tone}
                onClick={() => {
                  const nextKey = selectedQuadrantKey === item.key ? undefined : item.key
                  setSelectedQuadrantKey(nextKey)
                  if (nextKey && quadrant?.posts[0]) setActiveQuadrantPostId(quadrant.posts[0].aweme_id)
                }}
                className="quadrant-summary-card"
              >
                <span className="quadrant-summary-icon"><item.icon aria-hidden="true" className="h-4 w-4" /></span>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block text-xs font-semibold text-cyber-text-primary">{item.label}</span>
                  <span className="mt-0.5 block text-[10px] leading-4 text-cyber-text-muted">{item.description}</span>
                </span>
                <span className="text-right">
                  <span className="block text-base font-semibold numeric-value text-cyber-text-primary">{count}</span>
                  <span className="block text-[10px] numeric-value text-cyber-text-muted">{percent.toFixed(1)}%</span>
                </span>
                <span aria-hidden="true" className="quadrant-summary-progress"><span style={{ width: `${percent}%` }} /></span>
              </button>
            )
          })}
        </div>

        <div className="grid gap-3 p-3 xl:grid-cols-[minmax(0,1fr)_17rem]">
          <div className="min-w-0">
            <div className="quadrant-insight-strip">
              <div className="quadrant-insight-item"><span>{t('performance.coreShare')}</span><b>{corePercent.toFixed(1)}%</b><small>{t('performance.coreShareHint', { count: quadrants[0].posts.length })}</small></div>
              <div className="quadrant-insight-item"><span>{t('performance.potentialShare')}</span><b>{potentialPercent.toFixed(1)}%</b><small>{t('performance.potentialShareHint', { count: quadrants[2].posts.length })}</small></div>
              <div className="quadrant-insight-item"><span>{t('performance.likesCommentsCorrelation')}</span><b>{likesCommentsCorrelation == null ? '—' : likesCommentsCorrelation.toFixed(2)}</b><small>{t(`performance.correlation.${correlationKey}`)}</small></div>
              <span className="quadrant-bubble-legend">
                <span>{t('performance.bubbleScale')}</span>
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-primary/65" />
                <span aria-hidden="true" className="h-3 w-3 rounded-full bg-primary/85" />
              </span>
            </div>
            <p id="quadrant-chart-summary" className="sr-only">{t('performance.quadrantA11ySummary', { count: quadrantPosts.length, likes: formatNumber(medianLikes), comments: formatNumber(medianComments) })}</p>
            <div role="group" aria-labelledby="quadrant-chart-summary" className="quadrant-chart">
              <div className="quadrant-zone" data-zone="lowHigh" style={{ left: `${plotMinimum}%`, top: `${100 - plotMaximum}%`, width: `${medianX - plotMinimum}%`, height: `${plotMaximum - medianY}%` }}>
                <span className="quadrant-zone-label">{quadrants[2].label}<b>{quadrants[2].posts.length}</b></span>
              </div>
              <div className="quadrant-zone" data-zone="highHigh" style={{ left: `${medianX}%`, top: `${100 - plotMaximum}%`, width: `${plotMaximum - medianX}%`, height: `${plotMaximum - medianY}%` }}>
                <span className="quadrant-zone-label justify-end text-right">{quadrants[0].label}<b>{quadrants[0].posts.length}</b></span>
              </div>
              <div className="quadrant-zone items-end" data-zone="lowLow" style={{ left: `${plotMinimum}%`, top: `${100 - medianY}%`, width: `${medianX - plotMinimum}%`, height: `${medianY - plotMinimum}%` }}>
                <span className="quadrant-zone-label">{quadrants[3].label}<b>{quadrants[3].posts.length}</b></span>
              </div>
              <div className="quadrant-zone items-end" data-zone="highLow" style={{ left: `${medianX}%`, top: `${100 - medianY}%`, width: `${plotMaximum - medianX}%`, height: `${medianY - plotMinimum}%` }}>
                <span className="quadrant-zone-label justify-end text-right">{quadrants[1].label}<b>{quadrants[1].posts.length}</b></span>
              </div>

              {xTicks.map((tick, index) => (
                <div key={`x-${tick}`} aria-hidden="true" className="quadrant-gridline quadrant-gridline-vertical" style={{ left: `${xPosition(tick)}%`, top: `${100 - plotMaximum}%`, height: `${plotSpan}%` }}>
                  <span data-edge={index === 0 || index === xTicks.length - 1 ? 'true' : undefined}>{formatCompactNumber(tick)}</span>
                </div>
              ))}
              {yTicks.map((tick, index) => (
                <div key={`y-${tick}`} aria-hidden="true" className="quadrant-gridline quadrant-gridline-horizontal" style={{ left: `${plotMinimum}%`, bottom: `${yPosition(tick)}%`, width: `${plotSpan}%` }}>
                  <span data-edge={index === 0 || index === yTicks.length - 1 ? 'true' : undefined}>{formatCompactNumber(tick)}</span>
                </div>
              ))}

              <div aria-hidden="true" className="quadrant-median-line quadrant-median-line-vertical" style={{ left: `${medianX}%`, top: `${100 - plotMaximum}%`, height: `${plotSpan}%` }} />
              <div aria-hidden="true" className="quadrant-median-line quadrant-median-line-horizontal" style={{ left: `${plotMinimum}%`, top: `${100 - medianY}%`, width: `${plotSpan}%` }} />
              <span className="quadrant-median-chip hidden sm:inline-flex" style={{ left: `${medianX}%`, top: `${100 - plotMaximum + 2}%` }}>{t('performance.medianLikesLine', { value: formatNumber(medianLikes) })}</span>
              <span className="quadrant-median-chip quadrant-median-chip-y hidden sm:inline-flex" style={{ right: `${100 - plotMaximum + 1}%`, top: `${100 - medianY}%` }}>{t('performance.medianCommentsLine', { value: formatNumber(medianComments) })}</span>

              {quadrantPosts.map((post) => {
                const snapshot = stageSnapshot(post, lifecycleStage)
                const likes = snapshot?.liked_count || 0
                const comments = snapshot?.comment_count || 0
                const left = xPosition(likes)
                const bottom = yPosition(comments)
                const theme = classifyTheme(post)
                const quadrantKey = quadrantKeyForPost(post)
                const interaction = scoreForPost(post)
                const pointSize = 7 + Math.sqrt(Math.log10(interaction + 1) / Math.log10(maxPointInteraction + 1)) * 8
                const isExtreme = topRightExtreme?.aweme_id === post.aweme_id || bottomRightExtreme?.aweme_id === post.aweme_id
                const isActive = activeQuadrantPost?.aweme_id === post.aweme_id
                const isDimmed = Boolean((selectedQuadrantKey && selectedQuadrantKey !== quadrantKey) || (highlightedTheme && highlightedTheme !== theme))
                const quadrantLabel = quadrantMeta.find((item) => item.key === quadrantKey)?.label || quadrantKey
                return (
                  <button
                    key={post.aweme_id}
                    type="button"
                    aria-pressed={isActive}
                    aria-label={t('performance.quadrantPointLabel', { title: post.title || post.aweme_id, likes: formatNumber(likes), comments: formatNumber(comments), quadrant: quadrantLabel })}
                    title={`${post.title || post.aweme_id}\n${t('performance.likes')}: ${formatNumber(likes)}\n${t('performance.comments')}: ${formatNumber(comments)}`}
                    data-active={isActive ? 'true' : 'false'}
                    data-dimmed={isDimmed ? 'true' : 'false'}
                    data-extreme={isExtreme ? 'true' : undefined}
                    onMouseEnter={() => setActiveQuadrantPostId(post.aweme_id)}
                    onFocus={() => setActiveQuadrantPostId(post.aweme_id)}
                    onClick={() => setActiveQuadrantPostId(post.aweme_id)}
                    className="quadrant-point"
                    style={{ left: `${left}%`, bottom: `${bottom}%` }}
                  >
                    <span aria-hidden="true" className="quadrant-point-dot" style={{ width: `${pointSize}px`, height: `${pointSize}px`, background: THEME_COLORS[theme] || THEME_COLORS.other }} />
                  </button>
                )
              })}
              <span className="quadrant-axis-label quadrant-axis-label-x">{t('performance.likesAxis')} →</span>
              <span className="quadrant-axis-label quadrant-axis-label-y">{t('performance.commentsAxis')} →</span>
              {quadrantPosts.length === 0 ? <div className="quadrant-empty-state">{t('performance.noMatchingPosts')}</div> : null}
            </div>

            <div className="quadrant-theme-legend">
              <div className="flex min-w-0 items-center gap-2 sm:mr-auto">
                <span className="shrink-0 text-[10px] font-semibold text-cyber-text-secondary">{t('performance.themeLegend')}</span>
                <span className="hidden truncate text-[10px] text-cyber-text-muted sm:block">{t('performance.themeLegendHint')}</span>
              </div>
              <button type="button" aria-pressed={!highlightedTheme} data-active={!highlightedTheme ? 'true' : 'false'} onClick={() => setHighlightedTheme(undefined)} className="quadrant-theme-button">{t('performance.allThemes')}</button>
              {visibleThemes.map((theme) => (
                <button key={theme} type="button" aria-pressed={highlightedTheme === theme} data-active={highlightedTheme === theme ? 'true' : 'false'} onClick={() => {
                  const nextTheme = highlightedTheme === theme ? undefined : theme
                  setHighlightedTheme(nextTheme)
                  if (nextTheme) setActiveQuadrantPostId(quadrantPosts.find((post) => classifyTheme(post) === nextTheme)?.aweme_id)
                }} className="quadrant-theme-button">
                  <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: THEME_COLORS[theme] || THEME_COLORS.other }} />
                  {t(`topics.themes.${theme}`)}
                </button>
              ))}
            </div>
          </div>

          <aside className="quadrant-detail" aria-live="polite">
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-primary"><Sparkles aria-hidden="true" className="h-3.5 w-3.5" />{t('performance.focusedPost')}</div>
            {activeQuadrantPost && activeQuadrantMeta ? (
              <>
                <div className="mt-3 flex items-start gap-3">
                  <PostCover post={activeQuadrantPost} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="secondary">{activeQuadrantMeta.label}</Badge>
                      <span className="inline-flex items-center gap-1.5 text-[10px] text-cyber-text-muted"><span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: THEME_COLORS[activeQuadrantTheme || 'other'] || THEME_COLORS.other }} />{t(`topics.themes.${activeQuadrantTheme || 'other'}`)}</span>
                    </div>
                    <h3 className="mt-2 line-clamp-3 text-sm font-semibold leading-5 text-cyber-text-primary">{activeQuadrantPost.title || activeQuadrantPost.aweme_id}</h3>
                    <div className="mt-1 inline-flex items-center gap-1 text-[10px] text-cyber-text-muted"><Clock3 aria-hidden="true" className="h-3 w-3" />{formatPublishedAt(activeQuadrantPost.create_time)}</div>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <div className="quadrant-detail-metric"><span>{t('performance.likes')}</span><b>{formatCompactNumber(activeQuadrantSnapshot?.liked_count || 0)}</b></div>
                  <div className="quadrant-detail-metric"><span>{t('performance.comments')}</span><b>{formatCompactNumber(activeQuadrantSnapshot?.comment_count || 0)}</b></div>
                  <div className="quadrant-detail-metric"><span>{t(interactionMode === 'weighted' ? 'performance.weightedInteraction' : 'performance.totalInteraction')}</span><b>{formatCompactNumber(scoreForPost(activeQuadrantPost))}</b></div>
                </div>
                <div className="mt-3 rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-3">
                  <div className="flex items-center justify-between gap-2 text-[10px] text-cyber-text-muted"><span>{t('performance.interactionPercentile')}</span><b className="numeric-value text-primary">{activeInteractionPercentile.toFixed(0)}%</b></div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-cyber-bg-tertiary"><div className="h-full rounded-full bg-primary" style={{ width: `${activeInteractionPercentile}%` }} /></div>
                </div>
                <div className="mt-3 grid gap-2">
                  <div className="quadrant-benchmark-row"><span>{t('performance.likes')}</span><b>{t('performance.medianMultiple', { value: ((activeQuadrantSnapshot?.liked_count || 0) / Math.max(medianLikes, 1)).toFixed(1) })}</b></div>
                  <div className="quadrant-benchmark-row"><span>{t('performance.comments')}</span><b>{t('performance.medianMultiple', { value: ((activeQuadrantSnapshot?.comment_count || 0) / Math.max(medianComments, 1)).toFixed(1) })}</b></div>
                </div>
                <p className="mt-4 border-t border-cyber-border-subtle pt-3 text-[10px] leading-5 text-cyber-text-muted">{activeQuadrantMeta.description}</p>
                <Button type="button" variant="outline" size="sm" onClick={() => setDetailPost(activeQuadrantPost)} className="mt-3 w-full">{t('performance.viewPostDetails')}</Button>
              </>
            ) : <div className="py-10 text-center text-xs text-cyber-text-muted">{t('performance.noMatchingPosts')}</div>}
            <p className="mt-3 text-[10px] leading-4 text-cyber-text-muted">{t('performance.quadrantFocusHint')}</p>
          </aside>
        </div>
      </section>

      <Dialog open={Boolean(detailPost)} onOpenChange={(open) => !open && setDetailPost(undefined)}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto border-cyber-border-subtle bg-cyber-bg-panel">
          <DialogHeader>
            <DialogTitle className="pr-8 text-left text-cyber-text-primary">{detailPost?.title || detailPost?.aweme_id}</DialogTitle>
            <DialogDescription className="text-left text-cyber-text-muted">{detailPost ? `${formatPublishedAt(detailPost.create_time)} · ID ${detailPost.aweme_id}` : ''}</DialogDescription>
          </DialogHeader>
          {detailPost ? <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-[13rem_minmax(0,1fr)]"><div className="aspect-video overflow-hidden rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary">{detailPost.cover_url && !detailCoverFailed ? <img src={detailPost.cover_url} alt={t('performance.coverAlt', { title: detailPost.title || detailPost.aweme_id })} width={208} height={117} className="h-full w-full object-cover" decoding="async" referrerPolicy="no-referrer" onError={() => setDetailCoverFailed(true)} /> : <div className="grid h-full place-items-center gap-2 text-xs text-cyber-text-muted"><ImageIcon aria-hidden="true" className="h-6 w-6" /><span>{t('performance.noCover')}</span></div>}</div><div className="grid grid-cols-2 gap-2"><div className="metric-surface-card p-3"><span className="text-xs text-cyber-text-muted">{t('performance.currentState')}</span><b className="mt-2 block text-sm text-cyber-text-primary">{detailSnapshot?.stage || (detailState ? t(`performance.rowState.${detailState}`) : '—')}</b></div><div className="metric-surface-card p-3"><span className="text-xs text-cyber-text-muted">{t(interactionMode === 'weighted' ? 'performance.weightedInteraction' : 'performance.totalInteraction')}</span><b className="mt-2 block text-lg numeric-value text-status-success">{detailSnapshot ? formatNumber(interactionScore(detailSnapshot, interactionMode)) : '—'}</b></div><div className="metric-surface-card p-3"><span className="text-xs text-cyber-text-muted">{t('performance.growth24to72')}</span><b className="mt-2 block text-lg numeric-value text-primary">{detailGrowth == null ? '—' : formatNumber(detailGrowth)}</b></div><div className="metric-surface-card p-3"><span className="text-xs text-cyber-text-muted">{t('performance.firstSeenDelay')}</span><b className="mt-2 block text-lg numeric-value text-cyber-text-primary">{formatNumber(firstSeenDelayHours(detailPost))}h</b></div></div></div>
            {detailPost.canonical_url ? <a href={detailPost.canonical_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"><ExternalLink aria-hidden="true" className="h-4 w-4" />{t('performance.openPostAction')}</a> : <Badge variant="outline">{t('performance.noPostLink')}</Badge>}
            <div><h3 className="text-sm font-semibold text-cyber-text-primary">{t('performance.snapshotHistory')}</h3>{detailSnapshots.length ? <div className="mt-2 overflow-x-auto rounded-lg border border-cyber-border-subtle"><table className="w-full min-w-[620px] text-xs"><thead className="bg-cyber-bg-tertiary/50 text-cyber-text-secondary"><tr><th className="px-3 py-2 text-left">{t('performance.latestStage')}</th><th className="px-3 py-2 text-right">{t('monitorDashboard.metricLikes')}</th><th className="px-3 py-2 text-right">{t('monitorDashboard.metricCollections')}</th><th className="px-3 py-2 text-right">{t('monitorDashboard.metricComments')}</th><th className="px-3 py-2 text-right">{t('monitorDashboard.metricShares')}</th><th className="px-3 py-2 text-right">{t(interactionMode === 'weighted' ? 'performance.weightedInteraction' : 'performance.totalInteraction')}</th></tr></thead><tbody className="divide-y divide-cyber-border-subtle">{detailSnapshots.map((snapshot) => <tr key={`${snapshot.stage}-${snapshot.captured_at}`}><td className="px-3 py-2 text-cyber-text-primary">{snapshot.stage}</td><td className="px-3 py-2 text-right numeric-value">{formatNumber(snapshot.liked_count)}</td><td className="px-3 py-2 text-right numeric-value">{formatNumber(snapshot.collected_count)}</td><td className="px-3 py-2 text-right numeric-value">{formatNumber(snapshot.comment_count)}</td><td className="px-3 py-2 text-right numeric-value">{formatNumber(snapshot.share_count)}</td><td className="px-3 py-2 text-right font-semibold numeric-value text-status-success">{formatNumber(interactionScore(snapshot, interactionMode))}</td></tr>)}</tbody></table></div> : <div className="mt-2 rounded-lg border border-dashed border-cyber-border-subtle px-4 py-8 text-center text-xs text-cyber-text-muted">{t('performance.noSnapshotHistory')}</div>}</div>
          </div> : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}
