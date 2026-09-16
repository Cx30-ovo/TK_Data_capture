import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, Archive, CheckCircle2, Database, HardDrive, Radar, RefreshCw, Server, Wifi } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { StatePanel } from '@/components/ui/state-panel'
import { monitorApi, type MonitorHealthCheck } from '@/lib/api'


type HealthStatus = 'ok' | 'warning' | 'error'

const CHECK_ICONS: Record<string, typeof Activity> = {
  database: Database,
  browser: Wifi,
  monitor_loop: Radar,
  account: Server,
  discovery: Activity,
  disk: HardDrive,
  backup: Archive,
}

const CHECK_GROUPS: Array<{ key: string; icon: typeof Activity; checks: string[] }> = [
  { key: 'runtime', icon: Activity, checks: ['database', 'browser', 'monitor_loop'] },
  { key: 'pipeline', icon: Radar, checks: ['account', 'discovery'] },
  { key: 'maintenance', icon: Archive, checks: ['disk', 'backup'] },
]

const STATUS_CLASSES: Record<HealthStatus, { text: string; border: string; background: string; icon: typeof CheckCircle2 }> = {
  ok: {
    text: 'text-cyber-neon-green',
    border: 'border-cyber-neon-green/35',
    background: 'bg-cyber-neon-green/5',
    icon: CheckCircle2,
  },
  warning: {
    text: 'text-cyber-neon-orange',
    border: 'border-cyber-neon-orange/35',
    background: 'bg-cyber-neon-orange/5',
    icon: AlertTriangle,
  },
  error: {
    text: 'text-cyber-neon-pink',
    border: 'border-cyber-neon-pink/35',
    background: 'bg-cyber-neon-pink/5',
    icon: AlertTriangle,
  },
}


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


function formatGeneratedAt(value?: string): string {
  if (!value) return '-'
  const timestamp = new Date(value)
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString()
}


function displayCheckValue(
  check: MonitorHealthCheck,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (check.key === 'database' && check.value === 'connected') return t('health.values.connected')
  if (check.key === 'monitor_loop') return t(`health.values.${check.value}`, { defaultValue: check.value })
  if (check.key === 'browser') {
    return check.value === '-' ? t('health.values.disconnected') : t('health.values.port', { port: check.value })
  }
  if (check.key === 'discovery') {
    const seconds = Number.parseInt(check.value.replace('s', ''), 10)
    if (!Number.isNaN(seconds)) {
      if (seconds >= 3600) return t('health.values.hoursAgo', { count: Math.floor(seconds / 3600) })
      if (seconds >= 60) return t('health.values.minutesAgo', { count: Math.floor(seconds / 60) })
      return t('health.values.secondsAgo', { count: seconds })
    }
  }
  if (check.key === 'backup') {
    const count = Number.parseInt(check.value, 10)
    if (!Number.isNaN(count)) return t('health.values.backupCount', { count })
  }
  return check.value
}


function displayCheckDetail(
  check: MonitorHealthCheck,
  t: (key: string) => string,
): string {
  if (!check.detail) return ''
  if (['browser', 'account', 'discovery', 'disk', 'backup'].includes(check.key)) {
    return t(`health.details.${check.key}`)
  }
  return check.detail
}


export function MonitorHealth() {
  const { t } = useTranslation('config')
  const { data, error, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['monitorHealth'],
    queryFn: async () => (await monitorApi.getHealth()).data,
    refetchInterval: 30000,
  })

  const checks = data?.checks || []
  const overallStatus: HealthStatus = data?.overall_status || 'warning'
  const statusStyle = STATUS_CLASSES[overallStatus]
  const StatusIcon = statusStyle.icon
  const statusCounts = checks.reduce<Record<HealthStatus, number>>((counts, check) => {
    counts[check.status] += 1
    return counts
  }, { ok: 0, warning: 0, error: 0 })
  const healthyPercent = checks.length > 0 ? Math.round((statusCounts.ok / checks.length) * 100) : 0
  const checkMap = new Map(checks.map((check) => [check.key, check]))

  const metrics = [
    { label: t('health.metrics.unreadAlerts'), value: String(data?.metrics.unread_alerts ?? 0) },
    { label: t('health.metrics.dbSize'), value: formatBytes(data?.metrics.db_size_bytes) },
    { label: t('health.metrics.diskFree'), value: formatBytes(data?.metrics.disk_free_bytes) },
    { label: t('health.metrics.lastSnapshot'), value: formatDateTime(data?.metrics.last_snapshot_at) },
    { label: t('health.metrics.nextSnapshot'), value: formatDateTime(data?.metrics.next_snapshot_at) },
    { label: t('health.metrics.lastBackup'), value: formatDateTime(data?.metrics.last_backup_at) },
    { label: t('health.metrics.backupCount'), value: String(data?.metrics.backup_count ?? 0) },
  ]

  if (error) {
    return (
      <StatePanel
        variant="error"
        title={t('health.loadFailed')}
        description={error.message}
        action={<Button type="button" variant="outline" size="sm" onClick={() => refetch()}><RefreshCw className="h-3.5 w-3.5" />{t('health.refresh')}</Button>}
      />
    )
  }

  if (isLoading) {
    return <StatePanel variant="loading" title={t('health.loading')} />
  }

  return (
    <div className="space-y-3 animate-slide-up">
      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
          <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center">
            <Server className="h-4 w-4 text-cyber-neon-cyan" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('health.title')}</div>
            <div className="text-[10px] text-cyber-text-muted">{t('health.optimizedDescription')}</div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-[10px] font-mono text-cyber-text-muted sm:inline">
              {t('health.updatedAt')}: {formatGeneratedAt(data?.generated_at)}
            </span>
            <Button type="button" variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching} className="h-8 font-mono text-[10px]">
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
              {t('health.refresh')}
            </Button>
          </div>
        </header>

        <div className="p-3 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(240px,0.8fr)_minmax(0,2fr)]">
          <div className={`rounded-md border p-4 ${statusStyle.border} ${statusStyle.background}`}>
            <div className={`flex items-center gap-2 text-sm font-mono ${statusStyle.text}`}>
              <StatusIcon className="h-5 w-5" />
              {t(`health.status.${overallStatus}`)}
            </div>
            <div className="mt-3 text-3xl font-mono text-cyber-text-primary">{healthyPercent}%</div>
            <div className="mt-1 text-[10px] font-mono text-cyber-text-muted">{t('health.healthyPercent')}</div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-cyber-bg-panel">
              <div className={`h-full rounded-full ${overallStatus === 'ok' ? 'bg-cyber-neon-green' : overallStatus === 'warning' ? 'bg-cyber-neon-orange' : 'bg-cyber-neon-pink'}`} style={{ width: `${healthyPercent}%` }} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {(['ok', 'warning', 'error'] as const).map((status) => {
              const style = STATUS_CLASSES[status]
              const Icon = style.icon
              return (
                <div key={status} className={`rounded-md border p-3 ${style.border} ${style.background}`}>
                  <div className={`flex items-center gap-1.5 text-[10px] font-mono ${style.text}`}>
                    <Icon className="h-3.5 w-3.5" />
                    {t(`health.status.${status}`)}
                  </div>
                  <div className="mt-2 text-2xl font-mono text-cyber-text-primary">{statusCounts[status]}</div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-px border-t border-cyber-border-subtle bg-cyber-border-subtle/50 sm:grid-cols-3 xl:grid-cols-7">
          {metrics.map((metric) => (
            <div key={metric.label} className="bg-cyber-bg-panel px-3 py-2.5">
              <div className="text-[9px] font-mono text-cyber-text-muted">{metric.label}</div>
              <div className="mt-1 truncate text-[11px] font-mono text-cyber-text-primary">{metric.value}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        {CHECK_GROUPS.map((group) => {
          const GroupIcon = group.icon
          const groupChecks = group.checks.map((key) => checkMap.get(key)).filter((check): check is MonitorHealthCheck => Boolean(check))
          const groupErrors = groupChecks.filter((check) => check.status === 'error').length
          const groupWarnings = groupChecks.filter((check) => check.status === 'warning').length
          return (
            <section key={group.key} className="rounded-lg glass-panel float-panel overflow-hidden">
              <header className="px-3 py-2.5 border-b border-cyber-border-subtle/50 flex items-center gap-2 bg-cyber-bg-tertiary/30">
                <GroupIcon className="h-4 w-4 text-cyber-neon-cyan" />
                <div className="text-xs font-mono text-cyber-text-primary">{t(`health.groups.${group.key}`)}</div>
                <span className="ml-auto text-[9px] font-mono text-cyber-text-muted">
                  {groupErrors > 0
                    ? t('health.groupErrors', { count: groupErrors })
                    : groupWarnings > 0
                      ? t('health.groupWarnings', { count: groupWarnings })
                      : t('health.groupOk')}
                </span>
              </header>
              <div className="divide-y divide-cyber-border-subtle/50">
                {groupChecks.map((check) => {
                  const CheckIcon = CHECK_ICONS[check.key] || Activity
                  const style = STATUS_CLASSES[check.status]
                  return (
                    <div key={check.key} className={`flex items-start gap-3 border-l-2 px-3 py-3 ${style.border}`}>
                      <CheckIcon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${style.text}`} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-mono text-cyber-text-primary">{t(`health.checks.${check.key}`)}</span>
                          <span className={`ml-auto text-[9px] font-mono ${style.text}`}>{t(`health.status.${check.status}`)}</span>
                        </div>
                        <div className="mt-1 truncate text-xs font-mono text-cyber-text-secondary" title={displayCheckValue(check, t)}>
                          {displayCheckValue(check, t)}
                        </div>
                        {check.detail ? <div className="mt-1 text-[9px] font-mono text-cyber-text-muted">{displayCheckDetail(check, t)}</div> : null}
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
