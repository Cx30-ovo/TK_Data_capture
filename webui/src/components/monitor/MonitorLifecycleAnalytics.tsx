import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight, ExternalLink, X } from 'lucide-react'
import type { MonitorDashboardPost } from '@/lib/api'
import { classifyTheme, interactionByStage, lifecycleMetrics, lifecycleType, mean, postInteraction } from '@/lib/monitorMetrics'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'


const STAGES = ['1h', '6h', '24h', '72h'] as const
const STAGE_ORDER = ['1h', '6h', '24h', '72h'] as const
const LINE_COLORS = ['rgb(var(--cyber-neon-cyan))', 'rgb(var(--cyber-neon-purple))', 'rgb(var(--cyber-neon-pink))', 'rgb(var(--cyber-neon-orange))', 'rgb(var(--cyber-neon-green))']
const TYPE_COLORS = {
  earlyBurst: 'rgb(var(--cyber-neon-cyan))',
  quickDecline: 'rgb(var(--cyber-neon-orange))',
  longTail: 'rgb(var(--cyber-neon-purple))',
  sustained: 'rgb(var(--cyber-neon-green))',
}
const DETAIL_PAGE_SIZE = 50


function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
}


function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString()
}


function stageCompleteness(post: MonitorDashboardPost): 'complete' | 'missing72' | 'incomplete' {
  const stages = new Set(interactionByStage(post).keys())
  if (STAGE_ORDER.every((stage) => stages.has(stage))) return 'complete'
  if (!stages.has('72h')) return 'missing72'
  return 'incomplete'
}


function SnapshotCurve({ post }: { post: MonitorDashboardPost }) {
  const { t } = useTranslation('config')
  const interaction = interactionByStage(post)
  const values = STAGES.flatMap((stage, index) => {
    const value = interaction.get(stage)
    return value == null ? [] : [{ stage, index, value }]
  })
  const maxValue = Math.max(...values.map((item) => item.value), 1)
  const logMax = Math.log10(maxValue + 1)
  const width = 700
  const height = 260
  const padding = { left: 58, right: 28, top: 20, bottom: 40 }
  const innerWidth = width - padding.left - padding.right
  const innerHeight = height - padding.top - padding.bottom
  const x = (index: number) => padding.left + index / (STAGES.length - 1) * innerWidth
  const y = (value: number) => padding.top + innerHeight - Math.log10(value + 1) / logMax * innerHeight
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full">
      {[0, .25, .5, .75, 1].map((ratio) => <g key={ratio}><line x1={padding.left} y1={y(maxValue * ratio)} x2={width - padding.right} y2={y(maxValue * ratio)} stroke="rgb(var(--cyber-border-subtle))" /><text x={padding.left - 8} y={y(maxValue * ratio) + 3} textAnchor="end" fill="rgb(var(--cyber-text-muted))" fontSize="9">{Math.round(maxValue * ratio)}</text></g>)}
      {STAGES.map((stage, index) => <text key={stage} x={x(index)} y={height - 10} textAnchor="middle" fill="rgb(var(--cyber-text-muted))" fontSize="10">{stage}</text>)}
      {values.slice(1).map((current, index) => {
        const previous = values[index]
        const missing = current.index - previous.index > 1
        return <line key={current.stage} x1={x(previous.index)} y1={y(previous.value)} x2={x(current.index)} y2={y(current.value)} stroke="rgb(var(--cyber-neon-cyan))" strokeWidth="2.5" strokeDasharray={missing ? '6 4' : undefined} />
      })}
      {STAGES.map((stage, index) => {
        const value = interaction.get(stage)
        if (value == null) return <g key={stage}><circle cx={x(index)} cy={height - padding.bottom} r="4" fill="none" stroke="rgb(var(--cyber-neon-orange))" strokeDasharray="2 2" /><text x={x(index)} y={height - padding.bottom - 8} textAnchor="middle" fill="rgb(var(--cyber-neon-orange))" fontSize="8">{t('lifecycle.noData')}</text></g>
        return <circle key={stage} cx={x(index)} cy={y(value)} r="4" fill="rgb(var(--cyber-neon-cyan))"><title>{stage}: {value}</title></circle>
      })}
    </svg>
  )
}


export function MonitorLifecycleAnalytics({ posts }: { posts: MonitorDashboardPost[] }) {
  const { t } = useTranslation('config')
  const [curveGroup, setCurveGroup] = useState<'top' | 'earlyBurst' | 'quickDecline' | 'longTail' | 'sustained'>('top')
  const [detailTab, setDetailTab] = useState<'focus' | 'all'>('focus')
  const [typeFilter, setTypeFilter] = useState<'all' | 'earlyBurst' | 'quickDecline' | 'longTail' | 'sustained'>('all')
  const [themeFilter, setThemeFilter] = useState('all')
  const [completenessFilter, setCompletenessFilter] = useState<'all' | 'complete' | 'missing72' | 'incomplete'>('all')
  const [detailPage, setDetailPage] = useState(1)
  const [selectedPost, setSelectedPost] = useState<MonitorDashboardPost | null>(null)
  const fixedSample = useMemo(() => posts.filter((post) => STAGE_ORDER.every((stage) => interactionByStage(post).has(stage))), [posts])
  const aggregateSource = fixedSample
  const aggregate = STAGES.map((stage) => ({ stage, value: mean(aggregateSource.map((post) => interactionByStage(post).get(stage) || 0)) }))
  const candidates = curveGroup === 'top' ? posts : posts.filter((post) => lifecycleType(post) === curveGroup)
  const topPosts = [...candidates].sort((left, right) => postInteraction(right) - postInteraction(left)).slice(0, 5)
  const increments = STAGES.slice(1).map((stage, index) => {
    const previous = STAGES[index]
    const value = mean(aggregateSource.map((post) => {
      const byStage = interactionByStage(post)
      return (byStage.get(stage) || 0) - (byStage.get(previous) || 0)
    }))
    return { from: previous, to: stage, value }
  })
  const positiveIncrementTotal = increments.reduce((sum, item) => sum + Math.max(0, item.value), 0)
  const lifecycleCounts = posts.reduce<Record<string, number>>((result, post) => {
    const key = lifecycleType(post)
    result[key] = (result[key] || 0) + 1
    return result
  }, { earlyBurst: 0, quickDecline: 0, longTail: 0, sustained: 0 })
  const lifecycleTotal = Object.values(lifecycleCounts).reduce((sum, value) => sum + value, 0)
  const typeOrder = ['earlyBurst', 'quickDecline', 'longTail', 'sustained'] as const
  let donutStart = 0
  const donutGradient = typeOrder.map((type) => {
    const end = donutStart + (lifecycleTotal ? lifecycleCounts[type] / lifecycleTotal * 100 : 0)
    const segment = `${TYPE_COLORS[type]} ${donutStart}% ${end}%`
    donutStart = end
    return segment
  }).join(', ')
  const focusedRows = [...posts].sort((left, right) => postInteraction(right) - postInteraction(left)).slice(0, 12)
  const availableThemes = [...new Set(posts.map(classifyTheme))]
  const detailRows = [...posts]
    .filter((post) => typeFilter === 'all' || lifecycleType(post) === typeFilter)
    .filter((post) => themeFilter === 'all' || classifyTheme(post) === themeFilter)
    .filter((post) => completenessFilter === 'all' || stageCompleteness(post) === completenessFilter)
    .sort((left, right) => right.create_time - left.create_time)
  const detailPageCount = Math.max(1, Math.ceil(detailRows.length / DETAIL_PAGE_SIZE))
  const safeDetailPage = Math.min(detailPage, detailPageCount)
  const pagedDetailRows = detailRows.slice((safeDetailPage - 1) * DETAIL_PAGE_SIZE, safeDetailPage * DETAIL_PAGE_SIZE)

  useEffect(() => {
    setDetailPage(1)
  }, [completenessFilter, themeFilter, typeFilter])

  useEffect(() => {
    if (detailPage > detailPageCount) setDetailPage(detailPageCount)
  }, [detailPage, detailPageCount])

  const chartWidth = 820
  const chartHeight = 300
  const padding = { left: 64, right: 28, top: 24, bottom: 44 }
  const innerWidth = chartWidth - padding.left - padding.right
  const innerHeight = chartHeight - padding.top - padding.bottom
  const allValues = [
    ...topPosts.flatMap((post) => STAGES.flatMap((stage) => {
      const value = interactionByStage(post).get(stage)
      return value == null ? [] : [value]
    })),
    ...aggregate.map((item) => item.value),
  ]
  const maxValue = Math.max(...allValues, 1)
  const logMax = Math.log10(maxValue + 1)
  const x = (index: number) => padding.left + index / (STAGES.length - 1) * innerWidth
  const y = (value: number) => padding.top + innerHeight - Math.log10(value + 1) / logMax * innerHeight
  const averagePath = aggregate.map((item, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(item.value)}`).join(' ')

  return (
    <div className="space-y-3">
      <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><div className="text-xs font-semibold text-cyber-text-primary">{t('lifecycle.multiCurve')}</div><div className="mt-1 text-[9px] text-cyber-text-muted">{t('lifecycle.fixedSampleHint', { count: fixedSample.length })}</div></div>
          <Select value={curveGroup} onValueChange={(value) => setCurveGroup(value as typeof curveGroup)}>
            <SelectTrigger className="h-8 w-[170px] text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>{(['top', 'earlyBurst', 'quickDecline', 'longTail', 'sustained'] as const).map((group) => <SelectItem key={group} value={group}>{t(`lifecycle.groups.${group}`)}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {topPosts.length > 0 ? (
          <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="mt-3 w-full">
            {[0, .25, .5, .75, 1].map((ratio) => <g key={ratio}><line x1={padding.left} y1={y(maxValue * ratio)} x2={chartWidth - padding.right} y2={y(maxValue * ratio)} stroke="rgb(var(--cyber-border-subtle))" /><text x={padding.left - 8} y={y(maxValue * ratio) + 3} textAnchor="end" fill="rgb(var(--cyber-text-muted))" fontSize="9">{formatNumber(maxValue * ratio)}</text></g>)}
            {STAGES.map((stage, index) => <text key={stage} x={x(index)} y={chartHeight - 10} textAnchor="middle" fill="rgb(var(--cyber-text-muted))" fontSize="10">{stage}</text>)}
            <path d={averagePath} fill="none" stroke="rgb(var(--cyber-neon-green))" strokeWidth="4" strokeDasharray="8 5" opacity="0.9" />
            {topPosts.map((post, postIndex) => {
              const byStage = interactionByStage(post)
              const availablePoints = STAGE_ORDER.flatMap((stage, index) => {
                const value = byStage.get(stage)
                return value == null ? [] : [{ stage, index, value }]
              })
              return (
                <g key={post.aweme_id}>
                  {availablePoints.slice(1).map((current, index) => {
                    const previous = availablePoints[index]
                    const hasMissingStage = current.index - previous.index > 1
                    return <line key={`${current.stage}-line`} x1={x(previous.index)} y1={y(previous.value)} x2={x(current.index)} y2={y(current.value)} stroke={LINE_COLORS[postIndex]} strokeWidth="2" strokeDasharray={hasMissingStage ? '5 4' : undefined} />
                  })}
                  {STAGES.map((stage, index) => {
                    const value = byStage.get(stage)
                    if (value == null) return <g key={`${stage}-missing`}><circle cx={x(index)} cy={chartHeight - padding.bottom} r="4" fill="none" stroke="rgb(var(--cyber-neon-orange))" strokeDasharray="2 2" /><text x={x(index)} y={chartHeight - padding.bottom - 8} textAnchor="middle" fill="rgb(var(--cyber-neon-orange))" fontSize="8">{t('lifecycle.noData')}</text></g>
                    return <circle key={`${stage}-point`} cx={x(index)} cy={y(value)} r="3.5" fill={LINE_COLORS[postIndex]}><title>{post.title} · {stage}: {value}</title></circle>
                  })}
                </g>
              )
            })}
          </svg>
        ) : <div className="py-16 text-center text-xs text-cyber-text-muted">{t('lifecycle.noCurveData')}</div>}
        <div className="mt-2 flex flex-wrap gap-3">
          {topPosts.map((post, index) => <span key={post.aweme_id} className="inline-flex items-center gap-1.5 text-[9px] text-cyber-text-muted"><span className="h-2 w-2 rounded-full" style={{ background: LINE_COLORS[index] }} />{post.title.slice(0, 18)}</span>)}
          <span className="inline-flex items-center gap-1.5 text-[9px] text-cyber-neon-green"><span className="h-0.5 w-5 border-t-2 border-dashed border-cyber-neon-green" />{t('lifecycle.fullAverage')}</span>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12">
        <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm xl:col-span-4">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('lifecycle.averageCurve')}</div>
          <div className="mt-1 text-[9px] text-cyber-text-muted">{t('lifecycle.fixedSample')}</div>
          <div className="mt-4 space-y-3">{aggregate.map((item) => <div key={item.stage}><div className="flex items-center justify-between text-[10px]"><span className="text-cyber-text-secondary">{item.stage}</span><span className="font-semibold numeric-value text-cyber-text-primary">{formatNumber(item.value)}</span></div><div className="mt-1.5 h-2 rounded-sm bg-cyber-bg-tertiary"><div className="h-full rounded-sm bg-cyber-neon-cyan" style={{ width: `${Math.max(item.value ? .75 : 0, item.value / Math.max(...aggregate.map((row) => row.value), 1) * 100)}%` }} /></div></div>)}</div>
          {fixedSample.length === 0 ? <div className="mt-4 rounded-md border border-cyber-neon-orange/30 bg-cyber-neon-orange/5 p-3 text-[10px] text-cyber-neon-orange">{t('lifecycle.noFixedSample')}</div> : null}
        </section>

        <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm xl:col-span-4">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('lifecycle.increments')}</div>
          <div className="mt-4 space-y-4">{increments.map((item) => { const contribution = positiveIncrementTotal ? Math.max(0, item.value) / positiveIncrementTotal * 100 : 0; return <div key={`${item.from}-${item.to}`}><div className="flex items-center justify-between"><span className="text-[10px] text-cyber-text-secondary">{item.from} → {item.to}</span><span className="font-semibold numeric-value text-[11px] text-cyber-text-primary">{formatNumber(item.value)}</span></div><div className="mt-1 flex items-center justify-between text-[9px] text-cyber-text-muted"><span>{t('lifecycle.incrementContribution')}</span><span className="numeric-value">{contribution.toFixed(1)}%</span></div><div className="mt-1.5 h-2 rounded-sm bg-cyber-bg-tertiary"><div className={`h-full rounded-sm ${item.value < 0 ? 'bg-cyber-neon-pink' : 'bg-cyber-neon-green'}`} style={{ width: `${item.value ? Math.max(.75, Math.abs(item.value) / Math.max(...increments.map((row) => Math.abs(row.value)), 1) * 100) : 0}%` }} /></div></div> })}</div>
        </section>

        <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm xl:col-span-4">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('lifecycle.rhythm')}</div>
          <div className="mt-5 flex items-center gap-6">
            <div className="h-32 w-32 shrink-0 rounded-full" style={{ background: `conic-gradient(${donutGradient})` }}><div className="m-5 flex h-[88px] w-[88px] items-center justify-center rounded-full bg-cyber-bg-panel"><div className="text-center"><div className="text-lg font-semibold numeric-value text-cyber-text-primary">{lifecycleTotal}</div><div className="text-[9px] text-cyber-text-muted">{t('performance.posts')}</div></div></div></div>
            <div className="min-w-0 flex-1 space-y-2">{typeOrder.map((type) => <div key={type} className="flex items-center gap-2 text-[10px]"><span className="h-2.5 w-2.5 rounded-full" style={{ background: TYPE_COLORS[type] }} /><span className="text-cyber-text-secondary">{t(`lifecycle.types.${type}`)}</span><span className="ml-auto numeric-value text-cyber-text-primary">{lifecycleCounts[type]}</span><span className="w-12 text-right numeric-value text-cyber-text-muted">{lifecycleTotal ? (lifecycleCounts[type] / lifecycleTotal * 100).toFixed(1) : '0.0'}%</span></div>)}</div>
          </div>
          <div className="mt-4 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3 text-[9px] leading-4 text-cyber-text-muted">{t('lifecycle.classificationHint')}</div>
        </section>
      </div>

      <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-1 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-1">
            <button type="button" onClick={() => setDetailTab('focus')} className={`rounded px-3 py-1.5 text-[10px] ${detailTab === 'focus' ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'text-cyber-text-muted'}`}>{t('lifecycle.focusDetail')}</button>
            <button type="button" onClick={() => setDetailTab('all')} className={`rounded px-3 py-1.5 text-[10px] ${detailTab === 'all' ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'text-cyber-text-muted'}`}>{t('lifecycle.allPosts')}</button>
          </div>
          {detailTab === 'all' ? (
            <div className="flex flex-wrap items-center gap-2">
              <Select value={typeFilter} onValueChange={(value) => setTypeFilter(value as typeof typeFilter)}>
                <SelectTrigger className="h-8 w-[130px] text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{(['all', 'earlyBurst', 'quickDecline', 'longTail', 'sustained'] as const).map((type) => <SelectItem key={type} value={type}>{t(`lifecycle.filters.type.${type}`)}</SelectItem>)}</SelectContent>
              </Select>
              <Select value={themeFilter} onValueChange={setThemeFilter}>
                <SelectTrigger className="h-8 w-[140px] text-xs"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="all">{t('lifecycle.filters.allThemes')}</SelectItem>{availableThemes.map((theme) => <SelectItem key={theme} value={theme}>{t(`topics.themes.${theme}`)}</SelectItem>)}</SelectContent>
              </Select>
              <Select value={completenessFilter} onValueChange={(value) => setCompletenessFilter(value as typeof completenessFilter)}>
                <SelectTrigger className="h-8 w-[150px] text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{(['all', 'complete', 'missing72', 'incomplete'] as const).map((value) => <SelectItem key={value} value={value}>{t(`lifecycle.filters.completeness.${value}`)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          ) : null}
        </div>

        <div className="mt-4 max-h-[560px] overflow-auto rounded-md border border-cyber-border-subtle">
          <table className="w-full min-w-[1080px] text-xs">
            <thead className="sticky top-0 z-10 bg-cyber-bg-tertiary"><tr className="border-b border-cyber-border-subtle text-left text-[9px] text-cyber-text-muted"><th className="p-3">{t('analytics.post')}</th><th className="p-3">{t('lifecycle.publishDate')}</th><th className="p-3">{t('lifecycle.theme')}</th><th className="p-3">{t('lifecycle.type')}</th><th className="p-3">{t('lifecycle.completeness')}</th><th data-numeric="true" className="p-3 text-right">{t('lifecycle.burst')}</th><th data-numeric="true" className="p-3 text-right">{t('lifecycle.tail')}</th><th data-numeric="true" className="p-3 text-right">{t('lifecycle.persistence')}</th></tr></thead>
            <tbody>{(detailTab === 'focus' ? focusedRows : pagedDetailRows).map((post) => { const metrics = lifecycleMetrics(post); const type = lifecycleType(post); const completeness = stageCompleteness(post); const stages = interactionByStage(post); return <tr key={post.aweme_id} onClick={() => setSelectedPost(post)} className="cursor-pointer border-b border-cyber-border-subtle/40 hover:bg-cyber-bg-tertiary/30"><td title={post.title} className="max-w-[360px] truncate p-3 text-cyber-text-primary">{post.title}</td><td className="p-3 numeric-value text-cyber-text-secondary">{formatDate(post.create_time)}</td><td className="p-3 text-cyber-text-secondary">{t(`topics.themes.${classifyTheme(post)}`)}</td><td className="p-3"><span className="whitespace-nowrap rounded px-2 py-1 text-[9px]" style={{ color: TYPE_COLORS[type], background: `${TYPE_COLORS[type]}18` }}>{t(`lifecycle.types.${type}`)}</span></td><td className="p-3"><div className="flex gap-1">{STAGE_ORDER.map((stage) => <span key={stage} className={`rounded px-1.5 py-0.5 text-[8px] ${stages.has(stage) ? 'bg-cyber-neon-green/10 text-cyber-neon-green' : 'bg-cyber-bg-tertiary text-cyber-text-muted'}`}>{stage}</span>)}</div><div className="mt-1 text-[8px] text-cyber-text-muted">{t(`lifecycle.completenessValues.${completeness}`)}</div></td><td data-numeric="true" className="p-3 text-right text-cyber-text-secondary">{metrics.burst == null ? <span className="text-cyber-text-muted">{t('lifecycle.noData')}</span> : metrics.burst.toFixed(2)}</td><td data-numeric="true" className="p-3 text-right text-cyber-text-secondary">{metrics.tail == null ? <span className="text-cyber-text-muted">{t('lifecycle.noData')}</span> : metrics.tail.toFixed(2)}</td><td data-numeric="true" className="p-3 text-right text-cyber-text-secondary">{metrics.persistence == null ? <span className="text-cyber-text-muted">{t('lifecycle.noData')}</span> : metrics.persistence.toFixed(2)}</td></tr> })}</tbody>
          </table>
          {detailRows.length === 0 && detailTab === 'all' ? <div className="py-12 text-center text-xs text-cyber-text-muted">{t('lifecycle.noFilteredData')}</div> : null}
        </div>

        {detailTab === 'all' ? <div className="mt-3 flex items-center justify-between"><span className="text-[9px] text-cyber-text-muted">{t('lifecycle.detailResult', { count: detailRows.length })}</span><div className="flex items-center gap-2"><Button type="button" variant="outline" size="sm" disabled={safeDetailPage <= 1} onClick={() => setDetailPage((page) => Math.max(1, page - 1))} className="h-7 w-7 p-0"><ChevronLeft className="h-3.5 w-3.5" /></Button><span className="min-w-20 text-center text-[9px] numeric-value text-cyber-text-muted">{safeDetailPage} / {detailPageCount}</span><Button type="button" variant="outline" size="sm" disabled={safeDetailPage >= detailPageCount} onClick={() => setDetailPage((page) => Math.min(detailPageCount, page + 1))} className="h-7 w-7 p-0"><ChevronRight className="h-3.5 w-3.5" /></Button></div></div> : null}
      </section>

      {selectedPost ? (
        <div className="fixed inset-0 z-[70]">
          <button type="button" aria-label={t('lifecycle.closeDetail')} onClick={() => setSelectedPost(null)} className="absolute inset-0 cursor-default bg-black/45" />
          <aside className="absolute right-0 top-0 h-full w-full max-w-3xl overflow-y-auto border-l border-cyber-border-default bg-cyber-bg-panel shadow-2xl">
            <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-cyber-border-subtle bg-cyber-bg-panel/95 px-5 py-4 backdrop-blur">
              <div className="min-w-0"><div className="truncate text-sm font-semibold text-cyber-text-primary">{selectedPost.title}</div><div className="mt-1 text-[9px] text-cyber-text-muted">{formatDate(selectedPost.create_time)} · {t(`topics.themes.${classifyTheme(selectedPost)}`)} · {t(`lifecycle.types.${lifecycleType(selectedPost)}`)}</div></div>
              <div className="ml-auto flex items-center gap-1"><a href={selectedPost.canonical_url} target="_blank" rel="noopener noreferrer" className="flex h-8 w-8 items-center justify-center rounded-md text-cyber-text-muted hover:bg-cyber-bg-tertiary hover:text-cyber-neon-cyan"><ExternalLink className="h-4 w-4" /></a><Button type="button" variant="ghost" size="sm" onClick={() => setSelectedPost(null)} className="h-8 w-8 p-0"><X className="h-4 w-4" /></Button></div>
            </header>
            <div className="space-y-4 p-5"><SnapshotCurve post={selectedPost} /><div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr className="border-b border-cyber-border-subtle text-left text-[9px] text-cyber-text-muted"><th className="p-2">{t('monitorDashboard.stage')}</th><th className="p-2">{t('monitorDashboard.actualTime')}</th><th data-numeric="true" className="p-2 text-right">{t('monitorDashboard.metricLikes')}</th><th data-numeric="true" className="p-2 text-right">{t('monitorDashboard.metricCollections')}</th><th data-numeric="true" className="p-2 text-right">{t('monitorDashboard.metricComments')}</th><th data-numeric="true" className="p-2 text-right">{t('monitorDashboard.metricShares')}</th></tr></thead><tbody>{[...selectedPost.snapshots].sort((left, right) => left.actual_age_seconds - right.actual_age_seconds).map((snapshot) => <tr key={snapshot.stage} className="border-b border-cyber-border-subtle/40"><td className="p-2 text-cyber-neon-cyan">{snapshot.stage}</td><td className="p-2 numeric-value text-cyber-text-secondary">{new Date(snapshot.captured_at * 1000).toLocaleString()}</td><td data-numeric="true" className="p-2 text-right">{snapshot.liked_count}</td><td data-numeric="true" className="p-2 text-right">{snapshot.collected_count}</td><td data-numeric="true" className="p-2 text-right">{snapshot.comment_count}</td><td data-numeric="true" className="p-2 text-right">{snapshot.share_count}</td></tr>)}</tbody></table></div></div>
          </aside>
        </div>
      ) : null}
    </div>
  )
}
