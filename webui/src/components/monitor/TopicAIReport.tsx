import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainCircuit, CheckCircle2, ChevronDown, ChevronRight, History, RefreshCw, Sparkles, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { TopicIdeasSection } from '@/components/monitor/TopicIdeasSection'
import { monitorApi, type AIAnalysisResponse, type AITopicAnalysisResult } from '@/lib/api'


interface TopicAIReportProps {
  accountId: number | null
  timeRange: '24h' | '7d' | '30d' | 'all'
  postLimit: number
}


function formatDateTime(value?: number | null): string {
  if (!value) return '-'
  return new Date(value * 1000).toLocaleString()
}


function analysisErrorMessage(error: unknown): string {
  const responseError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = responseError.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message?: unknown }).message || '')
  }
  return String(error instanceof Error ? error.message : error || '')
}


function isDuplicateText(left: string, right: string): boolean {
  const normalize = (value: string) => String(value || '').replace(/[\s，。！？、；：,.!?;:（）()《》#]/g, '')
  const first = normalize(left)
  const second = normalize(right)
  if (!first) return true
  if (!second) return false
  if (first.includes(second) || second.includes(first)) return true
  const grams = (value: string) => new Set(Array.from({ length: Math.max(0, value.length - 1) }, (_, index) => value.slice(index, index + 2)))
  const firstGrams = grams(first)
  const secondGrams = grams(second)
  if (firstGrams.size === 0 || secondGrams.size === 0) return false
  let overlap = 0
  firstGrams.forEach((gram) => { if (secondGrams.has(gram)) overlap += 1 })
  return overlap / Math.min(firstGrams.size, secondGrams.size) >= 0.65
}


const TAG_CATEGORIES = [
  { key: 'taiwan', keywords: ['台湾', '台海', '两岸', '台独', '民进党', '国民党', '赖清德', '蔡英文', '沈伯洋', '敬一丹'], style: 'border-red-200 bg-red-100 text-red-800', dot: 'bg-red-500' },
  { key: 'politics', keywords: ['美联储', '加息', '财经', '经济', '日本', '内阁', '辞职', '国际', '时政', '外交', '美国', '关税', '俄乌', '中东'], style: 'border-orange-200 bg-orange-100 text-orange-800', dot: 'bg-orange-500' },
  { key: 'weather', keywords: ['台风', '杜苏芮', '暴雨', '天气', '高温', '寒潮', '预警', '洪水', '地震'], style: 'border-teal-200 bg-teal-100 text-teal-800', dot: 'bg-teal-500' },
  { key: 'transport', keywords: ['地铁', '4号线', '6号线', '交通', '通勤', '铁路', 'brt', '机场', '高速'], style: 'border-blue-200 bg-blue-100 text-blue-800', dot: 'bg-blue-500' },
  { key: 'local', keywords: ['厦门', '民生', '社区', '菜价', '物价', '住房', '保障房', '养老', '社保', '政务'], style: 'border-emerald-200 bg-emerald-100 text-emerald-800', dot: 'bg-emerald-500' },
  { key: 'culture', keywords: ['歌剧', '演出', '音乐会', '文化', '艺术', '电影节', '展演', '剧场'], style: 'border-purple-200 bg-purple-100 text-purple-800', dot: 'bg-purple-500' },
  { key: 'education', keywords: ['教育', '学校', '大学', '军训', '考试', '教师', '学生'], style: 'border-indigo-200 bg-indigo-100 text-indigo-800', dot: 'bg-indigo-500' },
  { key: 'health', keywords: ['医疗', '健康', '医院', '医生', '药品', '疾病', '医保'], style: 'border-pink-200 bg-pink-100 text-pink-800', dot: 'bg-pink-500' },
  { key: 'sports', keywords: ['闽超', '福厦大战', '足球', '联赛', '比赛', '冠军', '运动员'], style: 'border-lime-200 bg-lime-100 text-lime-800', dot: 'bg-lime-500' },
  { key: 'editorial', keywords: ['媒体原创', '原创', '独家', '转载', '来源', '记者', '编辑'], style: 'border-stone-200 bg-stone-100 text-stone-700', dot: 'bg-stone-500' },
  { key: 'hotness', keywords: ['热点', '热搜', '突发', '最新', '追踪', '焦点', '现场'], style: 'border-rose-200 bg-rose-100 text-rose-800', dot: 'bg-rose-500' },
  { key: 'content', keywords: ['新闻', '视频', '资讯', '快讯', '短讯', '直播', '图集', '访谈', '报道'], style: 'border-cyan-200 bg-cyan-100 text-cyan-800', dot: 'bg-cyan-500' },
  { key: 'other', keywords: [], style: 'border-slate-200 bg-slate-100 text-slate-600', dot: 'bg-slate-400' },
] as const


function classifyTag(tag: string) {
  const value = tag.toLowerCase()
  return TAG_CATEGORIES.find((category) => category.keywords.some((keyword) => value.includes(keyword))) || TAG_CATEGORIES[TAG_CATEGORIES.length - 1]
}


function TagBarrage({ tags, onCopyTag }: { tags: string[]; onCopyTag: (tag: string) => void }) {
  const { t } = useTranslation('config')
  if (tags.length === 0) return <div className="py-16 text-center text-sm text-slate-400">暂无核心标签</div>
  const categoryCounts = tags.reduce<Record<string, number>>((result, tag) => {
    const key = classifyTag(tag).key
    result[key] = (result[key] || 0) + 1
    return result
  }, {})
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-3 flex flex-wrap items-center justify-center gap-x-3 gap-y-1">{TAG_CATEGORIES.filter((category) => categoryCounts[category.key]).map((category) => <span key={category.key} className="inline-flex items-center gap-1 text-[10px] text-slate-500"><span className={`h-2 w-2 rounded-full ${category.dot}`} />{t(`topicReport.tagCategories.${category.key}`)} {categoryCounts[category.key]}</span>)}</div>
      <div className="relative min-h-0 flex-1 overflow-hidden px-2">
      {tags.map((tag, index) => {
        const category = classifyTag(tag)
        const lane = index % 10
        const duration = 22 + (index % 7) * 3
        const delay = -((index * 2.9) % duration)
        return <button key={tag} type="button" onClick={() => onCopyTag(tag)} className={`topic-tag-single rounded-full border px-4 py-1.5 text-sm font-semibold shadow-sm transition-transform hover:scale-105 ${category.style}`} style={{ top: `${8 + lane * 44}px`, animationDuration: `${duration}s`, animationDelay: `${delay}s` }}>#{tag}</button>
      })}
      </div>
    </div>
  )
}


export function TopicAIReport({ accountId, timeRange, postLimit }: TopicAIReportProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const currentAccountRef = useRef(accountId)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const historyKey = ['aiTopicHistory', accountId]
  const statusQuery = useQuery({
    queryKey: ['aiAnalysisStatus'],
    queryFn: async () => (await monitorApi.getAIStatus()).data,
    staleTime: 60000,
  })
  const historyQuery = useQuery({
    queryKey: historyKey,
    enabled: typeof accountId === 'number',
    queryFn: async () => {
      if (typeof accountId !== 'number') return []
      const response = await monitorApi.getAIResults(accountId, 'topic', undefined, 20)
      return response.data.results as unknown as AIAnalysisResponse<AITopicAnalysisResult>[]
    },
  })
  const mutation = useMutation({
    mutationFn: async (variables: { force: boolean; accountId: number; timeRange: TopicAIReportProps['timeRange']; postLimit: number }) => {
      return monitorApi.analyzeTopics({ account_id: variables.accountId, time_range: variables.timeRange, post_limit: variables.postLimit, force: variables.force })
    },
    onSuccess: (response, variables) => {
      if (currentAccountRef.current !== variables.accountId) return
      setSelectedId(response.data.id)
      queryClient.setQueryData<AIAnalysisResponse<AITopicAnalysisResult>[]>(['aiTopicHistory', variables.accountId], (current = []) => [response.data, ...current.filter((item) => item.id !== response.data.id)])
      toast.success(t('topicReport.completed'))
    },
    onError: (error: Error, variables) => {
      if (currentAccountRef.current === variables.accountId) toast.error(`${t('topicReport.failed')}: ${analysisErrorMessage(error)}`)
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
  const tagCloud = useMemo(() => {
    if (!current?.result?.clusters) return []
    return [...new Set(current.result.clusters.flatMap((cluster) => cluster.keywords || []))].slice(0, 30)
  }, [current])

  const copyTag = async (tag: string) => {
    try {
      await navigator.clipboard.writeText(`#${tag}`)
      toast.success(t('topicReport.tagCopied', { tag }))
    } catch {
      toast.error(t('topicReport.copyFailed'))
    }
  }

  return (
    <div className="w-full space-y-5 pb-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2 text-xl font-semibold tracking-normal text-slate-900">
            <BrainCircuit className="h-5 w-5 text-[#165DFF]" />
            {t('topicReport.title')}
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-500">{t('topicReport.description')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className={`flex items-center gap-2 rounded-md border px-3 py-2 text-xs ${configured ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'}`}>
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>{configured ? t('topicReport.modelConnected') : t('topicReport.modelUnavailable')}</span>
            <span className="rounded bg-white/70 px-1.5 py-0.5 font-mono text-[10px]">{statusQuery.data?.model || '-'}</span>
          </div>
          <details className="group relative">
            <summary className="flex h-9 cursor-pointer list-none items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs text-slate-600 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
              <History className="h-3.5 w-3.5" />
              {t('topicReport.history')}
              <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
            </summary>
            <div className="absolute right-0 z-30 mt-2 max-h-80 w-[360px] overflow-y-auto rounded-lg border border-slate-200 bg-white p-2 shadow-xl">
              {history.length > 0 ? history.map((item) => (
                <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className={`w-full rounded-md px-3 py-2 text-left transition-colors ${current?.id === item.id ? 'bg-blue-50' : 'hover:bg-slate-50'}`}>
                  <div className="flex items-center justify-between gap-2 text-[11px] text-slate-700"><span>{formatDateTime(item.updated_at)}</span><span className="font-mono text-[10px] text-slate-400">{item.model || '-'}</span></div>
                  <div className="mt-1 line-clamp-2 text-[10px] leading-4 text-slate-500">{item.result?.summary || item.status}</div>
                  <div className="mt-1 text-[9px] text-slate-400">{item.cache_hit ? t('topicReport.cacheHit') : t('topicReport.freshResult')}{item.expires_at ? ` · ${t('topicReport.expiresAt')} ${formatDateTime(item.expires_at)}` : ''}</div>
                </button>
              )) : <div className="px-3 py-8 text-center text-xs text-slate-400">{t('topicReport.noHistory')}</div>}
            </div>
          </details>
          <Button type="button" disabled={disabled} onClick={() => typeof accountId === 'number' && mutation.mutate({ force: Boolean(current), accountId, timeRange, postLimit })} className="h-9 bg-[#165DFF] px-4 text-xs text-white hover:bg-[#0E4FD8]">
            {mutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {mutation.isPending ? t('topicReport.analyzing') : current ? t('topicReport.reanalyze') : t('topicReport.analyze')}
          </Button>
        </div>
      </header>

      {typeof accountId !== 'number' ? <ReportNotice tone="warning" text={t('topicReport.singleAccountRequired')} /> : null}
      {typeof accountId === 'number' && !configured && !statusQuery.isLoading ? <ReportNotice tone="warning" text={t('topicReport.notConfigured')} /> : null}
      {mutation.isPending || historyQuery.isLoading ? <TopicReportSkeleton /> : current ? <TopicReportContent current={current} accountId={accountId} tagCloud={tagCloud} onCopyTag={copyTag} /> : typeof accountId === 'number' && configured ? <EmptyReport onAnalyze={() => mutation.mutate({ force: false, accountId, timeRange, postLimit })} /> : null}
    </div>
  )
}


function RichText({ text, className = '', highlightNumbers = false }: { text: string; className?: string; highlightNumbers?: boolean }) {
  const pattern = highlightNumbers ? /(\*\*[^*]+\*\*|\d+(?:\.\d+)?)/g : /(\*\*[^*]+\*\*)/g
  const parts = String(text || '').split(pattern)
  return <span className={className}>{parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={`${part}-${index}`} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>
    if (highlightNumbers && /^\d+(?:\.\d+)?$/.test(part)) return <span key={`${part}-${index}`} className="highlight-num">{part}</span>
    return <span key={`${part}-${index}`}>{part}</span>
  })}</span>
}


function ReportNotice({ text, tone }: { text: string; tone: 'warning' | 'info' }) {
  return <div className={`rounded-md border px-4 py-3 text-sm leading-6 ${tone === 'warning' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-blue-200 bg-blue-50 text-blue-800'}`}>{text}</div>
}


function TopicReportContent({ current, accountId, tagCloud, onCopyTag }: { current: AIAnalysisResponse<AITopicAnalysisResult>; accountId: number | null; tagCloud: string[]; onCopyTag: (tag: string) => void }) {
  const { t } = useTranslation('config')
  const [selectedTheme, setSelectedTheme] = useState<string | null>(null)
  const result = current.result
  const rankedClusters = useMemo(() => [...result.clusters].sort((left, right) => right.total_interaction - left.total_interaction), [result.clusters])
  const activeCluster = rankedClusters.find((cluster) => cluster.name === selectedTheme) || rankedClusters[0] || null
  const activeTags = activeCluster?.keywords?.length ? activeCluster.keywords : tagCloud
  useEffect(() => {
    setSelectedTheme(rankedClusters[0]?.name || null)
  }, [current.id])
  if (current.status === 'insufficient_data') return <ReportNotice tone="warning" text={result.summary || t('topicReport.insufficient')} />

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(300px,0.9fr)_minmax(420px,1.2fr)_minmax(320px,1fr)]">
        <aside className="flex h-[480px] flex-col rounded-lg border border-slate-200 bg-white">
          <div className="shrink-0 border-b border-slate-200 px-5 py-4"><div className="text-sm font-semibold text-slate-900">{t('topicReport.insightsTitle')}</div><p className="mt-1 text-[11px] leading-5 text-slate-500">{t('topicReport.insightsDescription')}</p></div>
          <div className="min-h-0 flex-1 divide-y divide-slate-100 overflow-y-auto">
            {rankedClusters.map((cluster, index) => {
              const selected = activeCluster?.name === cluster.name
              const highThreshold = Math.ceil(rankedClusters.length / 3)
              const midThreshold = Math.ceil(rankedClusters.length * 2 / 3)
              const priorityClass = index < highThreshold ? 'bg-red-500' : index < midThreshold ? 'bg-blue-500' : 'bg-slate-300'
              return (
                <button key={cluster.name} type="button" onClick={() => setSelectedTheme(cluster.name)} className={`w-full px-4 py-3 text-left transition-colors ${selected ? 'bg-blue-50' : 'hover:bg-slate-50'}`}>
                  <div className="flex items-start gap-2.5">
                    <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${priorityClass}`} />
                    <span className="min-w-0 flex-1 text-sm font-semibold leading-5 text-slate-800">{cluster.name}</span>
                    {selected ? <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-[#165DFF]" /> : null}
                  </div>
                  <p className="ml-5 mt-1 line-clamp-2 text-[11px] leading-5 text-slate-500">{cluster.description || '-'}</p>
                  {!isDuplicateText(cluster.representative_insight, cluster.description) ? <p className="ml-5 mt-1 line-clamp-2 text-[10px] leading-4 text-slate-400">{cluster.representative_insight}</p> : null}
                  <div className="ml-5 mt-2 flex items-center gap-2"><div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#165DFF]" style={{ width: `${Math.max(4, cluster.confidence * 100)}%` }} /></div><span className="w-8 text-right text-[9px] text-slate-400">{(cluster.confidence * 100).toFixed(0)}%</span></div>
                </button>
              )
            })}
          </div>
        </aside>

        <section className="flex h-[480px] flex-col overflow-hidden rounded-lg border border-slate-200 bg-gradient-to-b from-white via-blue-50/60 to-white px-4 py-5">
          <div className="mb-4 shrink-0 text-center"><div className="text-xs font-semibold tracking-[0.12em] text-slate-400">{t('topicReport.topTags')}</div>{activeCluster ? <div className="mt-1 text-[11px] text-[#165DFF]">{activeCluster.name}</div> : null}</div>
          <TagBarrage tags={activeTags} onCopyTag={onCopyTag} />
        </section>

        {typeof current.id === 'number' ? <TopicIdeasSection accountId={accountId} topicResultId={current.id} activeTheme={activeCluster?.name || ''} /> : null}
      </div>

      <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5">
        <details className="group"><summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-slate-700 [&::-webkit-details-marker]:hidden"><TriangleAlert className="h-4 w-4 text-slate-500" />{t('topicReport.dataLimitations')}<ChevronDown className="ml-auto h-4 w-4 text-slate-400 transition-transform group-open:rotate-180" /></summary><div className="mt-3 space-y-2 text-[13px] leading-6 text-slate-500">{(result.data_limits.length > 0 ? result.data_limits : [t('topicReport.defaultLimit')]).map((item) => <p key={item}><RichText text={item} /></p>)}</div></details>
      </section>
    </div>
  )
}


function TopicReportSkeleton() {
  const { t } = useTranslation('config')
  return (
    <div className="space-y-6" aria-label={t('topicReport.analyzing')}>
      <div className="rounded-lg bg-blue-50 px-6 py-5"><div className="h-3 w-24 animate-pulse rounded bg-blue-100" /><div className="mt-4 space-y-3">{[0, 1, 2].map((item) => <div key={item} className="h-4 animate-pulse rounded bg-blue-100" style={{ width: `${95 - item * 12}%` }} />)}</div></div>
      <div className="columns-1 gap-4 lg:columns-2">{[0, 1, 2, 3].map((item) => <div key={item} className="mb-4 break-inside-avoid rounded-lg border border-slate-200 bg-white p-5"><div className="h-5 w-2/3 animate-pulse rounded bg-slate-200" /><div className="mt-4 space-y-3">{[0, 1, 2].map((line) => <div key={line} className="h-4 animate-pulse rounded bg-slate-100" style={{ width: `${92 - line * 14}%` }} />)}</div><div className="mt-5 h-16 animate-pulse rounded bg-slate-100" /></div>)}</div>
      <div className="flex items-center justify-center gap-2 py-4 text-sm text-slate-500"><RefreshCw className="h-4 w-4 animate-spin" />{t('topicReport.analyzingHint')}</div>
    </div>
  )
}


function EmptyReport({ onAnalyze }: { onAnalyze: () => void }) {
  const { t } = useTranslation('config')
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-6 py-16 text-center">
      <Sparkles className="mx-auto h-8 w-8 text-[#165DFF]" />
      <div className="mt-4 text-base font-semibold text-slate-900">{t('topicReport.emptyTitle')}</div>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">{t('topicReport.emptyDescription')}</p>
      <Button type="button" onClick={onAnalyze} className="mt-5 bg-[#165DFF] text-white hover:bg-[#0E4FD8]"><Sparkles className="h-4 w-4" />{t('topicReport.analyze')}</Button>
    </div>
  )
}
