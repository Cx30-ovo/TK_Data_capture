import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ListChecks, RefreshCw, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { monitorApi, type MonitorJob } from '@/lib/api'


const STATUS_FILTERS = ['all', 'pending', 'running', 'done', 'failed', 'missed'] as const


function formatDateTime(timestamp: number | null): string {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleString()
}


export function MonitorTasks() {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const [searchText, setSearchText] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['monitorJobs'],
    queryFn: async () => (await monitorApi.getJobs()).data,
    refetchInterval: 30000,
  })

  const retryMutation = useMutation({
    mutationFn: (jobId: number) => monitorApi.retryJob(jobId),
    onSuccess: () => {
      toast.success(t('tasks.retrySuccess'))
      queryClient.invalidateQueries({ queryKey: ['monitorJobs'] })
      queryClient.invalidateQueries({ queryKey: ['monitorOverview'] })
      queryClient.invalidateQueries({ queryKey: ['monitorDashboard'] })
      queryClient.invalidateQueries({ queryKey: ['monitorStatus'] })
    },
    onError: (error: Error) => toast.error(`${t('tasks.retryFailed')}: ${error.message}`),
  })

  const jobs = data?.jobs || []
  const counts = useMemo(() => jobs.reduce<Record<string, number>>((result, job) => {
    result[job.status] = (result[job.status] || 0) + 1
    return result
  }, {}), [jobs])

  const normalizedSearch = searchText.trim().toLowerCase()
  const filteredJobs = jobs.filter((job) => {
    if (statusFilter !== 'all' && job.status !== statusFilter) return false
    if (!normalizedSearch) return true
    return job.title.toLowerCase().includes(normalizedSearch) || job.aweme_id.includes(normalizedSearch)
  })

  return (
    <div className="space-y-4 animate-slide-up">
      <section className="rounded-lg glass-panel float-panel overflow-hidden">
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

        <div className="p-4 space-y-4">
          <div className="flex flex-col lg:flex-row gap-3 lg:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-cyber-text-muted" />
              <Input
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder={t('tasks.searchPlaceholder')}
                className="h-9 pl-9 text-xs"
              />
            </div>
            <div className="flex flex-wrap gap-1">
              {STATUS_FILTERS.map((status) => (
                <Button
                  key={status}
                  type="button"
                  size="sm"
                  variant={statusFilter === status ? 'default' : 'outline'}
                  onClick={() => setStatusFilter(status)}
                  className="h-8 px-3 font-mono text-[10px]"
                >
                  {t(`tasks.status.${status}`)}
                  {status !== 'all' ? ` ${counts[status] || 0}` : ` ${jobs.length}`}
                </Button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-left text-cyber-text-muted border-b border-cyber-border-subtle">
                  <th className="py-2 pr-4">{t('tasks.statusColumn')}</th>
                  <th className="py-2 pr-4">{t('tasks.stage')}</th>
                  <th className="py-2 pr-4">{t('tasks.post')}</th>
                  <th className="py-2 pr-4">{t('tasks.dueAt')}</th>
                  <th className="py-2 pr-4">{t('tasks.attempts')}</th>
                  <th className="py-2 pr-4">{t('tasks.reason')}</th>
                  <th className="py-2 text-right">{t('tasks.action')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredJobs.map((job: MonitorJob) => (
                  <tr key={job.id} className="border-b border-cyber-border-subtle/40 text-cyber-text-secondary">
                    <td className="py-2 pr-4">
                      <span className={job.status === 'failed' ? 'text-cyber-neon-pink' : job.status === 'missed' ? 'text-cyber-neon-orange' : job.status === 'done' ? 'text-cyber-neon-green' : 'text-cyber-neon-cyan'}>
                        {job.status}
                      </span>
                    </td>
                    <td className="py-2 pr-4">{job.stage}</td>
                    <td className="py-2 pr-4 max-w-[420px]">
                      <div className="truncate">{job.title || job.aweme_id}</div>
                      <div className="text-[10px] text-cyber-text-muted">{job.aweme_id}</div>
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap">{formatDateTime(job.due_at)}</td>
                    <td className="py-2 pr-4">{job.attempts}</td>
                    <td className="py-2 pr-4 max-w-[360px] truncate" title={job.miss_reason || job.last_error || ''}>
                      {job.miss_reason || job.last_error || '-'}
                    </td>
                    <td className="py-2 text-right">
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
                      ) : (
                        <span className="text-cyber-text-muted">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!isLoading && filteredJobs.length === 0 ? (
              <div className="py-10 text-center text-xs font-mono text-cyber-text-muted">{t('tasks.noJobs')}</div>
            ) : null}
          </div>
        </div>
      </section>
    </div>
  )
}
