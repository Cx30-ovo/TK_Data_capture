import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, CheckCircle2, Database, HardDrive, Radar, Server, Wifi } from 'lucide-react'
import { monitorApi } from '@/lib/api'


function formatBytes(bytes?: number): string {
  if (bytes === undefined) return '-'
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${bytes} B`
}


function formatDateTime(timestamp?: number | null): string {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleString()
}


const CHECK_ICONS: Record<string, typeof Activity> = {
  database: Database,
  browser: Wifi,
  monitor_loop: Radar,
  account: Server,
  discovery: Activity,
  disk: HardDrive,
}


export function MonitorHealth() {
  const { t } = useTranslation('config')
  const { data } = useQuery({
    queryKey: ['monitorHealth'],
    queryFn: async () => (await monitorApi.getHealth()).data,
    refetchInterval: 30000,
  })

  const statusColor = data?.overall_status === 'ok' ? 'text-cyber-neon-green' : data?.overall_status === 'warning' ? 'text-cyber-neon-orange' : 'text-cyber-neon-pink'
  const StatusIcon = data?.overall_status === 'ok' ? CheckCircle2 : AlertTriangle

  return (
    <div className="space-y-4 animate-slide-up">
      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
          <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center">
            <Server className="h-4 w-4 text-cyber-neon-cyan" />
          </div>
          <div>
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('health.title')}</div>
            <div className="text-[10px] text-cyber-text-muted">{t('health.description')}</div>
          </div>
          <div className={`ml-auto flex items-center gap-2 text-xs font-mono ${statusColor}`}>
            <StatusIcon className="w-4 h-4" />
            {t(`health.status.${data?.overall_status || 'warning'}`)}
          </div>
        </header>

        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {(data?.checks || []).map((check) => {
              const Icon = CHECK_ICONS[check.key] || Activity
              const color = check.status === 'ok' ? 'text-cyber-neon-green' : check.status === 'warning' ? 'text-cyber-neon-orange' : 'text-cyber-neon-pink'
              return (
                <div key={check.key} className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3">
                  <div className="flex items-center gap-2">
                    <Icon className={`w-4 h-4 ${color}`} />
                    <span className="text-xs font-mono text-cyber-text-primary">{t(`health.checks.${check.key}`)}</span>
                    <span className={`ml-auto text-[10px] font-mono ${color}`}>{check.status}</span>
                  </div>
                  <div className="mt-2 text-sm font-mono text-cyber-text-secondary break-all">{check.value}</div>
                  {check.detail ? <div className="mt-1 text-[10px] font-mono text-cyber-text-muted">{check.detail}</div> : null}
                </div>
              )
            })}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3">
              <div className="text-[10px] font-mono text-cyber-text-muted">{t('health.metrics.unreadAlerts')}</div>
              <div className="mt-1 text-lg font-mono text-cyber-text-primary">{data?.metrics.unread_alerts ?? 0}</div>
            </div>
            <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3">
              <div className="text-[10px] font-mono text-cyber-text-muted">{t('health.metrics.dbSize')}</div>
              <div className="mt-1 text-lg font-mono text-cyber-text-primary">{formatBytes(data?.metrics.db_size_bytes)}</div>
            </div>
            <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3">
              <div className="text-[10px] font-mono text-cyber-text-muted">{t('health.metrics.lastSnapshot')}</div>
              <div className="mt-1 text-xs font-mono text-cyber-text-primary">{formatDateTime(data?.metrics.last_snapshot_at)}</div>
            </div>
            <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3">
              <div className="text-[10px] font-mono text-cyber-text-muted">{t('health.metrics.nextSnapshot')}</div>
              <div className="mt-1 text-xs font-mono text-cyber-text-primary">{formatDateTime(data?.metrics.next_snapshot_at)}</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
