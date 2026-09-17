import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainCircuit, CheckCircle2, ChevronDown, Copy, History, Lightbulb, RefreshCw, Sparkles, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
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
    return [...new Set(current.result.clusters.flatMap((cluster) => cluster.keywords || []))].slice(0, 5)
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
    <div className="mx-auto w-full max-w-[1100px] space-y-5 pb-6">
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
      {mutation.isPending || historyQuery.isLoading ? <TopicReportSkeleton /> : current ? <TopicReportContent current={current} tagCloud={tagCloud} onCopyTag={copyTag} /> : typeof accountId === 'number' && configured ? <EmptyReport onAnalyze={() => mutation.mutate({ force: false, accountId, timeRange, postLimit })} /> : null}
    </div>
  )
}


function RichText({ text, className = '' }: { text: string; className?: string }) {
  const parts = String(text || '').split(/(\*\*[^*]+\*\*)/g)
  return <span className={className}>{parts.map((part, index) => part.startsWith('**') && part.endsWith('**') ? <strong key={`${part}-${index}`} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong> : <span key={`${part}-${index}`}>{part}</span>)}</span>
}


function ReportNotice({ text, tone }: { text: string; tone: 'warning' | 'info' }) {
  return <div className={`rounded-md border px-4 py-3 text-sm leading-6 ${tone === 'warning' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-blue-200 bg-blue-50 text-blue-800'}`}>{text}</div>
}


function TopicReportContent({ current, tagCloud, onCopyTag }: { current: AIAnalysisResponse<AITopicAnalysisResult>; tagCloud: string[]; onCopyTag: (tag: string) => void }) {
  const { t } = useTranslation('config')
  const result = current.result
  if (current.status === 'insufficient_data') return <ReportNotice tone="warning" text={result.summary || t('topicReport.insufficient')} />

  return (
    <div className="space-y-6">
      <section className="border-l-4 border-l-[#165DFF] rounded-lg bg-[#F2F7FF] px-6 py-5">
        <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#165DFF]">{t('topicReport.executiveSummary')}</div>
        <p className="mt-3 text-[15px] leading-[1.8] text-slate-800"><RichText text={result.summary || '-'} /></p>
      </section>

      {tagCloud.length > 0 ? (
        <section className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3">
          <span className="mr-1 text-xs font-semibold text-slate-700">{t('topicReport.topTags')}</span>
          {tagCloud.map((tag) => <button key={tag} type="button" onClick={() => onCopyTag(tag)} className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-3 py-1 text-xs text-[#165DFF] hover:bg-blue-100"><Copy className="h-3 w-3" />#{tag}</button>)}
        </section>
      ) : null}

      <section>
        <div className="mb-3 flex items-end justify-between gap-3"><div><div className="text-base font-semibold text-slate-900">{t('topicReport.insightsTitle')}</div><p className="mt-1 text-xs text-slate-500">{t('topicReport.insightsDescription')}</p></div></div>
        <div className="columns-1 gap-4 lg:columns-2">
          {result.clusters.map((cluster) => {
            const confidenceHigh = cluster.confidence >= 0.8
            return (
              <article key={cluster.name} className="mb-4 break-inside-avoid rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-base font-semibold leading-6 text-slate-900">{cluster.name}</h3>
                  <span className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-medium ${confidenceHigh ? 'bg-emerald-50 text-emerald-700' : 'bg-orange-50 text-orange-700'}`}>{t('topicReport.confidence')} {(cluster.confidence * 100).toFixed(0)}%</span>
                </div>
                <p className="mt-3 text-sm leading-7 text-slate-600"><RichText text={cluster.description || '-'} /></p>
                {cluster.keywords.length > 0 ? <div className="mt-4 flex flex-wrap gap-2">{cluster.keywords.map((tag) => <button key={tag} type="button" onClick={() => onCopyTag(tag)} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-blue-50 hover:text-[#165DFF]">#{tag}</button>)}</div> : null}
                <div className="mt-4 border-l-2 border-l-[#722ED1] bg-[#F9F5FF] px-4 py-3 text-sm leading-7 text-slate-600"><span className="font-semibold text-[#722ED1]">{t('topicReport.representativeInsight')}</span><RichText text={cluster.representative_insight || cluster.description || '-'} /></div>
              </article>
            )
          })}
        </div>
      </section>

      {result.recommendations.length > 0 ? (
        <section className="rounded-lg bg-[#FFF7E8] p-5">
          <div className="flex items-center gap-2"><Lightbulb className="h-5 w-5 text-[#D97706]" /><h2 className="text-base font-semibold text-slate-900">{t('topicReport.recommendations')}</h2></div>
          <ol className="mt-4 space-y-3">{result.recommendations.map((item, index) => <li key={`${item}-${index}`} className="flex items-start gap-3 text-sm leading-7 text-slate-700"><span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#D97706] text-xs font-semibold text-white">{index + 1}</span><RichText text={item} /></li>)}</ol>
        </section>
      ) : null}

      <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><TriangleAlert className="h-4 w-4 text-slate-500" />{t('topicReport.dataLimitations')}</div>
        <div className="mt-3 space-y-2 text-[13px] leading-6 text-slate-500">{(result.data_limits.length > 0 ? result.data_limits : [t('topicReport.defaultLimit')]).map((item) => <p key={item}>{item}</p>)}</div>
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
