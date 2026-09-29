import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  Database,
  ExternalLink,
  FileText,
  Gauge,
  History,
  Image,
  KeyRound,
  Layers3,
  Palette,
  RefreshCw,
  Search,
  Sparkles,
  Target,
  TextCursorInput,
  Trash2,
  TrendingUp,
  UploadCloud,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  monitorApi,
  type AIAnalysisResponse,
  type AICoverAnalysis,
  type AICoverCandidateResult,
  type AICoverDimensionStat,
  type AICoverScoreRecord,
  type AITitleLengthGroup,
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


function formatScore(value?: number | null): string {
  return value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(1)
}


function formatCompactNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale.startsWith('zh') ? 'zh-CN' : 'en-US', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(Number(value || 0))
}


function formatLengthGroup(value: string): string {
  return value.replace(/(\d)-(\d)/g, '$1–$2')
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


function isCompatibleContentPerformanceResult(value: unknown): value is AITitleStrategyResult {
  if (!value || typeof value !== 'object') return false
  const result = value as Partial<AITitleStrategyResult>
  return Boolean(
    result.schema_version === 'content-performance-v2'
    && result.overview
    && result.meta
    && Array.isArray(result.title_length_analysis?.groups)
    && Array.isArray(result.top_keywords),
  )
}


export function TitleStrategyAIReport({ accountId, timeRange, postLimit }: TitleStrategyAIReportProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const currentAccountRef = useRef(accountId)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [legacyDeleteOpen, setLegacyDeleteOpen] = useState(false)
  const [historyDeleteTarget, setHistoryDeleteTarget] = useState<AIAnalysisResponse<AITitleStrategyResult> | null>(null)
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
      if (!isCompatibleContentPerformanceResult(response.data.result)) {
        toast.error(t('titleStrategy.incompatible'))
        return
      }
      setSelectedId(response.data.id)
      queryClient.setQueryData<AIAnalysisResponse<AITitleStrategyResult>[]>(
        ['aiTitleStrategyHistory', variables.accountId],
        (current = []) => [response.data, ...current.filter((item) => item.id !== response.data.id)],
      )
      toast.success(t('titleStrategy.completed'))
    },
    onError: (error, variables) => {
      if (currentAccountRef.current === variables.accountId) toast.error(`${t('titleStrategy.failed')}: ${analysisErrorMessage(error)}`)
    },
  })
  const deleteLegacyMutation = useMutation({
    mutationFn: async (targetAccountId: number) => monitorApi.deleteLegacyTitleStrategyReports(targetAccountId),
    onSuccess: async (response, targetAccountId) => {
      if (currentAccountRef.current !== targetAccountId) return
      setLegacyDeleteOpen(false)
      setSelectedId(null)
      await queryClient.invalidateQueries({ queryKey: ['aiTitleStrategyHistory', targetAccountId] })
      toast.success(t('titleStrategy.legacyDeleteSuccess', { count: response.data.deleted }))
    },
    onError: (error, targetAccountId) => {
      if (currentAccountRef.current === targetAccountId) toast.error(`${t('titleStrategy.legacyDeleteFailed')}: ${analysisErrorMessage(error)}`)
    },
  })
  const deleteHistoryMutation = useMutation({
    mutationFn: async ({ resultId }: { resultId: number; targetAccountId: number }) => monitorApi.deleteAIResult(resultId),
    onSuccess: async (_response, variables) => {
      if (currentAccountRef.current !== variables.targetAccountId) return
      setHistoryDeleteTarget(null)
      setSelectedId(null)
      mutation.reset()
      queryClient.setQueryData<AIAnalysisResponse<AITitleStrategyResult>[]>(
        ['aiTitleStrategyHistory', variables.targetAccountId],
        (items = []) => items.filter((item) => item.id !== variables.resultId),
      )
      await queryClient.invalidateQueries({ queryKey: ['aiTitleStrategyHistory', variables.targetAccountId] })
      toast.success(t('titleStrategy.historyDeleteSuccess'))
    },
    onError: (error, variables) => {
      if (currentAccountRef.current === variables.targetAccountId) toast.error(`${t('titleStrategy.historyDeleteFailed')}: ${analysisErrorMessage(error)}`)
    },
  })

  useEffect(() => {
    currentAccountRef.current = accountId
    setSelectedId(null)
    setLegacyDeleteOpen(false)
    setHistoryDeleteTarget(null)
    mutation.reset()
    deleteLegacyMutation.reset()
    deleteHistoryMutation.reset()
  }, [accountId])

  const rawHistory = historyQuery.data || []
  const history = rawHistory.filter((item) => isCompatibleContentPerformanceResult(item.result))
  const incompatibleHistoryCount = rawHistory.length - history.length
  const rawMutationResult = mutation.variables?.accountId === accountId ? mutation.data?.data : null
  const mutationResult = rawMutationResult && isCompatibleContentPerformanceResult(rawMutationResult.result) ? rawMutationResult : null
  const current = mutationResult || history.find((item) => item.id === selectedId) || history[0] || null
  const configured = Boolean(statusQuery.data?.configured)
  const visionConfigured = Boolean(statusQuery.data?.vision?.configured)
  const disabled = typeof accountId !== 'number' || !configured || mutation.isPending

  return (
    <div className="report-theme w-full space-y-4 pb-8">
      <header className="overflow-hidden rounded-xl border border-blue-100 bg-white shadow-sm">
        <div className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between lg:p-6">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-blue-700 text-white shadow-md shadow-blue-200"><BrainCircuit aria-hidden="true" className="h-5 w-5" /></span>
            <div className="min-w-0">
              <Badge className="mb-2 border-blue-200 bg-blue-100 text-blue-800 hover:bg-blue-100">{t('titleStrategy.badge')}</Badge>
              <h1 className="text-xl font-semibold tracking-tight text-slate-950 sm:text-2xl">{t('titleStrategy.title')}</h1>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{t('titleStrategy.description')}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill active={configured} label={configured ? t('titleStrategy.modelConnected') : t('titleStrategy.modelUnavailable')} value={statusQuery.data?.model || '-'} />
            <StatusPill active={visionConfigured} label={visionConfigured ? t('titleStrategy.visionConnected') : t('titleStrategy.visionUnavailable')} value={statusQuery.data?.vision?.model || '-'} />
            <details className="group relative">
              <summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 [&::-webkit-details-marker]:hidden"><History aria-hidden="true" className="h-3.5 w-3.5" />{t('titleStrategy.history')}<ChevronDown aria-hidden="true" className="h-3.5 w-3.5 transition-transform group-open:rotate-180" /></summary>
              <div className="absolute right-0 z-30 mt-2 max-h-80 w-[min(360px,calc(100vw-32px))] overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-xl">
                {history.length ? history.map((item) => <div key={item.id} className={`grid grid-cols-[minmax(0,1fr)_44px] items-center rounded-lg transition-colors ${current?.id === item.id ? 'bg-blue-50' : 'hover:bg-slate-50'}`}><button type="button" onClick={() => setSelectedId(item.id)} className="min-h-11 min-w-0 cursor-pointer rounded-lg px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"><div className="flex items-center justify-between gap-2 text-[11px] text-slate-700"><span>{formatDateTime(item.updated_at)}</span><span className="font-mono text-[10px] text-slate-400">{item.model || '-'}</span></div><div className="mt-1 line-clamp-1 text-[10px] leading-4 text-slate-500">{item.result?.meta?.period || item.status}</div></button><button type="button" disabled={item.id == null || deleteHistoryMutation.isPending} onClick={() => setHistoryDeleteTarget(item)} aria-label={t('titleStrategy.deleteHistoryAria', { time: formatDateTime(item.updated_at) })} className="grid h-11 w-11 cursor-pointer place-items-center rounded-lg text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-600 disabled:cursor-not-allowed disabled:opacity-40"><Trash2 aria-hidden="true" className="h-4 w-4" /></button></div>) : <div className="px-3 py-8 text-center text-xs text-slate-400">{t('titleStrategy.noHistory')}</div>}
              </div>
            </details>
            <Button type="button" disabled={disabled} onClick={() => typeof accountId === 'number' && mutation.mutate({ force: Boolean(current), accountId, timeRange, postLimit })} className="min-h-10 bg-blue-700 px-4 text-xs text-white hover:bg-blue-800 focus-visible:ring-blue-600">{mutation.isPending ? <RefreshCw aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden="true" className="h-4 w-4" />}{mutation.isPending ? t('titleStrategy.analyzing') : current ? t('titleStrategy.reanalyze') : t('titleStrategy.analyze')}</Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-blue-100 bg-slate-50/70 px-5 py-3 text-xs text-slate-600 lg:px-6"><span className="inline-flex items-center gap-2"><Gauge aria-hidden="true" className="h-3.5 w-3.5 text-blue-700" />{t('titleStrategy.metricRule')}</span><span className="inline-flex items-center gap-2"><Database aria-hidden="true" className="h-3.5 w-3.5 text-violet-700" />{t('titleStrategy.coverRule')}</span></div>
      </header>

      {typeof accountId !== 'number' ? <Notice text={t('titleStrategy.singleAccountRequired')} /> : null}
      {typeof accountId === 'number' && !configured && !statusQuery.isLoading ? <Notice text={t('titleStrategy.notConfigured')} /> : null}
      {incompatibleHistoryCount > 0 ? <div className="flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"><div className="flex min-w-0 items-start gap-2 text-sm leading-6 text-amber-900"><AlertTriangle aria-hidden="true" className="mt-1 h-4 w-4 shrink-0" /><span>{t('titleStrategy.historyIgnored', { count: incompatibleHistoryCount })}</span></div><Button type="button" variant="outline" onClick={() => setLegacyDeleteOpen(true)} disabled={deleteLegacyMutation.isPending} className="min-h-11 shrink-0 cursor-pointer border-rose-200 bg-white text-rose-700 hover:bg-rose-50 hover:text-rose-800 focus-visible:ring-rose-600"><Trash2 aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.deleteLegacy')}</Button></div> : null}
      {mutation.isPending || historyQuery.isLoading ? <StrategySkeleton /> : current && typeof accountId === 'number' ? <ContentPerformance current={current} accountId={accountId} /> : typeof accountId === 'number' && configured ? <EmptyStrategy onAnalyze={() => mutation.mutate({ force: false, accountId, timeRange, postLimit })} /> : null}

      <Dialog open={legacyDeleteOpen} onOpenChange={(open) => !deleteLegacyMutation.isPending && setLegacyDeleteOpen(open)}>
        <DialogContent className="max-w-md border-slate-200 bg-white">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-slate-950"><span className="grid h-9 w-9 place-items-center rounded-lg bg-rose-50 text-rose-700"><Trash2 aria-hidden="true" className="h-4 w-4" /></span>{t('titleStrategy.legacyDeleteTitle')}</DialogTitle>
            <DialogDescription className="pt-2 leading-6 text-slate-600">{t('titleStrategy.legacyDeleteDescription')}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" disabled={deleteLegacyMutation.isPending} onClick={() => setLegacyDeleteOpen(false)} className="min-h-11 cursor-pointer">{t('titleStrategy.cancel')}</Button>
            <Button type="button" disabled={deleteLegacyMutation.isPending || typeof accountId !== 'number'} onClick={() => typeof accountId === 'number' && deleteLegacyMutation.mutate(accountId)} className="min-h-11 cursor-pointer bg-rose-600 text-white hover:bg-rose-700 focus-visible:ring-rose-600">{deleteLegacyMutation.isPending ? <RefreshCw aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" /> : <Trash2 aria-hidden="true" className="h-4 w-4" />}{deleteLegacyMutation.isPending ? t('titleStrategy.legacyDeleting') : t('titleStrategy.confirmDeleteLegacy')}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(historyDeleteTarget)} onOpenChange={(open) => !open && !deleteHistoryMutation.isPending && setHistoryDeleteTarget(null)}>
        <DialogContent className="max-w-md border-slate-200 bg-white">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-slate-950"><span className="grid h-9 w-9 place-items-center rounded-lg bg-rose-50 text-rose-700"><Trash2 aria-hidden="true" className="h-4 w-4" /></span>{t('titleStrategy.historyDeleteTitle')}</DialogTitle>
            <DialogDescription className="pt-2 leading-6 text-slate-600">{t('titleStrategy.historyDeleteDescription', { time: formatDateTime(historyDeleteTarget?.updated_at), period: historyDeleteTarget?.result?.meta?.period || '—' })}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" disabled={deleteHistoryMutation.isPending} onClick={() => setHistoryDeleteTarget(null)} className="min-h-11 cursor-pointer">{t('titleStrategy.cancel')}</Button>
            <Button type="button" disabled={deleteHistoryMutation.isPending || historyDeleteTarget?.id == null || typeof accountId !== 'number'} onClick={() => historyDeleteTarget?.id != null && typeof accountId === 'number' && deleteHistoryMutation.mutate({ resultId: historyDeleteTarget.id, targetAccountId: accountId })} className="min-h-11 cursor-pointer bg-rose-600 text-white hover:bg-rose-700 focus-visible:ring-rose-600">{deleteHistoryMutation.isPending ? <RefreshCw aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" /> : <Trash2 aria-hidden="true" className="h-4 w-4" />}{deleteHistoryMutation.isPending ? t('titleStrategy.historyDeleting') : t('titleStrategy.confirmDeleteHistory')}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}


function StatusPill({ active, label, value }: { active: boolean; label: string; value: string }) {
  return <div className={`flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-xs ${active ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}><CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5" /><span>{label}</span><span className="max-w-28 truncate rounded bg-white/80 px-1.5 py-0.5 font-mono text-[10px]" title={value}>{value}</span></div>
}


function Notice({ text }: { text: string }) {
  return <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900"><AlertTriangle aria-hidden="true" className="mr-2 inline h-4 w-4" />{text}</div>
}


function ContentPerformance({ current, accountId }: { current: AIAnalysisResponse<AITitleStrategyResult>; accountId: number }) {
  const { t, i18n } = useTranslation('config')
  const result = current.result
  if (current.status === 'insufficient_data') {
    const summary = (result as unknown as { summary?: string }).summary
    return <Notice text={summary || t('titleStrategy.insufficient')} />
  }
  const cover = result.cover_analysis
  const lengthGroups = result.title_length_analysis.groups || []
  const stableLengthGroups = lengthGroups.filter((row) => row.count >= 30)
  const bestLengthGroup = [...(stableLengthGroups.length ? stableLengthGroups : lengthGroups)]
    .filter((row) => row.count > 0)
    .sort((left, right) => Number(right.median_interaction || 0) - Number(left.median_interaction || 0) || right.count - left.count)[0]
  const validCoverCount = cover?.valid_cover_count ?? Math.max(0, (cover?.requested_sample_count || 0) - (cover?.missing_cover_count || 0))
  const analyzedCoverCount = cover?.sample_count || 0
  const failedCoverCount = cover?.failed_count ?? Math.max(0, validCoverCount - analyzedCoverCount)
  const coverCoverage = validCoverCount > 0 ? analyzedCoverCount / validCoverCount : 0
  const kpis = [
    { label: t('titleStrategy.totalWorks'), value: formatNumber(result.overview.total_works), exactValue: formatNumber(result.overview.total_works), evidence: result.meta.period, status: t('titleStrategy.kpiRealData'), icon: FileText, tone: 'text-blue-700 bg-blue-50 border-blue-100', statusTone: 'border-blue-200 bg-blue-50 text-blue-700' },
    { label: t('titleStrategy.hitThreshold'), value: formatCompactNumber(result.overview.hit_threshold, i18n.language), exactValue: formatNumber(result.overview.hit_threshold), evidence: t('titleStrategy.weightedScoreFormula'), status: t('titleStrategy.kpiDynamicThreshold'), icon: Target, tone: 'text-rose-700 bg-rose-50 border-rose-100', statusTone: 'border-rose-200 bg-rose-50 text-rose-700' },
    { label: t('titleStrategy.bestRange'), value: bestLengthGroup ? formatLengthGroup(bestLengthGroup.len_group) : '—', exactValue: bestLengthGroup?.len_group || '—', evidence: bestLengthGroup ? t('titleStrategy.bestRangeEvidence', { count: bestLengthGroup.count, median: formatNumber(bestLengthGroup.median_interaction), hitRate: formatPercent(bestLengthGroup.hit_rate) }) : t('titleStrategy.sampleInsufficient'), status: bestLengthGroup && bestLengthGroup.count >= 30 ? t('titleStrategy.kpiStableSample') : t('titleStrategy.sampleInsufficient'), icon: TextCursorInput, tone: 'text-amber-700 bg-amber-50 border-amber-100', statusTone: 'border-amber-200 bg-amber-50 text-amber-700' },
    { label: t('titleStrategy.coverAnalyzed'), value: formatPercent(coverCoverage), exactValue: `${analyzedCoverCount} / ${validCoverCount}`, evidence: t('titleStrategy.coverCoverageEvidence', { analyzed: analyzedCoverCount, valid: validCoverCount, failed: failedCoverCount }), status: failedCoverCount > 0 ? t('titleStrategy.kpiCoverPartial', { count: failedCoverCount }) : t('titleStrategy.kpiCoverComplete'), icon: Image, tone: 'text-violet-700 bg-violet-50 border-violet-100', statusTone: failedCoverCount > 0 ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700' },
  ]

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label={t('titleStrategy.overview')}>
        {kpis.map((item) => <ContentKpiCard key={item.label} {...item} />)}
      </section>

      <Tabs defaultValue="titles" className="space-y-4">
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1 p-1" aria-label={t('titleStrategy.sectionNavigation')}>
          <TabsTrigger value="titles" className="min-h-11 cursor-pointer gap-2 px-4 py-2 text-sm"><BarChart3 aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.sectionTitles')}</TabsTrigger>
          <TabsTrigger value="covers" className="min-h-11 cursor-pointer gap-2 px-4 py-2 text-sm"><Image aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.sectionCovers')}<span className="rounded bg-violet-50 px-1.5 py-0.5 font-mono text-[10px] text-violet-700">{cover?.sample_count || 0}</span></TabsTrigger>
        </TabsList>

        <TabsContent value="titles" className="mt-0 space-y-4">
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <LengthPerformanceChart rows={result.title_length_analysis.groups} overallMedian={result.overview.interaction_median || 0} />
          </article>
          <KeywordPerformanceChart rows={result.top_keywords} />
        </TabsContent>

        <TabsContent value="covers" className="mt-0">
          <CoverAnalysisPanel data={cover} accountId={accountId} resultId={current.id} />
        </TabsContent>
      </Tabs>
    </div>
  )
}


function ContentKpiCard({ icon: Icon, label, value, exactValue, evidence, status, tone, statusTone }: { icon: typeof FileText; label: string; value: string; exactValue: string; evidence: string; status: string; tone: string; statusTone: string }) {
  return <article className="flex min-h-[148px] flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-2.5"><span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${tone}`}><Icon aria-hidden="true" className="h-4 w-4" /></span><span className="truncate text-xs font-medium text-slate-600">{label}</span></div><Badge variant="outline" className={`shrink-0 px-2 py-0.5 text-[9px] font-medium ${statusTone}`}>{status}</Badge></div><div className="mt-3 text-2xl font-semibold tracking-tight text-slate-950" title={exactValue}>{value}</div><p className="mt-2 line-clamp-2 text-[11px] leading-5 text-slate-500" title={evidence}>{evidence || '—'}</p></article>
}


function CoverAnalysisPanel({ data, accountId, resultId }: { data?: AICoverAnalysis; accountId: number; resultId: number | null }) {
  const { t } = useTranslation('config')
  if (!data || data.status === 'not_configured') return <Notice text={t('titleStrategy.coverNotConfigured')} />
  if (data.status === 'no_covers' || !data.sample_count) return <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><SectionTitle icon={Image} title={t('titleStrategy.coverTitle')} description={t('titleStrategy.coverDescription')} /><div className="mt-5"><EmptyLine text={t('titleStrategy.coverNoSamples')} /></div></article>

  const stats = data.statistics
  const hasScores = typeof stats.average_cover_score === 'number' && Boolean(data.prompt_version?.includes('performance'))
  const preferredDimensions = ['theme_type', 'text_density', 'text_hook', 'composition', 'visual_style', 'color_tone']
  const previousScoreDimensions = ['cover_type', 'text_density', 'composition', 'visual_style', 'color_tone']
  const legacyDimensions = ['subject_type', 'text_density', 'composition', 'visual_style', 'color_tone']
  const hasSixDimensions = preferredDimensions.every((key) => stats.dimensions.some((row) => row.dimension === key))
  const dimensionOrder = hasSixDimensions ? preferredDimensions : hasScores ? previousScoreDimensions : legacyDimensions
  const groups = dimensionOrder.map((key) => ({
    key,
    rows: stats.dimensions.filter((row) => row.dimension === key),
  })).filter((group) => group.rows.length)

  return (
    <div className="space-y-4">
      {!hasScores ? <Notice text={t('titleStrategy.coverLegacyNotice')} /> : !hasSixDimensions ? <Notice text={t('titleStrategy.coverDimensionLegacyNotice')} /> : null}
      {hasScores ? <CandidateCoverEvaluator accountId={accountId} resultId={resultId} referenceCount={data.sample_count} /> : null}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label={t('titleStrategy.coverOverview')}>
        <MiniSummary label={t('titleStrategy.coverTotal')} value={String(data.requested_sample_count)} hint={t('titleStrategy.coverScopeAll')} />
        <MiniSummary label={t('titleStrategy.coverValid')} value={String(data.valid_cover_count ?? Math.max(0, data.requested_sample_count - data.missing_cover_count))} hint={t('titleStrategy.coverValidHint')} />
        <MiniSummary label={t('titleStrategy.coverAnalyzed')} value={String(data.sample_count)} hint={data.status === 'partial' ? t('titleStrategy.coverPartial') : t('titleStrategy.coverCached')} />
        <MiniSummary label={t('titleStrategy.coverFailed')} value={String(data.failed_count || 0)} hint={data.model || '-'} />
      </section>

      {hasScores ? <>
        <section className="grid gap-3 lg:grid-cols-3" aria-label={t('titleStrategy.coverScoreOverview')}>
          <ScoreCard icon={Palette} label={t('titleStrategy.visualScore')} value={stats.average_visual_score} description={t('titleStrategy.visualScoreHint')} tone="blue" />
          <ScoreCard icon={TrendingUp} label={t('titleStrategy.dataScore')} value={stats.average_data_score} description={t('titleStrategy.dataScoreHint')} tone="emerald" />
          <ScoreCard icon={CircleGauge} label={t('titleStrategy.coverPerformanceScore')} value={stats.average_cover_score} description={stats.score_formula || t('titleStrategy.coverScoreFormula')} tone="violet" />
        </section>

        <CoverScoreDistribution rows={stats.score_distribution || []} records={data.score_records || []} />
      </> : null}

      <CoverFactorAnalysis groups={groups} statistics={stats} records={data.score_records || []} hasScores={hasScores} />
    </div>
  )
}


const CANDIDATE_COVER_MAX_BYTES = 8 * 1024 * 1024
const CANDIDATE_COVER_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])


function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('Failed to read image'))
    reader.readAsDataURL(file)
  })
}


function CandidateCoverEvaluator({ accountId, resultId, referenceCount }: { accountId: number; resultId: number | null; referenceCount: number }) {
  const { t } = useTranslation('config')
  const [open, setOpen] = useState(false)

  return (
    <>
      <article className="overflow-hidden rounded-xl border border-violet-200 bg-gradient-to-r from-violet-50 via-white to-blue-50 shadow-sm">
        <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-violet-600 text-white shadow-sm shadow-violet-200"><UploadCloud aria-hidden="true" className="h-5 w-5" /></span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-slate-950">{t('titleStrategy.coverCandidateTitle')}</h2>
              <p className="mt-1 text-xs leading-5 text-slate-600">{t('titleStrategy.coverCandidateDescription', { count: referenceCount })}</p>
            </div>
          </div>
          <Button type="button" onClick={() => setOpen(true)} className="min-h-11 shrink-0 cursor-pointer bg-violet-600 text-white hover:bg-violet-700 focus-visible:ring-violet-600"><UploadCloud aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.coverCandidateAction')}</Button>
        </div>
      </article>
      <CandidateCoverDialog open={open} onOpenChange={setOpen} accountId={accountId} resultId={resultId} />
    </>
  )
}


function CandidateCoverDialog({ open, onOpenChange, accountId, resultId }: { open: boolean; onOpenChange: (open: boolean) => void; accountId: number; resultId: number | null }) {
  const { t } = useTranslation('config')
  const inputRef = useRef<HTMLInputElement>(null)
  const requestTokenRef = useRef(0)
  const [fileName, setFileName] = useState('')
  const [imageData, setImageData] = useState('')
  const [result, setResult] = useState<AICoverCandidateResult | null>(null)
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: ({ dataUrl }: { dataUrl: string; token: number }) => monitorApi.analyzeCoverCandidate({
      account_id: accountId,
      ...(typeof resultId === 'number' ? { reference_result_id: resultId } : {}),
      image_data_url: dataUrl,
    }),
    onSuccess: (response, variables) => {
      if (variables.token !== requestTokenRef.current) return
      setResult(response.data)
      setError('')
    },
    onError: (cause, variables) => {
      if (variables.token !== requestTokenRef.current) return
      setError(analysisErrorMessage(cause) || t('titleStrategy.coverCandidateFailed'))
    },
  })

  const reset = () => {
    requestTokenRef.current += 1
    setFileName('')
    setImageData('')
    setResult(null)
    setError('')
    mutation.reset()
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen)
    if (!nextOpen) reset()
  }

  const selectFile = async (file?: File) => {
    if (!file) return
    if (!CANDIDATE_COVER_TYPES.has(file.type)) {
      setError(t('titleStrategy.coverCandidateTypeError'))
      return
    }
    if (file.size > CANDIDATE_COVER_MAX_BYTES) {
      setError(t('titleStrategy.coverCandidateSizeError'))
      return
    }
    try {
      const dataUrl = await readFileAsDataUrl(file)
      setFileName(file.name)
      setImageData(dataUrl)
      requestTokenRef.current += 1
      setResult(null)
      setError('')
      mutation.reset()
    } catch {
      setError(t('titleStrategy.coverCandidateReadError'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="flex max-h-[92vh] w-[min(1040px,calc(100vw-24px))] max-w-5xl flex-col gap-0 overflow-hidden border-slate-200 bg-slate-50 p-0">
        <DialogHeader className="border-b border-slate-200 bg-white px-5 py-4 sm:px-6">
          <DialogTitle className="flex items-center gap-2 text-base text-slate-950"><UploadCloud aria-hidden="true" className="h-5 w-5 text-violet-600" />{t('titleStrategy.coverCandidateDialogTitle')}</DialogTitle>
          <DialogDescription className="text-xs leading-5 text-slate-500">{t('titleStrategy.coverCandidateDialogDescription')}</DialogDescription>
        </DialogHeader>

        <div className="min-h-0 overflow-y-auto p-4 sm:p-6">
          <div className="grid gap-4 lg:grid-cols-[minmax(260px,0.78fr)_minmax(0,1.22fr)]">
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(event) => void selectFile(event.target.files?.[0])} />
              <button type="button" onClick={() => inputRef.current?.click()} className="group grid min-h-64 w-full cursor-pointer place-items-center overflow-hidden rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 transition-colors hover:border-violet-300 hover:bg-violet-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-600 focus-visible:ring-offset-2">
                {imageData ? <img src={imageData} alt={t('titleStrategy.coverCandidatePreviewAlt')} className="aspect-video h-full w-full object-contain" /> : <span className="px-6 text-center"><UploadCloud aria-hidden="true" className="mx-auto h-9 w-9 text-slate-300 transition-colors group-hover:text-violet-500" /><span className="mt-3 block text-sm font-semibold text-slate-700">{t('titleStrategy.coverCandidateSelect')}</span><span className="mt-1 block text-xs leading-5 text-slate-400">{t('titleStrategy.coverCandidateFileHint')}</span></span>}
              </button>
              {fileName ? <div className="mt-3 truncate text-center text-xs text-slate-500" title={fileName}>{fileName}</div> : null}
              {error ? <div role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">{error}</div> : null}
              <Button type="button" disabled={!imageData || mutation.isPending} onClick={() => { const token = requestTokenRef.current + 1; requestTokenRef.current = token; mutation.mutate({ dataUrl: imageData, token }) }} className="mt-4 min-h-11 w-full cursor-pointer bg-violet-600 text-white hover:bg-violet-700 focus-visible:ring-violet-600">{mutation.isPending ? <RefreshCw aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" /> : <Sparkles aria-hidden="true" className="h-4 w-4" />}{mutation.isPending ? t('titleStrategy.coverCandidateAnalyzing') : result ? t('titleStrategy.coverCandidateReanalyze') : t('titleStrategy.coverCandidateAnalyze')}</Button>
              <p className="mt-3 text-[11px] leading-5 text-slate-400">{t('titleStrategy.coverCandidatePrivacy')}</p>
            </section>

            <section aria-live="polite">
              {mutation.isPending ? <CandidateCoverLoading /> : result ? <CandidateCoverResultView result={result} /> : <div className="grid min-h-64 place-items-center rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center"><div><CircleGauge aria-hidden="true" className="mx-auto h-10 w-10 text-slate-200" /><h3 className="mt-4 text-sm font-semibold text-slate-700">{t('titleStrategy.coverCandidateEmptyTitle')}</h3><p className="mx-auto mt-2 max-w-md text-xs leading-6 text-slate-400">{t('titleStrategy.coverCandidateEmptyDescription')}</p></div></div>}
            </section>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}


function CandidateCoverLoading() {
  const { t } = useTranslation('config')
  return <div className="grid min-h-64 place-items-center rounded-xl border border-violet-100 bg-white p-8 text-center shadow-sm"><div><RefreshCw aria-hidden="true" className="mx-auto h-9 w-9 animate-spin text-violet-600 motion-reduce:animate-none" /><h3 className="mt-4 text-sm font-semibold text-slate-800">{t('titleStrategy.coverCandidateAnalyzing')}</h3><p className="mt-2 text-xs leading-5 text-slate-400">{t('titleStrategy.coverCandidateAnalyzingHint')}</p></div></div>
}


function CandidateCoverResultView({ result }: { result: AICoverCandidateResult }) {
  const { t } = useTranslation('config')
  const decisionTone = result.decision === 'recommended'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
    : result.decision === 'usable'
      ? 'border-blue-200 bg-blue-50 text-blue-800'
      : result.decision === 'adjust'
        ? 'border-amber-200 bg-amber-50 text-amber-800'
        : 'border-slate-200 bg-slate-50 text-slate-700'
  return (
    <div className="space-y-3">
      <article className={`rounded-xl border p-4 ${decisionTone}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><div className="text-xs font-medium opacity-75">{t('titleStrategy.coverCandidateDecisionLabel')}</div><div className="mt-1 text-xl font-semibold">{t(`titleStrategy.coverCandidateDecision.${result.decision}`)}</div></div>
          <div className="text-right"><div className="font-mono text-3xl font-semibold">{formatScore(result.feasibility_score)}</div><div className="text-[10px] opacity-70">{t('titleStrategy.coverCandidateReferenceScore')}</div></div>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] opacity-80"><span>{t('titleStrategy.coverCandidateConfidence')}：{t(`titleStrategy.coverCandidateConfidenceValue.${result.confidence}`)}</span><span>{t('titleStrategy.coverCandidateReferenceBasis', { total: result.reference_count, similar: result.similar_count })}</span></div>
      </article>

      <div className="grid gap-2 sm:grid-cols-3">
        <CandidateScoreTile label={t('titleStrategy.visualScore')} value={result.visual_quality_score} baseline={result.benchmark.average_visual_score} hint={t('titleStrategy.coverCandidateVisualPercentile', { value: formatScore(result.visual_percentile) })} tone="blue" />
        <CandidateScoreTile label={t('titleStrategy.coverCandidateEstimatedData')} value={result.estimated_data_score} baseline={result.benchmark.average_data_score} hint={t('titleStrategy.coverCandidateEstimateHint')} tone="emerald" />
        <CandidateScoreTile label={t('titleStrategy.coverCandidateReferenceScore')} value={result.feasibility_score} baseline={result.benchmark.average_cover_score} hint={t('titleStrategy.coverCandidateScoreHint')} tone="violet" />
      </div>

      <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-xs font-semibold text-slate-800">{t('titleStrategy.coverCandidateFactors')}</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {result.factor_evidence.map((row) => <div key={row.dimension} className="rounded-lg bg-slate-50 px-3 py-2"><div className="flex items-center justify-between gap-2"><span className="text-[11px] text-slate-500">{row.dimension_name}</span><span className="truncate text-xs font-semibold text-slate-800" title={row.label_names.join(' / ')}>{row.label_names.join(' / ')}</span></div><div className="mt-1 flex items-center justify-between gap-2 text-[10px]"><span className={row.delta_vs_overall == null ? 'text-slate-400' : row.delta_vs_overall >= 0 ? 'text-emerald-700' : 'text-rose-600'}>{row.delta_vs_overall == null ? t('titleStrategy.sampleInsufficient') : t('titleStrategy.coverCandidateFactorDelta', { value: `${row.delta_vs_overall >= 0 ? '+' : ''}${formatScore(row.delta_vs_overall)}` })}</span><span className="text-slate-400">n={row.sample_count}</span></div></div>)}
        </div>
      </article>

      <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-xs font-semibold text-slate-800">{t('titleStrategy.coverCandidateSuggestions')}</h3>
        <div className="mt-3 space-y-2">
          {result.suggestions.map((suggestion, index) => <div key={`${suggestion.type}-${suggestion.code || suggestion.dimension || index}`} className="flex items-start gap-2 rounded-lg bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-900"><CheckCircle2 aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-600" /><span>{suggestion.type === 'visual' ? t(`titleStrategy.coverCandidateSuggestion.${suggestion.code}`, { score: suggestion.score }) : suggestion.type === 'factor' ? t('titleStrategy.coverCandidateFactorSuggestion', { label: suggestion.label, delta: formatScore(Math.abs(Number(suggestion.delta || 0))), count: suggestion.sample_count }) : t('titleStrategy.coverCandidateSuggestion.keep')}</span></div>)}
        </div>
      </article>

      <p className="px-1 text-[10px] leading-5 text-slate-400">{t('titleStrategy.coverCandidateDisclaimer')}</p>
    </div>
  )
}


function CandidateScoreTile({ label, value, baseline, hint, tone }: { label: string; value: number; baseline: number; hint: string; tone: 'blue' | 'emerald' | 'violet' }) {
  const color = tone === 'blue' ? 'bg-blue-600 text-blue-700' : tone === 'emerald' ? 'bg-emerald-600 text-emerald-700' : 'bg-violet-600 text-violet-700'
  const [barColor, textColor] = color.split(' ')
  const delta = value - baseline
  return <article className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"><div className="flex items-center justify-between gap-2"><span className="text-[11px] font-medium text-slate-500">{label}</span><span className={`font-mono text-lg font-semibold ${textColor}`}>{formatScore(value)}</span></div><div className="relative mt-2 h-2 rounded-full bg-slate-100"><span className={`block h-full rounded-full ${barColor}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /><span aria-hidden="true" className="absolute -bottom-1 -top-1 w-px bg-slate-500" style={{ left: `calc(${Math.max(0, Math.min(100, baseline))}% - 0.5px)` }} /></div><div className="mt-2 flex items-center justify-between gap-2 text-[10px]"><span className={delta >= 0 ? 'text-emerald-700' : 'text-rose-600'}>{delta >= 0 ? '+' : ''}{formatScore(delta)}</span><span className="truncate text-slate-400" title={hint}>{hint}</span></div></article>
}


const COVER_RECORD_PAGE_SIZE = 12


function coverScoreMatchesBucket(score: number, label: string, index: number): boolean {
  if (label === '优秀') return score >= 80
  if (label === '良好') return score >= 65 && score < 80
  if (label === '一般') return score >= 50 && score < 65
  if (label === '偏弱') return score >= 0 && score < 50
  if (index === 0) return score >= 80
  if (index === 1) return score >= 65 && score < 80
  if (index === 2) return score >= 50 && score < 65
  return score >= 0 && score < 50
}


function formatCoverPublishTime(record: AICoverScoreRecord): string {
  if (Number(record.create_time) > 0) return new Date(Number(record.create_time) * 1000).toLocaleString()
  if (!record.publish_time) return '—'
  const parsed = new Date(record.publish_time)
  return Number.isNaN(parsed.getTime()) ? record.publish_time : parsed.toLocaleString()
}


function CoverRecordImage({ record }: { record: AICoverScoreRecord }) {
  const { t } = useTranslation('config')
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [record.cover_url])

  if (!record.cover_url || failed) {
    return <div className="grid aspect-video w-full place-items-center bg-slate-100 text-slate-400" aria-label={t('titleStrategy.coverNoImage')}><div className="text-center"><Image aria-hidden="true" className="mx-auto h-6 w-6" /><span className="mt-2 block text-[11px]">{t('titleStrategy.coverNoImage')}</span></div></div>
  }

  return (
    <img
      src={record.cover_url}
      alt={t('titleStrategy.coverWorkAlt', { title: record.title || record.aweme_id })}
      width={320}
      height={180}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="aspect-video h-full w-full object-cover"
    />
  )
}


function CoverScoreDistribution({ rows, records }: { rows: Array<{ label: string; count: number; ratio: number }>; records: AICoverScoreRecord[] }) {
  const { t } = useTranslation('config')
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const tones = [
    { fill: 'bg-emerald-600', hover: 'hover:border-emerald-300 hover:bg-emerald-50/40', focus: 'focus-visible:ring-emerald-600' },
    { fill: 'bg-blue-600', hover: 'hover:border-blue-300 hover:bg-blue-50/40', focus: 'focus-visible:ring-blue-600' },
    { fill: 'bg-amber-500', hover: 'hover:border-amber-300 hover:bg-amber-50/40', focus: 'focus-visible:ring-amber-600' },
    { fill: 'bg-slate-400', hover: 'hover:border-slate-300 hover:bg-slate-50', focus: 'focus-visible:ring-slate-500' },
  ]
  const selectedRow = selectedIndex === null ? null : rows[selectedIndex]
  const bucketRecords = selectedRow
    ? records
      .filter((record) => coverScoreMatchesBucket(Number(record.cover_performance_score || 0), selectedRow.label, selectedIndex || 0))
      .sort((left, right) => Number(right.cover_performance_score || 0) - Number(left.cover_performance_score || 0))
    : []
  const hasRecordDetails = records.length > 0

  const selectBucket = (index: number) => {
    if (!hasRecordDetails) return
    setSelectedIndex(index)
  }

  return (
    <>
      <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <SectionTitle icon={Layers3} title={t('titleStrategy.coverDistribution')} description={t('titleStrategy.coverDistributionHint')} />
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {rows.map((row, index) => {
            const tone = tones[index] || tones[tones.length - 1]
            return (
              <button
                key={`${row.label}-${index}`}
                type="button"
                disabled={!hasRecordDetails}
                onClick={() => selectBucket(index)}
                aria-label={`${row.label}，${row.count} ${t('titleStrategy.posts')}，${formatPercent(row.ratio)}，${t('titleStrategy.coverViewWorks')}`}
                className={`min-h-11 rounded-lg border border-slate-200 p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${hasRecordDetails ? `cursor-pointer ${tone.hover} ${tone.focus}` : 'cursor-not-allowed opacity-70'}`}
              >
                <div className="flex items-center justify-between gap-3 text-xs"><span className="font-semibold text-slate-800">{row.label}</span><span className="font-mono text-slate-500">{row.count} {t('titleStrategy.posts')}</span></div>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${tone.fill}`} style={{ width: `${Math.max(0, Math.min(100, row.ratio * 100))}%` }} /></div>
                <div className="mt-3 flex items-center justify-between gap-3"><span className="font-mono text-xs text-slate-600">{formatPercent(row.ratio)}</span><span className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-700">{t('titleStrategy.coverViewWorks')}<ChevronRight aria-hidden="true" className="h-3.5 w-3.5" /></span></div>
              </button>
            )
          })}
        </div>
        {!hasRecordDetails ? <div className="mt-4"><EmptyLine text={t('titleStrategy.coverNoRecords')} /></div> : null}
      </article>

      <CoverWorksDialog
        open={selectedIndex !== null}
        onOpenChange={(open) => { if (!open) setSelectedIndex(null) }}
        title={t('titleStrategy.coverWorksDialogTitle', { label: selectedRow?.label || '' })}
        description={t('titleStrategy.coverWorksDialogDescription', { count: bucketRecords.length })}
        records={bucketRecords}
      />
    </>
  )
}


function CoverWorksDialog({ open, onOpenChange, title, description, records }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description: string; records: AICoverScoreRecord[] }) {
  const { t } = useTranslation('config')
  const [page, setPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  useEffect(() => {
    setPage(1)
    setSearchQuery('')
  }, [open, title])

  const normalizedSearch = searchQuery.trim().toLocaleLowerCase()
  const filteredRecords = normalizedSearch
    ? records.filter((record) => (
      String(record.title || '').toLocaleLowerCase().includes(normalizedSearch)
      || String(record.aweme_id || '').toLocaleLowerCase().includes(normalizedSearch)
      || String(record.canonical_url || '').toLocaleLowerCase().includes(normalizedSearch)
    ))
    : records
  const totalPages = Math.max(1, Math.ceil(filteredRecords.length / COVER_RECORD_PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const visibleRecords = filteredRecords.slice((safePage - 1) * COVER_RECORD_PAGE_SIZE, safePage * COVER_RECORD_PAGE_SIZE)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88dvh] w-[calc(100vw-24px)] max-w-5xl grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden border-slate-200 bg-white p-0">
        <DialogHeader className="border-b border-slate-200 px-5 py-4 pr-14 sm:px-6 sm:py-5 sm:pr-16">
          <DialogTitle className="text-left text-lg text-slate-950">{title}</DialogTitle>
          <DialogDescription className="text-left text-xs leading-5 text-slate-500">{description}</DialogDescription>
          <div className="grid gap-2 pt-3 text-left sm:grid-cols-[72px_minmax(0,1fr)_auto] sm:items-center">
            <label htmlFor="cover-work-search" className="text-xs font-medium text-slate-700">{t('titleStrategy.coverSearchLabel')}</label>
            <div className="relative min-w-0">
              <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input id="cover-work-search" type="text" inputMode="search" role="searchbox" value={searchQuery} onChange={(event) => { setSearchQuery(event.target.value); setPage(1) }} placeholder={t('titleStrategy.coverSearchPlaceholder')} autoComplete="off" className="h-10 rounded-lg border-slate-200 bg-white pl-9 pr-10 text-sm text-slate-900 placeholder:text-slate-400 focus-visible:ring-blue-600" />
              {searchQuery ? <button type="button" onClick={() => { setSearchQuery(''); setPage(1) }} aria-label={t('titleStrategy.coverSearchClear')} className="absolute right-1 top-1/2 grid h-8 w-8 -translate-y-1/2 cursor-pointer place-items-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"><X aria-hidden="true" className="h-4 w-4" /></button> : null}
            </div>
            <span className="text-xs font-medium text-slate-500 sm:min-w-16 sm:text-right" aria-live="polite">{t('titleStrategy.coverSearchResult', { count: filteredRecords.length })}</span>
          </div>
        </DialogHeader>

        <div className="overflow-y-auto px-4 py-4 sm:px-6">
          {visibleRecords.length ? <div className="grid gap-3 lg:grid-cols-2">{visibleRecords.map((record) => (
            <article key={record.aweme_id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="grid min-w-0 sm:grid-cols-[180px_minmax(0,1fr)]">
                <div className="overflow-hidden bg-slate-100"><CoverRecordImage record={record} /></div>
                <div className="flex min-w-0 flex-col p-4">
                  <h3 className="line-clamp-2 text-sm font-semibold leading-6 text-slate-900" title={record.title || record.aweme_id}>{record.title || record.aweme_id || t('titleStrategy.coverUnknownWork')}</h3>
                  <div className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-500"><History aria-hidden="true" className="h-3.5 w-3.5 shrink-0" /><span>{t('titleStrategy.coverPublishedAt')}：{formatCoverPublishTime(record)}</span></div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                    <CoverRecordMetric label={t('titleStrategy.coverInteraction')} value={formatNumber(record.interaction)} />
                    <CoverRecordMetric label={t('titleStrategy.coverVisualShort')} value={formatScore(record.visual_quality_score)} />
                    <CoverRecordMetric label={t('titleStrategy.coverDataShort')} value={formatScore(record.data_performance_score)} />
                    <CoverRecordMetric label={t('titleStrategy.coverPerformanceShort')} value={formatScore(record.cover_performance_score)} emphasized />
                  </div>
                  <div className="mt-auto pt-3">
                    {record.canonical_url ? <Button asChild variant="outline" size="sm" className="min-h-10 w-full cursor-pointer border-blue-200 text-blue-700 hover:bg-blue-50 focus-visible:ring-blue-600"><a href={record.canonical_url} target="_blank" rel="noreferrer noopener">{t('titleStrategy.coverOpenWork')}<ExternalLink aria-hidden="true" className="h-3.5 w-3.5" /></a></Button> : <Button type="button" variant="outline" size="sm" disabled className="min-h-10 w-full">{t('titleStrategy.coverNoLink')}</Button>}
                  </div>
                </div>
              </div>
            </article>
          ))}</div> : <EmptyLine text={normalizedSearch ? t('titleStrategy.coverSearchEmpty') : t('titleStrategy.coverNoRecords')} />}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-4 py-3 sm:px-6">
          <span className="text-xs font-medium text-slate-500">{t('titleStrategy.coverPageInfo', { page: safePage, total: totalPages })}</span>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" disabled={safePage <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))} className="min-h-10 focus-visible:ring-blue-600"><ChevronLeft aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.coverPrevious')}</Button>
            <Button type="button" variant="outline" size="sm" disabled={safePage >= totalPages} onClick={() => setPage((current) => Math.min(totalPages, current + 1))} className="min-h-10 focus-visible:ring-blue-600">{t('titleStrategy.coverNext')}<ChevronRight aria-hidden="true" className="h-4 w-4" /></Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}


function CoverRecordMetric({ label, value, emphasized = false }: { label: string; value: string; emphasized?: boolean }) {
  return <div className={`rounded-lg px-2.5 py-2 ${emphasized ? 'bg-violet-50 text-violet-800' : 'bg-slate-50 text-slate-700'}`}><div className="font-mono text-sm font-semibold">{value}</div><div className={`mt-0.5 text-[10px] ${emphasized ? 'text-violet-600' : 'text-slate-400'}`}>{label}</div></div>
}


function ScoreCard({ icon: Icon, label, value, description, tone }: { icon: typeof Palette; label: string; value?: number; description: string; tone: 'blue' | 'emerald' | 'violet' }) {
  const color = tone === 'blue' ? 'bg-blue-600 text-blue-700 bg-blue-50' : tone === 'emerald' ? 'bg-emerald-600 text-emerald-700 bg-emerald-50' : 'bg-violet-600 text-violet-700 bg-violet-50'
  const [barColor, textColor, iconBg] = color.split(' ')
  const width = Math.max(0, Math.min(100, Number(value || 0)))
  return <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-4"><div><div className="text-xs font-medium text-slate-500">{label}</div><div className="mt-1 text-3xl font-semibold tracking-tight text-slate-950">{formatScore(value)}<span className="ml-1 text-xs font-normal text-slate-400">/ 100</span></div></div><span className={`grid h-9 w-9 place-items-center rounded-lg ${iconBg} ${textColor}`}><Icon aria-hidden="true" className="h-4 w-4" /></span></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${label} ${formatScore(value)} 分`}><div className={`h-full rounded-full ${barColor}`} style={{ width: `${width}%` }} /></div><p className="mt-3 text-[11px] leading-5 text-slate-500">{description}</p></article>
}


type CoverFactorMetric = 'data' | 'visual' | 'performance'


function coverFactorValue(row: AICoverDimensionStat, metric: CoverFactorMetric): number {
  if (metric === 'visual') return Number(row.avg_visual_score || 0)
  if (metric === 'performance') return Number(row.avg_cover_score || 0)
  return Number(row.avg_data_score || 0)
}


function coverRecordFactorValue(record: AICoverScoreRecord, metric: CoverFactorMetric): number {
  if (metric === 'visual') return Number(record.visual_quality_score || 0)
  if (metric === 'performance') return Number(record.cover_performance_score || 0)
  return Number(record.data_performance_score || 0)
}


function coverFactorSampleStatus(row: AICoverDimensionStat): 'insufficient' | 'reference' | 'stable' {
  if (row.sample_status) return row.sample_status
  if (row.count < 10) return 'insufficient'
  if (row.count < 30) return 'reference'
  return 'stable'
}


function recordMatchesDimension(record: AICoverScoreRecord, row: AICoverDimensionStat): boolean {
  const value = record.labels?.[row.dimension]
  return Array.isArray(value)
    ? value.map((item) => String(item)).includes(row.label)
    : String(value ?? '') === row.label
}


function CoverFactorAnalysis({ groups, statistics, records, hasScores }: { groups: Array<{ key: string; rows: AICoverDimensionStat[] }>; statistics: AICoverAnalysis['statistics']; records: AICoverScoreRecord[]; hasScores: boolean }) {
  const { t } = useTranslation('config')
  const [metric, setMetric] = useState<CoverFactorMetric>('data')
  const [selectedRow, setSelectedRow] = useState<AICoverDimensionStat | null>(null)
  if (!hasScores) return <section className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3" aria-label={t('titleStrategy.coverTagDistribution')}>{groups.map((group) => <LegacyDimensionCard key={group.key} rows={group.rows.slice(0, 5)} />)}</section>

  const metricLabel = metric === 'visual' ? t('titleStrategy.visualScore') : metric === 'performance' ? t('titleStrategy.coverPerformanceScore') : t('titleStrategy.dataScore')
  const baseline = metric === 'visual'
    ? Number(statistics.average_visual_score || 0)
    : metric === 'performance'
      ? Number(statistics.average_cover_score || 0)
      : Number(statistics.average_data_score || 0)
  const metricSwatchClass = metric === 'visual' ? 'bg-blue-600' : metric === 'performance' ? 'bg-violet-600' : 'bg-emerald-600'
  const selectedRecords = selectedRow
    ? records
      .filter((record) => recordMatchesDimension(record, selectedRow))
      .sort((left, right) => coverRecordFactorValue(right, metric) - coverRecordFactorValue(left, metric))
    : []

  return (
    <>
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-label={t('titleStrategy.coverTagDistribution')}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <SectionTitle icon={Layers3} title={t('titleStrategy.coverFactorTitle')} description={t('titleStrategy.coverFactorDescription')} />
          <div className="inline-grid grid-cols-3 rounded-lg border border-slate-200 bg-slate-50 p-1" role="group" aria-label={t('titleStrategy.coverFactorMetricLabel')}>
            {(['data', 'visual', 'performance'] as CoverFactorMetric[]).map((item) => {
              const label = item === 'data' ? t('titleStrategy.coverFactorMetricData') : item === 'visual' ? t('titleStrategy.coverFactorMetricVisual') : t('titleStrategy.coverFactorMetricPerformance')
              return <button key={item} type="button" aria-pressed={metric === item} onClick={() => setMetric(item)} className={`min-h-10 cursor-pointer rounded-md px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${metric === item ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}>{label}</button>
            })}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600">
          <span className="inline-flex items-center gap-2"><span aria-hidden="true" className={`h-2.5 w-2.5 rounded-sm ${metricSwatchClass}`} />{metricLabel}</span>
          <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="h-4 w-0.5 bg-slate-700" />{t('titleStrategy.coverFactorBaseline', { value: formatScore(baseline) })}</span>
          <span>{t('titleStrategy.coverFactorSampleLegend')}</span>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {groups.map((group) => <DimensionCard key={group.key} rows={group.rows} metric={metric} baseline={baseline} canViewWorks={records.length > 0} onSelect={setSelectedRow} />)}
        </div>

        <div className="mt-4 rounded-lg bg-blue-50 px-4 py-3 text-[11px] leading-5 text-blue-800">{t('titleStrategy.coverFactorCaveat')}</div>
      </section>

      <CoverWorksDialog
        open={selectedRow !== null}
        onOpenChange={(open) => { if (!open) setSelectedRow(null) }}
        title={t('titleStrategy.coverFactorWorksTitle', { dimension: selectedRow?.dimension_name || '', label: selectedRow?.label_name || '' })}
        description={t('titleStrategy.coverFactorWorksDescription', { count: selectedRecords.length, metric: metricLabel })}
        records={selectedRecords}
      />
    </>
  )
}


function DimensionCard({ rows, metric, baseline, canViewWorks, onSelect }: { rows: AICoverDimensionStat[]; metric: CoverFactorMetric; baseline: number; canViewWorks: boolean; onSelect: (row: AICoverDimensionStat) => void }) {
  const { t } = useTranslation('config')
  const [currentPage, setCurrentPage] = useState(1)
  const scrollRef = useRef<HTMLDivElement>(null)
  const sortedRows = [...rows].sort((left, right) => {
    const leftInsufficient = coverFactorSampleStatus(left) === 'insufficient' ? 1 : 0
    const rightInsufficient = coverFactorSampleStatus(right) === 'insufficient' ? 1 : 0
    return leftInsufficient - rightInsufficient || coverFactorValue(right, metric) - coverFactorValue(left, metric) || right.count - left.count
  })
  const leader = sortedRows.find((row) => coverFactorSampleStatus(row) === 'stable')
  const pages = Array.from({ length: Math.max(1, Math.ceil(sortedRows.length / 5)) }, (_, index) => sortedRows.slice(index * 5, index * 5 + 5))
  const fillClass = metric === 'visual' ? 'bg-blue-600' : metric === 'performance' ? 'bg-violet-600' : 'bg-emerald-600'
  const accentTextClass = metric === 'visual' ? 'text-blue-700' : metric === 'performance' ? 'text-violet-700' : 'text-emerald-700'

  const scrollToPage = (page: number) => {
    const element = scrollRef.current
    if (!element) return
    const targetPage = Math.min(pages.length, Math.max(1, page))
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    element.scrollTo({ top: (targetPage - 1) * element.clientHeight, behavior: reduceMotion ? 'auto' : 'smooth' })
  }

  useEffect(() => {
    setCurrentPage(1)
    scrollRef.current?.scrollTo({ top: 0, behavior: 'auto' })
  }, [metric])

  const renderRow = (row: AICoverDimensionStat) => {
    const status = coverFactorSampleStatus(row)
    const insufficient = status === 'insufficient'
    const score = coverFactorValue(row, metric)
    const delta = score - baseline
    const deltaText = Math.abs(delta) < 0.05
      ? t('titleStrategy.coverFactorNearBaseline')
      : delta > 0
        ? t('titleStrategy.coverFactorAbove', { value: formatScore(Math.abs(delta)) })
        : t('titleStrategy.coverFactorBelow', { value: formatScore(Math.abs(delta)) })
    return (
      <button
        key={`${row.dimension}-${row.label}`}
        type="button"
        disabled={!canViewWorks}
        onClick={() => onSelect(row)}
        aria-label={`${row.label_name}，${row.count} ${t('titleStrategy.posts')}，${insufficient ? t('titleStrategy.sampleInsufficient') : `${formatScore(score)} ${t('titleStrategy.points')}`}，${t('titleStrategy.coverViewWorks')}`}
        className={`min-h-[60px] w-full snap-start rounded-lg px-2 py-1.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${canViewWorks ? 'cursor-pointer hover:bg-slate-50' : 'cursor-not-allowed'}`}
      >
        <div className="flex items-center justify-between gap-3 text-[11px]">
          <span className="flex min-w-0 items-center gap-1.5"><span className="truncate font-medium text-slate-700" title={row.label_name}>{row.label_name}</span>{status === 'reference' ? <Badge variant="outline" className="shrink-0 border-amber-200 bg-amber-50 px-1.5 py-0 text-[9px] text-amber-700">{t('titleStrategy.sampleReference')}</Badge> : status === 'insufficient' ? <Badge variant="outline" className="shrink-0 border-slate-200 bg-slate-50 px-1.5 py-0 text-[9px] text-slate-500">{t('titleStrategy.sampleInsufficient')}</Badge> : null}</span>
          <span className="shrink-0 font-mono font-semibold text-slate-700">{insufficient ? '—' : `${formatScore(score)} ${t('titleStrategy.points')}`}</span>
        </div>
        <div className={`relative mt-1.5 h-2 rounded-full ${insufficient ? 'border border-dashed border-slate-300 bg-white' : 'bg-slate-100'}`} role="img" aria-label={insufficient ? t('titleStrategy.coverFactorHiddenScore') : `${row.label_name}，${formatScore(score)} ${t('titleStrategy.points')}，${t('titleStrategy.coverFactorBaseline', { value: formatScore(baseline) })}`}>
          {!insufficient ? <><span className={`block h-full rounded-full transition-[width] duration-300 motion-reduce:transition-none ${status === 'reference' ? 'bg-amber-500' : fillClass}`} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} /><span aria-hidden="true" className="absolute -bottom-1 -top-1 w-0.5 bg-slate-700" style={{ left: `calc(${Math.max(0, Math.min(100, baseline))}% - 1px)` }} /></> : null}
        </div>
        <div className="mt-1 flex items-center justify-between gap-3 text-[10px]"><span className={insufficient ? 'text-slate-400' : delta >= 0 ? 'text-emerald-700' : 'text-rose-600'}>{insufficient ? t('titleStrategy.coverFactorHiddenScore') : deltaText}</span><span className="inline-flex shrink-0 items-center gap-1 text-slate-500">{row.count} {t('titleStrategy.posts')} · {t('titleStrategy.coverFactorCoverage')} {formatPercent(row.ratio)}<ChevronRight aria-hidden="true" className="h-3 w-3" /></span></div>
      </button>
    )
  }

  return (
    <article className="flex h-[430px] min-w-0 flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex min-h-8 shrink-0 items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-900">{rows[0].dimension_name}</h3>
        {leader ? <Badge variant="outline" className="max-w-[62%] border-emerald-200 bg-emerald-50 text-[10px] text-emerald-700"><span className="truncate">{t('titleStrategy.coverFactorLeader', { label: leader.label_name })}</span></Badge> : null}
      </div>
      <div className="group relative mt-3 min-h-0 flex-1">
        <div
          ref={scrollRef}
          tabIndex={pages.length > 1 ? 0 : undefined}
          aria-label={pages.length > 1 ? t('titleStrategy.coverFactorScrollRegion', { count: sortedRows.length }) : undefined}
          onKeyDown={(event) => {
            if (event.key !== 'PageDown' && event.key !== 'PageUp') return
            event.preventDefault()
            scrollToPage(currentPage + (event.key === 'PageDown' ? 1 : -1))
          }}
          onScroll={(event) => {
            const element = event.currentTarget
            if (!element.clientHeight) return
            setCurrentPage(Math.min(pages.length, Math.max(1, Math.round(element.scrollTop / element.clientHeight) + 1)))
          }}
          className="h-full snap-y snap-proximity touch-pan-y overflow-y-auto overscroll-contain pr-1 scroll-smooth motion-reduce:scroll-auto focus-visible:rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
        >
          {pages.map((pageRows, pageIndex) => <div key={pageIndex} className="min-h-full snap-start space-y-1">{pageRows.map(renderRow)}</div>)}
        </div>
        {currentPage < pages.length ? <div aria-hidden="true" className="pointer-events-none absolute inset-x-1 bottom-0 h-8 bg-gradient-to-t from-white via-white/90 to-transparent transition-opacity duration-200 group-focus-within:opacity-0 motion-reduce:transition-none" /> : null}
      </div>
      <div className="mt-1 flex h-8 shrink-0 items-center justify-center gap-1 text-[10px] text-slate-400" aria-live="polite">
        {pages.length > 1 ? <>
          <div className="flex items-center" role="group" aria-label={t('titleStrategy.coverFactorPagination')}>
            {pages.map((_, index) => {
              const page = index + 1
              const active = currentPage === page
              return <button key={page} type="button" aria-current={active ? 'page' : undefined} aria-label={t('titleStrategy.coverFactorPageSelect', { page })} onClick={() => scrollToPage(page)} className="grid h-8 w-8 cursor-pointer place-items-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"><span aria-hidden="true" className={`block rounded-full transition-all motion-reduce:transition-none ${active ? `h-2.5 w-2.5 ${fillClass}` : 'h-1.5 w-1.5 bg-slate-300'}`} /></button>
            })}
          </div>
          <span className={`font-mono font-semibold ${accentTextClass}`}>{t('titleStrategy.coverFactorScrollPage', { page: currentPage, total: pages.length })}</span>
        </> : null}
      </div>
    </article>
  )
}


function LegacyDimensionCard({ rows }: { rows: AICoverDimensionStat[] }) {
  const { t } = useTranslation('config')
  const maxInteraction = Math.max(1, ...rows.map((row) => Number(row.avg_interaction || 0)))
  return <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold text-slate-900">{rows[0].dimension_name}</h3><span className="text-[10px] text-slate-400">{t('titleStrategy.byInteraction')}</span></div><div className="mt-4 space-y-3">{rows.map((row) => <div key={`${row.dimension}-${row.label}`}><div className="mb-1.5 flex items-center justify-between gap-3 text-[11px]"><span className="truncate font-medium text-slate-700">{row.label_name}</span><span className="shrink-0 font-mono text-slate-500">{row.count} {t('titleStrategy.posts')} · {formatNumber(row.avg_interaction)}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-slate-400" style={{ width: `${Math.max(4, Number(row.avg_interaction || 0) / maxInteraction * 100)}%` }} /></div></div>)}</div></article>
}


function MiniSummary({ label, value, hint }: { label: string; value: string; hint: string }) {
  return <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs font-medium text-slate-500">{label}</div><div className="mt-1 truncate text-xl font-semibold text-slate-950" title={value}>{value}</div><div className="mt-1 text-[11px] leading-5 text-slate-400">{hint}</div></article>
}


type KeywordPerformanceSort = 'lift' | 'coverage' | 'count'


function KeywordPerformanceChart({ rows }: { rows: AITitleStrategyKeyword[] }) {
  const { t } = useTranslation('config')
  const [sortBy, setSortBy] = useState<KeywordPerformanceSort>('lift')
  const [currentPage, setCurrentPage] = useState(1)
  if (!rows.length) return <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><SectionTitle icon={KeyRound} title={t('titleStrategy.keywordTitle')} description={t('titleStrategy.keywordDescription')} /><div className="mt-5"><EmptyLine text={t('titleStrategy.noKeyword')} /></div></article>
  const sortedRows = [...rows].sort((left, right) => {
    if (sortBy === 'coverage') return Number(right.ratio || 0) - Number(left.ratio || 0) || right.count - left.count
    if (sortBy === 'count') return right.count - left.count || Number(right.ratio || 0) - Number(left.ratio || 0)
    return Number(right.ex_top1_lift_percent ?? -Infinity) - Number(left.ex_top1_lift_percent ?? -Infinity) || right.count - left.count
  })
  const pages = Array.from({ length: Math.ceil(sortedRows.length / 5) }, (_, index) => sortedRows.slice(index * 5, index * 5 + 5))
  const maxRatio = Math.max(...rows.map((row) => Number(row.ratio) || 0), 0.01)
  const maxAbsLift = Math.max(...rows.map((row) => Math.abs(Number(row.ex_top1_lift_percent) || 0)), 10)
  const statusStyle = (status?: AITitleStrategyKeyword['status']) => {
    if (status === 'strong') return 'border-emerald-200 bg-emerald-50 text-emerald-700'
    if (status === 'slight') return 'border-blue-200 bg-blue-50 text-blue-700'
    if (status === 'drag') return 'border-rose-200 bg-rose-50 text-rose-700'
    if (status === 'no_hit') return 'border-amber-200 bg-amber-50 text-amber-700'
    return 'border-slate-200 bg-slate-50 text-slate-600'
  }
  return (
    <article className="flex h-[470px] flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex shrink-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <SectionTitle icon={KeyRound} title={t('titleStrategy.keywordTitle')} description={t('titleStrategy.keywordVisualDescription')} />
        <label htmlFor="keyword-performance-sort" className="flex min-h-11 shrink-0 items-center gap-2 text-xs font-medium text-slate-600"><span>{t('titleStrategy.lengthSortLabel')}</span><select id="keyword-performance-sort" value={sortBy} onChange={(event) => { setSortBy(event.target.value as KeywordPerformanceSort); setCurrentPage(1) }} className="min-h-11 cursor-pointer rounded-lg border border-slate-200 bg-white px-3 pr-8 text-xs font-medium text-slate-700 shadow-sm outline-none transition-colors hover:border-slate-300 focus-visible:border-blue-600 focus-visible:ring-2 focus-visible:ring-blue-600/20"><option value="lift">{t('titleStrategy.keywordSortLift')}</option><option value="coverage">{t('titleStrategy.keywordSortCoverage')}</option><option value="count">{t('titleStrategy.keywordSortCount')}</option></select></label>
      </div>
      <div className="mt-3 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-slate-500" aria-label={t('titleStrategy.chartLegend')}><span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-blue-600" />{t('titleStrategy.coverage')}</span><span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-emerald-500" />{t('titleStrategy.keywordPositive')}</span><span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-rose-500" />{t('titleStrategy.keywordNegative')}</span><span>{t('titleStrategy.keywordBaselineHint')}</span></div>
      <div className="mt-3 min-h-0 flex-1 snap-y snap-mandatory overflow-y-auto overscroll-contain pr-1 scroll-smooth motion-reduce:scroll-auto" tabIndex={pages.length > 1 ? 0 : undefined} aria-label={t('titleStrategy.keywordScrollRegion', { count: rows.length })} onScroll={(event) => { const element = event.currentTarget; if (element.clientHeight) setCurrentPage(Math.min(pages.length, Math.max(1, Math.round(element.scrollTop / element.clientHeight) + 1))) }}>
        {pages.map((pageRows, pageIndex) => <div key={pageIndex} className="min-h-full snap-start divide-y divide-slate-100">{pageRows.map((row, rowIndex) => {
          const status = row.status || (row.count < 10 ? 'insufficient' : 'neutral')
          const lift = row.ex_top1_lift_percent
          return <div key={row.keyword} className="grid min-h-[66px] gap-3 py-2 md:grid-cols-[minmax(170px,0.68fr)_minmax(300px,1.25fr)_minmax(230px,0.9fr)] md:items-center">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-100 font-mono text-[11px] font-semibold text-slate-500">{pageIndex * 5 + rowIndex + 1}</span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><span className="truncate text-sm font-semibold text-slate-900">{row.keyword}</span><Badge variant="outline" className={statusStyle(status)}>{t(`titleStrategy.keywordStatus.${status}`)}</Badge></div>
                  <div className="mt-1 text-[11px] text-slate-500">{row.count} {t('titleStrategy.posts')} · {t('titleStrategy.medianShort')} {formatNumber(row.median_interaction ?? row.avg_interaction)}</div>
                </div>
              </div>
              <div className="space-y-2" role="group" aria-label={`${row.keyword}${t('titleStrategy.keywordDualTrack')}`}>
                <MetricBar label={t('titleStrategy.coverage')} value={formatPercent(row.ratio)} width={row.ratio / maxRatio * 100} color="bg-blue-600" />
                <DivergingMetricBar label={t('titleStrategy.keywordExTop1')} value={lift} maxAbs={maxAbsLift} />
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px]"><div className="rounded-lg bg-slate-50 px-2.5 py-2"><div className="text-slate-400">{t('titleStrategy.keywordExTop1')}</div><div className={`mt-0.5 font-mono font-semibold ${Number(lift || 0) > 0 ? 'text-emerald-700' : Number(lift || 0) < 0 ? 'text-rose-700' : 'text-slate-700'}`}>{lift == null ? '—' : `${lift > 0 ? '+' : ''}${lift.toFixed(1)}%`}</div></div><div className="rounded-lg bg-slate-50 px-2.5 py-2"><div className="text-slate-400">{t('titleStrategy.keywordHitDiff')}</div><div className="mt-0.5 font-mono font-semibold text-slate-700">{row.count < 10 ? t('titleStrategy.sampleInsufficient') : row.hit_rate_diff_pp == null ? '—' : `${Number(row.hit_rate_diff_pp) > 0 ? '+' : ''}${Number(row.hit_rate_diff_pp).toFixed(1)} pp`}</div></div></div>
            </div>
        })}</div>)}
      </div>
      <div className="mt-2 h-5 shrink-0 text-center text-[10px] text-slate-400" aria-live="polite">{pages.length > 1 ? t('titleStrategy.keywordPageInfo', { page: currentPage, total: pages.length }) : t('titleStrategy.keywordCompareBasis')}</div>
    </article>
  )
}


function DivergingMetricBar({ label, value, maxAbs }: { label: string; value?: number | null; maxAbs: number }) {
  const numeric = Number(value || 0)
  const width = Math.min(50, Math.abs(numeric) / maxAbs * 50)
  return <div className="grid grid-cols-[64px_minmax(0,1fr)_52px] items-center gap-2 text-[10px]" role="img" aria-label={`${label} ${value == null ? '—' : `${numeric.toFixed(1)}%`}`}><span className="text-slate-400">{label}</span><span className="relative h-2 rounded-full bg-slate-100"><span aria-hidden="true" className="absolute inset-y-[-3px] left-1/2 w-px bg-slate-400" />{value != null && numeric !== 0 ? <span className={`absolute h-full rounded-full ${numeric > 0 ? 'bg-emerald-500' : 'bg-rose-500'}`} style={numeric > 0 ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }} /> : null}</span><span className={`text-right font-mono font-semibold ${numeric > 0 ? 'text-emerald-700' : numeric < 0 ? 'text-rose-700' : 'text-slate-600'}`}>{value == null ? '—' : `${numeric > 0 ? '+' : ''}${numeric.toFixed(1)}%`}</span></div>
}


function MetricBar({ label, value, width, marker, color }: { label: string; value: string; width: number; marker?: number; color: string }) {
  const safeWidth = width <= 0 ? 0 : Math.max(3, Math.min(100, width))
  const safeMarker = typeof marker === 'number' ? Math.max(0, Math.min(100, marker)) : null
  return <div className={`grid items-center gap-2 text-[10px] ${label ? 'grid-cols-[52px_minmax(0,1fr)_48px]' : 'grid-cols-[minmax(0,1fr)_48px]'}`} role="img" aria-label={`${label ? `${label} ` : ''}${value}`}>{label ? <span className="text-slate-400">{label}</span> : null}<span className="relative h-2 rounded-full bg-slate-100"><span className={`block h-full rounded-full transition-[width] duration-300 motion-reduce:transition-none ${color}`} style={{ width: `${safeWidth}%` }} />{safeMarker !== null ? <span aria-hidden="true" className="absolute -bottom-1 -top-1 w-px bg-slate-500" style={{ left: `calc(${safeMarker}% - 0.5px)` }} /> : null}</span><span className="text-right font-mono font-semibold text-slate-600">{value}</span></div>
}


type LengthPerformanceSort = 'natural' | 'count' | 'median' | 'hitRate'


function LengthPerformanceChart({ rows, overallMedian }: { rows: AITitleLengthGroup[]; overallMedian: number }) {
  const { t } = useTranslation('config')
  const [sortBy, setSortBy] = useState<LengthPerformanceSort>('natural')
  const maxValue = Math.max(1, overallMedian, ...rows.map((row) => row.median_interaction))
  const sortedRows = rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      if (sortBy === 'count') return right.row.count - left.row.count || left.index - right.index
      if (sortBy === 'median') return Number(right.row.median_interaction || 0) - Number(left.row.median_interaction || 0) || left.index - right.index
      if (sortBy === 'hitRate') return Number(right.row.hit_rate || 0) - Number(left.row.hit_rate || 0) || left.index - right.index
      return left.index - right.index
    })
    .map(({ row }) => row)

  const stableRows = rows.filter((row) => row.count >= 30)
  const best = [...(stableRows.length ? stableRows : rows.filter((row) => row.count >= 10))].sort((left, right) => right.median_interaction - left.median_interaction)[0]
  const summary = !best ? t('titleStrategy.sampleInsufficient') : rows.indexOf(best) <= 0 ? t('titleStrategy.lengthSummaryShort') : rows.indexOf(best) >= rows.length - 2 ? t('titleStrategy.lengthSummaryLong') : t('titleStrategy.lengthSummaryMiddle')
  return <div className="flex h-[430px] flex-col"><div className="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><SectionTitle icon={BarChart3} title={t('titleStrategy.lengthTitle')} description={t('titleStrategy.lengthVisualDescription')} /><div className="flex flex-wrap items-center gap-2"><div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-right"><div className="text-xs font-semibold text-blue-800">{summary}</div><div className="mt-0.5 text-[10px] text-blue-600">{best ? t('titleStrategy.lengthSummaryEvidence', { range: best.len_group, count: best.count, lift: `${Number(best.median_lift_percent || 0) > 0 ? '+' : ''}${Number(best.median_lift_percent || 0).toFixed(1)}%` }) : t('titleStrategy.sampleInsufficient')}</div></div><label htmlFor="title-length-sort" className="flex min-h-11 shrink-0 items-center gap-2 text-xs font-medium text-slate-600"><span>{t('titleStrategy.lengthSortLabel')}</span><select id="title-length-sort" value={sortBy} onChange={(event) => setSortBy(event.target.value as LengthPerformanceSort)} className="min-h-11 cursor-pointer rounded-lg border border-slate-200 bg-white px-3 pr-8 text-xs font-medium text-slate-700 shadow-sm outline-none transition-colors hover:border-slate-300 focus-visible:border-blue-600 focus-visible:ring-2 focus-visible:ring-blue-600/20"><option value="natural">{t('titleStrategy.lengthSortNatural')}</option><option value="count">{t('titleStrategy.lengthSortCount')}</option><option value="median">{t('titleStrategy.lengthSortMedian')}</option><option value="hitRate">{t('titleStrategy.lengthSortHitRate')}</option></select></label></div></div><div className="mt-4 min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain pr-1">{sortedRows.map((row) => { const sampleStatus = row.sample_status || (row.count < 10 ? 'insufficient' : row.count < 30 ? 'reference' : 'stable'); const isBest = best?.len_group === row.len_group; const canCompare = row.count >= 10; return <div key={row.len_group} className={`grid min-h-[56px] gap-2 rounded-lg border px-3 py-2 sm:grid-cols-[92px_minmax(0,1fr)_210px] sm:items-center ${isBest ? 'border-blue-200 bg-blue-50/50' : 'border-transparent bg-slate-50/60'}`}><div><div className="flex items-center gap-1.5"><span className="text-xs font-semibold text-slate-800">{row.len_group}</span>{isBest ? <Badge variant="outline" className="border-blue-200 bg-white text-[9px] text-blue-700">{t('titleStrategy.lengthBest')}</Badge> : null}</div><div className="mt-0.5 text-[10px] text-slate-400">{row.count} {t('titleStrategy.posts')} · {t(`titleStrategy.sampleStatus.${sampleStatus}`)}</div></div><MetricBar label="" value={formatNumber(row.median_interaction)} width={row.count ? row.median_interaction / maxValue * 100 : 0} marker={overallMedian / maxValue * 100} color={row.count < 10 ? 'bg-slate-400' : isBest ? 'bg-blue-700' : 'bg-blue-500'} /><div className="grid grid-cols-3 gap-1 text-center text-[10px]"><div><div className={`font-mono font-semibold ${canCompare && Number(row.median_lift_percent || 0) > 0 ? 'text-emerald-700' : canCompare && Number(row.median_lift_percent || 0) < 0 ? 'text-rose-700' : 'text-slate-700'}`}>{!canCompare || row.median_lift_percent == null ? '—' : `${Number(row.median_lift_percent) > 0 ? '+' : ''}${Number(row.median_lift_percent).toFixed(1)}%`}</div><div className="text-slate-400">{canCompare ? t('titleStrategy.vsOverall') : t('titleStrategy.sampleInsufficient')}</div></div><div><div className="font-mono font-semibold text-slate-700">{canCompare ? formatNumber(row.avg_interaction_ex_top1) : '—'}</div><div className="text-slate-400">{canCompare ? t('titleStrategy.exTop1') : t('titleStrategy.sampleInsufficient')}</div></div><div><div className="font-mono font-semibold text-slate-700">{canCompare ? formatPercent(row.hit_rate) : '—'}</div><div className="text-slate-400">{canCompare ? t('titleStrategy.hitRate') : t('titleStrategy.sampleInsufficient')}</div></div></div></div>})}</div><div className="mt-2 shrink-0 text-center text-[10px] text-slate-400">{t('titleStrategy.lengthBaseline', { value: formatNumber(overallMedian) })}</div></div>
}


function SectionTitle({ icon: Icon, title, description }: { icon: typeof BarChart3; title: string; description: string }) {
  return <div className="flex items-start gap-3"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-700"><Icon aria-hidden="true" className="h-4 w-4" /></span><div className="min-w-0"><h2 className="text-sm font-semibold text-slate-900">{title}</h2><p className="mt-0.5 text-xs leading-5 text-slate-500">{description}</p></div></div>
}


function EmptyLine({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">{text}</div>
}


function StrategySkeleton() {
  return <div className="space-y-4" aria-label="loading"><div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-32 animate-pulse rounded-xl bg-slate-100" />)}</div><div className="grid gap-4 xl:grid-cols-2"><div className="h-96 animate-pulse rounded-xl bg-slate-100" /><div className="h-96 animate-pulse rounded-xl bg-slate-100" /></div></div>
}


function EmptyStrategy({ onAnalyze }: { onAnalyze: () => void }) {
  const { t } = useTranslation('config')
  return <div className="rounded-xl border border-dashed border-blue-200 bg-blue-50/40 px-6 py-16 text-center"><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-blue-700 text-white shadow-md"><BrainCircuit aria-hidden="true" className="h-6 w-6" /></span><h2 className="mt-5 text-base font-semibold text-slate-900">{t('titleStrategy.emptyTitle')}</h2><p className="mx-auto mt-2 max-w-2xl text-sm leading-7 text-slate-600">{t('titleStrategy.emptyDescription')}</p><Button type="button" onClick={onAnalyze} className="mt-5 min-h-11 bg-blue-700 text-white hover:bg-blue-800"><Sparkles aria-hidden="true" className="h-4 w-4" />{t('titleStrategy.analyze')}</Button></div>
}
