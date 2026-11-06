import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, CalendarDays, ChevronLeft, ChevronRight, Flame, Maximize2, Minimize2, Pause, Play, RefreshCw, Sparkles, X } from 'lucide-react'
import { monitorApi, type MonitorDashboardPost } from '@/lib/api'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'
import { StatePanel } from '@/components/ui/state-panel'
import { Button } from '@/components/ui/button'
import { PostEditorialTags, postChannel, editorialChannels, editorialRegions, regionDescription } from './PostEditorialTags'

import { SpatialReadingDetail, type ReadingSignal } from './SpatialReadingDetail'
import { presentPost, splitPostText } from '@/lib/postPresentation'
import { hotRankAge, readHotRankCache, saveHotRankCache } from '@/lib/hotRankCache'
type Signal = ReadingSignal
const dayKey = (timestamp: number) => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(timestamp * 1000))
const stamp = (timestamp: number) => timestamp ? new Date(timestamp * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '时间未知'
const compact = (value: number | undefined) => value === undefined ? '—' : value >= 10000 ? `${(value / 10000).toFixed(1)}万` : value.toLocaleString('zh-CN')
const latest = (post: MonitorDashboardPost) => [...post.snapshots].sort((a, b) => b.captured_at - a.captured_at)[0]
const cloudTitle = (title: string) => splitPostText(title).text || '暂无可读标题'
const heat = (signal: Signal) => signal.kind === 'rank' ? signal.rank.hot_value : (() => { const s = latest(signal.post); return s ? s.liked_count + s.comment_count + s.share_count + s.collected_count : 0 })()


// Preserve the reference's scattered depth, with more room around the front card.
const cloudSlots = [
  [612,414,250,.55,-1.8],[887,515,250,.55,4],[838,268,250,.36,-5],
  [1080,137,180,.28,6],[1090,403,265,.48,3],[1050,704,200,.40,-4],
  [816,648,275,.58,5],[589,726,220,.46,-3],[372,583,270,.56,4],
  [134,704,185,.38,-5],[135,452,250,.50,4],[162,178,195,.30,6],
  [389,210,265,.42,-4],[641,134,250,.32,4],[347,343,250,.55,3],
]
const wrap = (n: number, m: number) => ((n % m) + m) % m
const smooth = (n: number) => { const t = Math.max(0, Math.min(1, n)); return t*t*t*(t*(6*t-15)+10) }
function useReferenceCloud(ref: RefObject<HTMLDivElement>, enabled: boolean, paused: boolean, compactView: boolean, rotation: number, count: number, identity: string) {
  const elapsed = useRef(0)
  useEffect(() => {
    const stage = ref.current
    if (!stage || !enabled || !count) return
    let frame = 0, previous = 0
    let width = stage.clientWidth, height = stage.clientHeight
    const resize = new ResizeObserver(() => { width = stage.clientWidth; height = stage.clientHeight })
    resize.observe(stage)
    const cards = Array.from(stage.querySelectorAll<HTMLButtonElement>('.spatial-cloud-card'))
    const draw = (now: number) => {
      if (previous && !paused && !document.hidden) elapsed.current += Math.min((now-previous)/1000, .05)
      previous = now
      const cycle = Math.floor(elapsed.current / 4.5)
      const focus = rotation + cycle + smooth((elapsed.current-cycle*4.5-1.5)/3)
      const size = Math.min(width/1224*.82, height/806*1.25)
      cards.forEach((card, index) => {
        const p = wrap((index-(count > 1 ? focus : 0))*cloudSlots.length/count,cloudSlots.length), i = Math.floor(p), t = p-i
        const points = [-1,0,1,2].map(offset => cloudSlots[wrap(i+offset,cloudSlots.length)])
        const pose = points[1].map((_, k) => { const [a,b,c,d] = points.map(point => point[k]); return b+.5*t*(c-a+t*(2*a-5*b+4*c-d+t*(3*(b-c)+d-a))) })
        const distance = Math.min(p,cloudSlots.length-p), emphasis = 1-smooth(distance)
        const layer = smooth((pose[3]-.28)/.30)
        // Keep labels readable instead of shrinking text with the source canvas.
        const font = Math.min(23, Math.max((compactView ? 4 : 9)+(compactView ? 4 : 8)*emphasis, (24+4*layer+10*emphasis)*size))
        const category = Math.max(compactView ? 3 : 7+3*emphasis, (14+2*layer)*size)
        const padding = Math.max(compactView ? 2 : 5+3*emphasis,14*size)
        const cardWidth = Math.min(width*.48, 300, Math.max((pose[2]+130*emphasis)*size, Math.min(compactView ? 36 : 72,width*.2)+Math.min(compactView ? 60 : 130,width*.25)*emphasis))
        const front = emphasis > .8
        const cardHeight = padding*2+category*1.2+5+font*(front ? 3 : 2)*1.4+3
        const depth = .28+.72*emphasis+.10*smooth(distance-1)*pose[3]
        const insetX = cardWidth/2+8, insetY = cardHeight/2+8
        card.style.left = `${Math.max(insetX, Math.min(width-insetX,pose[0]/1224*width))}px`
        card.style.top = `${Math.max(insetY, Math.min(height-insetY,pose[1]/806*height))}px`
        card.style.width = `${cardWidth}px`
        card.style.height = `${cardHeight}px`
        card.style.transform = `translate(-50%,-50%) rotate(${pose[4]*(1-emphasis)-1.8*emphasis}deg) skewY(${(1-emphasis)*-2}deg)`
        const restingOpacity = .42+.32*layer
        card.style.opacity = `${restingOpacity+(1-restingOpacity)*emphasis}`
        card.style.zIndex = `${Math.round(depth*100)}`
        card.style.setProperty('--reference-font', `${font}px`)
        card.style.setProperty('--reference-category', `${category}px`)
        card.style.setProperty('--reference-pad', `${padding}px`)
        card.dataset.front = front ? 'true' : 'false'
      })
      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(frame); resize.disconnect(); cards.forEach(card => { card.removeAttribute('data-front'); ['left','top','width','height','transform','opacity','z-index','--reference-font','--reference-category','--reference-pad'].forEach(key => card.style.removeProperty(key)) }) }
  }, [ref, enabled, paused, compactView, rotation, count, identity])
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => { const media = matchMedia('(prefers-reduced-motion: reduce)'); const update = () => setReduced(media.matches); media.addEventListener('change', update); return () => media.removeEventListener('change', update) }, [])
  return reduced
}

function useBarrageLayout(ref: RefObject<HTMLDivElement>, enabled: boolean, identity: string) {
  useEffect(() => {
    const stage = ref.current
    if (!stage || !enabled) return
    const layout = () => {
      const cards = Array.from(stage.querySelectorAll<HTMLButtonElement>('.spatial-cloud-card'))
      if (!cards.length || !stage.clientHeight || !stage.clientWidth) return
      const height = stage.clientHeight
      const lanes = Math.min(cards.length, Math.max(1, Math.floor((height - 16) / 46)))
      const band = (height - 16) / lanes
      const width = Math.min(560, stage.clientWidth * .7)
      // Equal travel speeds and enough room per slot prevent same-lane overtaking.
      const slots = Math.ceil(cards.length / lanes)
      const distance = Math.max(stage.clientWidth + width + 32, slots * (width + 32))
      const duration = distance / 65
      const order = Array.from({ length: lanes }, (_, i) => i)
      for (let i = order.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[order[i], order[j]] = [order[j], order[i]]
      }
      const phases = order.map(() => Math.random())
      cards.forEach((card, index) => {
        const lane = index % lanes
        const slot = Math.floor(index / lanes)
        const top = 8 + order[lane] * band + Math.random() * Math.max(0, band - 40)
        card.style.setProperty('--barrage-top', `${top}px`)
        card.style.setProperty('--barrage-width', `${width}px`)
        card.style.setProperty('--barrage-distance', `${-distance}px`)
        card.style.setProperty('--barrage-duration', `${duration}s`)
        card.style.setProperty('--barrage-delay', `${-(phases[lane] + slot / slots) * duration}s`)
      })
    }
    const observer = new ResizeObserver(layout)
    observer.observe(stage)
    layout()
    return () => observer.disconnect()
  }, [ref, enabled, identity])
}

export function SpatialInsights({ search, onSearchChange, onOpenData, onOpenTopics, onOpenHot, onOpenConfig }: { search: string; onSearchChange: (value: string) => void; onOpenData: (id?: string) => void; onOpenTopics: () => void; onOpenHot: () => void; onOpenConfig: () => void }) {
  const accountId = useMonitorAccountStore(state => state.activeAccountId)
  const dashboard = useQuery({ queryKey: ['monitorDashboard', 'spatial', accountId], queryFn: async () => (await monitorApi.getDashboard()).data, refetchInterval: 30000 })
  const queryClient = useQueryClient()
  const [savedRanks] = useState(() => { try { return readHotRankCache(localStorage) } catch { return undefined } })
  const ranks = useQuery({ queryKey: ['douyinHotRank'], queryFn: async () => (await monitorApi.getHotRank(false, 15000)).data, initialData: savedRanks, initialDataUpdatedAt: 0, refetchInterval: 120000, retry: false })
  useEffect(() => { if (ranks.data) { try { saveHotRankCache(localStorage, ranks.data) } catch { /* Storage unavailable. */ } } }, [ranks.data])
  const [rankClock, setRankClock] = useState(Date.now())
  useEffect(() => { const timer = window.setInterval(() => setRankClock(Date.now()), 60000); return () => window.clearInterval(timer) }, [])
  const [visibleCount, setVisibleCount] = useState(40)
  const [selected, setSelected] = useState<Signal | null>(null)
  const [day, setDay] = useState('all')
  const [period, setPeriod] = useState(0)
  const [mode, setMode] = useState<'cloud' | 'barrage'>('cloud')
  const [paused, setPaused] = useState(false)
  const [full, setFull] = useState(false)
  const cloudRef = useRef<HTMLElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const [reading, setReading] = useState(false)
  const [rotation, setRotation] = useState(0)
  const [cloudFocused, setCloudFocused] = useState(false)
  const reduced = useReducedMotion()
  const allPosts = dashboard.data?.posts ?? []
  const rankItems = ranks.data?.items ?? []
  const feedListRef = useRef<HTMLDivElement>(null)
  const [filtersOpen, setFiltersOpen] = useState(true)
  const [channel, setChannel] = useState('推荐')
  const [region, setRegion] = useState('全部')
  const hasTagFilter = channel !== '推荐' || region !== '全部'
  const keyword = search.trim().toLowerCase()
  const posts = useMemo(() => allPosts.filter(post => (channel === '推荐' || (postChannel(post.channel)) === channel) && (region === '全部' || (post.region || '待判定') === region) && (!keyword || `${post.title} ${post.desc}`.toLowerCase().includes(keyword)) && (day === 'all' || dayKey(post.create_time) === day) && (!period || post.create_time >= Date.now() / 1000 - period * 3600)).sort((a, b) => b.create_time - a.create_time), [allPosts, keyword, day, period, channel, region])
  const filteredRanks = rankItems.filter(item => !keyword || item.word.toLowerCase().includes(keyword))
  const signals = useMemo<Signal[]>(() => posts.length ? [...posts].map(post => ({ id: post.aweme_id, title: presentPost(post).title, kind: 'post' as const, post })).sort((a, b) => heat(b) - heat(a)).slice(0, 15) : day === 'all' && !period && !hasTagFilter ? filteredRanks.slice(0, 15).map(rank => ({ id: `rank-${rank.sentence_id || rank.word}`, title: rank.word, kind: 'rank' as const, rank })) : [], [posts, rankItems, keyword, day, period, hasTagFilter])
  const cloudSignals = signals
  useBarrageLayout(stageRef, mode === 'barrage', cloudSignals.map(signal => signal.id).join(','))
  useReferenceCloud(stageRef, mode === 'cloud', paused || reduced || cloudFocused || reading, reading, rotation, cloudSignals.length, cloudSignals.map(signal => signal.id).join(','))
  const availableDays = useMemo(() => { const counts = new Map<string, number>(); allPosts.forEach(post => { const key = dayKey(post.create_time); counts.set(key, (counts.get(key) ?? 0) + 1) }); return [...counts].sort(([a], [b]) => b.localeCompare(a)) }, [allPosts])
  const [dateOffset, setDateOffset] = useState(0)
  const today = dayKey(Date.now() / 1000)
  const dates = Array.from({ length: 7 }, (_, index) => { const key = dayKey(Date.now() / 1000 - (index + dateOffset) * 86400); return { key, count: availableDays.find(([d]) => d === key)?.[1] ?? 0 } })
  const [hotRefreshError, setHotRefreshError] = useState('')
  const [hotRefreshing, setHotRefreshing] = useState(false)
  const refreshRanks = async () => { setHotRefreshing(true); setHotRefreshError(''); try { const response = await monitorApi.getHotRank(true, 25000); queryClient.setQueryData(['douyinHotRank'], response.data) } catch { setHotRefreshError('暂时无法更新热榜，请检查浏览器连接后重试。') } finally { setHotRefreshing(false) } }
  const hotWarning = hotRefreshError || (ranks.isError ? '热榜更新失败，请检查浏览器连接后重试。' : ranks.data?.warning || '')
  useEffect(() => { setSelected(null); setDay('all'); setRotation(0); setReading(false) }, [accountId])
  useEffect(() => { setVisibleCount(40); feedListRef.current?.scrollTo({ top: 0 }) }, [accountId, keyword, day, period, channel, region])
  useEffect(() => { if (!selected) return; const next = selected.kind === 'post' ? posts.find(post => post.aweme_id === selected.id) : filteredRanks.find(rank => `rank-${rank.sentence_id || rank.word}` === selected.id); if (!next) { setSelected(null); setReading(false) } }, [posts, keyword, day, period])

  useEffect(() => { const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setFull(false); setReading(false) } }; document.addEventListener('keydown', escape); return () => document.removeEventListener('keydown', escape) }, [])
  useEffect(() => {
    if (!full) return
    const previous = document.activeElement as HTMLElement | null
    const background = [...document.querySelectorAll<HTMLElement>('.spatial-header,.spatial-context,.spatial-system-strip,.spatial-date-rail,.spatial-feed,.spatial-ranks,.spatial-detail')].map(element => ({ element, inert: element.inert }))
    background.forEach(({ element }) => { element.inert = true })
    cloudRef.current?.querySelector<HTMLButtonElement>('[aria-label="退出探索大视图"]')?.focus()
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const controls = [...(cloudRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])]
      const first = controls[0], last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', trapFocus)
    return () => { background.forEach(({ element, inert }) => { element.inert = inert }); document.removeEventListener('keydown', trapFocus); previous?.focus() }
  }, [full])
  const choose = (signal: Signal) => {
    setSelected(signal)
    setReading(false)
    setFull(false)
    if (signal.kind === 'post') {
      const index = posts.findIndex(post => post.aweme_id === signal.id)
      if (index >= visibleCount) setVisibleCount(Math.ceil((index + 1) / 40) * 40)
    }
  }
  useEffect(() => {
    if (selected?.kind !== 'post') return
    const row = Array.from(feedListRef.current?.querySelectorAll<HTMLButtonElement>('.spatial-news-row') || []).find(el => el.dataset.postId === selected.id)
    const list = feedListRef.current
    if (row && list) {
      const bounds = row.getBoundingClientRect(), viewport = list.getBoundingClientRect()
      if (bounds.top < viewport.top || bounds.bottom > viewport.bottom) list.scrollTop += bounds.top - viewport.top
    }
  }, [selected?.id, visibleCount])
  const currentPost = selected?.kind === 'post' ? posts.find(post => post.aweme_id === selected.id) : undefined
  const maxRankHeat = Math.max(1, ...rankItems.map(item => item.hot_value))
  return <div className="spatial-insights">
    <aside className="spatial-date-rail spatial-glass" aria-label="日期回看"><header><CalendarDays aria-hidden="true" /><strong>{dates[0].key.slice(5, 7)}月</strong><span>内容回溯</span></header><button className="spatial-today" onClick={() => { setDay('all'); setDateOffset(0); setPeriod(0) }} aria-pressed={day === 'all'}>全部日期</button><div className="spatial-date-list">{dates.map(date => <button key={date.key} aria-pressed={day === date.key} onClick={() => { setDay(date.key); setPeriod(0); setSelected(null) }}><span>{date.key === today ? '今天' : new Date(`${date.key}T00:00:00+08:00`).toLocaleDateString('zh-CN', { weekday: 'short', timeZone: 'Asia/Shanghai' })}</span><strong>{Number(date.key.slice(-2))}</strong><small>{date.count ? `${date.count} 条内容` : '暂无采集'}</small></button>)}</div><footer><button aria-label="前七天" onClick={() => setDateOffset(value => value + 7)}><ChevronLeft aria-hidden="true" /></button><button aria-label="后七天" disabled={!dateOffset} onClick={() => setDateOffset(value => Math.max(0, value - 7))}><ChevronRight aria-hidden="true" /></button></footer></aside>
    <section className="spatial-feed spatial-glass" aria-labelledby="spatial-feed-title"><header className="spatial-panel-heading"><h1 id="spatial-feed-title"><span className="spatial-live-dot" />内容线索</h1><div><span className="spatial-count" aria-label={`${posts.length} 条匹配内容`}>{posts.length}</span><button className="spatial-filter-toggle" aria-expanded={filtersOpen} aria-controls="spatial-content-filters" onClick={() => setFiltersOpen(value => !value)}>{filtersOpen ? '收起筛选' : '展开筛选'}</button></div></header>
      <div className="spatial-compact-filters" id="spatial-content-filters" hidden={!filtersOpen}>
        <div className="spatial-filter-selects"><label><span>频道</span><select aria-label="编辑频道" value={channel} onChange={event => setChannel(event.target.value)}>{editorialChannels.map(value => <option key={value} value={value}>{value === '推荐' ? '全部频道' : value}</option>)}</select></label><label><span>地域</span><select aria-label="地域筛选" value={region} title={regionDescription(region)} onChange={event => setRegion(event.target.value)}>{editorialRegions.map(value => <option key={value} value={value}>{value === '全部' ? '全部地域' : value}</option>)}</select></label></div>
        <div className="spatial-filter-time"><span>时间</span><div className="spatial-segment" role="group" aria-label="发布时间范围">{[[0, '全部'], [24, '24小时'], [168, '7天']].map(([value, label]) => <button key={value} aria-pressed={period === value} onClick={() => { setPeriod(Number(value)); setDay('all') }}>{label}</button>)}</div></div>
        <label className="spatial-feed-search"><span className="sr-only">搜索标题或正文</span><input aria-label="筛选内容线索" placeholder="搜索标题或正文" value={search} onChange={event => onSearchChange(event.target.value)} />{search && <button aria-label="清空关键词" onClick={() => onSearchChange('')}><X aria-hidden="true" /></button>}</label>
      </div>
      <div className="spatial-feed-caption spatial-filter-summary"><span title={[channel === '推荐' ? '全部频道' : channel, region === '全部' ? '全部地域' : region, day !== 'all' ? day : period ? `${period === 24 ? '24小时' : '7天'}内` : '最新发布', keyword ? `关键词：${search}` : ''].filter(Boolean).join(' · ')}>{[channel === '推荐' ? '全部频道' : channel, region === '全部' ? '全部地域' : region, day !== 'all' ? day : period ? `${period === 24 ? '24小时' : '7天'}内` : '最新发布', keyword ? `搜索：${search}` : ''].filter(Boolean).join(' · ')}</span><div>{(keyword || day !== 'all' || period || hasTagFilter) && <button className="spatial-filter-reset" onClick={() => { onSearchChange(''); setDay('all'); setPeriod(0); setChannel('推荐'); setRegion('全部') }}>重置</button>}<button aria-label="刷新内容线索" onClick={() => void dashboard.refetch()} disabled={dashboard.isFetching}><RefreshCw className={dashboard.isFetching ? 'animate-spin' : ''} aria-hidden="true" /></button></div></div><div ref={feedListRef} className="spatial-feed-list">
      {dashboard.isLoading ? <StatePanel variant="loading" title="正在读取内容" /> : dashboard.isError && !dashboard.data ? <StatePanel variant="error" title="内容加载失败" description="请检查服务连接后重试。" action={<Button variant="outline" onClick={() => void dashboard.refetch()}>重新加载</Button>} /> : posts.length ? posts.slice(0, visibleCount).map(post => { const snapshot = latest(post); const display = presentPost(post); return <button className="spatial-news-row" data-post-id={post.aweme_id} key={post.aweme_id} aria-pressed={selected?.id === post.aweme_id} onClick={() => choose({ id: post.aweme_id, title: post.title || post.desc || post.aweme_id, kind: 'post', post })}><span className="spatial-news-meta"><PostEditorialTags post={post} /><time>{stamp(post.create_time)}</time></span><h2>{display.title}</h2>{display.body && <p>{display.body}</p>}{display.topics.length > 0 && <span className="spatial-card-topics" aria-label="作品话题">{display.topics.slice(0, 2).map(topic => <span key={topic}>#{topic}</span>)}{display.topics.length > 2 && <span>+{display.topics.length - 2}</span>}</span>}<span className="spatial-news-footer"><span>{snapshot ? `互动 ${compact(snapshot.liked_count + snapshot.comment_count + snapshot.collected_count + snapshot.share_count)}` : '等待快照'}</span><span>{post.snapshots.length} 次快照<ArrowUpRight aria-hidden="true" /></span></span></button> }) : <StatePanel variant="empty" title={keyword || day !== 'all' || period || hasTagFilter ? '没有匹配的内容' : '还没有采集内容'} description={keyword || day !== 'all' || period || hasTagFilter ? '尝试更换日期或筛选条件。' : '接入账号后，内容线索将出现在这里。'} action={<Button variant="outline" onClick={keyword || day !== 'all' || period || hasTagFilter ? () => { onSearchChange(''); setDay('all'); setPeriod(0); setChannel('推荐'); setRegion('全部') } : onOpenConfig}>{keyword || day !== 'all' || period || hasTagFilter ? '重置筛选' : '接入账号'}</Button>} />}
      {posts.length > visibleCount && <button className="spatial-load-more" onClick={() => setVisibleCount(value => value + 40)}>加载更多 · 已显示 {visibleCount} / {posts.length}</button>}
      {dashboard.isError && dashboard.data && <p className="spatial-inline-warning" role="status">刷新失败，正在显示上次采集内容。</p>}
    </div><footer className="spatial-panel-footer"><span>时间按北京时间显示</span><button onClick={() => onOpenData()}>全部作品<ArrowUpRight aria-hidden="true" /></button></footer></section>
    <section className={`spatial-center ${!selected ? 'is-exploring' : ''} ${reading ? 'is-reading' : ''}`} aria-label="热点探索与内容详情"><section ref={cloudRef} role={full ? 'dialog' : undefined} aria-modal={full ? true : undefined} className={`spatial-cloud-panel ${full ? 'is-fullscreen' : ''}`} aria-label="热点星云"><header className="spatial-cloud-heading"><h2><span className="spatial-live-dot" />热点星云</h2><div><div className="spatial-segment" role="group" aria-label="热点展示方式"><button aria-pressed={mode === 'cloud'} onClick={() => setMode('cloud')}>星云</button><button aria-pressed={mode === 'barrage'} onClick={() => setMode('barrage')}>弹幕</button></div><button className="spatial-icon-button" onClick={() => setPaused(!paused)} aria-pressed={paused || reduced} aria-label={paused ? '播放星云动效' : '暂停星云动效'}>{paused || reduced ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}</button><button className="spatial-icon-button" onClick={() => setFull(!full)} aria-label={full ? '退出探索大视图' : '展开探索大视图'}>{full ? <Minimize2 aria-hidden="true" /> : <Maximize2 aria-hidden="true" />}</button></div></header>
      <div ref={stageRef} className={`spatial-cloud-stage ${mode} ${paused || reduced || cloudFocused || reading ? 'is-paused' : ''}`} onFocus={event => setCloudFocused(event.target.matches(':focus-visible'))} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setCloudFocused(false) }}><div className="spatial-orbit orbit-one" aria-hidden="true" /><div className="spatial-orbit orbit-two" aria-hidden="true" /><div className="spatial-orbit orbit-three" aria-hidden="true" />
        {cloudSignals.length ? cloudSignals.map(signal => <button key={signal.id} className="spatial-cloud-card" aria-pressed={selected?.id === signal.id} onClick={() => choose(signal)}><span>{signal.kind === 'post' ? `${postChannel(signal.post.channel)} · ${signal.post.region || '待判定'}` : '平台热度信号'}<Sparkles aria-hidden="true" /></span><strong>{cloudTitle(signal.title)}</strong><small>{signal.kind === 'rank' ? `热度 ${compact(signal.rank.hot_value)}` : signal.post.snapshots.length ? `互动 ${compact(heat(signal))}` : '等待互动快照'}</small></button>) : <div className="spatial-cloud-empty">{dashboard.isLoading || ranks.isLoading ? <><RefreshCw className="animate-spin" /><strong>正在生成星云</strong></> : <><Sparkles /><strong>等待新的内容信号</strong><p>采集内容或平台热榜就绪后，将在这里展开。</p></>}</div>}
      </div><footer className="spatial-cloud-footer"><span title={signals[0]?.kind === 'rank' ? '平台热度信号，事实待核验。卡片大小与位置用于轮换展示，不代表热度排名。' : '按最新互动总量选取当前筛选内的前 15 条内容。卡片大小与位置用于轮换展示，不代表热度排名。'}>{signals[0]?.kind === 'rank' ? '平台热度信号' : '点击卡片 · 下方阅读'} · 大小不代表排名</span>{mode === 'cloud' && <div><button disabled={signals.length < 2} aria-label="上一组星云位置" onClick={() => setRotation(value => value - 1)}><ChevronLeft aria-hidden="true" /></button><span aria-live="polite">{signals.length ? `${signals.length} 条线索 · 轮换展示` : '暂无线索'}</span><button disabled={signals.length < 2} aria-label="下一组星云位置" onClick={() => setRotation(value => value + 1)}><ChevronRight aria-hidden="true" /></button></div>}</footer></section>
      <section className="spatial-detail spatial-glass" aria-label="内容详情"><header className="spatial-panel-heading"><h2>{selected ? '内容情报' : '阅读与研判'}</h2>{selected && <div><button className="spatial-icon-button" aria-label={reading ? '恢复标准阅读' : '展开阅读'} onClick={() => setReading(!reading)}>{reading ? <Minimize2 aria-hidden="true" /> : <Maximize2 aria-hidden="true" />}</button><button className="spatial-icon-button" aria-label="收起内容详情" onClick={() => { setSelected(null); setReading(false) }}><X aria-hidden="true" /></button></div>}</header>{selected ? <SpatialReadingDetail key={selected.id} signal={selected} post={currentPost} onOpenData={onOpenData} onOpenTopics={onOpenTopics} /> : <div className="spatial-detail-placeholder"><div className="spatial-placeholder-symbol"><Sparkles aria-hidden="true" /></div><h3>从一条线索，发现更多</h3><p>选择左侧内容、星云卡片或右侧热榜，<br />在这里查看详情并继续分析。</p><span>发现 · 阅读 · 研判</span></div>}</section>
    </section>
    <section className="spatial-ranks spatial-glass" aria-labelledby="spatial-rank-title"><header className="spatial-panel-heading"><h2 id="spatial-rank-title"><Flame aria-hidden="true" />平台热榜</h2><button className="spatial-icon-button" onClick={() => void refreshRanks()} disabled={hotRefreshing || ranks.isFetching} aria-label="刷新平台热榜"><RefreshCw className={hotRefreshing || ranks.isFetching ? 'animate-spin' : ''} aria-hidden="true" /></button></header><div className="spatial-rank-tabs"><span>抖音热榜</span><button onClick={onOpenHot}>完整榜单<ArrowUpRight aria-hidden="true" /></button></div><p className="spatial-rank-meta" title={ranks.data?.generated_at ? `数据时间：${new Date(ranks.data.generated_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}` : undefined}>{ranks.data ? `${ranks.data.stale || ranks.isError || hotRefreshError ? '历史缓存' : '平台快照'} · ${hotRankAge(ranks.data.generated_at, rankClock)}` : '平台传播热度'}{(ranks.isFetching || hotRefreshing) && ranks.data ? ' · 更新中' : ''}</p>{hotWarning && <p className="spatial-inline-warning" role="status">{hotWarning}{rankItems.length > 0 ? ' 当前保留上次成功数据。' : ''}</p>}<div className="spatial-rank-list">{ranks.isLoading ? <StatePanel variant="loading" title="正在读取热榜" /> : ranks.isError && !ranks.data ? <StatePanel variant="error" title="热榜暂不可用" description="请检查采集浏览器连接，恢复后重试。" action={<Button variant="outline" onClick={() => void refreshRanks()} disabled={hotRefreshing}>重试</Button>} /> : filteredRanks.length ? filteredRanks.map((rank, index) => <button key={rank.sentence_id || rank.word} className="spatial-rank-row" aria-pressed={selected?.id === `rank-${rank.sentence_id || rank.word}`} onClick={() => choose({ id: `rank-${rank.sentence_id || rank.word}`, title: rank.word, kind: 'rank', rank })}><span className={`spatial-rank-number ${index < 3 ? 'is-top' : ''}`}>{rank.is_pinned ? '荐' : rank.rank ?? index + 1}</span><span className="spatial-rank-word">{rank.word}<span className="spatial-rank-meter"><i style={{ width: `${rank.hot_value / maxRankHeat * 100}%` }} /></span></span><small title="平台热度值">{rank.hot_value > 0 ? compact(rank.hot_value) : '—'}</small></button>) : <StatePanel variant="empty" title="暂无匹配热榜" />}</div><footer className="spatial-panel-footer"><span>平台热度值 · 事实待核验</span><Flame aria-hidden="true" /></footer></section>
  </div>
}

