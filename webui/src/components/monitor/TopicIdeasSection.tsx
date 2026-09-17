import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart3, Copy, Lightbulb, RefreshCw, Sparkles, Star, Tags } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { monitorApi, type AIAnalysisResponse, type AITopicIdea, type AITopicIdeasResult } from '@/lib/api'


interface TopicIdeasSectionProps {
  accountId: number | null
  topicResultId: number
  activeTheme?: string
}


function analysisErrorMessage(error: unknown): string {
  const responseError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = responseError.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message?: unknown }).message || '')
  return String(error instanceof Error ? error.message : error || '')
}


export function TopicIdeasSection({ accountId, topicResultId, activeTheme = '' }: TopicIdeasSectionProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(new Set())
  const storageKey = accountId ? `mediacrawler_topic_idea_favorites_${accountId}_${topicResultId}` : ''
  const historyKey = ['aiTopicIdeas', accountId]
  const ideasQuery = useQuery({
    queryKey: historyKey,
    enabled: typeof accountId === 'number',
    queryFn: async () => {
      if (typeof accountId !== 'number') return []
      const response = await monitorApi.getAIResults(accountId, 'topic_ideas', undefined, 20)
      return response.data.results as unknown as AIAnalysisResponse<AITopicIdeasResult>[]
    },
  })
  const mutation = useMutation({
    mutationFn: async (force: boolean) => {
      if (typeof accountId !== 'number') throw new Error(t('topicIdeas.singleAccountRequired'))
      return monitorApi.analyzeTopicIdeas({ account_id: accountId, topic_result_id: topicResultId, force })
    },
    onSuccess: (response) => {
      queryClient.setQueryData<AIAnalysisResponse<AITopicIdeasResult>[]>(historyKey, (current = []) => [response.data, ...current.filter((item) => item.id !== response.data.id)])
      toast.success(t('topicIdeas.completed'))
    },
    onError: (error: Error) => toast.error(`${t('topicIdeas.failed')}: ${analysisErrorMessage(error)}`),
  })

  const ideaHistory = ideasQuery.data || []
  const current = mutation.data?.data || ideaHistory.find((item) => Number((item.scope as Record<string, unknown>).source_result_id) === topicResultId) || ideaHistory[0] || null
  const ideas = useMemo(() => {
    const rows = current?.result?.ideas || []
    if (!activeTheme) return rows
    const matched = rows.filter((idea) => [idea.title, idea.angle, idea.why_now, ...(idea.evidence || [])].join(' ').includes(activeTheme))
    return matched.length > 0 ? matched : rows
  }, [activeTheme, current])
  useEffect(() => {
    if (!storageKey) {
      setFavoriteIds(new Set())
      return
    }
    try {
      setFavoriteIds(new Set(JSON.parse(localStorage.getItem(storageKey) || '[]') as number[]))
    } catch {
      setFavoriteIds(new Set())
    }
  }, [storageKey])

  const toggleFavorite = (idea: AITopicIdea) => {
    setFavoriteIds((currentIds) => {
      const next = new Set(currentIds)
      if (next.has(idea.id)) next.delete(idea.id)
      else next.add(idea.id)
      if (storageKey) localStorage.setItem(storageKey, JSON.stringify([...next]))
      toast.success(next.has(idea.id) ? t('topicIdeas.favorited') : t('topicIdeas.unfavorited'))
      return next
    })
  }

  const copyOutline = async (idea: AITopicIdea) => {
    const content = [
      idea.title,
      '',
      `${t('topicIdeas.dataSupport')}: ${idea.why_now || idea.evidence.join('；')}`,
      `${t('topicIdeas.angle')}: ${idea.angle}`,
      `${t('topicIdeas.format')}: ${idea.format}`,
      `${t('topicIdeas.audience')}: ${idea.audience}`,
    ].join('\n')
    await navigator.clipboard.writeText(content)
    toast.success(t('topicIdeas.outlineCopied'))
  }

  return (
    <aside className="flex h-[480px] flex-col rounded-lg border border-slate-200 bg-white">
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-4">
        <div><div className="flex items-center gap-2 text-sm font-semibold text-slate-900"><Sparkles className="h-4 w-4 text-[#D97706]" />{t('topicIdeas.title')}</div><p className="mt-1 text-[11px] leading-5 text-slate-500">{activeTheme ? t('topicIdeas.forTheme', { theme: activeTheme }) : t('topicIdeas.description')}</p></div>
        <Button type="button" size="sm" disabled={mutation.isPending || typeof accountId !== 'number'} onClick={() => mutation.mutate(Boolean(current))} className="h-8 shrink-0 bg-[#D97706] text-[11px] text-white hover:bg-[#B45309]">{mutation.isPending ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}{current ? t('topicIdeas.regenerate') : t('topicIdeas.generate')}</Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {mutation.isPending ? <TopicIdeasSkeleton /> : ideas.length > 0 ? <div className="space-y-3">{ideas.map((idea) => <article key={idea.id} className="rounded-lg border border-slate-200 bg-slate-50/40 p-4"><div className="flex justify-end gap-1"><button type="button" onClick={() => toggleFavorite(idea)} className={`flex h-7 w-7 items-center justify-center rounded-md ${favoriteIds.has(idea.id) ? 'bg-amber-100 text-amber-600' : 'text-slate-400 hover:bg-slate-100 hover:text-amber-600'}`} title={favoriteIds.has(idea.id) ? t('topicIdeas.unfavorite') : t('topicIdeas.favorite')}><Star className={`h-3.5 w-3.5 ${favoriteIds.has(idea.id) ? 'fill-current' : ''}`} /></button><button type="button" onClick={() => copyOutline(idea)} className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700" title={t('topicIdeas.copyOutline')}><Copy className="h-3.5 w-3.5" /></button></div><h3 className="px-1 text-center text-[15px] font-semibold leading-6 text-slate-900">{idea.title}</h3><div className="mt-4 flex items-start gap-2 text-[11px] leading-5 text-slate-500"><BarChart3 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#165DFF]" /><span><b className="font-semibold text-slate-600">{t('topicIdeas.dataSupport')}：</b>{idea.why_now || idea.evidence.join('；')}</span></div><div className="mt-3 flex items-start gap-2 text-[12px] leading-6 text-slate-600"><Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#D97706]" /><span><b className="font-semibold text-slate-700">{t('topicIdeas.coreAngle')}：</b>{idea.angle}</span></div><div className="mt-3 flex flex-wrap items-center gap-1.5"><span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-1 text-[10px] text-[#165DFF]"><Tags className="h-3 w-3" />{idea.format}</span><span className="rounded-full bg-purple-50 px-2 py-1 text-[10px] text-purple-700">{idea.audience}</span></div></article>)}</div> : <div className="flex h-full flex-col items-center justify-center px-5 text-center"><Sparkles className="h-7 w-7 text-[#D97706]" /><div className="mt-3 text-sm font-medium text-slate-800">{t('topicIdeas.emptyTitle')}</div><p className="mt-1 text-xs leading-5 text-slate-500">{t('topicIdeas.emptyDescription')}</p></div>}
      </div>
    </aside>
  )
}


function TopicIdeasSkeleton() {
  return <div className="space-y-3">{[0, 1, 2].map((item) => <div key={item} className="rounded-lg border border-slate-200 bg-white p-4"><div className="mx-auto h-5 w-3/4 animate-pulse rounded bg-slate-200" /><div className="mt-4 space-y-2">{[0, 1, 2].map((line) => <div key={line} className="h-3 animate-pulse rounded bg-slate-100" style={{ width: `${92 - line * 14}%` }} />)}</div><div className="mt-4 h-8 animate-pulse rounded bg-slate-100" /></div>)}</div>
}
