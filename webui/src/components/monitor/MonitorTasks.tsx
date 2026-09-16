import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronLeft, ChevronRight, ExternalLink, Eye, ListChecks, RefreshCw, Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { StatePanel } from '@/components/ui/state-panel'
import { monitorApi, type MonitorJob } from '@/lib/api'


const STATUS_FILTERS = ['all', 'pending', 'running', 'done', 'abnormal', 'failed', 'missed'] as const
const PAGE_SIZE = 50
type SortOption = 'due_asc' | 'due_desc' | 'attempts_desc' | 'failed_desc'

const CATEGORY_CLASSES: Record<string, string> = {
  risk_control: 'border-cyber-neon-pink/40 bg-cyber-neon-pink/10 text-cyber-neon-pink',
  login_required: 'border-cyber-neon-orange/40 bg-cyber-neon-orange/10 text-cyber-neon-orange',
  browser_disconnected: 'border-cyber-neon-purple/40 bg-cyber-neon-purple/10 text-cyber-neon-purple',
  network_timeout: 'border-cyber-neon-orange/40 bg-cyber-neon-orange/10 text-cyber-neon-orange',
  post_not_found: 'border-cyber-border-default bg-cyber-bg-tertiary text-cyber-text-muted',
  parse_error: 'border-cyber-neon-orange/40 bg-cyber-neon-orange/10 text-cyber-neon-orange',
  unknown: 'border-cyber-border-default bg-cyber-bg-tertiary text-cyber-text-secondary',
  none: 'border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted',
}


function formatDateTime(timestamp: number | null): string {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleString()
}


function ErrorCategoryTag({ category, label }: { category: string; label: string }) {
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-mono ${CATEGORY_CLASSES[category] || CATEGORY_CLASSES.unknown}`}>
      {label}
    </span>
  )
}


interface MonitorTasksProps {
  statusFilter: string
  onStatusFilterChange: (status: string) => void
  focusJobId?: number
  focusToken?: number
}


export function MonitorTasks({ statusFilter, onStatusFilterChange, focusJobId, focusToken }: MonitorTasksProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [searchText, setSearchText] = useState('')
  const [sortBy, setSortBy] = useState<SortOption>('due_asc')
  const [selectedJobIds, setSelectedJobIds] = useState<number[]>([])
  const [detailJob, setDetailJob] = useState<MonitorJob | null>(null)
  const [page, setPage] = useState(1)
  const handledFocusToken = useRef<number | undefined>()

  const { data, isLoading } = useQuery({
    queryKey: ['monitorJobs'],
    queryFn: async () => (await monitorApi.getJobs()).data,
    refetchInterval: 30000,
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['monitorJobs'] })
    queryClient.invalidateQueries({ queryKey: ['monitorOverview'] })
    queryClient.invalidateQueries({ queryKey: ['monitorDashboard'] })
    queryClient.invalidateQueries({ queryKey: ['monitorStatus'] })
    queryClient.invalidateQueries({ queryKey: ['monitorHealth'] })
  }

  const retryMutation = useMutation({
    mutationFn: (jobId: number) => monitorApi.retryJob(jobId),
    onSuccess: (_response, jobId) => {
      toast.success(t('tasks.retrySuccess'))
      setDetailJob((current) => current?.id === jobId
        ? { ...current, status: 'pending', attempts: 0, last_error: null, finished_at: null }
        : current)
      refresh()
    },
    onError: (error: Error) => toast.error(`${t('tasks.retryFailed')}: ${error.message}`),
  })

  const batchRetryMutation = useMutation({
    mutationFn: (jobIds: number[]) => monitorApi.retryFailedJobs(jobIds),
    onSuccess: (response) => {
      toast.success(t('tasks.batchRetrySuccess', { count: response.data.updated }))
      setSelectedJobIds([])
      refresh()
    },
    onError: (error: Error) => toast.error(`${t('tasks.retryFailed')}: ${error.message}`),
  })

  const jobs = useMemo(() => data?.jobs || [], [data])
  const counts = useMemo(() => jobs.reduce<Record<string, number>>((result, job) => {
    result[job.status] = (result[job.status] || 0) + 1
    return result
  }, {}), [jobs])

  const normalizedSearch = searchText.trim().toLowerCase()
  const filteredJobs = useMemo(() => jobs.filter((job) => {
    if (statusFilter === 'abnormal') return job.status === 'failed' || job.status === 'missed'
    if (statusFilter !== 'all' && job.status !== statusFilter) return false
    if (!normalizedSearch) return true
    return job.title.toLowerCase().includes(normalizedSearch) || job.aweme_id.includes(normalizedSearch)
  }), [jobs, normalizedSearch, statusFilter])

  const sortedJobs = useMemo(() => [...filteredJobs].sort((left, right) => {
    if (sortBy === 'due_desc') return right.due_at - left.due_at
    if (sortBy === 'attempts_desc') return right.attempts - left.attempts || right.due_at - left.due_at
    if (sortBy === 'failed_desc') {
      return (right.finished_at || right.due_at) - (left.finished_at || left.due_at)
    }
    return left.due_at - right.due_at
  }), [filteredJobs, sortBy])

  const pageCount = Math.max(1, Math.ceil(sortedJobs.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const pagedJobs = sortedJobs.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)
  const failedVisible = filteredJobs.filter((job) => job.status === 'failed')
  const allFailedSelected = failedVisible.length > 0 && failedVisible.every((job) => selectedJobIds.includes(job.id))

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [page, pageCount])

  useEffect(() => {
    if (!focusJobId || focusToken === undefined || handledFocusToken.current === focusToken) return
    const target = jobs.find((job) => job.id === focusJobId)
    if (!target) return
    handledFocusToken.current = focusToken
    setSearchText('')
    setSelectedJobIds([])
    setPage(1)
    onStatusFilterChange(target.status)
    setDetailJob(target)
  }, [focusJobId, focusToken, jobs, onStatusFilterChange])

  const changeStatus = (status: string) => {
    onStatusFilterChange(status)
    setSelectedJobIds([])
    setPage(1)
  }

  const toggleJob = (job: MonitorJob) => {
    if (job.status !== 'failed') return
    setSelectedJobIds((current) => current.includes(job.id)
      ? current.filter((id) => id !== job.id)
      : [...current, job.id])
  }

  const toggleAllFailed = () => {
    setSelectedJobIds(allFailedSelected ? [] : failedVisible.map((job) => job.id))
  }

  const categoryLabel = (job: MonitorJob) => t(`tasks.errorCategory.${job.error_category}`, {
    defaultValue: job.error_category || 'none',
  })
  const statusLabel = (job: MonitorJob) => t(`tasks.status.${job.status}`, {
    defaultValue: job.status,
  })
  const statusClass = (status: string) => status === 'failed'
    ? 'text-cyber-neon-pink'
    : status === 'missed'
      ? 'text-cyber-neon-orange'
      : status === 'done'
        ? 'text-cyber-neon-green'
        : 'text-cyber-neon-cyan'

  const renderActions = (job: MonitorJob) => (
    <div className="flex items-center justify-end gap-1">
      <Button type="button" variant="ghost" size="sm" onClick={() => setDetailJob(job)} className="h-7 w-7 p-0" aria-label={t('tasks.details')}>
        <Eye className="w-3.5 h-3.5" />
      </Button>
      {job.status === 'failed' ? (
        <Button
          type="button"
          size="sm"
          onClick={() => retryMutation.mutate(job.id)}
          disabled={retryMutation.isPending}
          className="h-7 px-2.5 font-mono text-[10px]"
        >
          <RefreshCw className="w-3 h-3" />
          {t('tasks.retry')}
        </Button>
      ) : null}
    </div>
  )

  return (
    <div className="grid grid-cols-1 items-start gap-3 animate-slide-up xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="min-w-0 rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
          <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center">
            <ListChecks className="h-4 w-4 text-cyber-neon-cyan" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('tasks.title')}</div>
            <div className="text-[10px] text-cyber-text-muted">{t('tasks.description')}</div>
          </div>
          <div className="ml-auto text-[10px] font-mono text-cyber-text-muted">
            {t('tasks.total', { count: jobs.length })}
          </div>
        </header>

        <div className="p-3 space-y-3">
          <div className="flex gap-1 overflow-x-auto rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-1">
            {STATUS_FILTERS.map((status) => {
              const count = status === 'all'
                ? jobs.length
                : status === 'abnormal'
                  ? (counts.failed || 0) + (counts.missed || 0)
                  : counts[status] || 0
              const active = statusFilter === status
              return (
                <button
                  key={status}
                  type="button"
                  onClick={() => changeStatus(status)}
                  className={`inline-flex shrink-0 items-center gap-2 rounded px-2.5 py-1.5 text-[10px] font-mono transition-colors ${active ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'text-cyber-text-muted hover:bg-cyber-bg-tertiary hover:text-cyber-text-primary'}`}
                >
                  {t(`tasks.status.${status}`)}
                  <span className={`rounded px-1.5 py-0.5 text-[9px] ${active ? 'bg-cyber-neon-cyan/15' : 'bg-cyber-bg-panel'}`}>{count}</span>
                </button>
              )
            })}
          </div>

          <div className="flex flex-col lg:flex-row gap-2 lg:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-cyber-text-muted" />
              <Input
                value={searchText}
                onChange={(event) => {
                  setSearchText(event.target.value)
                  setSelectedJobIds([])
                  setPage(1)
                }}
                placeholder={t('tasks.searchPlaceholder')}
                className="h-8 pl-9 text-xs"
              />
            </div>
            <Select
              value={sortBy}
              onValueChange={(value) => {
                setSortBy(value as SortOption)
                setPage(1)
              }}
            >
              <SelectTrigger className="h-8 w-full text-xs lg:w-[170px]">
                <SelectValue placeholder={t('tasks.sortBy')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="due_asc">{t('tasks.sort.dueAsc')}</SelectItem>
                <SelectItem value="due_desc">{t('tasks.sort.dueDesc')}</SelectItem>
                <SelectItem value="attempts_desc">{t('tasks.sort.attemptsDesc')}</SelectItem>
                <SelectItem value="failed_desc">{t('tasks.sort.failedDesc')}</SelectItem>
              </SelectContent>
            </Select>
            {failedVisible.length > 0 ? (
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" size="sm" onClick={toggleAllFailed} className="h-7 font-mono text-[10px]">
                  {allFailedSelected ? t('tasks.unselectAllFailed') : t('tasks.selectAllFailed')}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => batchRetryMutation.mutate(selectedJobIds)}
                  disabled={selectedJobIds.length === 0 || batchRetryMutation.isPending}
                  className="h-7 font-mono text-[10px]"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  {t('tasks.retrySelected', { count: selectedJobIds.length })}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => batchRetryMutation.mutate([])}
                  disabled={batchRetryMutation.isPending}
                  className="h-7 font-mono text-[10px]"
                >
                  {t('tasks.retryAllFailed')}
                </Button>
              </div>
            ) : null}
          </div>

          <div className="hidden max-h-[58vh] overflow-auto rounded-md border border-cyber-border-subtle/60 md:block">
            <table className="w-full min-w-[900px] text-xs font-mono">
              <thead className="sticky top-0 z-10 bg-cyber-bg-tertiary">
                <tr className="text-left text-cyber-text-muted border-b border-cyber-border-subtle">
                  <th className="py-2 pr-3 w-8" />
                  <th className="py-2 pr-4">{t('tasks.statusColumn')}</th>
                  <th className="py-2 pr-4">{t('tasks.stage')}</th>
                  <th className="py-2 pr-4">{t('tasks.post')}</th>
                  <th data-numeric="true" className="py-2 pr-4 text-right">{t('tasks.dueAt')}</th>
                  <th data-numeric="true" className="py-2 pr-4 text-right">{t('tasks.attempts')}</th>
                  <th className="py-2 pr-4">{t('tasks.reason')}</th>
                  <th className="py-2 text-right">{t('tasks.action')}</th>
                </tr>
              </thead>
              <tbody>
                {pagedJobs.map((job) => (
                  <tr key={job.id} className={`border-b border-cyber-border-subtle/40 text-cyber-text-secondary ${detailJob?.id === job.id ? 'bg-cyber-neon-cyan/5' : ''}`}>
                    <td className="py-2 pr-3">
                      <Checkbox
                        checked={selectedJobIds.includes(job.id)}
                        onCheckedChange={() => toggleJob(job)}
                        disabled={job.status !== 'failed'}
                        aria-label={t('tasks.selectJob')}
                      />
                    </td>
                    <td className={`py-2 pr-4 ${statusClass(job.status)}`}>{statusLabel(job)}</td>
                    <td className="py-2 pr-4">{job.stage}</td>
                    <td className="py-2 pr-4 max-w-[420px]">
                      <div className="truncate">{job.title || job.aweme_id}</div>
                      <div className="text-[10px] text-cyber-text-muted">{job.aweme_id}</div>
                    </td>
                    <td data-numeric="true" className="py-2 pr-4 text-right whitespace-nowrap">{formatDateTime(job.due_at)}</td>
                    <td data-numeric="true" className="py-2 pr-4 text-right">{job.attempts}</td>
                    <td className="py-2 pr-4">
                      {job.last_error || job.miss_reason
                        ? <ErrorCategoryTag category={job.error_category} label={categoryLabel(job)} />
                        : '-'}
                    </td>
                    <td className="py-2 text-right">{renderActions(job)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!isLoading && sortedJobs.length === 0 ? (
              <div className="py-10 text-center text-xs font-mono text-cyber-text-muted">{t('tasks.noJobs')}</div>
            ) : null}
          </div>

          <div className="max-h-[58vh] space-y-2 overflow-y-auto md:hidden">
            {pagedJobs.map((job) => (
              <div key={job.id} className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3 font-mono">
                <div className="flex items-start gap-2">
                  <Checkbox
                    checked={selectedJobIds.includes(job.id)}
                    onCheckedChange={() => toggleJob(job)}
                    disabled={job.status !== 'failed'}
                    aria-label={t('tasks.selectJob')}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs text-cyber-text-primary">{job.title || job.aweme_id}</div>
                    <div className="mt-0.5 truncate text-[9px] text-cyber-text-muted">{job.aweme_id}</div>
                  </div>
                  <span className={`text-[10px] ${statusClass(job.status)}`}>{statusLabel(job)}</span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-[10px]">
                  <div><span className="text-cyber-text-muted">{t('tasks.stage')}: </span>{job.stage}</div>
                  <div><span className="text-cyber-text-muted">{t('tasks.attempts')}: </span>{job.attempts}</div>
                  <div className="col-span-2"><span className="text-cyber-text-muted">{t('tasks.dueAt')}: </span>{formatDateTime(job.due_at)}</div>
                </div>
                {job.last_error || job.miss_reason ? (
                  <div className="mt-2"><ErrorCategoryTag category={job.error_category} label={categoryLabel(job)} /></div>
                ) : null}
                <div className="mt-3 flex justify-end border-t border-cyber-border-subtle/50 pt-2">
                  {renderActions(job)}
                </div>
              </div>
            ))}
            {!isLoading && sortedJobs.length === 0 ? (
              <div className="py-10 text-center text-xs font-mono text-cyber-text-muted">{t('tasks.noJobs')}</div>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[10px] font-mono text-cyber-text-muted">
              {t('tasks.pageInfo', {
                from: sortedJobs.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1,
                to: Math.min(safePage * PAGE_SIZE, sortedJobs.length),
                total: sortedJobs.length,
              })}
            </div>
            <div className="flex items-center gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={safePage <= 1}
                className="h-7 w-7 p-0"
                aria-label={t('tasks.previousPage')}
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </Button>
              <span className="min-w-20 text-center text-[10px] font-mono text-cyber-text-muted">
                {t('tasks.pageOf', { page: safePage, total: pageCount })}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                disabled={safePage >= pageCount}
                className="h-7 w-7 p-0"
                aria-label={t('tasks.nextPage')}
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </section>

      <aside className="sticky top-16 max-h-[calc(100vh-5rem)] overflow-y-auto rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel shadow-sm">
        {detailJob ? (
          <>
            <header className="sticky top-0 z-10 px-4 py-3 border-b border-cyber-border-subtle flex items-center gap-3 bg-cyber-bg-panel/95 backdrop-blur">
              <h2 className="text-sm font-mono font-semibold text-cyber-text-primary">{t('tasks.detailTitle')}</h2>
              <Button type="button" variant="ghost" size="sm" onClick={() => setDetailJob(null)} className="ml-auto h-7 w-7 p-0" aria-label={t('tasks.closeDetails')} title={t('tasks.closeDetails')}>
                <X className="w-4 h-4" />
              </Button>
            </header>
            <div className="p-4 space-y-4 text-xs font-mono">
              <div className="text-sm text-cyber-text-primary">{detailJob.title || detailJob.aweme_id}</div>
              <div className="text-cyber-text-muted break-all">{detailJob.aweme_id}</div>
              {detailJob.canonical_url ? (
                <a href={detailJob.canonical_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-cyber-neon-cyan hover:underline">
                  <ExternalLink className="w-3.5 h-3.5" />
                  {t('tasks.openPost')}
                </a>
              ) : null}
              <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3">
                <div className="grid grid-cols-2 gap-3">
                  <div><div className="text-[10px] text-cyber-text-muted">{t('tasks.statusColumn')}</div><div className={`mt-1 ${statusClass(detailJob.status)}`}>{statusLabel(detailJob)}</div></div>
                  <div><div className="text-[10px] text-cyber-text-muted">{t('tasks.stage')}</div><div className="mt-1 text-cyber-text-primary">{detailJob.stage}</div></div>
                  <div><div className="text-[10px] text-cyber-text-muted">{t('tasks.publishTime')}</div><div className="mt-1 text-cyber-text-primary">{formatDateTime(detailJob.create_time)}</div></div>
                  <div><div className="text-[10px] text-cyber-text-muted">{t('tasks.dueAt')}</div><div className="mt-1 text-cyber-text-primary">{formatDateTime(detailJob.due_at)}</div></div>
                  <div><div className="text-[10px] text-cyber-text-muted">{t('tasks.attempts')}</div><div className="mt-1 text-cyber-text-primary">{detailJob.attempts}</div></div>
                  <div><div className="text-[10px] text-cyber-text-muted">{t('tasks.errorCategoryLabel')}</div><div className="mt-1"><ErrorCategoryTag category={detailJob.error_category} label={categoryLabel(detailJob)} /></div></div>
                </div>
              </div>
              <details className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
                <summary className="cursor-pointer px-3 py-2 text-[10px] text-cyber-text-muted">{t('tasks.moreTimes')}</summary>
                <div className="grid grid-cols-3 gap-2 border-t border-cyber-border-subtle p-3 text-[10px]">
                  <div><div className="text-cyber-text-muted">{t('tasks.createdAt')}</div><div className="mt-1">{formatDateTime(detailJob.created_at)}</div></div>
                  <div><div className="text-cyber-text-muted">{t('tasks.startedAt')}</div><div className="mt-1">{formatDateTime(detailJob.started_at)}</div></div>
                  <div><div className="text-cyber-text-muted">{t('tasks.finishedAt')}</div><div className="mt-1">{formatDateTime(detailJob.finished_at)}</div></div>
                </div>
              </details>
              <details className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
                <summary className="cursor-pointer px-3 py-2 text-[10px] text-cyber-text-muted">{t('tasks.rawError')}</summary>
                <pre className="whitespace-pre-wrap border-t border-cyber-border-subtle p-3 text-[11px] text-cyber-text-secondary">{detailJob.last_error || detailJob.miss_reason || '-'}</pre>
              </details>
              {detailJob.status === 'failed' ? (
                <Button type="button" onClick={() => retryMutation.mutate(detailJob.id)} disabled={retryMutation.isPending} className="w-full text-xs">
                  <RefreshCw className="w-4 h-4" />
                  {t('tasks.retry')}
                </Button>
              ) : null}
            </div>
          </>
        ) : (
          <StatePanel variant="empty" title={t('tasks.selectJobHint')} description={t('tasks.selectJobHintDetail')} />
        )}
      </aside>
    </div>
  )
}
