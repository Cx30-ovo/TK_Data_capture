import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, ArrowDown, ArrowUp, ArrowUpDown, BarChart3, Bookmark, CalendarRange, Clock3, Crosshair, Flame, Gauge, Heart, MessageSquare, Search, Share2, Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { MonitorDashboardPost } from '@/lib/api'
import { classifyTheme, firstSeenDelayHours, latestSnapshot, mean, median, postInteraction, THEME_COLORS } from '@/lib/monitorMetrics'


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


type OverviewSort = 'publishDesc' | 'publishAsc' | 'likesDesc' | 'likesAsc' | 'collectionsDesc' | 'collectionsAsc' | 'commentsDesc' | 'commentsAsc' | 'sharesDesc' | 'sharesAsc' | 'interactionDesc' | 'interactionAsc'
type QuadrantKey = 'highHigh' | 'highLow' | 'lowHigh' | 'lowLow'
type QuadrantTimeRange = '24h' | '7d' | '30d' | 'all'


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


export function MonitorPerformanceOverview({ posts, focusAwemeId, focusToken }: { posts: MonitorDashboardPost[]; focusAwemeId?: string; focusToken?: number }) {
  const { t } = useTranslation('config')
  const [activeStructureMetric, setActiveStructureMetric] = useState<'liked' | 'collected' | 'comment' | 'share' | null>(null)
  const [overviewSearch, setOverviewSearch] = useState('')
  const [overviewSort, setOverviewSort] = useState<OverviewSort>('publishDesc')
  const [highlightedAwemeId, setHighlightedAwemeId] = useState<string>()
  const [activeQuadrantPostId, setActiveQuadrantPostId] = useState<string>()
  const [selectedQuadrantKey, setSelectedQuadrantKey] = useState<QuadrantKey>()
  const [highlightedTheme, setHighlightedTheme] = useState<string>()
  const [quadrantTimeRange, setQuadrantTimeRange] = useState<QuadrantTimeRange>('all')
  const handledFocusToken = useRef<number | undefined>()
  const interactions = posts.map(postInteraction)
  const average = mean(interactions)
  const middle = median(interactions)
  const burstThreshold = Math.max(middle * 2, 1)
  const burstPosts = posts.filter((post) => postInteraction(post) >= burstThreshold)
  const zeroPosts = posts.filter((post) => postInteraction(post) === 0)
  const delays = posts.map(firstSeenDelayHours)
  const latestSnapshots = posts.map(latestSnapshot)
  const structure = {
    liked: latestSnapshots.reduce((sum, snapshot) => sum + (snapshot?.liked_count || 0), 0),
    collected: latestSnapshots.reduce((sum, snapshot) => sum + (snapshot?.collected_count || 0), 0),
    comment: latestSnapshots.reduce((sum, snapshot) => sum + (snapshot?.comment_count || 0), 0),
    share: latestSnapshots.reduce((sum, snapshot) => sum + (snapshot?.share_count || 0), 0),
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
  const overviewPosts = useMemo(() => {
    const keyword = overviewSearch.trim().toLowerCase()
    const metricValue = (post: MonitorDashboardPost, metric: 'liked_count' | 'collected_count' | 'comment_count' | 'share_count' | 'interaction') => {
      const snapshot = latestSnapshot(post)
      if (!snapshot) return 0
      if (metric === 'interaction') return snapshot.liked_count + snapshot.collected_count + snapshot.comment_count + snapshot.share_count
      return snapshot[metric]
    }
    return posts
      .filter((post) => !keyword || (post.title || '').toLowerCase().includes(keyword) || post.aweme_id.toLowerCase().includes(keyword))
      .sort((left, right) => {
        if (overviewSort === 'publishAsc') return left.create_time - right.create_time
        if (overviewSort === 'publishDesc') return right.create_time - left.create_time
        const metric = overviewSort.startsWith('likes') ? 'liked_count' : overviewSort.startsWith('collections') ? 'collected_count' : overviewSort.startsWith('comments') ? 'comment_count' : overviewSort.startsWith('shares') ? 'share_count' : 'interaction'
        const difference = metricValue(right, metric) - metricValue(left, metric)
        return overviewSort.endsWith('Asc') ? -difference : difference
      })
  }, [overviewSearch, overviewSort, posts])
  const overviewRows = useMemo(() => overviewPosts.map((post) => {
    const snapshot = latestSnapshot(post)
    return {
      post,
      snapshot,
      total: snapshot ? snapshot.liked_count + snapshot.collected_count + snapshot.comment_count + snapshot.share_count : null,
    }
  }), [overviewPosts])
  const metricMaximums = useMemo(() => overviewRows.reduce((result, row) => ({
    likes: Math.max(result.likes, row.snapshot?.liked_count || 0),
    collections: Math.max(result.collections, row.snapshot?.collected_count || 0),
    comments: Math.max(result.comments, row.snapshot?.comment_count || 0),
    shares: Math.max(result.shares, row.snapshot?.share_count || 0),
    total: Math.max(result.total, row.total || 0),
  }), { likes: 1, collections: 1, comments: 1, shares: 1, total: 1 }), [overviewRows])

  const toggleOverviewSort = (group: 'publish' | 'likes' | 'collections' | 'comments' | 'shares' | 'interaction') => {
    setOverviewSort((current) => {
      const desc = `${group}Desc` as OverviewSort
      const asc = `${group}Asc` as OverviewSort
      return current === desc ? asc : desc
    })
  }

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
    if (quadrantTimeRange === 'all') return posts
    const rangeHours = quadrantTimeRange === '24h' ? 24 : quadrantTimeRange === '7d' ? 24 * 7 : 24 * 30
    const cutoff = Date.now() / 1000 - rangeHours * 60 * 60
    return posts.filter((post) => post.create_time >= cutoff)
  }, [posts, quadrantTimeRange])
  const quadrantInteractions = quadrantPosts.map(postInteraction)

  const meanMedianRatio = middle > 0 ? average / middle : 0
  const topTenInteraction = [...posts].sort((left, right) => postInteraction(right) - postInteraction(left)).slice(0, 10).reduce((sum, post) => sum + postInteraction(post), 0)
  const totalInteraction = interactions.reduce((sum, value) => sum + value, 0)
  const concentration = totalInteraction > 0 ? topTenInteraction / totalInteraction * 100 : 0
  const maxLikes = Math.max(...quadrantPosts.map((post) => latestSnapshot(post)?.liked_count || 0), 1)
  const maxComments = Math.max(...quadrantPosts.map((post) => latestSnapshot(post)?.comment_count || 0), 1)
  const medianLikes = median(quadrantPosts.map((post) => latestSnapshot(post)?.liked_count || 0))
  const medianComments = median(quadrantPosts.map((post) => latestSnapshot(post)?.comment_count || 0))
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
    .filter((post) => (latestSnapshot(post)?.liked_count || 0) >= medianLikes && (latestSnapshot(post)?.comment_count || 0) >= medianComments)
    .sort((left, right) => postInteraction(right) - postInteraction(left))[0]
  const bottomRightExtreme = [...quadrantPosts]
    .filter((post) => (latestSnapshot(post)?.liked_count || 0) >= medianLikes && (latestSnapshot(post)?.comment_count || 0) < medianComments)
    .sort((left, right) => (latestSnapshot(right)?.liked_count || 0) - (latestSnapshot(left)?.liked_count || 0))[0]
  const visibleThemes = [...new Set(quadrantPosts.map(classifyTheme))]
  const quadrants = useMemo(() => [
    { key: 'highHigh' as const, label: t('performance.quadrants.highHigh'), posts: quadrantPosts.filter((post) => (latestSnapshot(post)?.liked_count || 0) >= medianLikes && (latestSnapshot(post)?.comment_count || 0) >= medianComments) },
    { key: 'highLow' as const, label: t('performance.quadrants.highLow'), posts: quadrantPosts.filter((post) => (latestSnapshot(post)?.liked_count || 0) >= medianLikes && (latestSnapshot(post)?.comment_count || 0) < medianComments) },
    { key: 'lowHigh' as const, label: t('performance.quadrants.lowHigh'), posts: quadrantPosts.filter((post) => (latestSnapshot(post)?.liked_count || 0) < medianLikes && (latestSnapshot(post)?.comment_count || 0) >= medianComments) },
    { key: 'lowLow' as const, label: t('performance.quadrants.lowLow'), posts: quadrantPosts.filter((post) => (latestSnapshot(post)?.liked_count || 0) < medianLikes && (latestSnapshot(post)?.comment_count || 0) < medianComments) },
  ], [medianComments, medianLikes, quadrantPosts, t])
  const quadrantMeta = [
    { key: 'highHigh' as const, label: t('performance.quadrants.highHigh'), description: t('performance.quadrantDescriptions.highHigh'), icon: Sparkles, tone: 'success' },
    { key: 'highLow' as const, label: t('performance.quadrants.highLow'), description: t('performance.quadrantDescriptions.highLow'), icon: Heart, tone: 'info' },
    { key: 'lowHigh' as const, label: t('performance.quadrants.lowHigh'), description: t('performance.quadrantDescriptions.lowHigh'), icon: MessageSquare, tone: 'purple' },
    { key: 'lowLow' as const, label: t('performance.quadrants.lowLow'), description: t('performance.quadrantDescriptions.lowLow'), icon: Gauge, tone: 'muted' },
  ]
  const quadrantKeyForPost = (post: MonitorDashboardPost): QuadrantKey => {
    const snapshot = latestSnapshot(post)
    const highLikes = (snapshot?.liked_count || 0) >= medianLikes
    const highComments = (snapshot?.comment_count || 0) >= medianComments
    if (highLikes && highComments) return 'highHigh'
    if (highLikes) return 'highLow'
    if (highComments) return 'lowHigh'
    return 'lowLow'
  }
  const maxPointInteraction = Math.max(...quadrantInteractions, 1)
  const activeQuadrantPost = quadrantPosts.find((post) => post.aweme_id === activeQuadrantPostId) || topRightExtreme || quadrantPosts[0]
  const activeQuadrantSnapshot = activeQuadrantPost ? latestSnapshot(activeQuadrantPost) : undefined
  const activeQuadrantTheme = activeQuadrantPost ? classifyTheme(activeQuadrantPost) : undefined
  const activeQuadrantKey = activeQuadrantPost ? quadrantKeyForPost(activeQuadrantPost) : undefined
  const activeQuadrantMeta = quadrantMeta.find((item) => item.key === activeQuadrantKey)

  const kpis = [
    { label: t('performance.samplePosts'), value: formatNumber(posts.length), icon: BarChart3, tone: 'text-cyber-neon-cyan' },
    { label: t('performance.totalInteraction'), value: formatNumber(interactions.reduce((sum, value) => sum + value, 0)), icon: Activity, tone: 'text-cyber-neon-green' },
    { label: t('performance.averageInteraction'), value: formatNumber(average), icon: Gauge, tone: 'text-cyber-neon-cyan' },
    { label: t('performance.medianInteraction'), value: formatNumber(middle), icon: Gauge, tone: 'text-cyber-neon-purple' },
    { label: t('performance.burstRate'), value: `${posts.length ? (burstPosts.length / posts.length * 100).toFixed(1) : '0.0'}%`, icon: Flame, tone: 'text-cyber-neon-pink' },
    { label: t('performance.zeroRate'), value: `${posts.length ? (zeroPosts.length / posts.length * 100).toFixed(1) : '0.0'}%`, icon: Activity, tone: zeroPosts.length ? 'text-cyber-neon-orange' : 'text-cyber-neon-green' },
    { label: t('performance.firstSeenDelay'), value: `${formatNumber(median(delays))}h`, icon: Gauge, tone: 'text-cyber-text-secondary' },
  ]

  return (
    <div className="flex flex-col space-y-3">
      <section className={`rounded-lg border p-4 ${meanMedianRatio >= 1.5 ? 'border-cyber-neon-orange/35 bg-cyber-neon-orange/5' : 'border-cyber-neon-cyan/30 bg-cyber-neon-cyan/5'}`}>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('performance.meanMedianAlert')}</div>
          <div className="flex flex-wrap gap-4 text-[10px] text-cyber-text-secondary">
            <span>{t('performance.averageInteraction')}: <b className="numeric-value">{formatNumber(average)}</b></span>
            <span>{t('performance.medianInteraction')}: <b className="numeric-value">{formatNumber(middle)}</b></span>
            <span>{t('performance.meanMedianRatio')}: <b className="numeric-value">{meanMedianRatio.toFixed(2)}x</b></span>
            <span>{t('performance.topTenConcentration')}: <b className="numeric-value">{concentration.toFixed(1)}%</b></span>
          </div>
        </div>
        <p className="mt-2 text-[10px] text-cyber-text-muted">{t('performance.concentrationHint')}</p>
      </section>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
        {kpis.map((item) => (
          <div key={item.label} className="metric-surface-card p-3">
            <div className="flex items-center gap-2 text-[9px] text-cyber-text-muted"><item.icon className="h-3 w-3" />{item.label}</div>
            <div className={`mt-2 text-xl font-semibold numeric-value ${item.tone}`}>{item.value}</div>
          </div>
        ))}
      </div>

      <section className="overview-panel post-overview-panel order-3 overflow-hidden">
        <div className="overview-panel-header min-h-0 flex-col items-stretch gap-3 py-3 xl:flex-row xl:items-end xl:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary"><BarChart3 aria-hidden="true" className="h-4 w-4" /></span>
            <div className="min-w-0"><div className="overview-panel-title">{t('performance.postOverview')}</div><div className="overview-panel-description">{t('performance.postOverviewHint')}</div></div>
            <div className="ml-auto flex shrink-0 flex-col items-end gap-1 xl:ml-2"><Badge variant="secondary">{t('performance.postOverviewCount', { count: overviewRows.length })}</Badge><span className="hidden text-[10px] text-cyber-text-muted sm:block">{t('performance.metricScaleHint')}</span></div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 xl:min-w-[520px]">
            <label className="grid gap-1 text-[11px] font-medium text-cyber-text-secondary">
              {t('performance.searchLabel')}
              <span className="relative"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cyber-text-muted" /><Input type="search" aria-label={t('performance.searchLabel')} value={overviewSearch} onChange={(event) => setOverviewSearch(event.target.value)} placeholder={t('performance.postSearchPlaceholder')} className="h-9 pl-9 text-xs" /></span>
            </label>
            <div className="grid gap-1 text-[11px] font-medium text-cyber-text-secondary">
              <span id="post-overview-sort-label">{t('performance.sortLabel')}</span>
              <Select value={overviewSort} onValueChange={(value) => setOverviewSort(value as OverviewSort)}><SelectTrigger aria-labelledby="post-overview-sort-label" className="h-9 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="publishDesc">{t('performance.sort.publishDesc')}</SelectItem><SelectItem value="publishAsc">{t('performance.sort.publishAsc')}</SelectItem><SelectItem value="likesDesc">{t('performance.sort.likesDesc')}</SelectItem><SelectItem value="likesAsc">{t('performance.sort.likesAsc')}</SelectItem><SelectItem value="collectionsDesc">{t('performance.sort.collectionsDesc')}</SelectItem><SelectItem value="collectionsAsc">{t('performance.sort.collectionsAsc')}</SelectItem><SelectItem value="commentsDesc">{t('performance.sort.commentsDesc')}</SelectItem><SelectItem value="commentsAsc">{t('performance.sort.commentsAsc')}</SelectItem><SelectItem value="sharesDesc">{t('performance.sort.sharesDesc')}</SelectItem><SelectItem value="sharesAsc">{t('performance.sort.sharesAsc')}</SelectItem><SelectItem value="interactionDesc">{t('performance.sort.interactionDesc')}</SelectItem><SelectItem value="interactionAsc">{t('performance.sort.interactionAsc')}</SelectItem></SelectContent></Select>
            </div>
          </div>
        </div>

        <div className="hidden lg:block">
          <div className="data-table-frame post-overview-frame max-h-[540px] rounded-none border-0 shadow-none">
            <table className="data-table post-overview-table w-full min-w-[940px] text-xs">
              <caption className="sr-only">{t('performance.tableCaption')}</caption>
              <colgroup><col className="w-[40%]" /><col className="w-[12%]" /><col className="w-[12%]" /><col className="w-[12%]" /><col className="w-[12%]" /><col className="w-[12%]" /></colgroup>
              <thead className="sticky top-0 z-20 text-left backdrop-blur">
                <tr><SortableHeader label={t('performance.postAndPublish')} active={overviewSort.startsWith('publish')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} sticky icon={Clock3} onClick={() => toggleOverviewSort('publish')} /><SortableHeader label={t('monitorDashboard.metricLikes')} active={overviewSort.startsWith('likes')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Heart} toneClass="text-status-info" onClick={() => toggleOverviewSort('likes')} /><SortableHeader label={t('monitorDashboard.metricCollections')} active={overviewSort.startsWith('collections')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Bookmark} toneClass="text-status-purple" onClick={() => toggleOverviewSort('collections')} /><SortableHeader label={t('monitorDashboard.metricComments')} active={overviewSort.startsWith('comments')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={MessageSquare} toneClass="text-cyber-neon-pink" onClick={() => toggleOverviewSort('comments')} /><SortableHeader label={t('monitorDashboard.metricShares')} active={overviewSort.startsWith('shares')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Share2} toneClass="text-status-warning" onClick={() => toggleOverviewSort('shares')} /><SortableHeader label={t('performance.totalInteraction')} active={overviewSort.startsWith('interaction')} direction={overviewSort.endsWith('Asc') ? 'asc' : 'desc'} numeric icon={Activity} toneClass="text-status-success" onClick={() => toggleOverviewSort('interaction')} /></tr>
              </thead>
              <tbody>
                {overviewRows.map(({ post, snapshot, total }, index) => (
                  <tr key={post.aweme_id} data-aweme-id={post.aweme_id} data-selected={highlightedAwemeId === post.aweme_id ? 'true' : undefined} className="group">
                    <td className="post-overview-primary-cell sticky left-0 z-10 max-w-[420px] px-4 py-3">
                      <div className="flex min-w-0 items-start gap-3"><span aria-hidden="true" className="post-overview-index font-mono">{String(index + 1).padStart(2, '0')}</span><div className="min-w-0 flex-1"><div className="flex min-w-0 items-center gap-2"><div title={post.title || post.aweme_id} className="min-w-0 flex-1 truncate text-sm font-semibold text-cyber-text-primary">{post.title || post.aweme_id}</div><span className={`status-chip shrink-0 ${stageBadgeClass(snapshot?.stage)}`}>{snapshot?.stage || t('performance.noSnapshot')}</span></div><div className="mt-1.5 flex min-w-0 items-center gap-3 text-[11px] text-cyber-text-muted"><span className="inline-flex shrink-0 items-center gap-1"><Clock3 aria-hidden="true" className="h-3 w-3" />{formatPublishedAt(post.create_time)}</span><span title={post.aweme_id} className="truncate font-mono">ID {post.aweme_id}</span></div></div></div>
                    </td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('monitorDashboard.metricLikes')} value={snapshot?.liked_count ?? null} max={metricMaximums.likes} textClass="text-status-info" barClass="bg-status-info" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('monitorDashboard.metricCollections')} value={snapshot?.collected_count ?? null} max={metricMaximums.collections} textClass="text-status-purple" barClass="bg-status-purple" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('monitorDashboard.metricComments')} value={snapshot?.comment_count ?? null} max={metricMaximums.comments} textClass="text-cyber-neon-pink" barClass="bg-cyber-neon-pink" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell px-3 py-3"><MetricValue label={t('monitorDashboard.metricShares')} value={snapshot?.share_count ?? null} max={metricMaximums.shares} textClass="text-status-warning" barClass="bg-status-warning" /></td>
                    <td data-numeric="true" className="post-overview-metric-cell post-overview-total-cell px-3 py-3"><MetricValue label={t('performance.totalInteraction')} value={total} max={metricMaximums.total} textClass="text-status-success" barClass="bg-status-success" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-3 p-3 lg:hidden">
          {overviewRows.map(({ post, snapshot, total }, index) => (
            <article key={post.aweme_id} data-aweme-id={post.aweme_id} data-selected={highlightedAwemeId === post.aweme_id ? 'true' : undefined} className="metric-surface-card post-overview-card p-3 data-[selected=true]:border-primary/50 data-[selected=true]:ring-2 data-[selected=true]:ring-primary/15">
              <div className="flex min-w-0 items-start gap-2"><span aria-hidden="true" className="post-overview-index font-mono">{String(index + 1).padStart(2, '0')}</span><h3 className="min-w-0 flex-1 text-sm font-semibold leading-5 text-cyber-text-primary">{post.title || post.aweme_id}</h3><span className={`status-chip shrink-0 ${stageBadgeClass(snapshot?.stage)}`}>{snapshot?.stage || t('performance.noSnapshot')}</span></div>
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-cyber-text-muted"><span className="inline-flex items-center gap-1"><Clock3 aria-hidden="true" className="h-3 w-3" />{formatPublishedAt(post.create_time)}</span><span className="break-all font-mono">ID {post.aweme_id}</span></div>
              <dl className="mt-3 grid grid-cols-2 gap-2">
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricLikes')}</dt><dd><MetricValue label={t('monitorDashboard.metricLikes')} value={snapshot?.liked_count ?? null} max={metricMaximums.likes} textClass="text-status-info" barClass="bg-status-info" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricCollections')}</dt><dd><MetricValue label={t('monitorDashboard.metricCollections')} value={snapshot?.collected_count ?? null} max={metricMaximums.collections} textClass="text-status-purple" barClass="bg-status-purple" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricComments')}</dt><dd><MetricValue label={t('monitorDashboard.metricComments')} value={snapshot?.comment_count ?? null} max={metricMaximums.comments} textClass="text-cyber-neon-pink" barClass="bg-cyber-neon-pink" /></dd></div>
                <div className="post-overview-mobile-metric"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('monitorDashboard.metricShares')}</dt><dd><MetricValue label={t('monitorDashboard.metricShares')} value={snapshot?.share_count ?? null} max={metricMaximums.shares} textClass="text-status-warning" barClass="bg-status-warning" /></dd></div>
                <div className="post-overview-mobile-metric post-overview-mobile-total col-span-2"><dt className="mb-1 text-[11px] text-cyber-text-muted">{t('performance.totalInteraction')}</dt><dd><MetricValue label={t('performance.totalInteraction')} value={total} max={metricMaximums.total} textClass="text-status-success" barClass="bg-status-success" /></dd></div>
              </dl>
            </article>
          ))}
        </div>
        {overviewRows.length === 0 ? <div className="px-4 py-12 text-center text-sm text-cyber-text-muted">{t('performance.noMatchingPosts')}</div> : null}
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
              <div
                key={item.key}
                className={`border-t-2 px-1 pt-2 transition-all ${item.borderClass} ${activeStructureMetric && activeStructureMetric !== item.key ? 'opacity-40' : 'opacity-100'} ${activeStructureMetric === item.key ? 'bg-cyber-bg-tertiary/25' : ''}`}
                onMouseEnter={() => setActiveStructureMetric(item.key)}
                onMouseLeave={() => setActiveStructureMetric(null)}
              >
                <div className="text-[10px] text-cyber-text-muted">{item.label}</div>
                <div className="mt-1 text-sm font-semibold numeric-value text-cyber-text-primary">{formatNumber(item.value)}</div>
                <div className="mt-0.5 text-[10px] font-medium numeric-value text-cyber-text-secondary">{item.percent.toFixed(1)}%</div>
              </div>
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
              <Badge variant="secondary">{t('performance.quadrantFilteredPosts', { count: quadrantPosts.length, total: posts.length })}</Badge>
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
              </button>
            )
          })}
        </div>

        <div className="grid gap-3 p-3 xl:grid-cols-[minmax(0,1fr)_17rem]">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-cyber-text-muted">
              <span>{t('performance.quadrantReadingHint')}</span>
              <span className="inline-flex items-center gap-2 rounded-full border border-cyber-border-subtle bg-cyber-bg-tertiary/35 px-2.5 py-1">
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
                const snapshot = latestSnapshot(post)
                const likes = snapshot?.liked_count || 0
                const comments = snapshot?.comment_count || 0
                const left = xPosition(likes)
                const bottom = yPosition(comments)
                const theme = classifyTheme(post)
                const quadrantKey = quadrantKeyForPost(post)
                const interaction = postInteraction(post)
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
              <span className="quadrant-axis-label quadrant-axis-label-x">{t('performance.likes')} · log →</span>
              <span className="quadrant-axis-label quadrant-axis-label-y">{t('performance.comments')} · log →</span>
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
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{activeQuadrantMeta.label}</Badge>
                  <span className="inline-flex items-center gap-1.5 text-[10px] text-cyber-text-muted"><span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: THEME_COLORS[activeQuadrantTheme || 'other'] || THEME_COLORS.other }} />{t(`topics.themes.${activeQuadrantTheme || 'other'}`)}</span>
                </div>
                <h3 className="mt-3 line-clamp-4 text-sm font-semibold leading-6 text-cyber-text-primary">{activeQuadrantPost.title || activeQuadrantPost.aweme_id}</h3>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <div className="quadrant-detail-metric"><span>{t('performance.likes')}</span><b>{formatCompactNumber(activeQuadrantSnapshot?.liked_count || 0)}</b></div>
                  <div className="quadrant-detail-metric"><span>{t('performance.comments')}</span><b>{formatCompactNumber(activeQuadrantSnapshot?.comment_count || 0)}</b></div>
                  <div className="quadrant-detail-metric"><span>{t('performance.totalInteraction')}</span><b>{formatCompactNumber(postInteraction(activeQuadrantPost))}</b></div>
                </div>
                <div className="mt-3 grid gap-2">
                  <div className="quadrant-benchmark-row"><span>{t('performance.likes')}</span><b>{t('performance.medianMultiple', { value: ((activeQuadrantSnapshot?.liked_count || 0) / Math.max(medianLikes, 1)).toFixed(1) })}</b></div>
                  <div className="quadrant-benchmark-row"><span>{t('performance.comments')}</span><b>{t('performance.medianMultiple', { value: ((activeQuadrantSnapshot?.comment_count || 0) / Math.max(medianComments, 1)).toFixed(1) })}</b></div>
                </div>
                <p className="mt-4 border-t border-cyber-border-subtle pt-3 text-[10px] leading-5 text-cyber-text-muted">{activeQuadrantMeta.description}</p>
              </>
            ) : <div className="py-10 text-center text-xs text-cyber-text-muted">{t('performance.noMatchingPosts')}</div>}
            <p className="mt-3 text-[10px] leading-4 text-cyber-text-muted">{t('performance.quadrantFocusHint')}</p>
          </aside>
        </div>
      </section>
    </div>
  )
}
