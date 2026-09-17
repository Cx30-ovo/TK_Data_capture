import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainCircuit, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, History, Lightbulb, RefreshCw, Search, Sparkles, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { monitorApi, type AIAnalysisResponse, type AILifecycleAnalysisResult, type MonitorDashboardPost } from '@/lib/api'
import { interactionByStage, lifecycleType } from '@/lib/monitorMetrics'


interface LifecycleAIReportProps {
  accountId: number | null
  timeRange: '24h' | '7d' | '30d' | 'all'
  postLimit: number
  posts: MonitorDashboardPost[]
}

const STAGES = ['1h', '6h', '24h', '72h'] as const
const TYPE_COLORS: Record<string, string> = {
  earlyBurst: 'rgb(var(--cyber-neon-cyan))',
  quickDecline: 'rgb(var(--cyber-neon-orange))',
  longTail: 'rgb(var(--cyber-neon-purple))',
  sustained: 'rgb(var(--cyber-neon-green))',
  unknown: 'rgb(var(--cyber-text-muted))',
}


function formatDateTime(value?: number | null): string {
  if (!value) return '-'
  return new Date(value * 1000).toLocaleString()
}


function formatDate(value: number): string {
  return new Date(value * 1000).toLocaleDateString()
}


function analysisErrorMessage(error: unknown): string {
  const responseError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = responseError.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message?: unknown }).message || '')
  return String(error instanceof Error ? error.message : error || '')
}


function replacePostIds(text: string, titleById: Map<string, string>): string {
  let result = String(text || '')
  titleById.forEach((title, postId) => {
    if (title) result = result.split(postId).join(`《${title}》`)
  })
  return result
}


export function LifecycleAIReport({ accountId, timeRange, postLimit, posts }: LifecycleAIReportProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const currentAccountRef = useRef(accountId)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const historyKey = ['aiLifecycleHistory', accountId]
  const statusQuery = useQuery({ queryKey: ['aiAnalysisStatus'], queryFn: async () => (await monitorApi.getAIStatus()).data, staleTime: 60000 })
  const historyQuery = useQuery({
    queryKey: historyKey,
    enabled: typeof accountId === 'number',
    queryFn: async () => {
      if (typeof accountId !== 'number') return []
      const response = await monitorApi.getAIResults(accountId, 'lifecycle', undefined, 20)
      return response.data.results as unknown as AIAnalysisResponse<AILifecycleAnalysisResult>[]
    },
  })
  const mutation = useMutation({
    mutationFn: async (variables: { force: boolean; accountId: number; timeRange: LifecycleAIReportProps['timeRange']; postLimit: number }) => {
      return monitorApi.analyzeLifecycle({ account_id: variables.accountId, time_range: variables.timeRange, post_limit: variables.postLimit, force: variables.force })
    },
    onSuccess: (response, variables) => {
      if (currentAccountRef.current !== variables.accountId) return
      setSelectedId(response.data.id)
      queryClient.setQueryData<AIAnalysisResponse<AILifecycleAnalysisResult>[]>(['aiLifecycleHistory', variables.accountId], (current = []) => [response.data, ...current.filter((item) => item.id !== response.data.id)])
      toast.success(t('lifecycleReport.completed'))
    },
    onError: (error: Error, variables) => {
      if (currentAccountRef.current === variables.accountId) toast.error(`${t('lifecycleReport.failed')}: ${analysisErrorMessage(error)}`)
    },
  })

  useEffect(() => {
    currentAccountRef.current = accountId
    setSelectedId(null)
    mutation.reset()
  }, [accountId])

  const history = historyQuery.data || []
  const mutationResult = mutation.variables?.accountId === accountId ? mutation.data?.data : null
  const current = mutationResult || history.find((item) => item.id === selectedId) || history[0] || null
  const configured = Boolean(statusQuery.data?.configured)
  const disabled = typeof accountId !== 'number' || !configured || mutation.isPending
  const insightMap = useMemo(() => new Map((current?.result?.post_insights || []).map((item) => [item.aweme_id, item])), [current])
  const titleById = useMemo(() => new Map(posts.map((post) => [post.aweme_id, post.title || post.aweme_id])), [posts])

  return (
    <div className="w-full space-y-5 pb-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2 text-xl font-semibold text-slate-900"><BrainCircuit className="h-5 w-5 text-[#722ED1]" />{t('lifecycleReport.title')}</div>
          <p className="mt-1 text-xs leading-5 text-slate-500">{t('lifecycleReport.description')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className={`flex items-center gap-2 rounded-md border px-3 py-2 text-xs ${configured ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'}`}><CheckCircle2 className="h-3.5 w-3.5" /><span>{configured ? t('lifecycleReport.modelConnected') : t('lifecycleReport.modelUnavailable')}</span><span className="rounded bg-white/70 px-1.5 py-0.5 font-mono text-[10px]">{statusQuery.data?.model || '-'}</span></div>
          <details className="group relative"><summary className="flex h-9 cursor-pointer list-none items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs text-slate-600 hover:bg-slate-50 [&::-webkit-details-marker]:hidden"><History className="h-3.5 w-3.5" />{t('lifecycleReport.history')}<ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" /></summary><div className="absolute right-0 z-30 mt-2 max-h-80 w-[360px] overflow-y-auto rounded-lg border border-slate-200 bg-white p-2 shadow-xl">{history.length > 0 ? history.map((item) => <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className={`w-full rounded-md px-3 py-2 text-left ${current?.id === item.id ? 'bg-purple-50' : 'hover:bg-slate-50'}`}><div className="flex items-center justify-between text-[11px] text-slate-700"><span>{formatDateTime(item.updated_at)}</span><span className="font-mono text-[10px] text-slate-400">{item.model || '-'}</span></div><div className="mt-1 line-clamp-2 text-[10px] leading-4 text-slate-500"><RichText text={replacePostIds(item.result?.overall_summary || item.status, titleById)} /></div></button>) : <div className="px-3 py-8 text-center text-xs text-slate-400">{t('lifecycleReport.noHistory')}</div>}</div></details>
          <Button type="button" disabled={disabled} onClick={() => typeof accountId === 'number' && mutation.mutate({ force: Boolean(current), accountId, timeRange, postLimit })} className="h-9 bg-[#722ED1] px-4 text-xs text-white hover:bg-[#5A1FA8]">{mutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}{mutation.isPending ? t('lifecycleReport.analyzing') : current ? t('lifecycleReport.reanalyze') : t('lifecycleReport.analyze')}</Button>
        </div>
      </header>

      {typeof accountId !== 'number' ? <ReportNotice text={t('lifecycleReport.singleAccountRequired')} /> : null}
      {typeof accountId === 'number' && !configured && !statusQuery.isLoading ? <ReportNotice text={t('lifecycleReport.notConfigured')} /> : null}
      {mutation.isPending || historyQuery.isLoading ? <LifecycleReportSkeleton postCount={postLimit} /> : current ? <LifecycleReportContent current={current} posts={posts} insightMap={insightMap} titleById={titleById} /> : typeof accountId === 'number' && configured ? <LifecycleEmpty onAnalyze={() => mutation.mutate({ force: false, accountId, timeRange, postLimit })} /> : null}
    </div>
  )
}


function RichText({ text, className = '' }: { text: string; className?: string }) {
  return <span className={className}>{String(text || '').split(/(\*\*[^*]+\*\*|《[^》]+》)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={`${part}-${index}`} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>
    if (part.startsWith('《') && part.endsWith('》')) return <strong key={`${part}-${index}`} className="rounded bg-amber-100 px-1 py-0.5 font-semibold text-amber-900 [box-decoration-break:clone]">{part}</strong>
    return <span key={`${part}-${index}`}>{part}</span>
  })}</span>
}


function ReportNotice({ text }: { text: string }) {
  return <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">{text}</div>
}


function fallbackDiagnosis(type: string): string {
  return {
    earlyBurst: '快速爆发，后续增长有限',
    quickDecline: '短期冲高后快速回落',
    longTail: '长尾发酵，值得持续跟踪',
    sustained: '持续增长，适合二次推广',
    unknown: '快照不足，暂无法判断',
  }[type] || '快照不足，暂无法判断'
}


function SnapshotTimeline({ post }: { post: MonitorDashboardPost }) {
  const stages = interactionByStage(post)
  return <div className="flex min-w-[190px] items-center gap-1">{[...STAGES].map((stage, index) => { const present = stages.has(stage); return <div key={stage} className="flex items-center gap-1"><span className={`h-2.5 w-2.5 rounded-full ${present ? 'bg-emerald-500' : 'bg-slate-300'}`} /><span className={`text-[10px] ${present ? 'text-slate-600' : 'text-slate-400'}`}>{stage}</span>{index < STAGES.length - 1 ? <span className="text-[9px] text-slate-300">→</span> : null}</div> })}</div>
}


function RhythmDistribution({ result }: { result: AILifecycleAnalysisResult }) {
  const { t } = useTranslation('config')
  const entries = Object.entries(result.type_distribution)
  const total = entries.reduce((sum, [, value]) => sum + value, 0)
  const dominant = entries.sort((left, right) => right[1] - left[1])[0]
  let start = 0
  const gradient = entries.map(([type, count]) => { const end = start + (total ? count / total * 100 : 0); const segment = `${TYPE_COLORS[type] || TYPE_COLORS.unknown} ${start}% ${end}%`; start = end; return segment }).join(', ')
  const dominantPercent = total && dominant ? dominant[1] / total * 100 : 0
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="text-base font-semibold text-slate-900">{t('lifecycleReport.rhythmTitle')}</div>
      <p className="mt-1 text-xs text-slate-500">{t('lifecycleReport.rhythmDescription')}</p>
      <div className="mt-5 flex flex-wrap items-center gap-6">
        <div className="h-32 w-32 shrink-0 rounded-full" style={{ background: `conic-gradient(${gradient})` }}><div className="m-5 flex h-[88px] w-[88px] items-center justify-center rounded-full bg-white"><div className="text-center"><div className="text-xl font-semibold text-slate-900">{total}</div><div className="text-[10px] text-slate-500">{t('lifecycleReport.posts')}</div></div></div></div>
        <div className="min-w-[220px] flex-1 space-y-2">{entries.map(([type, count]) => <div key={type} className="flex items-center gap-2 text-xs"><span className="h-2.5 w-2.5 rounded-full" style={{ background: TYPE_COLORS[type] || TYPE_COLORS.unknown }} /><span className="text-slate-600">{t(`lifecycle.types.${type}`, { defaultValue: type })}</span><span className="ml-auto font-semibold text-slate-900">{count}</span><span className="w-12 text-right text-slate-500">{total ? (count / total * 100).toFixed(1) : '0.0'}%</span></div>)}</div>
      </div>
      {dominant ? <div className="mt-4 rounded-md bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">{t('lifecycleReport.dominantConclusion', { type: t(`lifecycle.types.${dominant[0]}`, { defaultValue: dominant[0] }), percent: dominantPercent.toFixed(1) })}</div> : null}
    </section>
  )
}


function LifecycleReportContent({ current, posts, insightMap, titleById }: { current: AIAnalysisResponse<AILifecycleAnalysisResult>; posts: MonitorDashboardPost[]; insightMap: Map<string, AILifecycleAnalysisResult['post_insights'][number]>; titleById: Map<string, string> }) {
  const { t } = useTranslation('config')
  const result = current.result
  const summary = replacePostIds(result.overall_summary || t('lifecycleReport.fallbackSummary', { count: result.source_post_count || posts.length }), titleById)
  const stageObservation = replacePostIds(result.stage_observation || t('lifecycleReport.fallbackStage'), titleById)
  const [searchText, setSearchText] = useState('')
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('newest')
  const [page, setPage] = useState(1)
  const pageSize = 20
  const filteredPosts = useMemo(() => {
    const keyword = searchText.trim().toLowerCase()
    return [...posts]
      .filter((post) => !keyword || (post.title || '').toLowerCase().includes(keyword) || post.aweme_id.toLowerCase().includes(keyword))
      .sort((left, right) => sortOrder === 'newest' ? right.create_time - left.create_time : left.create_time - right.create_time)
  }, [posts, searchText, sortOrder])
  const pageCount = Math.max(1, Math.ceil(filteredPosts.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const tablePosts = filteredPosts.slice((safePage - 1) * pageSize, safePage * pageSize)

  useEffect(() => {
    setPage(1)
  }, [searchText, sortOrder])

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [page, pageCount])

  return (
    <div className="space-y-6">
      <section className="rounded-lg border-l-4 border-l-[#722ED1] bg-[#F9F5FF] px-6 py-5"><div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#722ED1]">{t('lifecycleReport.aiSummary')}</div><p className="mt-3 text-[15px] leading-[1.8] text-slate-800"><RichText text={summary} /></p></section>
      <section className="rounded-lg border-l-4 border-l-[#165DFF] bg-[#F2F7FF] px-5 py-4"><div className="text-xs font-semibold text-[#165DFF]">{t('lifecycleReport.stageObservation')}</div><p className="mt-2 text-sm leading-7 text-slate-700"><RichText text={stageObservation} /></p></section>
      <RhythmDistribution result={result} />

      {result.recommendations.length > 0 ? <section className="rounded-lg bg-[#FFF7E8] p-5"><div className="flex items-center gap-2"><Lightbulb className="h-5 w-5 text-[#D97706]" /><h2 className="text-base font-semibold text-slate-900">{t('lifecycleReport.recommendations')}</h2></div><ol className="mt-4 space-y-3">{result.recommendations.map((item, index) => <li key={`${item}-${index}`} className="flex items-start gap-3 text-sm leading-7 text-slate-700"><span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#D97706] text-xs font-semibold text-white">{index + 1}</span><RichText text={replacePostIds(item, titleById)} /></li>)}</ol></section> : null}

      {result.caveats.length > 0 ? <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5"><div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><TriangleAlert className="h-4 w-4 text-slate-500" />{t('lifecycleReport.caveats')}</div><div className="mt-3 space-y-2 text-[13px] leading-6 text-slate-500">{result.caveats.map((item) => <p key={item}><RichText text={replacePostIds(item, titleById)} /></p>)}</div></section> : null}

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div><div className="text-base font-semibold text-slate-900">{t('lifecycleReport.detailTitle')}</div><p className="mt-1 text-xs text-slate-500">{t('lifecycleReport.detailDescription')}</p></div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" /><Input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder={t('lifecycleReport.searchPlaceholder')} className="h-8 w-[240px] pl-8 text-xs" /></div>
            <Select value={sortOrder} onValueChange={(value) => setSortOrder(value as 'newest' | 'oldest')}><SelectTrigger className="h-8 w-[130px] text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="newest">{t('lifecycleReport.sortNewest')}</SelectItem><SelectItem value="oldest">{t('lifecycleReport.sortOldest')}</SelectItem></SelectContent></Select>
            <span className="text-xs text-slate-400">{t('lifecycleReport.detailTotal', { count: filteredPosts.length })}</span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-xs">
            <thead className="bg-slate-50 text-left text-[11px] text-slate-500"><tr><th className="px-4 py-3">{t('lifecycleReport.post')}</th><th className="px-4 py-3">{t('lifecycleReport.publishDate')}</th><th className="px-4 py-3">{t('lifecycleReport.rhythm')}</th><th className="px-4 py-3">{t('lifecycleReport.snapshotCompleteness')}</th><th className="px-4 py-3">{t('lifecycleReport.aiDiagnosis')}</th></tr></thead>
            <tbody>{tablePosts.map((post) => { const type = lifecycleType(post); const insight = insightMap.get(post.aweme_id); return <tr key={post.aweme_id} className="border-t border-slate-100 hover:bg-slate-50/70"><td className="max-w-[320px] px-4 py-3"><div title={post.title} className="truncate font-medium text-slate-800">{post.title || post.aweme_id}</div></td><td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDate(post.create_time)}</td><td className="whitespace-nowrap px-4 py-3"><span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-600">{t(`lifecycle.types.${type}`, { defaultValue: type })}</span></td><td className="px-4 py-3"><SnapshotTimeline post={post} /></td><td className="px-4 py-3 text-slate-600"><RichText text={replacePostIds(insight?.pattern || fallbackDiagnosis(type), titleById)} /></td></tr> })}</tbody>
          </table>
        </div>
        {tablePosts.length === 0 ? <div className="px-5 py-12 text-center text-sm text-slate-500">{t('lifecycleReport.noMatchingPosts')}</div> : null}
        {filteredPosts.length > 0 ? <div className="flex items-center justify-between border-t border-slate-200 px-5 py-3"><span className="text-xs text-slate-400">{t('lifecycleReport.pageInfo', { page: safePage, total: pageCount })}</span><div className="flex items-center gap-2"><Button type="button" variant="outline" size="sm" disabled={safePage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="h-7 w-7 p-0"><ChevronLeft className="h-3.5 w-3.5" /></Button><span className="min-w-14 text-center text-xs text-slate-500">{safePage} / {pageCount}</span><Button type="button" variant="outline" size="sm" disabled={safePage >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))} className="h-7 w-7 p-0"><ChevronRight className="h-3.5 w-3.5" /></Button></div></div> : null}
      </section>
    </div>
  )
}


function LifecycleReportSkeleton({ postCount }: { postCount: number }) {
  const { t } = useTranslation('config')
  return (
    <div className="space-y-6" aria-label={t('lifecycleReport.analyzing')}>
      <div className="rounded-lg bg-purple-50 px-6 py-5"><div className="h-3 w-28 animate-pulse rounded bg-purple-100" /><div className="mt-4 space-y-3">{[0, 1, 2].map((item) => <div key={item} className="h-4 animate-pulse rounded bg-purple-100" style={{ width: `${96 - item * 13}%` }} />)}</div></div>
      <div className="flex items-center gap-3 rounded-lg bg-blue-50 px-5 py-4 text-sm text-blue-700"><RefreshCw className="h-4 w-4 animate-spin" />{t('lifecycleReport.readingHint', { count: postCount })}</div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)]"><div className="h-48 animate-pulse rounded-lg bg-slate-100" /><div className="h-48 animate-pulse rounded-lg bg-slate-100" /></div>
      <div className="h-64 animate-pulse rounded-lg bg-slate-100" />
    </div>
  )
}


function LifecycleEmpty({ onAnalyze }: { onAnalyze: () => void }) {
  const { t } = useTranslation('config')
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-2xl">📊</div>
      <div className="mt-4 text-base font-semibold text-slate-900">{t('lifecycleReport.emptyTitle')}</div>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-7 text-slate-500">{t('lifecycleReport.emptyDescription')}</p>
      <Button type="button" onClick={onAnalyze} className="mt-5 bg-[#722ED1] text-white hover:bg-[#5A1FA8]"><Sparkles className="h-4 w-4" />{t('lifecycleReport.analyze')}</Button>
    </div>
  )
}
