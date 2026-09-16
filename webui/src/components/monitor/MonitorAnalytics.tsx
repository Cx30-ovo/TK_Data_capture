import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, BarChart3, Gauge, Grid3X3, TrendingUp } from 'lucide-react'
import { monitorApi, type AnalyticsGrowthRate, type AnalyticsLeaderboardItem, type MonitorDashboardPost } from '@/lib/api'
import { Button } from '@/components/ui/button'


type AnalyticsMetric = 'liked_count' | 'collected_count' | 'comment_count' | 'share_count'

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const STAGE_ORDER = ['first_seen', '1h', '6h', '24h', '72h', '7d']
const METRICS: AnalyticsMetric[] = ['liked_count', 'collected_count', 'comment_count', 'share_count']
const COLORS = {
  normal: 'bg-cyber-neon-green',
  warning: 'bg-cyber-neon-orange',
  abnormal: 'bg-cyber-neon-pink',
  info: 'bg-cyber-neon-cyan',
}
const METRIC_COLORS: Record<AnalyticsMetric, string> = {
  liked_count: 'bg-cyber-neon-cyan',
  collected_count: 'bg-cyber-neon-purple',
  comment_count: 'bg-cyber-neon-pink',
  share_count: 'bg-cyber-neon-orange',
}
const LEADERBOARD_COLORS: Record<string, string> = {
  likes: 'bg-cyber-neon-cyan',
  collections: 'bg-cyber-neon-purple',
  comments: 'bg-cyber-neon-pink',
  shares: 'bg-cyber-neon-orange',
  overall: 'bg-cyber-neon-green',
}
const LEADERBOARD_FIELDS: Record<string, keyof AnalyticsLeaderboardItem> = {
  likes: 'liked_count',
  collections: 'collected_count',
  comments: 'comment_count',
  shares: 'share_count',
  overall: 'score',
}


function metricLabel(metric: string, t: (key: string) => string): string {
  return t(`analytics.metric.${metric}`)
}


function BarRow({
  label,
  detail,
  value,
  maxValue,
  color,
  suffix,
  valueDetail,
}: {
  label: string
  detail: string
  value: number
  maxValue: number
  color: string
  suffix?: string
  valueDetail?: string
}) {
  const width = maxValue > 0 && value !== 0
    ? Math.max(0.75, Math.min(100, Math.abs(value) / maxValue * 100))
    : 0
  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div title={label} className="line-clamp-2 text-[11px] font-mono leading-4 text-cyber-text-primary">{label}</div>
          <div className="mt-1 truncate text-[9px] font-mono text-cyber-text-muted">{detail}</div>
        </div>
        <div className="min-w-[90px] text-right">
          <div className="whitespace-nowrap text-[12px] font-semibold numeric-value text-cyber-text-primary">{value}{suffix}</div>
          {valueDetail ? <div className="mt-0.5 text-[9px] text-cyber-text-muted">{valueDetail}</div> : null}
        </div>
      </div>
      <div className="relative h-2 overflow-hidden rounded-sm bg-cyber-bg-tertiary">
        <div className={`h-full rounded-sm transition-[width] duration-300 ${color}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}


export function MonitorAnalytics({
  allPosts,
  posts,
  postIds,
  stageFilter,
}: {
  allPosts: MonitorDashboardPost[]
  posts: MonitorDashboardPost[]
  postIds: Set<string>
  stageFilter: string
}) {
  const { t } = useTranslation('config')
  const [analyticsTab, setAnalyticsTab] = useState<'stage' | 'growth' | 'ranking' | 'distribution'>(() => {
    const queryTab = new URLSearchParams(window.location.search).get('analysis')
    return queryTab === 'growth' || queryTab === 'ranking' || queryTab === 'distribution' ? queryTab : 'stage'
  })
  const [stageMetric, setStageMetric] = useState<AnalyticsMetric>('liked_count')
  const [leaderboardMetric, setLeaderboardMetric] = useState('likes')
  const [rankingScope, setRankingScope] = useState<'7d' | 'filtered' | 'all'>('filtered')
  const { data } = useQuery({
    queryKey: ['monitorAnalytics'],
    queryFn: async () => (await monitorApi.getAnalytics()).data,
    refetchInterval: 60000,
  })

  const postMatches = (itemAwemeId: string) => postIds.has(itemAwemeId)
  const stageMatches = (value: string) => stageFilter === 'all' || value === stageFilter
  const stageDeltas = useMemo(() => {
    const aggregates = new Map<string, Array<Record<AnalyticsMetric, number>>>()
    posts.forEach((post) => {
      const byStage = new Map(post.snapshots.map((snapshot) => [snapshot.stage, snapshot]))
      const base = byStage.get('first_seen') || post.snapshots[0]
      if (!base) return
      STAGE_ORDER.slice(1).forEach((stage) => {
        const snapshot = byStage.get(stage)
        if (!snapshot || (stageFilter !== 'all' && stage !== stageFilter)) return
        const delta = {
          liked_count: snapshot.liked_count - base.liked_count,
          collected_count: snapshot.collected_count - base.collected_count,
          comment_count: snapshot.comment_count - base.comment_count,
          share_count: snapshot.share_count - base.share_count,
        }
        aggregates.set(stage, [...(aggregates.get(stage) || []), delta])
      })
    })
    return STAGE_ORDER.slice(1).flatMap((stage) => {
      const rows = aggregates.get(stage) || []
      if (rows.length === 0) return []
      return [{
        stage,
        sample_count: rows.length,
        ...METRICS.reduce<Record<AnalyticsMetric, number>>((result, metric) => {
          result[metric] = Math.round(rows.reduce((sum, row) => sum + row[metric], 0) / rows.length * 100) / 100
          return result
        }, { liked_count: 0, collected_count: 0, comment_count: 0, share_count: 0 }),
      }]
    })
  }, [posts, stageFilter])
  const growth = (data?.growth_rates || [])
    .filter((item) => postMatches(item.aweme_id) && stageMatches(item.from_stage) && stageMatches(item.to_stage))
    .slice(0, 12)
  const engagement = (data?.engagement_rates || [])
    .filter((item) => postMatches(item.aweme_id) && stageMatches(item.stage))
    .slice(0, 12)
  const rankingPostIds = rankingScope === 'filtered'
    ? postIds
    : rankingScope === '7d'
      ? new Set(allPosts.filter((post) => post.create_time >= Math.floor(Date.now() / 1000) - 7 * 24 * 60 * 60).map((post) => post.aweme_id))
      : null
  const leaderboard = (data?.leaderboard?.[leaderboardMetric] || [])
    .filter((item) => (!rankingPostIds || rankingPostIds.has(item.aweme_id)) && stageMatches(item.stage))
    .slice(0, 10)
  const anomalies = (data?.anomalies || [])
    .filter((item) => postMatches(item.aweme_id) && stageMatches(item.from_stage) && stageMatches(item.to_stage))
    .slice(0, 10)

  const heatmap = useMemo(() => {
    const cells = new Map<string, number[]>()
    posts.forEach((post) => {
      const date = new Date(post.create_time * 1000)
      const snapshot = stageFilter === 'all'
        ? post.snapshots[post.snapshots.length - 1]
        : post.snapshots.find((item) => item.stage === stageFilter)
      const key = `${date.getDay() === 0 ? 6 : date.getDay() - 1}:${date.getHours()}`
      cells.set(key, [...(cells.get(key) || []), snapshot?.liked_count || 0])
    })
    return Array.from({ length: 7 }, (_, weekday) => Array.from({ length: 24 }, (_, hour) => {
      const values = cells.get(`${weekday}:${hour}`) || []
      return {
        weekday,
        hour,
        post_count: values.length,
        avg_likes: values.length > 0 ? values.reduce((sum, value) => sum + value, 0) / values.length : 0,
      }
    })).flat()
  }, [posts, stageFilter])

  const heatmapMax = Math.max(...heatmap.map((cell) => cell.avg_likes), 1)
  const stageMax = Math.max(...stageDeltas.map((item) => Math.abs(item[stageMetric])), 1)
  const growthMax = Math.max(...growth.map((item) => Math.abs(item.per_hour)), 1)
  const leaderboardValue = (item: AnalyticsLeaderboardItem) => {
    const field = LEADERBOARD_FIELDS[leaderboardMetric] || 'liked_count'
    const value = item[field]
    return typeof value === 'number' ? value : 0
  }
  const leaderboardMax = Math.max(...leaderboard.map(leaderboardValue), 1)
  const changeAnalyticsTab = (tab: typeof analyticsTab) => {
    setAnalyticsTab(tab)
    const url = new URL(window.location.href)
    url.searchParams.set('analysis', tab)
    window.history.replaceState(null, '', url.toString())
  }

  return (
    <div className="grid grid-cols-1 gap-3 animate-slide-up xl:grid-cols-2">
      <nav className="flex gap-1 overflow-x-auto border-b border-cyber-border-subtle px-1 xl:col-span-2" aria-label={t('analytics.tabs.label')}>
        {(['stage', 'growth', 'ranking', 'distribution'] as const).map((tab) => (
          <button key={tab} type="button" onClick={() => changeAnalyticsTab(tab)} className={`shrink-0 border-b-2 px-4 py-2.5 text-xs font-medium transition-colors ${analyticsTab === tab ? 'border-cyber-neon-cyan text-cyber-neon-cyan' : 'border-transparent text-cyber-text-muted hover:text-cyber-text-primary'}`}>
            {t(`analytics.tabs.${tab}`)}
          </button>
        ))}
      </nav>

      <section className={`rounded-lg glass-panel float-panel overflow-hidden xl:col-span-2 ${analyticsTab === 'stage' ? '' : 'hidden'}`}>
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex flex-wrap items-center gap-3 bg-cyber-bg-tertiary/30">
          <TrendingUp className="h-4 w-4 text-cyber-neon-green" />
          <div className="min-w-0">
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.stageDelta')}</div>
            <div className="text-[10px] text-cyber-text-muted">{t('analytics.stageDeltaHint')}</div>
          </div>
          <div className="ml-auto flex flex-wrap gap-1">
            {(['liked_count', 'collected_count', 'comment_count', 'share_count'] as const).map((metric) => (
              <Button key={metric} type="button" size="sm" variant={stageMetric === metric ? 'default' : 'outline'} onClick={() => setStageMetric(metric)} className="h-7 px-2 font-mono text-[10px]">
                {metricLabel(metric, t)}
              </Button>
            ))}
          </div>
        </header>
        <div className="max-h-[520px] space-y-4 overflow-y-auto p-4">
          {stageDeltas.length > 0 ? (
            <div className="space-y-3">
              {stageDeltas.map((item) => (
                <BarRow
                  key={item.stage}
                  label={item.stage}
                  detail={t('analytics.samplesValue', { count: item.sample_count })}
                  value={item[stageMetric]}
                  maxValue={stageMax}
                  color={item[stageMetric] < 0 ? COLORS.abnormal : METRIC_COLORS[stageMetric]}
                  valueDetail={t('analytics.average')}
                />
              ))}
            </div>
          ) : <div className="py-8 text-center text-xs font-mono text-cyber-text-muted">{t('analytics.noData')}</div>}
          <details className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
            <summary className="cursor-pointer px-3 py-2 text-[10px] font-mono text-cyber-text-muted">{t('analytics.expandTable')}</summary>
            <div className="overflow-x-auto border-t border-cyber-border-subtle">
              <table className="w-full text-xs font-mono">
                <thead><tr className="border-b border-cyber-border-subtle text-left text-cyber-text-muted"><th className="py-2 pl-3 pr-4">{t('analytics.stage')}</th><th data-numeric="true" className="py-2 pr-4 text-right">{t('analytics.samples')}</th><th data-numeric="true" className="py-2 pr-4 text-right">{t('analytics.avgLikes')}</th><th data-numeric="true" className="py-2 pr-4 text-right">{t('analytics.avgCollections')}</th><th data-numeric="true" className="py-2 pr-4 text-right">{t('analytics.avgComments')}</th><th data-numeric="true" className="py-2 pr-3 text-right">{t('analytics.avgShares')}</th></tr></thead>
                <tbody>{stageDeltas.map((item) => <tr key={item.stage} className="border-b border-cyber-border-subtle/40"><td className="py-2 pl-3 pr-4 text-cyber-neon-cyan">{item.stage}</td><td data-numeric="true" className="py-2 pr-4 text-right">{item.sample_count}</td><td data-numeric="true" className="py-2 pr-4 text-right">{item.liked_count}</td><td data-numeric="true" className="py-2 pr-4 text-right">{item.collected_count}</td><td data-numeric="true" className="py-2 pr-4 text-right">{item.comment_count}</td><td data-numeric="true" className="py-2 pr-3 text-right">{item.share_count}</td></tr>)}</tbody>
              </table>
            </div>
          </details>
        </div>
      </section>

      <section className={`rounded-lg glass-panel float-panel overflow-hidden xl:col-span-2 ${analyticsTab === 'growth' ? '' : 'hidden'}`}>
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-2 bg-cyber-bg-tertiary/30">
          <Gauge className="h-4 w-4 text-cyber-neon-green" />
          <div><div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.growthSpeed')}</div><div className="text-[10px] text-cyber-text-muted">{t('analytics.growthHint')}</div></div>
        </header>
        <div className="max-h-[520px] space-y-3 overflow-y-auto p-4">
          {growth.length > 0 ? growth.map((item: AnalyticsGrowthRate) => (
            <BarRow key={`${item.aweme_id}-${item.metric}-${item.from_stage}-${item.to_stage}`} label={item.title} detail={`${item.from_stage} → ${item.to_stage}`} value={item.per_hour} maxValue={growthMax} color={item.per_hour < 0 ? COLORS.abnormal : METRIC_COLORS[item.metric]} suffix="/h" valueDetail={metricLabel(item.metric, t)} />
          )) : <div className="py-8 text-center text-xs font-mono text-cyber-text-muted">{t('analytics.noData')}</div>}
          <details className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
            <summary className="cursor-pointer px-3 py-2 text-[10px] font-mono text-cyber-text-muted">{t('analytics.expandTable')}</summary>
            <div className="overflow-x-auto border-t border-cyber-border-subtle"><table className="w-full text-xs font-mono"><thead><tr className="border-b border-cyber-border-subtle text-left text-cyber-text-muted"><th className="py-2 pl-3 pr-4">{t('analytics.post')}</th><th className="py-2 pr-4">{t('analytics.metric')}</th><th className="py-2 pr-4">{t('analytics.range')}</th><th data-numeric="true" className="py-2 pr-3 text-right">{t('analytics.perHour')}</th></tr></thead><tbody>{growth.map((item) => <tr key={`${item.aweme_id}-${item.metric}`} className="border-b border-cyber-border-subtle/40"><td className="max-w-[360px] truncate py-2 pl-3 pr-4">{item.title}</td><td className="py-2 pr-4">{metricLabel(item.metric, t)}</td><td className="py-2 pr-4">{item.from_stage} → {item.to_stage}</td><td data-numeric="true" className="py-2 pr-3 text-right">{item.per_hour}</td></tr>)}</tbody></table></div>
          </details>
        </div>
      </section>

      <div className={`grid grid-cols-1 gap-3 xl:col-span-2 xl:grid-cols-2 ${analyticsTab === 'ranking' ? '' : 'hidden'}`}>
        <section className="rounded-lg glass-panel float-panel overflow-hidden">
          <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex flex-wrap items-center gap-3 bg-cyber-bg-tertiary/30">
            <BarChart3 className="h-4 w-4 text-cyber-neon-cyan" />
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.leaderboard')}</div>
          </header>
          <div className="flex flex-wrap items-center gap-2 border-b border-cyber-border-subtle px-3 py-2">
            <span className="text-[10px] text-cyber-text-muted">{t('analytics.rankingScope')}</span>
            <div className="flex gap-1">
              {(['7d', 'filtered', 'all'] as const).map((scope) => (
                <Button key={scope} type="button" size="sm" variant={rankingScope === scope ? 'default' : 'outline'} onClick={() => setRankingScope(scope)} className="h-7 px-2 text-[10px]">{t(`analytics.scope.${scope}`)}</Button>
              ))}
            </div>
            <div className="ml-auto flex flex-wrap gap-1">
              {['likes', 'collections', 'comments', 'shares', 'overall'].map((metric) => (
                <Button key={metric} type="button" size="sm" variant={leaderboardMetric === metric ? 'default' : 'outline'} onClick={() => setLeaderboardMetric(metric)} className="h-7 px-2 text-[10px]">{t(`analytics.rank.${metric}`)}</Button>
              ))}
            </div>
          </div>
          <div className="p-4 space-y-3">
            {leaderboard.length > 0 ? leaderboard.map((item, index) => (
              <BarRow key={item.aweme_id} label={`${index + 1}. ${item.title}`} detail={t(`analytics.rank.${leaderboardMetric}`)} value={leaderboardValue(item)} maxValue={leaderboardMax} color={LEADERBOARD_COLORS[leaderboardMetric] || COLORS.info} valueDetail={item.stage} />
            )) : <div className="py-8 text-center text-xs font-mono text-cyber-text-muted">{t('analytics.noData')}</div>}
            <details className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20"><summary className="cursor-pointer px-3 py-2 text-[10px] font-mono text-cyber-text-muted">{t('analytics.expandTable')}</summary><div className="overflow-x-auto border-t border-cyber-border-subtle"><table className="w-full text-xs font-mono"><thead><tr className="border-b border-cyber-border-subtle text-left text-cyber-text-muted"><th data-numeric="true" className="py-2 pl-3 pr-4 text-right">#</th><th className="py-2 pr-4">{t('analytics.post')}</th><th className="py-2 pr-4">{t('analytics.stage')}</th><th data-numeric="true" className="py-2 pr-3 text-right">{t('analytics.value')}</th></tr></thead><tbody>{leaderboard.map((item, index) => <tr key={item.aweme_id} className="border-b border-cyber-border-subtle/40"><td data-numeric="true" className="py-2 pl-3 pr-4 text-right text-cyber-neon-cyan">{index + 1}</td><td className="max-w-[300px] truncate py-2 pr-4">{item.title}</td><td className="py-2 pr-4">{item.stage}</td><td data-numeric="true" className="py-2 pr-3 text-right">{leaderboardValue(item)}</td></tr>)}</tbody></table></div></details>
          </div>
        </section>

        <section className="rounded-lg glass-panel float-panel overflow-hidden">
          <header className="px-4 py-3 border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30"><div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.engagementRates')}</div></header>
          <div className="overflow-x-auto p-4"><table className="w-full text-xs font-mono"><thead><tr className="border-b border-cyber-border-subtle text-left text-cyber-text-muted"><th className="py-2 pr-4">{t('analytics.post')}</th><th data-numeric="true" className="py-2 pr-3 text-right">{t('analytics.likeRate')}</th><th data-numeric="true" className="py-2 pr-3 text-right">{t('analytics.collectRate')}</th><th data-numeric="true" className="py-2 pr-3 text-right">{t('analytics.commentRate')}</th><th data-numeric="true" className="py-2 text-right">{t('analytics.shareRate')}</th></tr></thead><tbody>{engagement.map((item) => <tr key={item.aweme_id} className="border-b border-cyber-border-subtle/40 text-cyber-text-secondary"><td className="max-w-[260px] truncate py-2 pr-4 text-cyber-text-primary">{item.title}</td><td data-numeric="true" className="py-2 pr-3 text-right text-cyber-neon-cyan">{item.like_rate}%</td><td data-numeric="true" className="py-2 pr-3 text-right text-cyber-neon-cyan">{item.collect_rate}%</td><td data-numeric="true" className="py-2 pr-3 text-right text-cyber-neon-cyan">{item.comment_rate}%</td><td data-numeric="true" className="py-2 text-right text-cyber-neon-cyan">{item.share_rate}%</td></tr>)}</tbody></table></div>
        </section>
      </div>

      <section className={`max-h-[460px] rounded-lg glass-panel float-panel overflow-hidden ${analyticsTab === 'distribution' ? '' : 'hidden'}`}>
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-2 bg-cyber-bg-tertiary/30"><Grid3X3 className="h-4 w-4 text-cyber-neon-cyan" /><div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.publishHeatmap')}</div></header>
        <div className="max-h-[400px] overflow-auto p-4"><div className="grid min-w-[760px] grid-cols-[54px_repeat(24,1fr)] gap-0.5"><div />{Array.from({ length: 24 }, (_, hour) => <div key={hour} className="text-center text-[9px] font-mono text-cyber-text-muted">{hour}</div>)}{WEEKDAYS.map((weekday, weekdayIndex) => <div key={weekday} className="contents"><div className="py-1 text-[10px] font-mono text-cyber-text-muted">{weekday}</div>{Array.from({ length: 24 }, (_, hour) => { const cell = heatmap.find((item) => item.weekday === weekdayIndex && item.hour === hour); const intensity = cell ? cell.avg_likes / heatmapMax : 0; return <div key={`${weekdayIndex}-${hour}`} title={`${weekday} ${hour}:00 · ${cell?.post_count || 0} 篇 · ${cell?.avg_likes || 0} 平均点赞`} className="h-6 rounded-sm border border-cyber-border-subtle/30" style={{ backgroundColor: `rgb(var(--cyber-neon-cyan) / ${Math.max(0.04, intensity * 0.8)})` }} /> })}</div>)}</div></div>
      </section>

      <section className={`max-h-[460px] rounded-lg glass-panel float-panel overflow-hidden ${analyticsTab === 'distribution' ? '' : 'hidden'}`}>
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-2 bg-cyber-bg-tertiary/30"><AlertTriangle className="h-4 w-4 text-cyber-neon-pink" /><div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.anomalies')}</div></header>
        <div className="max-h-[400px] space-y-2 overflow-y-auto p-4">{anomalies.length > 0 ? anomalies.map((item) => <div key={`${item.aweme_id}-${item.from_stage}-${item.to_stage}`} className="rounded-md border border-cyber-neon-pink/30 bg-cyber-neon-pink/5 px-3 py-2"><div className="flex flex-wrap items-center gap-2"><span className="text-xs font-mono text-cyber-neon-pink">{t('analytics.abnormalGrowth')}</span><span className="truncate text-xs font-mono text-cyber-text-primary">{item.title}</span><span className="ml-auto text-xs font-mono text-cyber-neon-pink">{item.per_hour}/h</span></div><div className="mt-1 text-[10px] font-mono text-cyber-text-muted">{item.from_stage} → {item.to_stage} · {t('analytics.baseline')} {item.baseline_per_hour}/h · {t('analytics.multiple')} {item.score}x</div></div>) : <div className="py-8 text-center text-xs text-cyber-text-muted">{t('analytics.noAnomalies')}</div>}</div>
      </section>
    </div>
  )
}
