import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Activity, BarChart3, Clock3, Database, Eye, Heart, MessageSquare, Search, Share2, X } from 'lucide-react'
import { monitorApi, type MonitorSnapshot } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'


type MetricKey = 'liked_count' | 'collected_count' | 'comment_count' | 'share_count'

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


function MetricTrend({ snapshots, metric }: { snapshots: MonitorSnapshot[]; metric: MetricKey }) {
  const points = useMemo(
    () => snapshots
      .map((snapshot) => ({ x: snapshot.actual_age_seconds, y: Number(snapshot[metric] || 0), stage: snapshot.stage }))
      .sort((a, b) => a.x - b.x),
    [snapshots, metric],
  )

  if (points.length === 0) {
    return <div className="h-56 flex items-center justify-center text-xs text-cyber-text-muted">暂无快照数据</div>
  }

  const width = 760
  const height = 250
  const padding = { top: 20, right: 28, bottom: 42, left: 58 }
  const innerWidth = width - padding.left - padding.right
  const innerHeight = height - padding.top - padding.bottom
  const minX = points[0].x
  const maxX = Math.max(points[points.length - 1].x, minX + 1)
  const maxY = Math.max(...points.map((point) => point.y), 1)
  const chartMaxY = Math.ceil(maxY * 1.1)
  const x = (value: number) => padding.left + ((value - minX) / (maxX - minX)) * innerWidth
  const y = (value: number) => padding.top + innerHeight - (value / chartMaxY) * innerHeight
  const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(point.x)} ${y(point.y)}`).join(' ')
  const xTicks = [minX, (minX + maxX) / 2, maxX]
  const yTicks = [0, chartMaxY / 2, chartMaxY]

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-64 text-cyber-neon-cyan" role="img" aria-label="作品互动增长曲线">
      <title>作品互动增长曲线</title>
      {yTicks.map((tick) => (
        <g key={`y-${tick}`} className="text-cyber-border-subtle">
          <line x1={padding.left} y1={y(tick)} x2={width - padding.right} y2={y(tick)} stroke="currentColor" strokeWidth="1" opacity="0.55" />
          <text x={padding.left - 10} y={y(tick) + 4} textAnchor="end" fill="currentColor" className="text-[11px] text-cyber-text-muted">
            {Math.round(tick)}
          </text>
        </g>
      ))}
      <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} className="text-cyber-border-default" stroke="currentColor" strokeWidth="1" />
      <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} className="text-cyber-border-default" stroke="currentColor" strokeWidth="1" />
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((point) => (
        <g key={`${point.stage}-${point.x}`}>
          <circle cx={x(point.x)} cy={y(point.y)} r="5" fill="currentColor" />
          <text x={x(point.x)} y={height - 16} textAnchor="middle" fill="currentColor" className="text-[11px] text-cyber-text-muted">
            {formatAge(point.x)}
          </text>
          <title>{`${point.stage}: ${point.y}`}</title>
        </g>
      ))}
      {xTicks.map((tick, index) => (
        <text
          key={`x-${index}`}
          x={x(tick)}
          y={height - 4}
          textAnchor={index === 0 ? 'start' : index === xTicks.length - 1 ? 'end' : 'middle'}
          fill="currentColor"
          className="text-[11px] text-cyber-text-muted"
        >
          {formatAge(tick)}
        </text>
      ))}
    </svg>
  )
}


export function MonitorDashboard() {
  const { t } = useTranslation('config')
  const { data } = useQuery({
    queryKey: ['monitorDashboard'],
    queryFn: async () => (await monitorApi.getDashboard()).data,
    refetchInterval: 30000,
  })
  const [selectedAwemeId, setSelectedAwemeId] = useState('')
  const [metric, setMetric] = useState<MetricKey>('liked_count')
  const [searchText, setSearchText] = useState('')

  const normalizedSearch = searchText.trim().toLowerCase()
  const filteredPosts = (data?.posts || []).filter((post) => {
    if (!normalizedSearch) return true
    return post.title.toLowerCase().includes(normalizedSearch) || post.aweme_id.includes(normalizedSearch)
  })
  const selectedPost = (data?.posts || []).find((post) => post.aweme_id === selectedAwemeId)

  const counts = data?.counts
  const jobCounts = counts?.jobs || {}
  const stats = [
    { label: t('monitorDashboard.totalPosts'), value: counts?.posts ?? 0, icon: Database },
    { label: t('monitorDashboard.snapshots'), value: counts?.snapshots ?? 0, icon: Activity },
    { label: t('monitorDashboard.pending'), value: jobCounts.pending ?? 0, icon: Clock3 },
    { label: t('monitorDashboard.done'), value: jobCounts.done ?? 0, icon: Eye },
    { label: t('monitorDashboard.missed'), value: jobCounts.missed ?? 0, icon: BarChart3 },
  ]

  return (
    <section className="rounded-lg glass-panel float-panel overflow-hidden">
      <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
        <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center flex-shrink-0">
          <Activity className="h-4 w-4 text-cyber-neon-cyan" />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-mono font-semibold text-cyber-text-primary tracking-wide">
            {t('monitorDashboard.title')}
          </div>
          <div className="text-[10px] text-cyber-text-muted leading-snug truncate">
            {t('monitorDashboard.description')}
          </div>
        </div>
      </header>

      <div className="p-4 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {stats.map(({ label, value, icon: Icon }) => (
            <div key={label} className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-3">
              <div className="flex items-center gap-2 text-[10px] font-mono text-cyber-text-muted">
                <Icon className="w-3.5 h-3.5" />
                {label}
              </div>
              <div className="mt-1 text-lg font-mono text-cyber-text-primary">{value}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(240px,340px)_1fr] gap-4">
          <div className="space-y-3">
            <div className="text-[10px] font-mono text-cyber-text-muted">{t('monitorDashboard.selectPost')}</div>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-cyber-text-muted" />
              <Input
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder={t('monitorDashboard.searchPlaceholder')}
                className="h-9 pl-9 pr-3 text-xs"
              />
            </div>
            <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 max-h-64 overflow-y-auto">
              {filteredPosts.length > 0 ? filteredPosts.map((post) => {
                const active = post.aweme_id === selectedAwemeId
                return (
                  <button
                    key={post.aweme_id}
                    type="button"
                    onClick={() => setSelectedAwemeId(post.aweme_id)}
                    className={`w-full text-left px-3 py-2 border-b border-cyber-border-subtle/40 last:border-b-0 transition-colors ${active ? 'bg-cyber-neon-cyan/10 text-cyber-neon-cyan' : 'text-cyber-text-secondary hover:bg-cyber-bg-tertiary/50'}`}
                  >
                    <div className="text-xs font-mono line-clamp-2">{post.title || post.aweme_id}</div>
                    <div className="mt-1 text-[10px] text-cyber-text-muted font-mono">
                      {post.aweme_id} · {t('monitorDashboard.snapshotCount', { count: post.snapshots.length })}
                    </div>
                  </button>
                )
              }) : (
                <div className="px-3 py-4 text-xs text-cyber-text-muted">{t('monitorDashboard.noMatch')}</div>
              )}
            </div>
            <div className="flex items-center justify-between gap-2 text-[10px] font-mono text-cyber-text-muted">
              <span>{t('monitorDashboard.searchResult', { count: filteredPosts.length })}</span>
              {selectedPost ? (
                <button type="button" onClick={() => setSelectedAwemeId('')} className="inline-flex items-center gap-1 hover:text-cyber-neon-pink">
                  <X className="w-3 h-3" />
                  {t('monitorDashboard.clearSelection')}
                </button>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-1">
              {METRICS.map(({ key, label, icon: Icon }) => (
                <Button
                  key={key}
                  type="button"
                  variant={metric === key ? 'default' : 'outline'}
                  size="sm"
                  aria-pressed={metric === key}
                  onClick={() => setMetric(key)}
                  className="h-8 px-2.5 font-mono text-[10px]"
                >
                  <Icon className="w-3.5 h-3.5" />
                  {t(`monitorDashboard.${label}`)}
                </Button>
              ))}
            </div>
          </div>

          <div className="min-w-0">
            {selectedPost ? <MetricTrend snapshots={selectedPost.snapshots} metric={metric} /> : (
              <div className="h-64 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 flex flex-col items-center justify-center gap-3">
                <div className="text-3xl font-mono text-cyber-neon-cyan">{counts?.posts ?? 0}</div>
                <div className="text-xs font-mono text-cyber-text-primary">{t('monitorDashboard.totalPosts')}</div>
                <div className="text-[10px] font-mono text-cyber-text-muted">
                  {t('monitorDashboard.totalSnapshots', { count: counts?.snapshots ?? 0 })}
                </div>
              </div>
            )}
          </div>
        </div>

        {selectedPost && selectedPost.snapshots.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-left text-cyber-text-muted border-b border-cyber-border-subtle">
                  <th className="py-2 pr-4">{t('monitorDashboard.stage')}</th>
                  <th className="py-2 pr-4">{t('monitorDashboard.actualTime')}</th>
                  <th className="py-2 pr-4">{t('monitorDashboard.actualAge')}</th>
                  <th className="py-2 pr-4">{t('monitorDashboard.likes')}</th>
                  <th className="py-2 pr-4">{t('monitorDashboard.collections')}</th>
                  <th className="py-2 pr-4">{t('monitorDashboard.comments')}</th>
                  <th className="py-2">{t('monitorDashboard.shares')}</th>
                </tr>
              </thead>
              <tbody>
                {[...selectedPost.snapshots].sort((a, b) => a.actual_age_seconds - b.actual_age_seconds).map((snapshot) => (
                  <tr key={`${snapshot.stage}-${snapshot.captured_at}`} className="border-b border-cyber-border-subtle/40 text-cyber-text-secondary">
                    <td className="py-2 pr-4 text-cyber-neon-cyan">{snapshot.stage}</td>
                    <td className="py-2 pr-4">{new Date(snapshot.captured_at * 1000).toLocaleString()}</td>
                    <td className="py-2 pr-4">{formatAge(snapshot.actual_age_seconds)}</td>
                    <td className="py-2 pr-4">{snapshot.liked_count}</td>
                    <td className="py-2 pr-4">{snapshot.collected_count}</td>
                    <td className="py-2 pr-4">{snapshot.comment_count}</td>
                    <td className="py-2">{snapshot.share_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </section>
  )
}
