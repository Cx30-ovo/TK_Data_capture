import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Sparkles, UsersRound } from 'lucide-react'
import { monitorApi } from '@/lib/api'


function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
}


export function MonitorAccountComparison() {
  const { t } = useTranslation('config')
  const { data } = useQuery({
    queryKey: ['monitorAccountComparison'],
    queryFn: async () => (await monitorApi.getAccountComparison()).data.accounts,
    refetchInterval: 60000,
  })
  const accounts = data || []
  if (accounts.length <= 1) return null
  const maxPosts = Math.max(...accounts.map((account) => account.posts), 1)

  return (
    <section className="overview-panel p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-cyber-text-primary">
          <span className="flex h-8 w-8 items-center justify-center rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/45">
            <UsersRound className="h-4 w-4 text-status-info" />
          </span>
          {t('accountComparison.title')}
        </div>
        <span className="text-[11px] text-cyber-text-muted">{t('accountComparison.hint')}</span>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        {accounts.map((account, index) => (
          <div key={account.id} className="metric-surface-card p-3">
            <div className="flex items-center gap-2"><span className={`grid h-6 w-6 place-items-center rounded text-[10px] font-bold ${index === 0 ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'bg-cyber-bg-panel text-cyber-text-muted'}`}>{index + 1}</span><span className="min-w-0 flex-1 truncate text-xs font-medium text-cyber-text-primary">{account.display_name}</span><span className={`h-2 w-2 rounded-full ${account.enabled ? 'bg-cyber-neon-green' : 'bg-cyber-text-muted'}`} /></div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div><div className="text-[10px] leading-4 text-cyber-text-muted">{t('performance.totalInteraction')}</div><div className="mt-1 text-sm font-semibold numeric-value text-status-info">{formatNumber(account.total_interaction)}</div></div>
              <div><div className="text-[10px] leading-4 text-cyber-text-muted">{t('performance.averageInteraction')}</div><div className="mt-1 text-sm font-semibold numeric-value text-status-success">{formatNumber(account.average_interaction)}</div></div>
              <div><div className="text-[10px] leading-4 text-cyber-text-muted">{t('performance.medianInteraction')}</div><div className="mt-1 text-sm font-semibold numeric-value text-status-purple">{formatNumber(account.median_interaction)}</div></div>
            </div>
            <div className="mt-3 space-y-2">
              <div><div className="flex items-center justify-between text-[10px] text-cyber-text-muted"><span className="inline-flex items-center gap-1"><BarChart3 className="h-3 w-3" />{t('performance.posts')}</span><span className="numeric-value text-cyber-text-secondary">{account.posts}</span></div><div className="mt-1 h-1.5 rounded-sm bg-cyber-bg-panel"><div className="h-full rounded-sm bg-status-info" style={{ width: `${Math.max(account.posts ? .75 : 0, account.posts / maxPosts * 100)}%` }} /></div></div>
              <div><div className="flex items-center justify-between text-[10px] text-cyber-text-muted"><span className="inline-flex items-center gap-1"><Sparkles className="h-3 w-3" />{t('performance.burstRate')}</span><span className="numeric-value text-cyber-text-secondary">{account.burst_rate.toFixed(1)}%</span></div><div className="mt-1 h-1.5 rounded-sm bg-cyber-bg-panel"><div className="h-full rounded-sm bg-status-warning" style={{ width: `${Math.max(account.burst_rate ? .75 : 0, account.burst_rate)}%` }} /></div></div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-[10px] text-cyber-text-muted"><span>{t('performance.zeroRate')}: {account.zero_rate.toFixed(1)}%</span><span>·</span><span>{t('monitorDashboard.snapshots')}: {account.snapshots}</span><span>·</span><span>{t('tasks.status.failed')}: {account.jobs.failed || 0}</span><span>·</span><span>{t('tasks.status.missed')}: {account.jobs.missed || 0}</span></div>
          </div>
        ))}
      </div>
    </section>
  )
}
