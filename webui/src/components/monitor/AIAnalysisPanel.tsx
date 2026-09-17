import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainCircuit, CheckCircle2, Clock3, Database, RefreshCw, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  monitorApi,
  type AIAnalysisResponse,
  type AIAnalysisType,
  type AILifecycleAnalysisResult,
  type AITopicAnalysisResult,
} from '@/lib/api'


interface AIAnalysisPanelProps {
  analysisType: AIAnalysisType
  accountId: number | null
  timeRange: '24h' | '7d' | '30d' | 'all'
  postLimit: number
}


function formatDateTime(value?: number | null): string {
  if (!value) return '-'
  return new Date(value * 1000).toLocaleString()
}


function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
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


export function AIAnalysisPanel({ analysisType, accountId, timeRange, postLimit }: AIAnalysisPanelProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const queryKey = ['aiAnalysisLatest', analysisType, accountId]
  const statusQuery = useQuery({
    queryKey: ['aiAnalysisStatus'],
    queryFn: async () => (await monitorApi.getAIStatus()).data,
    staleTime: 60000,
  })
  const latestQuery = useQuery({
    queryKey,
    enabled: typeof accountId === 'number',
    queryFn: async () => {
      if (typeof accountId !== 'number') return null
      const response = await monitorApi.getAIResults(accountId, analysisType, undefined, 1)
      return response.data.results[0] || null
    },
  })
  const analysisMutation = useMutation({
    mutationFn: async (force: boolean) => {
      if (typeof accountId !== 'number') throw new Error(t('aiAnalysis.singleAccountRequired'))
      const payload = { account_id: accountId, time_range: timeRange, post_limit: postLimit, force }
      return analysisType === 'topic'
        ? monitorApi.analyzeTopics(payload)
        : monitorApi.analyzeLifecycle(payload)
    },
    onSuccess: (response) => {
      queryClient.setQueryData(queryKey, response.data)
      queryClient.invalidateQueries({ queryKey: ['aiAnalysisResults'] })
      toast.success(t('aiAnalysis.completed'))
    },
    onError: (error: Error) => toast.error(`${t('aiAnalysis.failed')}: ${analysisErrorMessage(error)}`),
  })

  const current = (analysisMutation.data?.data || latestQuery.data || null) as AIAnalysisResponse | null
  const configured = Boolean(statusQuery.data?.configured)
  const busy = analysisMutation.isPending
  const buttonDisabled = typeof accountId !== 'number' || !configured || busy
  const title = analysisType === 'topic' ? t('aiAnalysis.topicTitle') : t('aiAnalysis.lifecycleTitle')
  const description = analysisType === 'topic' ? t('aiAnalysis.topicDescription') : t('aiAnalysis.lifecycleDescription')

  return (
    <section className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-cyber-neon-purple/30 bg-cyber-neon-purple/10 text-cyber-neon-purple">
            <BrainCircuit className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs font-semibold text-cyber-text-primary">{title}</div>
            <div className="mt-1 max-w-3xl text-[9px] leading-4 text-cyber-text-muted">{description}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-[9px] ${configured ? 'border-cyber-neon-green/30 bg-cyber-neon-green/5 text-cyber-neon-green' : 'border-cyber-neon-orange/30 bg-cyber-neon-orange/5 text-cyber-neon-orange'}`}>
            <CheckCircle2 className="h-3 w-3" />
            {configured ? t('aiAnalysis.modelConnected') : t('aiAnalysis.modelUnavailable')}
          </span>
          <Button
            type="button"
            size="sm"
            disabled={buttonDisabled}
            onClick={() => analysisMutation.mutate(Boolean(current))}
            className="h-8 font-mono text-[10px]"
          >
            {busy ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <BrainCircuit className="h-3.5 w-3.5" />}
            {busy ? t('aiAnalysis.analyzing') : current ? t('aiAnalysis.reanalyze') : t('aiAnalysis.analyze')}
          </Button>
        </div>
      </div>

      {typeof accountId !== 'number' ? <div className="mt-3 rounded-md border border-cyber-neon-orange/30 bg-cyber-neon-orange/5 p-3 text-[10px] text-cyber-neon-orange">{t('aiAnalysis.singleAccountRequired')}</div> : null}
      {typeof accountId === 'number' && !configured && !statusQuery.isLoading ? <div className="mt-3 rounded-md border border-cyber-neon-orange/30 bg-cyber-neon-orange/5 p-3 text-[10px] text-cyber-neon-orange">{t('aiAnalysis.notConfigured')}</div> : null}

      {latestQuery.isLoading && typeof accountId === 'number' ? <div className="mt-4 flex items-center gap-2 text-[10px] text-cyber-text-muted"><RefreshCw className="h-3.5 w-3.5 animate-spin" />{t('aiAnalysis.loading')}</div> : null}
      {busy ? <div className="mt-4 flex items-center gap-2 rounded-md border border-cyber-neon-purple/30 bg-cyber-neon-purple/5 p-3 text-[10px] text-cyber-neon-purple"><RefreshCw className="h-3.5 w-3.5 animate-spin" />{t('aiAnalysis.analyzingHint')}</div> : null}
      {current?.refresh_error ? <div className="mt-4 flex items-start gap-2 rounded-md border border-cyber-neon-orange/30 bg-cyber-neon-orange/5 p-3 text-[10px] text-cyber-neon-orange"><TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />{t('aiAnalysis.refreshFailedKeptCache')}</div> : null}

      {current ? (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 px-3 py-2 text-[9px] text-cyber-text-muted">
            <span className={`rounded border px-2 py-1 ${current.cache_hit ? 'border-cyber-neon-cyan/30 bg-cyber-neon-cyan/5 text-cyber-neon-cyan' : 'border-cyber-neon-green/30 bg-cyber-neon-green/5 text-cyber-neon-green'}`}>{current.cache_hit ? t('aiAnalysis.cacheHit') : t('aiAnalysis.freshResult')}</span>
            <span className="inline-flex items-center gap-1"><Database className="h-3 w-3" />{current.model || '-'}</span>
            <span className="inline-flex items-center gap-1"><Clock3 className="h-3 w-3" />{t('aiAnalysis.generatedAt')}: {formatDateTime(current.updated_at)}</span>
            <span>{t('aiAnalysis.expiresAt')}: {formatDateTime(current.expires_at)}</span>
          </div>

          {current.status === 'insufficient_data' ? (
            <div className="rounded-md border border-cyber-neon-orange/30 bg-cyber-neon-orange/5 p-4 text-xs text-cyber-neon-orange">
              {analysisType === 'topic'
                ? String((current.result as unknown as AITopicAnalysisResult).summary || t('aiAnalysis.insufficient'))
                : String((current.result as unknown as AILifecycleAnalysisResult).overall_summary || t('aiAnalysis.insufficient'))}
            </div>
          ) : analysisType === 'topic' ? (
            <TopicResultView result={current.result as unknown as AITopicAnalysisResult} />
          ) : (
            <LifecycleResultView result={current.result as unknown as AILifecycleAnalysisResult} />
          )}
        </div>
      ) : null}
    </section>
  )
}


function StringList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div>
      <div className="text-[10px] font-semibold text-cyber-text-secondary">{title}</div>
      <ul className="mt-2 space-y-1.5 text-[10px] leading-4 text-cyber-text-muted">
        {items.map((item) => <li key={item} className="flex gap-2"><span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-cyber-neon-cyan" />{item}</li>)}
      </ul>
    </div>
  )
}


function TopicResultView({ result }: { result: AITopicAnalysisResult }) {
  const { t } = useTranslation('config')
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/15 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><div className="text-[10px] font-semibold text-cyber-text-secondary">{t('aiAnalysis.summary')}</div><span className="text-[9px] text-cyber-text-muted">{t('aiAnalysis.sourcePostCount', { count: result.source_post_count })}</span></div>
        <p className="mt-2 text-[11px] leading-5 text-cyber-text-primary">{result.summary || '-'}</p>
      </div>

      <div>
        <div className="text-[10px] font-semibold text-cyber-text-secondary">{t('aiAnalysis.clusters')}</div>
        <div className="mt-2 grid grid-cols-1 gap-3 xl:grid-cols-2">
          {result.clusters.map((cluster) => (
            <div key={cluster.name} className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/10 p-3">
              <div className="flex items-start gap-2"><div className="min-w-0 flex-1 text-[11px] font-semibold text-cyber-text-primary">{cluster.name}</div><span className="rounded border border-cyber-neon-purple/30 bg-cyber-neon-purple/5 px-1.5 py-0.5 text-[8px] text-cyber-neon-purple">{t('aiAnalysis.confidence')} {(cluster.confidence * 100).toFixed(0)}%</span></div>
              <p className="mt-1.5 text-[9px] leading-4 text-cyber-text-muted">{cluster.description}</p>
              <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                <div><div className="text-[8px] text-cyber-text-muted">{t('aiAnalysis.postsCount')}</div><div className="mt-1 text-xs font-semibold numeric-value text-cyber-text-primary">{cluster.posts}</div></div>
                <div><div className="text-[8px] text-cyber-text-muted">{t('aiAnalysis.totalInteraction')}</div><div className="mt-1 text-xs font-semibold numeric-value text-cyber-neon-cyan">{formatNumber(cluster.total_interaction)}</div></div>
                <div><div className="text-[8px] text-cyber-text-muted">{t('aiAnalysis.averageInteraction')}</div><div className="mt-1 text-xs font-semibold numeric-value text-cyber-neon-green">{formatNumber(cluster.average_interaction)}</div></div>
                <div><div className="text-[8px] text-cyber-text-muted">{t('aiAnalysis.burstRate')}</div><div className="mt-1 text-xs font-semibold numeric-value text-cyber-neon-orange">{cluster.burst_rate.toFixed(1)}%</div></div>
              </div>
              {cluster.keywords.length > 0 ? <div className="mt-3 flex flex-wrap gap-1">{cluster.keywords.map((keyword) => <span key={keyword} className="rounded bg-cyber-bg-tertiary px-1.5 py-0.5 text-[8px] text-cyber-text-muted">#{keyword}</span>)}</div> : null}
              {cluster.representative_posts.length > 0 ? <div className="mt-3 border-t border-cyber-border-subtle/40 pt-2"><div className="text-[8px] text-cyber-text-muted">{t('aiAnalysis.representativePosts')}</div><div className="mt-1.5 space-y-1">{cluster.representative_posts.map((post) => <div key={post.aweme_id} className="flex items-center gap-2 text-[9px]"><span title={post.title} className="min-w-0 flex-1 truncate text-cyber-text-secondary">{post.title}</span><span className="shrink-0 numeric-value text-cyber-text-muted">{formatNumber(post.interaction_total)}</span></div>)}</div></div> : null}
            </div>
          ))}
        </div>
      </div>

      {result.tag_groups.length > 0 ? <div><div className="text-[10px] font-semibold text-cyber-text-secondary">{t('aiAnalysis.tagGroups')}</div><div className="mt-2 grid grid-cols-1 gap-2 xl:grid-cols-2">{result.tag_groups.map((group) => <div key={group.name} className="rounded-md border border-cyber-border-subtle p-3"><div className="text-[10px] font-medium text-cyber-text-primary">{group.name}</div><div className="mt-1 text-[9px] text-cyber-text-muted">{group.summary}</div><div className="mt-2 flex flex-wrap gap-1">{group.tags.map((tag) => <span key={tag} className="rounded bg-cyber-bg-tertiary px-1.5 py-0.5 text-[8px] text-cyber-text-secondary">#{tag}</span>)}</div></div>)}</div></div> : null}
      <div className="grid grid-cols-1 gap-4 border-t border-cyber-border-subtle/50 pt-3 xl:grid-cols-2"><StringList title={t('aiAnalysis.recommendations')} items={result.recommendations} /><StringList title={t('aiAnalysis.dataLimits')} items={result.data_limits} /></div>
    </div>
  )
}


function LifecycleResultView({ result }: { result: AILifecycleAnalysisResult }) {
  const { t } = useTranslation('config')
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/15 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><div className="text-[10px] font-semibold text-cyber-text-secondary">{t('aiAnalysis.summary')}</div><span className="text-[9px] text-cyber-text-muted">{t('aiAnalysis.sourcePostCount', { count: result.source_post_count })}</span></div>
        <p className="mt-2 text-[11px] leading-5 text-cyber-text-primary">{result.overall_summary || '-'}</p>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="rounded-md border border-cyber-border-subtle p-3"><div className="text-[10px] font-semibold text-cyber-text-secondary">{t('aiAnalysis.stageSummary')}</div><div className="mt-2 grid grid-cols-4 gap-2">{result.stage_summary.map((row) => <div key={row.stage} className="text-center"><div className="text-[9px] text-cyber-text-muted">{row.stage}</div><div className="mt-1 text-xs font-semibold numeric-value text-cyber-neon-cyan">{row.average_interaction == null ? '-' : formatNumber(row.average_interaction)}</div><div className="mt-0.5 text-[8px] text-cyber-text-muted">{row.sample_count} samples</div></div>)}</div></div>
        <div className="rounded-md border border-cyber-border-subtle p-3"><div className="text-[10px] font-semibold text-cyber-text-secondary">{t('aiAnalysis.typeDistribution')}</div><div className="mt-2 flex flex-wrap gap-2">{Object.entries(result.type_distribution).map(([type, count]) => <span key={type} className="rounded border border-cyber-border-subtle bg-cyber-bg-tertiary/20 px-2 py-1 text-[9px] text-cyber-text-secondary">{t(`lifecycle.types.${type}`, { defaultValue: type })}: <b className="numeric-value text-cyber-text-primary">{count}</b></span>)}</div></div>
      </div>

      <div><div className="text-[10px] font-semibold text-cyber-text-secondary">{t('aiAnalysis.postInsights')}</div><div className="mt-2 space-y-2">{result.post_insights.map((insight) => <div key={insight.aweme_id} className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/10 p-3"><div className="flex items-start gap-2"><div className="min-w-0 flex-1"><div className="truncate text-[10px] font-medium text-cyber-text-primary" title={insight.title}>{insight.title}</div><div className="mt-1 text-[9px] text-cyber-text-muted">{insight.pattern}</div></div><div className="flex shrink-0 items-center gap-1"><span className="rounded bg-cyber-bg-tertiary px-1.5 py-0.5 text-[8px] text-cyber-text-muted">{insight.source === 'model' ? 'AI' : t('aiAnalysis.deterministic')}</span><span className="text-[8px] text-cyber-text-muted">{t('aiAnalysis.confidence')} {(insight.confidence * 100).toFixed(0)}%</span></div></div>{insight.evidence.length > 0 ? <div className="mt-2 flex flex-wrap gap-1">{insight.evidence.map((item) => <span key={item} className="rounded bg-cyber-bg-tertiary px-1.5 py-0.5 text-[8px] text-cyber-text-secondary">{item}</span>)}</div> : null}{insight.possible_factors.length > 0 ? <div className="mt-2 text-[9px] text-cyber-text-muted">{t('aiAnalysis.possibleFactors')}: {insight.possible_factors.join('；')}</div> : null}</div>)}</div></div>

      <div className="grid grid-cols-1 gap-4 border-t border-cyber-border-subtle/50 pt-3 xl:grid-cols-2"><StringList title={t('aiAnalysis.contentPatterns')} items={result.content_patterns} /><StringList title={t('aiAnalysis.anomalyNotes')} items={result.anomaly_notes} /><StringList title={t('aiAnalysis.recommendations')} items={result.recommendations} /><StringList title={t('aiAnalysis.caveats')} items={result.caveats} /></div>
    </div>
  )
}
