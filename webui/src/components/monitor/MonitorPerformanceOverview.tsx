import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, BarChart3, Flame, Gauge, Heart, MessageSquare, Share2 } from 'lucide-react'
import type { MonitorDashboardPost } from '@/lib/api'
import { classifyTheme, firstSeenDelayHours, latestSnapshot, mean, median, postInteraction, THEME_COLORS } from '@/lib/monitorMetrics'
import { Button } from '@/components/ui/button'


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
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(Math.round(value))
}


export function MonitorPerformanceOverview({ posts }: { posts: MonitorDashboardPost[] }) {
  const { t } = useTranslation('config')
  const [rankingMetric, setRankingMetric] = useState<'liked_count' | 'share_count' | 'comment_count'>('liked_count')
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
  const ranking = [...posts].sort((left, right) => (latestSnapshot(right)?.[rankingMetric] || 0) - (latestSnapshot(left)?.[rankingMetric] || 0)).slice(0, 10)
  const maxRankingValue = Math.max(...ranking.map((post) => latestSnapshot(post)?.[rankingMetric] || 0), 1)
  const meanMedianRatio = middle > 0 ? average / middle : 0
  const topTenInteraction = [...posts].sort((left, right) => postInteraction(right) - postInteraction(left)).slice(0, 10).reduce((sum, post) => sum + postInteraction(post), 0)
  const totalInteraction = interactions.reduce((sum, value) => sum + value, 0)
  const concentration = totalInteraction > 0 ? topTenInteraction / totalInteraction * 100 : 0
  const maxLikes = Math.max(...posts.map((post) => latestSnapshot(post)?.liked_count || 0), 1)
  const maxComments = Math.max(...posts.map((post) => latestSnapshot(post)?.comment_count || 0), 1)
  const medianLikes = median(posts.map((post) => latestSnapshot(post)?.liked_count || 0))
  const medianComments = median(posts.map((post) => latestSnapshot(post)?.comment_count || 0))
  const logMaxLikes = Math.log10(maxLikes + 1)
  const logMaxComments = Math.log10(maxComments + 1)
  const xPosition = (likes: number) => 2 + Math.log10(likes + 1) / logMaxLikes * 96
  const yPosition = (comments: number) => 2 + Math.log10(comments + 1) / logMaxComments * 96
  const medianX = xPosition(medianLikes)
  const medianY = yPosition(medianComments)
  const xTicks = logTicks(maxLikes)
  const yTicks = logTicks(maxComments)
  const topRightExtreme = [...posts]
    .filter((post) => (latestSnapshot(post)?.liked_count || 0) >= medianLikes && (latestSnapshot(post)?.comment_count || 0) >= medianComments)
    .sort((left, right) => postInteraction(right) - postInteraction(left))[0]
  const bottomRightExtreme = [...posts]
    .filter((post) => (latestSnapshot(post)?.liked_count || 0) >= medianLikes && (latestSnapshot(post)?.comment_count || 0) < medianComments)
    .sort((left, right) => (latestSnapshot(right)?.liked_count || 0) - (latestSnapshot(left)?.liked_count || 0))[0]
  const visibleThemes = [...new Set(posts.map(classifyTheme))]
  const quadrants = useMemo(() => [
    { key: 'highHigh', label: t('performance.quadrants.highHigh'), posts: posts.filter((post) => (latestSnapshot(post)?.liked_count || 0) >= medianLikes && (latestSnapshot(post)?.comment_count || 0) >= medianComments) },
    { key: 'highLow', label: t('performance.quadrants.highLow'), posts: posts.filter((post) => (latestSnapshot(post)?.liked_count || 0) >= medianLikes && (latestSnapshot(post)?.comment_count || 0) < medianComments) },
    { key: 'lowHigh', label: t('performance.quadrants.lowHigh'), posts: posts.filter((post) => (latestSnapshot(post)?.liked_count || 0) < medianLikes && (latestSnapshot(post)?.comment_count || 0) >= medianComments) },
    { key: 'lowLow', label: t('performance.quadrants.lowLow'), posts: posts.filter((post) => (latestSnapshot(post)?.liked_count || 0) < medianLikes && (latestSnapshot(post)?.comment_count || 0) < medianComments) },
  ], [medianComments, medianLikes, posts, t])

  const kpis = [
    { label: t('performance.posts'), value: formatNumber(posts.length), icon: BarChart3, tone: 'text-cyber-neon-cyan' },
    { label: t('performance.totalInteraction'), value: formatNumber(interactions.reduce((sum, value) => sum + value, 0)), icon: Activity, tone: 'text-cyber-neon-green' },
    { label: t('performance.averageInteraction'), value: formatNumber(average), icon: Gauge, tone: 'text-cyber-neon-cyan' },
    { label: t('performance.medianInteraction'), value: formatNumber(middle), icon: Gauge, tone: 'text-cyber-neon-purple' },
    { label: t('performance.burstRate'), value: `${posts.length ? (burstPosts.length / posts.length * 100).toFixed(1) : '0.0'}%`, icon: Flame, tone: 'text-cyber-neon-pink' },
    { label: t('performance.zeroRate'), value: `${posts.length ? (zeroPosts.length / posts.length * 100).toFixed(1) : '0.0'}%`, icon: Activity, tone: zeroPosts.length ? 'text-cyber-neon-orange' : 'text-cyber-neon-green' },
    { label: t('performance.firstSeenDelay'), value: `${formatNumber(median(delays))}h`, icon: Gauge, tone: 'text-cyber-text-secondary' },
  ]

  return (
    <div className="space-y-3">
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
          <div key={item.label} className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-3 shadow-sm">
            <div className="flex items-center gap-2 text-[9px] text-cyber-text-muted"><item.icon className="h-3 w-3" />{item.label}</div>
            <div className={`mt-2 text-xl font-semibold numeric-value ${item.tone}`}>{item.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12">
        <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm xl:col-span-4">
          <div className="text-xs font-semibold text-cyber-text-primary">{t('performance.structure')}</div>
          <div className="mt-6">
            <div className="flex h-7 overflow-hidden rounded-md bg-cyber-bg-tertiary">
              <div className="h-full bg-cyber-neon-cyan" style={{ width: `${structureShares.liked}%` }} />
              <div className="h-full bg-cyber-neon-purple" style={{ width: `${structureShares.collected}%` }} />
              <div className="h-full bg-cyber-neon-pink" style={{ width: `${structureShares.comment}%` }} />
              <div className="h-full bg-cyber-neon-orange" style={{ width: `${structureShares.share}%` }} />
            </div>
            <div className="mt-4 space-y-3 text-[10px]">
              {[
                { label: t('monitorDashboard.metricLikes'), value: structure.liked, percent: structureShares.liked, icon: Heart, color: 'bg-cyber-neon-cyan' },
                { label: t('monitorDashboard.metricCollections'), value: structure.collected, percent: structureShares.collected, icon: BarChart3, color: 'bg-cyber-neon-purple' },
                { label: t('monitorDashboard.metricComments'), value: structure.comment, percent: structureShares.comment, icon: MessageSquare, color: 'bg-cyber-neon-pink' },
                { label: t('monitorDashboard.metricShares'), value: structure.share, percent: structureShares.share, icon: Share2, color: 'bg-cyber-neon-orange' },
              ].map((item) => <div key={item.label} className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-sm ${item.color}`} /><item.icon className="h-3 w-3 text-cyber-text-muted" /><span className="text-cyber-text-muted">{item.label}</span><span className="ml-auto numeric-value text-cyber-text-primary">{formatNumber(item.value)}</span><span className="w-12 text-right font-semibold numeric-value text-cyber-text-secondary">{item.percent.toFixed(1)}%</span></div>)}
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm xl:col-span-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs font-semibold text-cyber-text-primary">{t('performance.ranking')}</div>
            <div className="flex items-center gap-1 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-1">
              {([
                { key: 'liked_count', icon: Heart },
                { key: 'share_count', icon: Share2 },
                { key: 'comment_count', icon: MessageSquare },
              ] as const).map((metric) => (
                <Button key={metric.key} type="button" variant={rankingMetric === metric.key ? 'default' : 'outline'} size="sm" onClick={() => setRankingMetric(metric.key)} className="h-8 px-3 text-[10px]">
                  <metric.icon className="h-3.5 w-3.5" />
                  {t(`performance.rankingMetrics.${metric.key}`)}
                </Button>
              ))}
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {ranking.map((post, index) => {
              const value = latestSnapshot(post)?.[rankingMetric] || 0
              const width = Math.max(value > 0 ? 0.75 : 0, value / maxRankingValue * 100)
              return (
                <div key={post.aweme_id} className="grid grid-cols-[24px_minmax(0,1fr)_90px] items-center gap-3">
                  <span className={`text-center text-[11px] font-bold ${index < 3 ? 'text-cyber-neon-orange' : 'text-cyber-text-muted'}`}>{index + 1}</span>
                  <div className="min-w-0"><div title={post.title || post.aweme_id} className="line-clamp-1 text-[11px] text-cyber-text-primary">{post.title || post.aweme_id}</div><div className="mt-1.5 h-1.5 overflow-hidden rounded-sm bg-cyber-bg-tertiary"><div className={`h-full rounded-sm ${index === 0 ? 'bg-cyber-neon-pink' : index === 1 ? 'bg-cyber-neon-orange' : 'bg-cyber-neon-cyan'}`} style={{ width: `${width}%` }} /></div></div>
                  <span className="text-right text-[11px] font-semibold numeric-value text-cyber-text-primary">{formatNumber(value)}</span>
                </div>
              )
            })}
          </div>
        </section>
      </div>

      <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm">
        <div className="flex items-baseline justify-between"><div className="text-xs font-semibold text-cyber-text-primary">{t('performance.quadrantTitle')}</div><span className="text-[9px] text-cyber-text-muted">{t('performance.quadrantHint')}</span></div>
        <div className="relative mt-4 h-[440px] overflow-hidden rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/10">
          <div className="absolute left-0 top-0 bg-cyber-neon-cyan/5" style={{ width: `${medianX}%`, height: `${100 - medianY}%` }} />
          <div className="absolute top-0 bg-cyber-neon-pink/5" style={{ left: `${medianX}%`, width: `${100 - medianX}%`, height: `${100 - medianY}%` }} />
          <div className="absolute left-0 bg-cyber-neon-purple/5" style={{ top: `${100 - medianY}%`, width: `${medianX}%`, height: `${medianY}%` }} />
          <div className="absolute bg-cyber-neon-orange/5" style={{ left: `${medianX}%`, top: `${100 - medianY}%`, width: `${100 - medianX}%`, height: `${medianY}%` }} />
          <div className="absolute top-0 h-full w-px bg-cyber-border-default" style={{ left: `${medianX}%` }} />
          <div className="absolute left-0 h-px w-full bg-cyber-border-default" style={{ top: `${100 - medianY}%` }} />
          <div className="absolute bottom-[4px] left-[2%] h-[96%] w-px bg-cyber-border-default/80" />
          <div className="absolute bottom-[4px] left-[2%] h-px w-[96%] bg-cyber-border-default/80" />
          {xTicks.map((tick) => <div key={`x-${tick}`} className="absolute bottom-[2px] h-2 w-px bg-cyber-text-muted" style={{ left: `${xPosition(tick)}%` }}><span className="absolute left-1/2 top-3 -translate-x-1/2 whitespace-nowrap text-[8px] text-cyber-text-muted">{formatCompactNumber(tick)}</span></div>)}
          {yTicks.map((tick) => <div key={`y-${tick}`} className="absolute left-[2px] h-px w-2 bg-cyber-text-muted" style={{ bottom: `${yPosition(tick)}%` }}><span className="absolute right-3 -translate-y-1/2 whitespace-nowrap text-[8px] text-cyber-text-muted">{formatCompactNumber(tick)}</span></div>)}
          <div className="absolute left-3 top-3 text-[9px] text-cyber-text-muted">{quadrants[1].label} · {quadrants[1].posts.length}</div>
          <div className="absolute right-3 top-3 text-[9px] text-cyber-text-muted">{quadrants[0].label} · {quadrants[0].posts.length}</div>
          <div className="absolute bottom-3 left-3 text-[9px] text-cyber-text-muted">{quadrants[3].label} · {quadrants[3].posts.length}</div>
          <div className="absolute bottom-3 right-3 text-[9px] text-cyber-text-muted">{quadrants[2].label} · {quadrants[2].posts.length}</div>
          {posts.map((post) => {
            const likes = latestSnapshot(post)?.liked_count || 0
            const comments = latestSnapshot(post)?.comment_count || 0
            const left = xPosition(likes)
            const bottom = yPosition(comments)
            const theme = classifyTheme(post)
            const isTopRight = topRightExtreme?.aweme_id === post.aweme_id
            const isBottomRight = bottomRightExtreme?.aweme_id === post.aweme_id
            return <div key={post.aweme_id} title={`${post.title}\n${t('performance.likes')}: ${likes}\n${t('performance.comments')}: ${comments}`} className={`absolute h-2.5 w-2.5 -translate-x-1/2 translate-y-1/2 rounded-full border opacity-80 hover:z-20 hover:h-4 hover:w-4 hover:opacity-100 ${isTopRight ? 'border-cyber-neon-pink ring-2 ring-cyber-neon-pink/35' : isBottomRight ? 'border-cyber-neon-orange ring-2 ring-cyber-neon-orange/35' : 'border-white/60'}`} style={{ left: `${left}%`, bottom: `${bottom}%`, background: THEME_COLORS[theme] || THEME_COLORS.other }} />
          })}
          <div className="absolute bottom-1 left-1/2 -translate-x-1/2 text-[9px] font-medium text-cyber-text-secondary">{t('performance.likes')} (log) →</div>
          <div className="absolute left-1 top-1/2 origin-left -rotate-90 text-[9px] font-medium text-cyber-text-secondary">{t('performance.comments')} (log) →</div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 px-3 py-2">
          <span className="text-[9px] font-medium text-cyber-text-secondary">{t('performance.themeLegend')}</span>
          {visibleThemes.map((theme) => <span key={theme} className="inline-flex items-center gap-1.5 text-[9px] text-cyber-text-muted"><span className="h-2 w-2 rounded-full" style={{ background: THEME_COLORS[theme] || THEME_COLORS.other }} />{t(`topics.themes.${theme}`)}</span>)}
        </div>
      </section>
    </div>
  )
}
