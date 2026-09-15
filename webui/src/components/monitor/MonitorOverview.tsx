import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { CalendarClock, Camera, CircleAlert, PlusCircle, Radar } from 'lucide-react'
import { monitorApi } from '@/lib/api'


function formatDateTime(timestamp: number | null): string {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleString()
}


function formatCountdown(timestamp: number | null): string {
  if (!timestamp) return '-'
  const seconds = timestamp - Math.floor(Date.now() / 1000)
  if (seconds <= 0) return '即将执行'
  if (seconds >= 3600) return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分后`
  if (seconds >= 60) return `${Math.floor(seconds / 60)} 分钟后`
  return `${seconds} 秒后`
}


export function MonitorOverview() {
  const { t } = useTranslation('config')
  const { data } = useQuery({
    queryKey: ['monitorOverview'],
    queryFn: async () => (await monitorApi.getOverview()).data,
    refetchInterval: 30000,
  })

  const jobCounts = data?.jobs || {}
  const abnormalJobs = data?.recent_abnormal_jobs || []

  return (
    <div className="space-y-4 animate-slide-up">
      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
          <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center">
            <Radar className="h-4 w-4 text-cyber-neon-cyan" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('overview.title')}</div>
            <div className="text-[10px] text-cyber-text-muted">{t('overview.description')}</div>
          </div>
          <div className="ml-auto text-[10px] font-mono text-cyber-text-muted">
            {t('overview.updatedAt')}: {data?.generated_at || '-'}
          </div>
        </header>

        <div className="p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-4">
            <div className="flex items-center gap-2 text-[10px] font-mono text-cyber-text-muted">
              <CalendarClock className="w-4 h-4 text-cyber-neon-cyan" />
              {t('overview.nextDiscovery')}
            </div>
            <div className="mt-2 text-base font-mono text-cyber-text-primary">{formatDateTime(data?.next_discovery_at ?? null)}</div>
            <div className="mt-1 text-[10px] font-mono text-cyber-neon-cyan">{formatCountdown(data?.next_discovery_at ?? null)}</div>
          </div>

          <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-4">
            <div className="flex items-center gap-2 text-[10px] font-mono text-cyber-text-muted">
              <Camera className="w-4 h-4 text-cyber-neon-green" />
              {t('overview.nextSnapshot')}
            </div>
            <div className="mt-2 text-base font-mono text-cyber-text-primary">{formatDateTime(data?.next_snapshot?.due_at ?? null)}</div>
            <div className="mt-1 text-[10px] font-mono text-cyber-neon-green">
              {data?.next_snapshot ? `${data.next_snapshot.stage} · ${formatCountdown(data.next_snapshot.due_at)}` : t('overview.noPendingSnapshot')}
            </div>
          </div>

          <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-4">
            <div className="flex items-center gap-2 text-[10px] font-mono text-cyber-text-muted">
              <PlusCircle className="w-4 h-4 text-cyber-neon-purple" />
              {t('overview.todayNewPosts')}
            </div>
            <div className="mt-2 text-2xl font-mono text-cyber-text-primary">{data?.today_new_posts ?? 0}</div>
            <div className="mt-1 text-[10px] font-mono text-cyber-text-muted">{t('overview.todayUnit')}</div>
          </div>

          <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-4">
            <div className="flex items-center gap-2 text-[10px] font-mono text-cyber-text-muted">
              <CircleAlert className="w-4 h-4 text-cyber-neon-orange" />
              {t('overview.abnormalJobs')}
            </div>
            <div className="mt-2 text-2xl font-mono text-cyber-text-primary">{data?.abnormal_total ?? 0}</div>
            <div className="mt-1 text-[10px] font-mono text-cyber-text-muted">
              failed: {jobCounts.failed ?? 0} · missed: {jobCounts.missed ?? 0}
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30">
          <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('overview.recentAbnormal')}</div>
        </header>
        <div className="p-4">
          {abnormalJobs.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-left text-cyber-text-muted border-b border-cyber-border-subtle">
                    <th className="py-2 pr-4">{t('overview.status')}</th>
                    <th className="py-2 pr-4">{t('overview.stage')}</th>
                    <th className="py-2 pr-4">{t('overview.post')}</th>
                    <th className="py-2 pr-4">{t('overview.time')}</th>
                    <th className="py-2">{t('overview.reason')}</th>
                  </tr>
                </thead>
                <tbody>
                  {abnormalJobs.map((job) => (
                    <tr key={job.id} className="border-b border-cyber-border-subtle/40 text-cyber-text-secondary">
                      <td className={`py-2 pr-4 ${job.status === 'failed' ? 'text-cyber-neon-pink' : 'text-cyber-neon-orange'}`}>{job.status}</td>
                      <td className="py-2 pr-4">{job.stage}</td>
                      <td className="py-2 pr-4 max-w-[420px] truncate">{job.title}</td>
                      <td className="py-2 pr-4 whitespace-nowrap">{formatDateTime(job.due_at)}</td>
                      <td className="py-2 max-w-[360px] truncate">{job.miss_reason || job.last_error || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-8 text-center text-xs font-mono text-cyber-text-muted">{t('overview.noAbnormal')}</div>
          )}
        </div>
      </section>
    </div>
  )
}
