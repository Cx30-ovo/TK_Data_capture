import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ClipboardCopy,
  FileText,
  Gauge,
  History,
  Image,
  KeyRound,
  Lightbulb,
  RefreshCw,
  ScanText,
  Sparkles,
  Target,
  TextCursorInput,
  TrendingUp,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  monitorApi,
  type AIAnalysisResponse,
  type AICoverAnalysis,
  type AITitleLengthGroup,
  type AITitleStrategyHitWork,
  type AITitleStrategyKeyword,
  type AITitleStrategyResult,
} from '@/lib/api'


interface TitleStrategyAIReportProps {
  accountId: number | null
  timeRange: '24h' | '7d' | '30d' | 'all'
  postLimit: number
}


function formatNumber(value?: number | null): string {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(Number(value || 0))
}


function formatPercent(value?: number | null): string {
  return `${(Number(value || 0) * 100).toFixed(1)}%`
}


function formatDateTime(value?: number | null): string {
  return value ? new Date(value * 1000).toLocaleString() : '-'
}


function analysisErrorMessage(error: unknown): string {
  const responseError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = responseError.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message?: unknown }).message || '')
  return String(error instanceof Error ? error.message : error || '')
}


export function TitleStrategyAIReport({ accountId, timeRange, postLimit }: TitleStrategyAIReportProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const currentAccountRef = useRef(accountId)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const historyKey = ['aiTitleStrategyHistory', accountId]
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
      const response = await monitorApi.getAIResults(accountId, 'title_strategy', undefined, 20)
      return response.data.results as unknown as AIAnalysisResponse<AITitleStrategyResult>[]
    },
  })
  const mutation = useMutation({
    mutationFn: async (variables: { force: boolean; accountId: number; timeRange: TitleStrategyAIReportProps['timeRange']; postLimit: number }) => (
      monitorApi.analyzeTitleStrategy({ account_id: variables.accountId, time_range: variables.timeRange, post_limit: variables.postLimit, force: variables.force })
    ),
    onSuccess: (response, variables) => {
      if (currentAccountRef.current !== variables.accountId) return
      setSelectedId(response.data.id)
      queryClient.setQueryData<AIAnalysisResponse<AITitleStrategyResult>[]>(['aiTitleStrategyHistory', variables.accountId], (current = []) => [response.data, ...current.filter((item) => item.id !== response.data.id)])
      toast.success(t('titleStrategy.completed'))
    },
    onError: (error, variables) => {
      if (currentAccountRef.current === variables.accountId) toast.error(`${t('titleStrategy.failed')}: ${analysisErrorMessage(error)}`)
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

  return (
    <div className="report-theme w-full space-y-5 pb-8">
      <header className="overflow-hidden rounded-xl border border-blue-100 bg-white shadow-sm">
        <div className="flex flex-col gap-5 p-5 lg:flex-row lg:items-end lg:justify-between lg:p-6">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-blue-700 text-white shadow-md shadow-blue-200"><BrainCircuit aria-hidden="true" className="h-5 w-5" /></span>
            <div className="min-w-0">
              <Badge className="mb-2 border-blue-200 bg-blue-100 text-blue-800 hover:bg-blue-100">{t('titleStrategy.badge')}</Badge>
              <h1 className="text-xl font-semibold tracking-tight text-slate-950 sm:text-2xl">{t('titleStrategy.title')}</h1>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{t('titleStrategy.description')}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className={`flex min-h-9 items-center gap-2 rounded-lg border px-3 py-2 text-xs ${configured ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}><CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5" /><span>{configured ? t('titleStrategy.modelConnected') : t('titleStrategy.modelUnavailable')}</span><span className="rounded bg-white/80 px-1.5 py-0.5 font-mono text-[10px]">{statusQuery.data?.model || '-'}</span></div>
            <details className="group relative">
              <summary className="flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 [&::-webkit-details-marker]:hidden"><History aria-hidden="true" className="h-3.5 w-3.5" />{t('titleStrategy.history')}<ChevronDown aria-hidden="true" className="h-3.5 w-3.5 transition-transform group-open:rotate-180" /></summary>
              <div className="absolute right-0 z-30 mt-2 max-h-80 w-[min(360px,calc(100vw-32px))] overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-xl">
                {history.length ? history.map((item) => <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className={`w-full cursor-pointer rounded-lg px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${current?.id === item.id ? 'bg-blue-50' : 'hover:bg-slate-50'}`}><div className="flex items-center justify-between gap-2 text-[11px] text-slate-700"><span>{formatDateTime(item.updated_at)}</span><span className="font-mono text-[10px] text-slate-400">{item.model || '-'}</span></div><div className="mt-1 line-clamp-2 text-[10px] leading-4 text-slate-500">{item.result?.overview?.core_finding || item.status}</div></button>) : <div className="px-3 py-8 text-center text-xs text-slate-400">{t('titleStrategy.noHistory')}</div>}
              </div>
            </details>
            <Button type="button" disabled={disabled} onClick={() => typeof accountId === 'number' && mutation.mutate({ force: Boolean(current), accountId, timeRange, postLimit })} className="min-h-9 bg-blue-700 px-4 text-xs text-white hover:bg-blue-800 focus-visible:ring-blue-600">{mutation.isPending ? <RefreshCw aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden="true" className="h-4 w-4" />}{mutation.isPending ? t('titleStrategy.analyzing') : current ? t('titleStrategy.reanalyze') : t('titleStrategy.analyze')}</Button>
          </div>
        </div>
        <div className="border-t border-blue-100 bg-white/70 px-5 py-3 text-xs text-slate-500 lg:px-6"><span className="inline-flex items-center gap-2"><Gauge aria-hidden="true" className="h-3.5 w-3.5 text-amber-600" />{t('titleStrategy.metricRule')}</span></div>
      </header>

      {typeof accountId !== 'number' ? <Notice text={t('titleStrategy.singleAccountRequired')} /> : null}
      {typeof accountId === 'number' && !configured && !statusQuery.isLoading ? <Notice text={t('titleStrategy.notConfigured')} /> : null}
      {mutation.isPending || historyQuery.isLoading ? <StrategySkeleton /> : current ? <StrategyContent current={current} /> : typeof accountId === 'number' && configured ? <EmptyStrategy onAnalyze={() => mutation.mutate({ force: false, accountId, timeRange, postLimit })} /> : null}
    </div>
  )
}


function Notice({ text }: { text: string }) {
  return <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900"><AlertTriangle aria-hidden="true" className="mr-2 inline h-4 w-4" />{text}</div>
}


function StrategyContent({ current }: { current: AIAnalysisResponse<AITitleStrategyResult> }) {
  const { t } = useTranslation('config')
  const result = current.result
  const [expandedHits, setExpandedHits] = useState(6)
  const copyTitle = async (title: string) => {
    try {
      await navigator.clipboard.writeText(title)
      toast.success(t('titleStrategy.copied'))
    } catch {
      toast.error(t('titleStrategy.copyFailed'))
    }
  }
  if (current.status === 'insufficient_data') {
    const summary = (result as unknown as { summary?: string }).summary
    return <Notice text={summary || t('titleStrategy.insufficient')} />
  }
  const longShort = result.title_length_analysis.long_vs_short

  const kpis = [
    { label: t('titleStrategy.totalWorks'), value: formatNumber(result.overview.total_works), hint: result.meta.period, icon: FileText, tone: 'text-blue-700 bg-blue-50 border-blue-100' },
    { label: t('titleStrategy.hitThreshold'), value: formatNumber(result.overview.hit_threshold), hint: t('titleStrategy.weightedScore'), icon: Target, tone: 'text-rose-700 bg-rose-50 border-rose-100' },
    { label: t('titleStrategy.hitWorks'), value: formatNumber(result.overview.hit_count), hint: formatPercent(result.overview.overall_hit_rate), icon: TrendingUp, tone: 'text-emerald-700 bg-emerald-50 border-emerald-100' },
    { label: t('titleStrategy.bestRange'), value: result.title_length_analysis.best_range, hint: result.title_length_analysis.winner, icon: TextCursorInput, tone: 'text-amber-700 bg-amber-50 border-amber-100' },
  ]

  return (
    <div className="space-y-5">
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label={t('titleStrategy.overview')}>
        {kpis.map((item) => <article key={item.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-shadow duration-200 hover:shadow-md"><div className={`mb-3 grid h-9 w-9 place-items-center rounded-lg border ${item.tone}`}><item.icon aria-hidden="true" className="h-4 w-4" /></div><div className="text-xs font-medium text-slate-500">{item.label}</div><div className="mt-1 truncate text-2xl font-semibold tracking-tight text-slate-950" title={item.value}>{item.value}</div><div className="mt-1 truncate text-[11px] text-slate-400" title={item.hint}>{item.hint || '-'}</div></article>)}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <article className="rounded-xl border border-blue-100 bg-gradient-to-br from-blue-700 to-blue-900 p-5 text-white shadow-sm"><div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-blue-200"><Sparkles aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.coreFinding')}</div><p className="mt-3 text-base leading-8 text-white">{result.overview.core_finding}</p><div className="mt-4 grid gap-3 border-t border-white/15 pt-4 sm:grid-cols-3"><Insight label={t('titleStrategy.lengthAdvice')} text={result.overview.title_length_advice} /><Insight label={t('titleStrategy.keywordAdvice')} text={result.overview.keyword_advice} /><Insight label={t('titleStrategy.contentAdvice')} text={result.overview.content_advice} /></div></article>
        <article className="rounded-xl border border-amber-200 bg-amber-50 p-5"><div className="flex items-center gap-2 text-sm font-semibold text-amber-950"><BookOpenCheck aria-hidden="true" className="h-4 w-4 text-amber-700" />{t('titleStrategy.method')}</div><dl className="mt-4 space-y-3 text-xs"><MetaRow label={t('titleStrategy.account')} value={result.meta.account} /><MetaRow label={t('titleStrategy.period')} value={result.meta.period} /><MetaRow label={t('titleStrategy.formula')} value={result.meta.interaction_formula} /><MetaRow label={t('titleStrategy.reused')} value={String(result.meta.reused_hit_analyses || 0)} /></dl><p className="mt-4 border-t border-amber-200 pt-3 text-xs leading-5 text-amber-800">{result.meta.data_limit}</p></article>
      </section>

      <Tabs defaultValue="insights" className="space-y-4">
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1 p-1 sm:grid-cols-4" aria-label={t('titleStrategy.sectionNavigation')}>
          <TabsTrigger value="insights" className="min-h-11 cursor-pointer gap-2 px-2 py-2 text-xs sm:px-4">
            <BarChart3 aria-hidden="true" className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('titleStrategy.sectionInsights')}</span>
          </TabsTrigger>
          <TabsTrigger value="viral" className="min-h-11 cursor-pointer gap-2 px-2 py-2 text-xs sm:px-4">
            <TrendingUp aria-hidden="true" className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('titleStrategy.sectionViral')}</span>
            <span className="rounded bg-rose-50 px-1.5 py-0.5 font-mono text-[10px] text-rose-700">{result.hit_works.length}</span>
          </TabsTrigger>
          <TabsTrigger value="covers" className="min-h-11 cursor-pointer gap-2 px-2 py-2 text-xs sm:px-4">
            <Image aria-hidden="true" className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('titleStrategy.sectionCovers')}</span>
            {result.cover_analysis?.sample_count ? <span className="rounded bg-violet-50 px-1.5 py-0.5 font-mono text-[10px] text-violet-700">{result.cover_analysis.sample_count}</span> : null}
          </TabsTrigger>
          <TabsTrigger value="ideas" className="min-h-11 cursor-pointer gap-2 px-2 py-2 text-xs sm:px-4">
            <Lightbulb aria-hidden="true" className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('titleStrategy.sectionIdeas')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="insights" className="mt-0 space-y-4">
          <KeywordPerformanceChart rows={result.top_keywords} />
          <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <SectionTitle icon={BarChart3} title={t('titleStrategy.lengthTitle')} description={result.title_length_analysis.trend} />
              <LengthPerformanceChart rows={result.title_length_analysis.groups} />
              <div className="mt-5 grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-2"><CompareCard title={t('titleStrategy.shortTitle')} data={longShort.short} active={result.title_length_analysis.winner.includes('短')} /><CompareCard title={t('titleStrategy.longTitle')} data={longShort.long} active={result.title_length_analysis.winner.includes('长')} /></div>
              <p className="mt-4 rounded-lg bg-slate-50 px-4 py-3 text-xs leading-6 text-slate-600">{result.title_length_analysis.comparison_explanation}</p>
            </article>
            <HitInteractionMix rows={result.hit_works} />
          </section>
        </TabsContent>

        <TabsContent value="viral" className="mt-0 space-y-4">
          <section className="rounded-xl border border-slate-200 bg-white shadow-sm"><div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><SectionTitle icon={TrendingUp} title={t('titleStrategy.hitTitle')} description={t('titleStrategy.hitDescription', { count: result.hit_works.length })} /><Badge className="w-fit border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-50">Top {result.hit_works.length}</Badge></div>
            <div className="divide-y divide-slate-100">{result.hit_works.slice(0, expandedHits).map((row, index) => <article key={row.aweme_id} className="grid gap-4 px-5 py-4 transition-colors hover:bg-slate-50/70 lg:grid-cols-[minmax(260px,1.1fr)_minmax(280px,1fr)_minmax(240px,0.8fr)]"><div><div className="flex items-start gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-rose-50 font-mono text-[11px] font-semibold text-rose-700">{index + 1}</span><div className="min-w-0"><h3 className="text-sm font-semibold leading-6 text-slate-900">{row.title}</h3><div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500"><span>{formatNumber(row.interaction)} {t('titleStrategy.score')}</span><span>·</span><span>{row.title_len} {t('titleStrategy.characters')}</span><span>·</span><span>{row.publish_time?.slice(0, 10)}</span></div></div></div></div><div><Badge variant="outline" className="mb-2 border-blue-200 bg-blue-50 text-blue-700">{row.hook_type}</Badge><p className="text-xs leading-6 text-slate-600">{row.why_viral}</p></div><div className="rounded-lg border border-amber-100 bg-amber-50/70 px-4 py-3"><div className="text-[10px] font-semibold uppercase tracking-wider text-amber-700">{t('titleStrategy.reusableFormula')}</div><p className="mt-1.5 text-xs font-medium leading-5 text-amber-950">{row.title_formula}</p><p className="mt-2 text-[11px] leading-5 text-amber-800">{row.interaction_structure}</p></div></article>)}</div>
            {result.hit_works.length > expandedHits ? <div className="border-t border-slate-100 p-3 text-center"><Button type="button" variant="ghost" size="sm" className="cursor-pointer text-xs" onClick={() => setExpandedHits((value) => value + 6)}>{t('titleStrategy.showMore')}</Button></div> : null}
          </section>
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><SectionTitle icon={ArrowUpRight} title={t('titleStrategy.differenceTitle')} description={result.hit_vs_normal.common_patterns} /><ul className="mt-4 grid gap-2 lg:grid-cols-2">{result.hit_vs_normal.key_differences.map((item, index) => <li key={`${item}-${index}`} className="flex gap-3 rounded-lg bg-slate-50 px-3 py-2.5 text-xs leading-6 text-slate-700"><span className="mt-1 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-blue-700 text-[10px] font-semibold text-white">{index + 1}</span>{item}</li>)}</ul></article>
        </TabsContent>

        <TabsContent value="covers" className="mt-0 space-y-4">
          <CoverAnalysisPanel data={result.cover_analysis} />
        </TabsContent>

        <TabsContent value="ideas" className="mt-0 space-y-4">
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><SectionTitle icon={Lightbulb} title={t('titleStrategy.formulaTitle')} description={t('titleStrategy.formulaDescription')} /><div className="mt-4 grid gap-3 lg:grid-cols-2">{result.reusable_formulas.map((row, index) => <div key={`${row.formula}-${index}`} className="rounded-lg border border-slate-200 p-4"><div className="text-sm font-semibold text-slate-900">{row.formula}</div><div className="mt-2 rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-800">{row.example}</div><p className="mt-2 text-xs leading-5 text-slate-500">{row.why_effective}</p></div>)}</div></article>
          <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 shadow-sm"><SectionTitle icon={TextCursorInput} title={t('titleStrategy.nextTitle')} description={t('titleStrategy.nextDescription')} /><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{result.next_titles.map((row, index) => <article key={`${row.title}-${index}`} className="flex min-h-44 flex-col rounded-xl border border-emerald-100 bg-white p-4 shadow-sm"><div className="flex items-start justify-between gap-3"><Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">{row.hook_type}</Badge><button type="button" onClick={() => copyTitle(row.title)} aria-label={t('titleStrategy.copyTitle', { title: row.title })} className="grid h-9 w-9 shrink-0 cursor-pointer place-items-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"><ClipboardCopy aria-hidden="true" className="h-4 w-4" /></button></div><h3 className="mt-3 text-sm font-semibold leading-6 text-slate-900">{row.title}</h3><div className="mt-auto pt-4 text-[11px] leading-5 text-slate-500"><div>{row.formula}</div><div>{row.expected_length} {t('titleStrategy.characters')} · {row.target_audience}</div></div></article>)}</div></section>
          <section className="rounded-xl border border-slate-200 bg-slate-50 p-5"><div className="flex items-center gap-2 text-sm font-semibold text-slate-800"><AlertTriangle aria-hidden="true" className="h-4 w-4 text-slate-500" />{t('titleStrategy.riskTitle')}</div><ul className="mt-3 grid gap-2 md:grid-cols-2">{result.risk_notes.map((item, index) => <li key={`${item}-${index}`} className="text-xs leading-6 text-slate-600">• {item}</li>)}</ul></section>
        </TabsContent>
      </Tabs>
    </div>
  )
}


function CoverAnalysisPanel({ data }: { data?: AICoverAnalysis }) {
  const { t } = useTranslation('config')
  if (!data || data.status === 'not_configured') {
    return <Notice text={t('titleStrategy.coverNotConfigured')} />
  }
  if (data.status === 'no_covers' || !data.sample_count) {
    return <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><SectionTitle icon={Image} title={t('titleStrategy.coverTitle')} description={t('titleStrategy.coverDescription')} /><div className="mt-5"><EmptyLine text={t('titleStrategy.coverNoSamples')} /></div></article>
  }
  const preferredDimensions = ['subject_type', 'text_density', 'text_hook', 'composition', 'visual_style', 'color_tone']
  const groups = preferredDimensions.map((key) => ({
    key,
    rows: data.statistics.dimensions.filter((row) => row.dimension === key).slice(0, 4),
  })).filter((group) => group.rows.length)
  const previewSamples = data.samples.slice(0, 8)
  return (
    <div className="space-y-4">
      <section className="grid gap-3 sm:grid-cols-3" aria-label={t('titleStrategy.coverOverview')}>
        <MiniSummary label={t('titleStrategy.coverSamples')} value={String(data.sample_count)} hint={t('titleStrategy.coverSampleRule', { count: data.requested_sample_count })} />
        <MiniSummary label={t('titleStrategy.coverHitNormal')} value={`${data.statistics.hit_sample_count || 0} / ${data.statistics.normal_sample_count || 0}`} hint={t('titleStrategy.coverHitNormalHint')} />
        <MiniSummary label={t('titleStrategy.coverModel')} value={data.model || '-'} hint={data.status === 'partial' ? t('titleStrategy.coverPartial') : t('titleStrategy.coverCached')} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <article className="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-700 to-indigo-900 p-5 text-white shadow-sm">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-violet-200"><ScanText aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.coverFinding')}</div>
          <p className="mt-3 text-sm leading-7 text-white">{data.summary}</p>
          <div className="mt-4 border-t border-white/15 pt-4"><div className="text-[10px] font-semibold uppercase tracking-wider text-violet-200">{t('titleStrategy.coverDifference')}</div><ul className="mt-2 space-y-1.5">{data.hit_differences.map((item) => <li key={item} className="text-xs leading-5 text-violet-50">• {item}</li>)}</ul></div>
        </article>
        <article className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 shadow-sm"><SectionTitle icon={Lightbulb} title={t('titleStrategy.coverRecommendations')} description={t('titleStrategy.coverRecommendationHint')} /><ul className="mt-4 space-y-2">{data.recommendations.map((item, index) => <li key={`${item}-${index}`} className="flex gap-2 rounded-lg bg-white px-3 py-2.5 text-xs leading-5 text-emerald-950"><span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-emerald-700 text-[10px] font-semibold text-white">{index + 1}</span>{item}</li>)}</ul></article>
      </section>

      <section className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3" aria-label={t('titleStrategy.coverTagDistribution')}>
        {groups.map((group) => <article key={group.key} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-sm font-semibold text-slate-900">{group.rows[0].dimension_name}</div><div className="mt-3 space-y-3">{group.rows.map((row) => <div key={`${row.dimension}-${row.label}`}><div className="mb-1.5 flex items-center justify-between gap-3 text-[11px]"><span className="font-medium text-slate-700">{row.label_name}</span><span className="font-mono text-slate-500">{row.count} · {formatPercent(row.ratio)} · ×{row.lift.toFixed(2)}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${row.label_name} ${formatPercent(row.ratio)}`}><div className="h-full rounded-full bg-violet-600" style={{ width: `${Math.max(3, row.ratio * 100)}%` }} /></div></div>)}</div></article>)}
      </section>

      <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><SectionTitle icon={Image} title={t('titleStrategy.coverSampleTitle')} description={t('titleStrategy.coverSampleDescription')} /><div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{previewSamples.map((row) => <article key={row.aweme_id} className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50"><div className="aspect-video overflow-hidden bg-slate-100"><img src={row.cover_url} alt={t('titleStrategy.coverSampleAlt', { title: row.title })} loading="lazy" className="h-full w-full object-cover" /></div><div className="p-3"><div className="flex items-center justify-between gap-2"><Badge variant="outline" className={row.is_hit ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-slate-200 bg-white text-slate-600'}>{row.is_hit ? t('titleStrategy.coverHit') : t('titleStrategy.coverNormal')}</Badge><span className="font-mono text-[10px] text-slate-400">{Math.round(Number(row.labels.confidence || 0) * 100)}%</span></div><p className="mt-2 line-clamp-2 text-xs font-medium leading-5 text-slate-800">{row.title}</p><div className="mt-2 flex flex-wrap gap-1">{(row.display_tags || []).map((tag) => <span key={tag} className="rounded bg-violet-50 px-1.5 py-0.5 text-[10px] text-violet-700">{tag}</span>)}</div>{row.labels.ocr_text ? <p className="mt-2 line-clamp-2 border-t border-slate-200 pt-2 text-[10px] leading-4 text-slate-500">OCR · {row.labels.ocr_text}</p> : null}</div></article>)}</div></article>
    </div>
  )
}


function MiniSummary({ label, value, hint }: { label: string; value: string; hint: string }) {
  return <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs font-medium text-slate-500">{label}</div><div className="mt-1 truncate text-xl font-semibold text-slate-950" title={value}>{value}</div><div className="mt-1 text-[11px] leading-5 text-slate-400">{hint}</div></article>
}


function KeywordPerformanceChart({ rows }: { rows: AITitleStrategyKeyword[] }) {
  const { t } = useTranslation('config')
  if (!rows.length) return <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><SectionTitle icon={KeyRound} title={t('titleStrategy.keywordTitle')} description={t('titleStrategy.keywordDescription')} /><div className="mt-5"><EmptyLine text={t('titleStrategy.noKeyword')} /></div></article>
  const maxLift = Math.max(...rows.map((row) => row.lift), 1)
  const ratios = rows.map((row) => row.ratio).sort((left, right) => left - right)
  const middle = Math.floor(ratios.length / 2)
  const medianRatio = ratios.length % 2 ? ratios[middle] : (ratios[middle - 1] + ratios[middle]) / 2
  const tier = (row: AITitleStrategyKeyword) => {
    const wide = row.ratio >= medianRatio
    const strong = row.lift >= 1
    if (wide && strong) return { label: t('titleStrategy.keywordTierLeader'), className: 'border-emerald-200 bg-emerald-50 text-emerald-700' }
    if (wide) return { label: t('titleStrategy.keywordTierCoverage'), className: 'border-blue-200 bg-blue-50 text-blue-700' }
    if (strong) return { label: t('titleStrategy.keywordTierPotential'), className: 'border-amber-200 bg-amber-50 text-amber-700' }
    return { label: t('titleStrategy.keywordTierWatch'), className: 'border-slate-200 bg-slate-50 text-slate-600' }
  }

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <SectionTitle icon={KeyRound} title={t('titleStrategy.keywordTitle')} description={t('titleStrategy.keywordVisualDescription')} />
        <div className="flex flex-wrap gap-3 text-[11px] text-slate-500" aria-label={t('titleStrategy.chartLegend')}><span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-blue-600" />{t('titleStrategy.coverage')}</span><span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-amber-500" />{t('titleStrategy.lift')}</span><span>{t('titleStrategy.keywordDecisionHint')}</span></div>
      </div>
      <div className="mt-5 divide-y divide-slate-100">
        {rows.map((row, index) => {
          const category = tier(row)
          return (
            <div key={row.keyword} className="grid gap-3 py-3 first:pt-0 last:pb-0 md:grid-cols-[minmax(170px,0.65fr)_minmax(280px,1.35fr)_minmax(220px,0.8fr)] md:items-center">
              <div className="flex min-w-0 items-center gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-slate-100 font-mono text-[10px] font-semibold text-slate-500">{index + 1}</span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="truncate text-sm font-semibold text-slate-900">{row.keyword}</span><Badge variant="outline" className={category.className}>{category.label}</Badge></div><div className="mt-1 text-[11px] text-slate-500">{row.count} {t('titleStrategy.posts')} · {t('titleStrategy.average')} {formatNumber(row.avg_interaction)} · {t('titleStrategy.hitRate')} {formatPercent(row.hit_rate)}</div></div></div>
              <div className="space-y-2" role="img" aria-label={`${row.keyword}: ${t('titleStrategy.coverage')} ${formatPercent(row.ratio)}, ${t('titleStrategy.lift')} ${row.lift.toFixed(2)}`}>
                <MetricBar label={t('titleStrategy.coverage')} value={formatPercent(row.ratio)} width={row.ratio * 100} marker={medianRatio * 100} color="bg-blue-600" />
                <MetricBar label={t('titleStrategy.lift')} value={row.lift.toFixed(2)} width={row.lift / maxLift * 100} marker={100 / maxLift} color="bg-amber-500" />
              </div>
              <p className="text-xs leading-5 text-slate-600">{row.conclusion}</p>
            </div>
          )
        })}
      </div>
    </article>
  )
}


function MetricBar({ label, value, width, marker, color }: { label: string; value: string; width: number; marker?: number; color: string }) {
  const safeWidth = width <= 0 ? 0 : Math.max(3, Math.min(100, width))
  const safeMarker = typeof marker === 'number' ? Math.max(0, Math.min(100, marker)) : null
  return <div className="grid grid-cols-[52px_minmax(0,1fr)_48px] items-center gap-2 text-[10px]"><span className="text-slate-400">{label}</span><span className="relative h-2 rounded-full bg-slate-100"><span className={`block h-full rounded-full transition-[width] duration-300 motion-reduce:transition-none ${color}`} style={{ width: `${safeWidth}%` }} />{safeMarker !== null ? <span aria-hidden="true" className="absolute -bottom-1 -top-1 w-px bg-slate-500" style={{ left: `calc(${safeMarker}% - 0.5px)` }} /> : null}</span><span className="text-right font-mono font-semibold text-slate-600">{value}</span></div>
}


function LengthPerformanceChart({ rows }: { rows: AITitleLengthGroup[] }) {
  const { t } = useTranslation('config')
  const maxValue = Math.max(1, ...rows.flatMap((row) => [row.avg_interaction, row.median_interaction]))
  return (
    <div className="mt-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500"><div className="flex gap-4" aria-label={t('titleStrategy.chartLegend')}><span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-blue-600" />{t('titleStrategy.average')}</span><span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-amber-500" />{t('titleStrategy.median')}</span></div><span>{t('titleStrategy.lengthChartHint')}</span></div>
      <div className="space-y-4">{rows.map((row) => <div key={row.len_group} className="grid gap-2 sm:grid-cols-[72px_minmax(0,1fr)_92px] sm:items-center"><div><div className="text-xs font-semibold text-slate-800">{row.len_group}</div><div className="mt-0.5 text-[10px] text-slate-400">{row.count} {t('titleStrategy.posts')}</div></div><div className="space-y-2" role="img" aria-label={`${row.len_group}: ${t('titleStrategy.average')} ${formatNumber(row.avg_interaction)}, ${t('titleStrategy.median')} ${formatNumber(row.median_interaction)}`}><MetricBar label={t('titleStrategy.averageShort')} value={formatNumber(row.avg_interaction)} width={row.count ? row.avg_interaction / maxValue * 100 : 0} color="bg-blue-600" /><MetricBar label={t('titleStrategy.medianShort')} value={formatNumber(row.median_interaction)} width={row.count ? row.median_interaction / maxValue * 100 : 0} color="bg-amber-500" /></div><div className="rounded-lg bg-slate-50 px-3 py-2 text-center"><div className="text-sm font-semibold text-slate-900">{formatPercent(row.hit_rate)}</div><div className="text-[10px] text-slate-400">{t('titleStrategy.hitRate')}</div></div></div>)}</div>
    </div>
  )
}


function HitInteractionMix({ rows }: { rows: AITitleStrategyHitWork[] }) {
  const { t } = useTranslation('config')
  const metrics = [
    { key: 'likes', label: t('titleStrategy.likesContribution'), raw: rows.reduce((sum, row) => sum + row.likes, 0), weighted: rows.reduce((sum, row) => sum + row.likes, 0), color: 'bg-blue-600' },
    { key: 'comments', label: t('titleStrategy.commentsContribution'), raw: rows.reduce((sum, row) => sum + row.comments, 0), weighted: rows.reduce((sum, row) => sum + row.comments * 2, 0), color: 'bg-violet-500' },
    { key: 'collects', label: t('titleStrategy.collectsContribution'), raw: rows.reduce((sum, row) => sum + row.collects, 0), weighted: rows.reduce((sum, row) => sum + row.collects * 2, 0), color: 'bg-amber-500' },
    { key: 'shares', label: t('titleStrategy.sharesContribution'), raw: rows.reduce((sum, row) => sum + row.shares, 0), weighted: rows.reduce((sum, row) => sum + row.shares * 3, 0), color: 'bg-emerald-500' },
  ]
  const total = metrics.reduce((sum, item) => sum + item.weighted, 0)
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <SectionTitle icon={Gauge} title={t('titleStrategy.mixTitle')} description={t('titleStrategy.mixDescription')} />
      {rows.length && total ? <><div className="mt-6 flex h-5 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={metrics.map((item) => `${item.label} ${formatPercent(item.weighted / total)}`).join('，')}>{metrics.map((item) => <span key={item.key} className={`${item.color} h-full first:rounded-l-full last:rounded-r-full`} style={{ width: `${item.weighted / total * 100}%` }} />)}</div><div className="mt-5 grid grid-cols-2 gap-3">{metrics.map((item) => <div key={item.key} className="rounded-lg border border-slate-200 p-3"><div className="flex items-center gap-2 text-[11px] text-slate-500"><span className={`h-2.5 w-2.5 rounded-sm ${item.color}`} />{item.label}</div><div className="mt-2 flex items-end justify-between gap-2"><span className="text-lg font-semibold text-slate-900">{formatPercent(item.weighted / total)}</span><span className="text-[10px] text-slate-400">{formatNumber(item.raw)} → {formatNumber(item.weighted)}</span></div></div>)}</div><div className="mt-4 rounded-lg bg-blue-50 px-4 py-3 text-xs leading-6 text-blue-800">{t('titleStrategy.mixInsight', { metric: metrics.reduce((best, item) => item.weighted > best.weighted ? item : best).label })}</div></> : <div className="mt-5"><EmptyLine text={t('titleStrategy.noHitMix')} /></div>}
    </article>
  )
}


function Insight({ label, text }: { label: string; text: string }) {
  return <div><div className="text-[10px] font-semibold uppercase tracking-wider text-blue-200">{label}</div><p className="mt-1 text-xs leading-5 text-blue-50">{text}</p></div>
}


function MetaRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-start justify-between gap-4"><dt className="text-amber-700">{label}</dt><dd className="max-w-[65%] text-right font-medium text-amber-950">{value || '-'}</dd></div>
}


function SectionTitle({ icon: Icon, title, description }: { icon: typeof BarChart3; title: string; description: string }) {
  return <div className="flex items-start gap-3"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-700"><Icon aria-hidden="true" className="h-4 w-4" /></span><div className="min-w-0"><h2 className="text-sm font-semibold text-slate-900">{title}</h2><p className="mt-0.5 text-xs leading-5 text-slate-500">{description}</p></div></div>
}


function CompareCard({ title, data, active }: { title: string; data: { count: number; avg_interaction: number; hit_rate: number; avg_shares: number }; active: boolean }) {
  const { t } = useTranslation('config')
  return <div className={`rounded-lg border p-3 ${active ? 'border-blue-200 bg-blue-50' : 'border-slate-200 bg-white'}`}><div className="flex items-center justify-between"><span className="text-xs font-semibold text-slate-800">{title}</span>{active ? <Badge className="bg-blue-700 text-white hover:bg-blue-700">{t('titleStrategy.better')}</Badge> : null}</div><div className="mt-3 grid grid-cols-3 gap-2 text-center"><MiniMetric label={t('titleStrategy.average')} value={formatNumber(data.avg_interaction)} /><MiniMetric label={t('titleStrategy.hitRate')} value={formatPercent(data.hit_rate)} /><MiniMetric label={t('titleStrategy.shares')} value={formatNumber(data.avg_shares)} /></div></div>
}


function MiniMetric({ label, value }: { label: string; value: string }) {
  return <div><div className="text-sm font-semibold text-slate-900">{value}</div><div className="mt-0.5 text-[10px] text-slate-400">{label}</div></div>
}


function EmptyLine({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">{text}</div>
}


function StrategySkeleton() {
  return <div className="space-y-4" aria-label="loading"><div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-32 animate-pulse rounded-xl bg-slate-100" />)}</div><div className="grid gap-4 xl:grid-cols-2"><div className="h-96 animate-pulse rounded-xl bg-slate-100" /><div className="h-96 animate-pulse rounded-xl bg-slate-100" /></div></div>
}


function EmptyStrategy({ onAnalyze }: { onAnalyze: () => void }) {
  const { t } = useTranslation('config')
  return <div className="rounded-xl border border-dashed border-blue-200 bg-blue-50/40 px-6 py-16 text-center"><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-blue-700 text-white shadow-md"><BrainCircuit aria-hidden="true" className="h-6 w-6" /></span><h2 className="mt-5 text-base font-semibold text-slate-900">{t('titleStrategy.emptyTitle')}</h2><p className="mx-auto mt-2 max-w-2xl text-sm leading-7 text-slate-600">{t('titleStrategy.emptyDescription')}</p><Button type="button" onClick={onAnalyze} className="mt-5 bg-blue-700 text-white hover:bg-blue-800"><Sparkles aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.analyze')}</Button></div>
}
