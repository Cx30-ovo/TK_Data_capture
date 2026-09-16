import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MonitorDashboardPost } from '@/lib/api'
import { classifyTheme, extractTags, GENERIC_TAGS, mean, median, postInteraction, THEME_COLORS, THEME_DEFINITIONS } from '@/lib/monitorMetrics'


function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
}


interface TagStat {
  tag: string
  posts: MonitorDashboardPost[]
  count: number
  total: number
  average: number
  dominantTheme: string
}


function buildTagStats(posts: MonitorDashboardPost[]): { tags: TagStat[]; pairs: Array<[string, string, number]> } {
  const groups = new Map<string, MonitorDashboardPost[]>()
  const pairs = new Map<string, number>()
  posts.forEach((post) => {
    const tags = extractTags(post)
    tags.forEach((tag) => groups.set(tag, [...(groups.get(tag) || []), post]))
    for (let index = 0; index < tags.length; index += 1) {
      for (let next = index + 1; next < tags.length; next += 1) {
        const key = [tags[index], tags[next]].sort().join('|||')
        pairs.set(key, (pairs.get(key) || 0) + 1)
      }
    }
  })

  const tagStats = [...groups.entries()].map(([tag, tagPosts]) => {
    const themeCounts = tagPosts.reduce<Record<string, number>>((result, post) => {
      const theme = classifyTheme(post)
      result[theme] = (result[theme] || 0) + 1
      return result
    }, {})
    const dominantTheme = Object.entries(themeCounts).sort((left, right) => right[1] - left[1])[0]?.[0] || 'other'
    const interactions = tagPosts.map(postInteraction)
    return {
      tag,
      posts: tagPosts,
      count: tagPosts.length,
      total: interactions.reduce((sum, value) => sum + value, 0),
      average: mean(interactions),
      dominantTheme,
    }
  }).sort((left, right) => right.total - left.total)

  return {
    tags: tagStats,
    pairs: [...pairs.entries()].map(([key, count]) => {
      const [left, right] = key.split('|||')
      return [left, right, count] as [string, string, number]
    }).sort((left, right) => right[2] - left[2]),
  }
}


export function MonitorTopicAnalytics({ posts }: { posts: MonitorDashboardPost[] }) {
  const { t } = useTranslation('config')
  const [tagMode, setTagMode] = useState<'theme' | 'generic'>('theme')

  const themeStats = useMemo(() => {
    const keys = [...THEME_DEFINITIONS.map((theme) => theme.key), 'other']
    return keys.map((key) => {
      const themePosts = posts.filter((post) => classifyTheme(post) === key)
      const interactions = themePosts.map(postInteraction)
      const middle = median(interactions)
      const threshold = Math.max(middle * 2, 1)
      return {
        key,
        count: themePosts.length,
        total: interactions.reduce((sum, value) => sum + value, 0),
        average: mean(interactions),
        median: middle,
        burstRate: themePosts.length ? themePosts.filter((post) => postInteraction(post) >= threshold).length / themePosts.length * 100 : 0,
      }
    }).filter((item) => item.count > 0)
  }, [posts])

  const allTagStats = useMemo(() => buildTagStats(posts), [posts])
  const displayedTags = tagMode === 'generic'
    ? allTagStats.tags.filter((item) => GENERIC_TAGS.has(item.tag))
    : allTagStats.tags.filter((item) => !GENERIC_TAGS.has(item.tag))
  const displayedPairs = allTagStats.pairs.filter(([left, right]) => {
    const leftGeneric = GENERIC_TAGS.has(left)
    const rightGeneric = GENERIC_TAGS.has(right)
    return tagMode === 'generic' ? leftGeneric || rightGeneric : !leftGeneric && !rightGeneric
  })

  const maxVolume = Math.max(...themeStats.map((item) => item.count), 1)
  const maxAverage = Math.max(...themeStats.map((item) => item.average), 1)
  const maxTotal = Math.max(...themeStats.map((item) => item.total), 1)
  const logMaxAverage = Math.log10(maxAverage + 1)
  const maxTagTotal = Math.max(...displayedTags.map((item) => item.total), 1)

  const network = useMemo(() => {
    const nodes = displayedTags.slice(0, 14).map((item, index) => ({
      ...item,
      x: 50 + Math.cos(index / Math.max(1, Math.min(14, displayedTags.length)) * Math.PI * 2) * 30,
      y: 50 + Math.sin(index / Math.max(1, Math.min(14, displayedTags.length)) * Math.PI * 2) * 30,
    }))
    const indexByTag = new Map(nodes.map((node, index) => [node.tag, index]))
    const edges = displayedPairs.map(([left, right, count]) => ({ left: indexByTag.get(left), right: indexByTag.get(right), count })).filter((edge) => edge.left != null && edge.right != null)

    for (let iteration = 0; iteration < 80; iteration += 1) {
      nodes.forEach((node) => {
        let dx = 0
        let dy = 0
        nodes.forEach((other) => {
          if (node === other) return
          const deltaX = node.x - other.x
          const deltaY = node.y - other.y
          const distanceSquared = Math.max(4, deltaX * deltaX + deltaY * deltaY)
          dx += deltaX / distanceSquared * 2.2
          dy += deltaY / distanceSquared * 2.2
        })
        edges.forEach((edge) => {
          if (edge.left === indexByTag.get(node.tag)) {
            const other = nodes[edge.right as number]
            dx += (other.x - node.x) * 0.004 * edge.count
            dy += (other.y - node.y) * 0.004 * edge.count
          }
          if (edge.right === indexByTag.get(node.tag)) {
            const other = nodes[edge.left as number]
            dx += (other.x - node.x) * 0.004 * edge.count
            dy += (other.y - node.y) * 0.004 * edge.count
          }
        })
        dx += (50 - node.x) * 0.004
        dy += (50 - node.y) * 0.004
        node.x = Math.max(8, Math.min(92, node.x + dx))
        node.y = Math.max(10, Math.min(90, node.y + dy))
      })
    }
    const maxCount = Math.max(...nodes.map((node) => node.count), 1)
    const maxEdge = Math.max(...edges.map((edge) => edge.count), 1)
    return { nodes, edges, maxCount, maxEdge }
  }, [displayedPairs, displayedTags])

  return (
    <div className="space-y-3">
      <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm">
        <div className="flex items-baseline justify-between"><div className="text-xs font-semibold text-cyber-text-primary">{t('topics.comparison')}</div><span className="text-[9px] text-cyber-text-muted">{t('topics.comparisonHint')}</span></div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-xs">
            <thead><tr className="border-b border-cyber-border-subtle text-left text-[9px] text-cyber-text-muted"><th className="pb-2 pr-4">{t('topics.theme')}</th><th data-numeric="true" className="pb-2 pr-4 text-right">{t('topics.volume')}</th><th data-numeric="true" className="pb-2 pr-4 text-right">{t('topics.total')}</th><th data-numeric="true" className="pb-2 pr-4 text-right">{t('topics.average')}</th><th data-numeric="true" className="pb-2 pr-4 text-right">{t('topics.median')}</th><th data-numeric="true" className="pb-2 text-right">{t('topics.burstRate')}</th></tr></thead>
            <tbody>{themeStats.map((item) => <tr key={item.key} className="border-b border-cyber-border-subtle/40"><td className="py-3 pr-4 font-medium text-cyber-text-primary"><span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: THEME_COLORS[item.key] }} />{t(`topics.themes.${item.key}`)}</td><td data-numeric="true" className="py-3 pr-4 text-right text-cyber-text-secondary">{item.count}</td><td data-numeric="true" className="py-3 pr-4 text-right text-cyber-text-primary">{formatNumber(item.total)}</td><td data-numeric="true" className="py-3 pr-4 text-right text-cyber-neon-green">{formatNumber(item.average)}</td><td data-numeric="true" className="py-3 pr-4 text-right text-cyber-neon-purple">{formatNumber(item.median)}</td><td data-numeric="true" className="py-3 text-right text-cyber-neon-orange">{item.burstRate.toFixed(1)}%</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12">
        <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm xl:col-span-8">
          <div className="flex items-center justify-between"><div className="text-xs font-semibold text-cyber-text-primary">{t('topics.bubbleTitle')}</div><span className="text-[9px] text-cyber-text-muted">{t('topics.bubbleScaleHint')}</span></div>
          <div className="relative mt-4 h-[460px] overflow-visible rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/10">
            {themeStats.map((item, index) => {
              const left = 5 + item.count / maxVolume * 88
              const bottom = 8 + Math.log10(item.average + 1) / logMaxAverage * 78
              const size = 28 + Math.sqrt(item.total / maxTotal) * 62
              const color = THEME_COLORS[item.key] || THEME_COLORS.other
              return (
                <div key={item.key} className="group absolute z-10 -translate-x-1/2 translate-y-1/2 hover:z-[100]" style={{ left: `${left}%`, bottom: `${bottom}%`, width: size, height: size }}>
                  <div className="h-full w-full rounded-full border opacity-75 transition-opacity group-hover:opacity-100" style={{ borderColor: color, background: `${color}33` }} />
                  <div className={`absolute left-1/2 w-[112px] -translate-x-1/2 text-center text-[8px] leading-3 ${index % 2 === 0 ? 'top-full mt-1' : 'bottom-full mb-1'}`} style={{ color }}>{t(`topics.themes.${item.key}`)}</div>
                  <div className="pointer-events-none absolute bottom-full left-1/2 z-[999] mb-2 hidden w-52 -translate-x-1/2 rounded-md border border-cyber-border-default bg-cyber-bg-panel p-3 text-left shadow-2xl group-hover:block">
                    <div className="text-[11px] font-semibold text-cyber-text-primary">{t(`topics.themes.${item.key}`)}</div>
                    <div className="mt-2 space-y-1 text-[9px] text-cyber-text-muted"><div>{t('topics.total')}: <b className="numeric-value text-cyber-text-primary">{formatNumber(item.total)}</b></div><div>{t('topics.volume')}: <b className="numeric-value text-cyber-text-primary">{item.count}</b></div><div>{t('topics.burstRate')}: <b className="numeric-value text-cyber-neon-orange">{item.burstRate.toFixed(1)}%</b></div></div>
                  </div>
                </div>
              )
            })}
            <div className="absolute bottom-1 left-1/2 -translate-x-1/2 text-[9px] text-cyber-text-muted">{t('topics.volume')} →</div>
            <div className="absolute left-1 top-1/2 origin-left -rotate-90 text-[9px] text-cyber-text-muted">{t('topics.average')} (log) →</div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 px-3 py-2">
            <span className="text-[9px] font-medium text-cyber-text-secondary">{t('performance.themeLegend')}</span>
            {themeStats.map((item) => <span key={item.key} className="inline-flex items-center gap-1.5 text-[9px] text-cyber-text-muted"><span className="h-2.5 w-2.5 rounded-full" style={{ background: THEME_COLORS[item.key] }} />{t(`topics.themes.${item.key}`)}</span>)}
          </div>
        </section>

        <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm xl:col-span-4">
          <div className="flex items-center justify-between gap-2"><div className="text-xs font-semibold text-cyber-text-primary">{t('topics.tagContribution')}</div><div className="flex gap-1"><button type="button" onClick={() => setTagMode('theme')} className={`rounded px-2 py-1 text-[9px] ${tagMode === 'theme' ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'text-cyber-text-muted'}`}>{t('topics.tagModes.theme')}</button><button type="button" onClick={() => setTagMode('generic')} className={`rounded px-2 py-1 text-[9px] ${tagMode === 'generic' ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'text-cyber-text-muted'}`}>{t('topics.tagModes.generic')}</button></div></div>
          <div className="mt-4 max-h-[390px] space-y-3 overflow-y-auto pr-1">
            {displayedTags.map((item) => <div key={item.tag}><div className="flex items-center justify-between gap-3 text-[10px]"><span className="min-w-0 truncate text-cyber-text-secondary">#{item.tag}{item.count < 3 ? <span className="ml-1 rounded bg-cyber-neon-orange/10 px-1 py-0.5 text-[8px] text-cyber-neon-orange">{t('topics.singleBurst')}</span> : null}</span><span className="font-semibold numeric-value text-cyber-text-primary">{formatNumber(item.total)}</span></div><div className="mt-1 flex items-center justify-between text-[8px] text-cyber-text-muted"><span>{t('topics.volume')}: {item.count}</span><span>{t('topics.average')}: {formatNumber(item.average)}</span></div><div className="mt-1 h-2 overflow-hidden rounded-sm bg-cyber-bg-tertiary"><div className="h-full rounded-sm" style={{ width: `${Math.max(item.total ? .75 : 0, item.total / maxTagTotal * 100)}%`, background: THEME_COLORS[item.dominantTheme] || THEME_COLORS.other }} /></div></div>)}
            {displayedTags.length === 0 ? <div className="py-8 text-center text-xs text-cyber-text-muted">{t('topics.noTags')}</div> : null}
          </div>
        </section>
      </div>

      <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm">
        <div className="flex items-baseline justify-between"><div className="text-xs font-semibold text-cyber-text-primary">{t('topics.networkTitle')}</div><span className="text-[9px] text-cyber-text-muted">{t('topics.networkHint')}</span></div>
        <svg viewBox="0 0 760 420" className="mt-3 h-[420px] w-full">
          {network.edges.map((edge, index) => {
            const left = network.nodes[edge.left as number]
            const right = network.nodes[edge.right as number]
            return <line key={index} x1={left.x * 7.6} y1={left.y * 4.2} x2={right.x * 7.6} y2={right.y * 4.2} stroke="rgb(var(--cyber-neon-cyan))" strokeOpacity={0.18 + edge.count / network.maxEdge * 0.35} strokeWidth={1 + Math.sqrt(edge.count / network.maxEdge) * 4}><title>{left.tag} + {right.tag}: {edge.count}</title></line>
          })}
          {network.nodes.map((node) => {
            const radius = 7 + Math.sqrt(node.count / network.maxCount) * 16
            return <g key={node.tag}><circle cx={node.x * 7.6} cy={node.y * 4.2} r={radius} fill={`${THEME_COLORS[node.dominantTheme] || THEME_COLORS.other}66`} stroke={THEME_COLORS[node.dominantTheme] || THEME_COLORS.other} strokeWidth="1.5"><title>{node.tag}: {node.count} 篇，总互动 {formatNumber(node.total)}</title></circle><text x={node.x * 7.6} y={node.y * 4.2 + radius + 12} textAnchor="middle" fill="rgb(var(--cyber-text-secondary))" fontSize="10">#{node.tag}</text></g>
          })}
        </svg>
      </section>
    </div>
  )
}
