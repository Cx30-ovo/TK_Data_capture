import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, BarChart3, Gauge, Grid3X3, TrendingUp } from 'lucide-react'
import { monitorApi, type AnalyticsGrowthRate } from '@/lib/api'
import { Button } from '@/components/ui/button'


const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


function metricLabel(metric: string): string {
  return metric.replace('_count', '').replace('collected', 'collect')
}


export function MonitorAnalytics() {
  const { t } = useTranslation('config')
  const [leaderboardMetric, setLeaderboardMetric] = useState('likes')
  const { data } = useQuery({
    queryKey: ['monitorAnalytics'],
    queryFn: async () => (await monitorApi.getAnalytics()).data,
    refetchInterval: 60000,
  })

  const heatmapMax = Math.max(...(data?.heatmap || []).map((cell) => cell.avg_likes), 1)
  const leaderboard = data?.leaderboard?.[leaderboardMetric] || []
  const growth = (data?.growth_rates || []).slice(0, 12)
  const anomalies = data?.anomalies || []

  return (
    <div className="space-y-4 animate-slide-up">
      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
          <TrendingUp className="h-4 w-4 text-cyber-neon-green" />
          <div>
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.stageDelta')}</div>
            <div className="text-[10px] text-cyber-text-muted">{t('analytics.stageDeltaHint')}</div>
          </div>
        </header>
        <div className="p-4 overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-left text-cyber-text-muted border-b border-cyber-border-subtle">
                <th className="py-2 pr-4">{t('analytics.stage')}</th>
                <th className="py-2 pr-4">{t('analytics.samples')}</th>
                <th className="py-2 pr-4">{t('analytics.avgLikes')}</th>
                <th className="py-2 pr-4">{t('analytics.avgCollections')}</th>
                <th className="py-2 pr-4">{t('analytics.avgComments')}</th>
                <th className="py-2">{t('analytics.avgShares')}</th>
              </tr>
            </thead>
            <tbody>
              {(data?.stage_deltas || []).map((item) => (
                <tr key={item.stage} className="border-b border-cyber-border-subtle/40">
                  <td className="py-2 pr-4 text-cyber-neon-cyan">{item.stage}</td>
                  <td className="py-2 pr-4">{item.sample_count}</td>
                  <td className="py-2 pr-4">{item.liked_count}</td>
                  <td className="py-2 pr-4">{item.collected_count}</td>
                  <td className="py-2 pr-4">{item.comment_count}</td>
                  <td className="py-2">{item.share_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <section className="rounded-lg glass-panel float-panel overflow-hidden">
          <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-2 bg-cyber-bg-tertiary/30">
            <Gauge className="h-4 w-4 text-cyber-neon-cyan" />
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.growthSpeed')}</div>
          </header>
          <div className="p-4 space-y-2">
            {growth.map((item: AnalyticsGrowthRate) => (
              <div key={`${item.aweme_id}-${item.metric}-${item.from_stage}-${item.to_stage}`} className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-2.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-mono text-cyber-text-primary truncate">{item.title}</span>
                  <span className="text-xs font-mono text-cyber-neon-cyan">+{item.per_hour}/h</span>
                </div>
                <div className="mt-1 text-[10px] font-mono text-cyber-text-muted">
                  {metricLabel(item.metric)} · {item.from_stage} → {item.to_stage} · +{item.delta}
                </div>
              </div>
            ))}
            {growth.length === 0 ? <div className="py-8 text-center text-xs text-cyber-text-muted">{t('analytics.noData')}</div> : null}
          </div>
        </section>

        <section className="rounded-lg glass-panel float-panel overflow-hidden">
          <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-2 bg-cyber-bg-tertiary/30">
            <BarChart3 className="h-4 w-4 text-cyber-neon-purple" />
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.engagementRates')}</div>
          </header>
          <div className="p-4 overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-left text-cyber-text-muted border-b border-cyber-border-subtle">
                  <th className="py-2 pr-4">{t('analytics.post')}</th>
                  <th className="py-2 pr-3">{t('analytics.likeRate')}</th>
                  <th className="py-2 pr-3">{t('analytics.collectRate')}</th>
                  <th className="py-2 pr-3">{t('analytics.commentRate')}</th>
                  <th className="py-2">{t('analytics.shareRate')}</th>
                </tr>
              </thead>
              <tbody>
                {(data?.engagement_rates || []).slice(0, 12).map((item) => (
                  <tr key={item.aweme_id} className="border-b border-cyber-border-subtle/40">
                    <td className="py-2 pr-4 max-w-[320px] truncate text-cyber-text-primary">{item.title}</td>
                    <td className="py-2 pr-3">{item.like_rate}%</td>
                    <td className="py-2 pr-3">{item.collect_rate}%</td>
                    <td className="py-2 pr-3">{item.comment_rate}%</td>
                    <td className="py-2">{item.share_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex flex-wrap items-center gap-3 bg-cyber-bg-tertiary/30">
          <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.leaderboard')}</div>
          <div className="flex flex-wrap gap-1">
            {['likes', 'collections', 'comments', 'shares', 'overall'].map((metric) => (
              <Button key={metric} type="button" size="sm" variant={leaderboardMetric === metric ? 'default' : 'outline'} onClick={() => setLeaderboardMetric(metric)} className="h-7 px-2.5 font-mono text-[10px]">
                {t(`analytics.rank.${metric}`)}
              </Button>
            ))}
          </div>
        </header>
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-2">
          {leaderboard.slice(0, 10).map((item, index) => (
            <div key={item.aweme_id} className="flex items-center gap-3 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 px-3 py-2">
              <span className="w-6 text-center text-xs font-mono text-cyber-neon-cyan">{index + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-mono text-cyber-text-primary truncate">{item.title}</div>
                <div className="text-[10px] font-mono text-cyber-text-muted">{item.stage}</div>
              </div>
              <div className="text-xs font-mono text-cyber-text-secondary">{item[leaderboardMetric === 'overall' ? 'score' : `${leaderboardMetric}_count` as keyof typeof item]}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-2 bg-cyber-bg-tertiary/30">
          <Grid3X3 className="h-4 w-4 text-cyber-neon-orange" />
          <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.publishHeatmap')}</div>
        </header>
        <div className="p-4 overflow-x-auto">
          <div className="min-w-[760px] grid grid-cols-[54px_repeat(24,1fr)] gap-0.5">
            <div />
            {Array.from({ length: 24 }, (_, hour) => <div key={hour} className="text-center text-[9px] font-mono text-cyber-text-muted">{hour}</div>)}
            {WEEKDAYS.map((weekday, weekdayIndex) => (
              <div key={weekday} className="contents">
                <div className="text-[10px] font-mono text-cyber-text-muted py-1">{weekday}</div>
                {Array.from({ length: 24 }, (_, hour) => {
                  const cell = data?.heatmap.find((item) => item.weekday === weekdayIndex && item.hour === hour)
                  const intensity = cell ? cell.avg_likes / heatmapMax : 0
                  return (
                    <div
                      key={`${weekdayIndex}-${hour}`}
                      title={`${weekday} ${hour}:00 · ${cell?.post_count || 0} 篇 · ${cell?.avg_likes || 0} 平均点赞`}
                      className="h-6 rounded-sm border border-cyber-border-subtle/30"
                      style={{ backgroundColor: `rgb(var(--cyber-neon-cyan) / ${Math.max(0.04, intensity * 0.8)})` }}
                    />
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-2 bg-cyber-bg-tertiary/30">
          <AlertTriangle className="h-4 w-4 text-cyber-neon-pink" />
          <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('analytics.anomalies')}</div>
        </header>
        <div className="p-4 space-y-2">
          {anomalies.length > 0 ? anomalies.slice(0, 10).map((item) => (
            <div key={`${item.aweme_id}-${item.from_stage}-${item.to_stage}`} className="rounded-md border border-cyber-neon-pink/30 bg-cyber-neon-pink/5 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-mono text-cyber-neon-pink">异常爆发</span>
                <span className="text-xs font-mono text-cyber-text-primary truncate">{item.title}</span>
                <span className="ml-auto text-xs font-mono text-cyber-neon-pink">{item.per_hour}/h</span>
              </div>
              <div className="mt-1 text-[10px] font-mono text-cyber-text-muted">
                {item.from_stage} → {item.to_stage} · 基线 {item.baseline_per_hour}/h · 倍数 {item.score}x
              </div>
            </div>
          )) : <div className="py-8 text-center text-xs text-cyber-text-muted">{t('analytics.noAnomalies')}</div>}
        </div>
      </section>
    </div>
  )
}
