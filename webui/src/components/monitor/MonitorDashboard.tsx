import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, BarChart3, Heart, MessageSquare, Share2 } from 'lucide-react'
import { type MonitorDashboardPost, type MonitorJob, type MonitorSnapshot } from '@/lib/api'
import { Button } from '@/components/ui/button'


type MetricKey = 'liked_count' | 'collected_count' | 'comment_count' | 'share_count'
type MarkerState = 'actual' | 'missed' | 'failed' | 'pending' | 'insufficient' | 'future'

const STAGE_ORDER = ['first_seen', '1h', '6h', '24h', '72h', '7d'] as const
const STAGE_AGE_SECONDS: Record<string, number> = {
  first_seen: 0,
  '1h': 3600,
  '6h': 6 * 3600,
  '24h': 24 * 3600,
  '72h': 72 * 3600,
  '7d': 7 * 24 * 3600,
}
const METRICS: Array<{ key: MetricKey; label: string; icon: typeof Heart }> = [
  { key: 'liked_count', label: 'metricLikes', icon: Heart },
  { key: 'collected_count', label: 'metricCollections', icon: BarChart3 },
  { key: 'comment_count', label: 'metricComments', icon: MessageSquare },
  { key: 'share_count', label: 'metricShares', icon: Share2 },
]


function formatAge(seconds: number): string {
  if (seconds >= 86400) return `${(seconds / 86400).toFixed(1)}d`
  if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)}h`
  return `${Math.max(1, Math.round(seconds / 60))}m`
}


function formatDateTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}


function markerState(
  stage: string,
  snapshot: MonitorSnapshot | undefined,
  job: MonitorJob | undefined,
  postAgeSeconds: number,
): MarkerState {
  if (snapshot) return 'actual'
  if (job?.status === 'missed') return 'missed'
  if (job?.status === 'failed') return 'failed'
  if (job?.status === 'pending' || job?.status === 'running') return 'pending'
  if (job?.status === 'done') return 'insufficient'
  return postAgeSeconds >= (STAGE_AGE_SECONDS[stage] || 0) ? 'insufficient' : 'future'
}


function MetricTrendChart({
  snapshots,
  jobs,
  metric,
  stageFilter,
  postAgeSeconds,
  compact,
  comparisonPosts,
  showComparison,
}: {
  snapshots: MonitorSnapshot[]
  jobs: MonitorJob[]
  metric: MetricKey
  stageFilter: string
  postAgeSeconds: number
  compact: boolean
  comparisonPosts: MonitorDashboardPost[]
  showComparison: boolean
}) {
  const { t } = useTranslation('config')
  const displayedStages = stageFilter === 'all'
    ? [...STAGE_ORDER]
    : STAGE_ORDER.filter((stage) => stage === stageFilter)
  const snapshotByStage = useMemo(() => new Map(snapshots.map((snapshot) => [snapshot.stage, snapshot])), [snapshots])
  const jobByStage = useMemo(() => new Map(jobs.map((job) => [job.stage, job])), [jobs])
  const comparisonByStage = useMemo(() => new Map(STAGE_ORDER.map((stage) => {
    const values = comparisonPosts.flatMap((post) => {
      const snapshot = post.snapshots.find((item) => item.stage === stage)
      return snapshot ? [Number(snapshot[metric] || 0)] : []
    })
    return [stage, values.length > 0 ? values.reduce((sum, value) => sum + value, 0) / values.length : null]
  })), [comparisonPosts, metric])
  const states = displayedStages.map((stage) => markerState(
    stage,
    snapshotByStage.get(stage),
    jobByStage.get(stage),
    postAgeSeconds,
  ))
  const values = displayedStages.map((stage) => Number(snapshotByStage.get(stage)?.[metric] || 0))
  const maxY = Math.max(...values, 1)
  const chartMaxY = Math.ceil(maxY * 1.15)
  const width = 760
  const height = compact ? 190 : 260
  const padding = { top: 20, right: 28, bottom: 44, left: 58 }
  const innerWidth = width - padding.left - padding.right
  const innerHeight = height - padding.top - padding.bottom
  const denominator = Math.max(displayedStages.length - 1, 1)
  const x = (index: number) => padding.left + (index / denominator) * innerWidth
  const y = (value: number) => padding.top + innerHeight - (value / chartMaxY) * innerHeight
  const yTicks = [0, chartMaxY / 2, chartMaxY]

  const segments: string[] = []
  for (let index = 0; index < displayedStages.length - 1; index += 1) {
    if (states[index] !== 'actual' || states[index + 1] !== 'actual') continue
    const leftValue = values[index]
    const rightValue = values[index + 1]
    segments.push(`M ${x(index)} ${y(leftValue)} L ${x(index + 1)} ${y(rightValue)}`)
  }
  const comparisonSegments: string[] = []
  if (showComparison) {
    for (let index = 0; index < displayedStages.length - 1; index += 1) {
      const leftValue = comparisonByStage.get(displayedStages[index])
      const rightValue = comparisonByStage.get(displayedStages[index + 1])
      if (leftValue == null || rightValue == null) continue
      comparisonSegments.push(`M ${x(index)} ${y(leftValue)} L ${x(index + 1)} ${y(rightValue)}`)
    }
  }

  if (snapshots.length === 0 && states.every((state) => state === 'future')) {
    return <div className="flex h-64 items-center justify-center text-xs font-mono text-cyber-text-muted">{t('monitorDashboard.noSnapshots')}</div>
  }

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={t('monitorDashboard.trendTitle')}>
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="text-cyber-border-subtle">
            <line x1={padding.left} y1={y(tick)} x2={width - padding.right} y2={y(tick)} stroke="currentColor" strokeWidth="1" opacity="0.55" />
            <text x={padding.left - 10} y={y(tick) + 4} textAnchor="end" fill="currentColor" className="text-[11px] text-cyber-text-muted">{Math.round(tick)}</text>
          </g>
        ))}
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} className="text-cyber-border-default" stroke="currentColor" strokeWidth="1" />
        <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} className="text-cyber-border-default" stroke="currentColor" strokeWidth="1" />

        <g className="text-cyber-neon-green">
          {segments.map((path) => <path key={path} d={path} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />)}
          {displayedStages.map((stage, index) => states[index] === 'actual' ? (
            <g key={`actual-${stage}`}>
              <circle cx={x(index)} cy={y(values[index])} r="5" fill="currentColor" />
              <title>{`${stage}: ${values[index]}`}</title>
            </g>
          ) : null)}
        </g>
        {showComparison ? <g className="text-cyber-neon-cyan">{comparisonSegments.map((path) => <path key={path} d={path} fill="none" stroke="currentColor" strokeWidth="1.8" strokeDasharray="5 4" />)}</g> : null}

        {displayedStages.map((stage, index) => {
          const state = states[index]
          if (state === 'actual' || state === 'future') return null
          if (state === 'missed') {
            return <text key={`marker-${stage}`} x={x(index)} y={height - padding.bottom + 15} textAnchor="middle" className="text-cyber-neon-orange text-[13px] font-bold">×<title>{t('monitorDashboard.marker.missed')}</title></text>
          }
          if (state === 'failed') {
            return <polygon key={`marker-${stage}`} points={`${x(index)},${height - padding.bottom + 10} ${x(index) - 5},${height - padding.bottom + 20} ${x(index) + 5},${height - padding.bottom + 20}`} className="fill-cyber-neon-pink"><title>{t('monitorDashboard.marker.failed')}</title></polygon>
          }
          if (state === 'pending') {
            return <circle key={`marker-${stage}`} cx={x(index)} cy={height - padding.bottom + 15} r="5" fill="none" strokeWidth="2" className="stroke-cyber-neon-cyan"><title>{t('monitorDashboard.marker.pending')}</title></circle>
          }
          return <circle key={`marker-${stage}`} cx={x(index)} cy={height - padding.bottom + 15} r="5" fill="none" strokeWidth="2" strokeDasharray="2 2" className="stroke-cyber-neon-cyan"><title>{t('monitorDashboard.marker.insufficient')}</title></circle>
        })}

        {displayedStages.map((stage, index) => (
          <text key={`x-${stage}`} x={x(index)} y={height - 5} textAnchor="middle" fill="currentColor" className="text-[10px] text-cyber-text-muted">{stage === 'first_seen' ? 'first' : stage}</text>
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[9px] font-mono">
        <span className="text-cyber-neon-green">● {t('monitorDashboard.marker.actual')}</span>
        <span className="text-cyber-neon-orange">× {t('monitorDashboard.marker.missed')}</span>
        <span className="text-cyber-neon-pink">▲ {t('monitorDashboard.marker.failed')}</span>
        <span className="text-cyber-neon-cyan">○ {t('monitorDashboard.marker.pending')}</span>
        <span className="text-cyber-neon-cyan">◌ {t('monitorDashboard.marker.insufficient')}</span>
        {showComparison ? <span className="text-cyber-neon-cyan">-- {t('monitorDashboard.accountAverage')}</span> : null}
      </div>
    </div>
  )
}


interface MonitorDashboardProps {
  posts: MonitorDashboardPost[]
  selectedPost?: MonitorDashboardPost
  selectedJobs: MonitorJob[]
  stageFilter: string
  compact?: boolean
  comparisonPosts?: MonitorDashboardPost[]
}


export function MonitorDashboard({ posts, selectedPost, selectedJobs, stageFilter, compact = false, comparisonPosts = [] }: MonitorDashboardProps) {
  const { t } = useTranslation('config')
  const [metric, setMetric] = useState<MetricKey>('liked_count')
  const [showComparison, setShowComparison] = useState(false)
  const postAgeSeconds = selectedPost ? Math.max(0, Math.floor(Date.now() / 1000) - selectedPost.create_time) : 0

  return (
    <section className="rounded-lg glass-panel float-panel overflow-hidden">
      <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
        <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center flex-shrink-0">
          <Activity className="h-4 w-4 text-cyber-neon-green" />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('monitorDashboard.trendTitle')}</div>
          <div className="text-[10px] text-cyber-text-muted">{t('monitorDashboard.trendHint')}</div>
        </div>
      </header>

      <div className="p-4 space-y-4">
        {selectedPost ? (
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
              <div className="min-w-0 truncate text-xs font-mono text-cyber-text-primary">{selectedPost.title || selectedPost.aweme_id}</div>
              <div className="text-[10px] font-mono text-cyber-text-muted">{t('monitorDashboard.publishTime')}: {formatDateTime(selectedPost.create_time)}</div>
              <div className="text-[10px] font-mono text-cyber-text-muted">{t('monitorDashboard.firstSeen')}: {formatDateTime(selectedPost.first_seen_at)}</div>
              <div className="text-[10px] font-mono text-cyber-text-muted">ID: {selectedPost.aweme_id}</div>
            </div>
            <div className="flex flex-wrap gap-1">
              {METRICS.map(({ key, label, icon: Icon }) => (
                <Button key={key} type="button" variant={metric === key ? 'default' : 'outline'} size="sm" aria-pressed={metric === key} onClick={() => setMetric(key)} className="h-8 px-2.5 font-mono text-[10px]">
                  <Icon className="h-3.5 w-3.5" />
                  {t(`monitorDashboard.${label}`)}
                </Button>
              ))}
              <Button type="button" variant={showComparison ? 'default' : 'outline'} size="sm" aria-pressed={showComparison} onClick={() => setShowComparison((visible) => !visible)} className="h-8 px-2.5 text-[10px]">
                {t('monitorDashboard.compareAverage')}
              </Button>
            </div>
            <MetricTrendChart snapshots={selectedPost.snapshots} jobs={selectedJobs} metric={metric} stageFilter={stageFilter} postAgeSeconds={postAgeSeconds} compact={compact} comparisonPosts={comparisonPosts} showComparison={showComparison} />
            <details className="mt-3 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
              <summary className="cursor-pointer px-3 py-2 text-[10px] font-mono text-cyber-text-muted">{t('monitorDashboard.expandTable')}</summary>
              <div className="overflow-x-auto border-t border-cyber-border-subtle">
                <table className="data-table data-table-compact w-full text-xs font-mono">
                  <thead>
                    <tr className="text-left text-cyber-text-muted border-b border-cyber-border-subtle">
                      <th className="py-2 pl-3 pr-4">{t('monitorDashboard.stage')}</th>
                      <th className="py-2 pr-4">{t('monitorDashboard.markerState')}</th>
                      <th className="py-2 pr-4">{t('monitorDashboard.actualTime')}</th>
                      <th data-numeric="true" className="py-2 pr-4 text-right">{t('monitorDashboard.actualAge')}</th>
                      <th data-numeric="true" className="py-2 pr-4 text-right">{t('monitorDashboard.likes')}</th>
                      <th data-numeric="true" className="py-2 pr-4 text-right">{t('monitorDashboard.collections')}</th>
                      <th data-numeric="true" className="py-2 pr-4 text-right">{t('monitorDashboard.comments')}</th>
                      <th data-numeric="true" className="py-2 pr-3 text-right">{t('monitorDashboard.shares')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {STAGE_ORDER.filter((stage) => stageFilter === 'all' || stage === stageFilter).map((stage) => {
                      const snapshot = selectedPost.snapshots.find((item) => item.stage === stage)
                      const job = selectedJobs.find((item) => item.stage === stage)
                      const state = markerState(stage, snapshot, job, postAgeSeconds)
                      return (
                        <tr key={stage} className="border-b border-cyber-border-subtle/40 text-cyber-text-secondary">
                          <td className="py-2 pl-3 pr-4 text-cyber-neon-cyan">{stage}</td>
                          <td className="py-2 pr-4">{t(`monitorDashboard.marker.${state}`)}</td>
                          <td className="py-2 pr-4">{snapshot ? formatDateTime(snapshot.captured_at) : '-'}</td>
                          <td data-numeric="true" className="py-2 pr-4 text-right">{snapshot ? formatAge(snapshot.actual_age_seconds) : '-'}</td>
                          <td data-numeric="true" className="py-2 pr-4 text-right">{snapshot?.liked_count ?? '-'}</td>
                          <td data-numeric="true" className="py-2 pr-4 text-right">{snapshot?.collected_count ?? '-'}</td>
                          <td data-numeric="true" className="py-2 pr-4 text-right">{snapshot?.comment_count ?? '-'}</td>
                          <td data-numeric="true" className="py-2 pr-3 text-right">{snapshot?.share_count ?? '-'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        ) : (
          <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
            <div className="text-3xl font-mono text-cyber-neon-cyan">{posts.length}</div>
            <div className="text-xs font-mono text-cyber-text-primary">{t('monitorDashboard.totalPosts')}</div>
            <div className="text-[10px] font-mono text-cyber-text-muted">{t('monitorDashboard.selectPostHint')}</div>
          </div>
        )}
      </div>
    </section>
  )
}


export function MonitorDataSummary({
  posts,
  selectedPost,
  scopeStats,
}: {
  posts: MonitorDashboardPost[]
  selectedPost?: MonitorDashboardPost
  scopeStats: { normal: number; insufficient: number; missed: number; abnormal: number }
}) {
  const { t } = useTranslation('config')
  const latestSnapshot = selectedPost
    ? [...selectedPost.snapshots].sort((left, right) => right.actual_age_seconds - left.actual_age_seconds)[0]
    : undefined
  const latestCapturedAt = posts.flatMap((post) => post.snapshots).reduce((latest, snapshot) => Math.max(latest, snapshot.captured_at), 0)
  const stageCoverage = STAGE_ORDER.map((stage) => ({
    stage,
    count: posts.filter((post) => post.snapshots.some((snapshot) => snapshot.stage === stage)).length,
  }))
  const currentScore = latestSnapshot
    ? latestSnapshot.liked_count + latestSnapshot.collected_count * 2 + latestSnapshot.comment_count * 3 + latestSnapshot.share_count * 2
    : 0

  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-4">
      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('monitorDashboard.dataScope')}</div>
        </header>
        <div className="grid grid-cols-3 gap-2 p-3 text-left">
          <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-2">
            <div className="text-[9px] text-cyber-text-muted">{t('monitorDashboard.totalPosts')}</div>
            <div className="mt-1 text-lg numeric-value text-cyber-neon-cyan">{posts.length}</div>
          </div>
          <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-2">
            <div className="text-[9px] text-cyber-text-muted">{t('monitorDashboard.snapshots')}</div>
            <div className="mt-1 text-lg numeric-value text-cyber-neon-green">{posts.reduce((sum, post) => sum + post.snapshots.length, 0)}</div>
          </div>
          <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-2">
            <div className="text-[9px] text-cyber-text-muted">{t('monitorDashboard.lastSnapshot')}</div>
            <div className="mt-1 text-[10px] numeric-value text-cyber-text-primary">{latestCapturedAt ? formatDateTime(latestCapturedAt) : '-'}</div>
          </div>
        </div>
      </section>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('monitorDashboard.samplingQuality')}</div>
        </header>
        <div className="grid grid-cols-2 gap-2 p-3">
          <div className="rounded-md border border-cyber-neon-green/25 bg-cyber-neon-green/5 p-2.5"><div className="text-[9px] text-cyber-text-muted">{t('dataCenter.status.normal')}</div><div className="mt-1 text-lg numeric-value text-cyber-neon-green">{scopeStats.normal}</div></div>
          <div className="rounded-md border border-cyber-neon-cyan/25 bg-cyber-neon-cyan/5 p-2.5"><div className="text-[9px] text-cyber-text-muted">{t('dataCenter.status.insufficient')}</div><div className="mt-1 text-lg numeric-value text-cyber-neon-cyan">{scopeStats.insufficient}</div></div>
          <div className="rounded-md border border-cyber-neon-orange/25 bg-cyber-neon-orange/5 p-2.5"><div className="text-[9px] text-cyber-text-muted">{t('dataCenter.status.missed')}</div><div className="mt-1 text-lg numeric-value text-cyber-neon-orange">{scopeStats.missed}</div></div>
          <div className="rounded-md border border-cyber-neon-pink/25 bg-cyber-neon-pink/5 p-2.5"><div className="text-[9px] text-cyber-text-muted">{t('dataCenter.status.abnormal')}</div><div className="mt-1 text-lg numeric-value text-cyber-neon-pink">{scopeStats.abnormal}</div></div>
        </div>
      </section>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('monitorDashboard.currentKeyMetrics')}</div>
        </header>
        {selectedPost ? (
          <div className="grid grid-cols-3 gap-2 p-3 text-left">
            <div><div className="text-[9px] text-cyber-text-muted">{t('dataCenter.compositeScore')}</div><div className={`mt-1 numeric-value ${latestSnapshot ? 'text-cyber-neon-green' : 'text-cyber-neon-pink'}`}>{currentScore}</div></div>
            <div><div className="text-[9px] text-cyber-text-muted">{t('monitorDashboard.currentStage')}</div><div className="mt-1 text-cyber-text-primary">{latestSnapshot?.stage || '-'}</div></div>
            <div><div className="text-[9px] text-cyber-text-muted">{t('monitorDashboard.latestAge')}</div><div className="mt-1 numeric-value text-cyber-text-primary">{latestSnapshot ? formatAge(latestSnapshot.actual_age_seconds) : '-'}</div></div>
          </div>
        ) : (
          <div className="px-4 py-8 text-center text-xs text-cyber-text-muted">{t('monitorDashboard.selectPostHint')}</div>
        )}
      </section>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('monitorDashboard.stageCoverage')}</div>
        </header>
        <div className="grid grid-cols-2 gap-1.5 p-3">
          {stageCoverage.map((item) => (
            <div key={item.stage} className="flex items-center justify-between rounded border border-cyber-border-subtle bg-cyber-bg-tertiary/20 px-2 py-1.5">
              <span className="text-[9px] text-cyber-text-muted">{item.stage}</span>
              <span className={`numeric-value text-[10px] ${item.count > 0 ? 'text-cyber-neon-green' : 'text-cyber-text-muted'}`}>{item.count}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
