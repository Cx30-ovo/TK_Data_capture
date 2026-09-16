import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Bell, CheckCheck, CheckCircle2, Eye, RefreshCw, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { StatePanel } from '@/components/ui/state-panel'
import { monitorApi, type MonitorAlert } from '@/lib/api'


export type AlertViewFilter = 'open' | 'unread' | 'resolved' | 'ignored' | 'all'
type AlertSeverityFilter = 'all' | MonitorAlert['severity']

interface AlertGroup {
  key: string
  alert_type: string
  severity: MonitorAlert['severity']
  title: string
  message: string
  status: MonitorAlert['status']
  count: number
  first_at: number
  last_at: number
  alert_ids: number[]
}

interface MonitorAlertsProps {
  viewFilter: AlertViewFilter
  onViewFilterChange: (view: AlertViewFilter) => void
  onOpenTasks: (status: string) => void
  focusAlertId?: number
  focusToken?: number
}

const SEVERITY_RANK: Record<MonitorAlert['severity'], number> = { info: 0, warning: 1, error: 2 }
const SEVERITY_BORDER: Record<MonitorAlert['severity'], string> = {
  error: 'border-l-cyber-neon-pink',
  warning: 'border-l-cyber-neon-orange',
  info: 'border-l-cyber-neon-cyan',
}
const SEVERITY_TEXT: Record<MonitorAlert['severity'], string> = {
  error: 'text-cyber-neon-pink',
  warning: 'text-cyber-neon-orange',
  info: 'text-cyber-neon-cyan',
}
const RETRYABLE_ALERT_TYPES = new Set(['snapshot_errors'])
const TASK_ALERT_TYPES = new Set(['snapshot_errors', 'missed_jobs', 'loop_error'])


function formatDateTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}


function groupingStatus(alerts: MonitorAlert[]): MonitorAlert['status'] {
  const statuses = new Set(alerts.map((alert) => alert.status))
  if (statuses.has('unread')) return 'unread'
  if (statuses.has('read')) return 'read'
  if (statuses.size === 1 && statuses.has('resolved')) return 'resolved'
  if (statuses.size === 1 && statuses.has('ignored')) return 'ignored'
  return 'read'
}


function buildAlertGroups(alerts: MonitorAlert[]): AlertGroup[] {
  const grouped = new Map<string, MonitorAlert[]>()
  alerts.forEach((alert) => {
    const key = `${alert.alert_type}:${alert.title}`
    grouped.set(key, [...(grouped.get(key) || []), alert])
  })

  return [...grouped.entries()]
    .map(([key, items]) => {
      const ordered = [...items].sort((left, right) => right.created_at - left.created_at)
      const latest = ordered[0]
      const severity = ordered.reduce<MonitorAlert['severity']>(
        (current, alert) => SEVERITY_RANK[alert.severity] > SEVERITY_RANK[current] ? alert.severity : current,
        'info',
      )
      return {
        key,
        alert_type: latest.alert_type,
        severity,
        title: latest.title,
        message: latest.message,
        status: groupingStatus(ordered),
        count: ordered.length,
        first_at: Math.min(...ordered.map((alert) => alert.created_at)),
        last_at: Math.max(...ordered.map((alert) => alert.created_at)),
        alert_ids: ordered.map((alert) => alert.id),
      }
    })
    .sort((left, right) => right.last_at - left.last_at)
}


export function MonitorAlerts({ viewFilter, onViewFilterChange, onOpenTasks, focusAlertId, focusToken }: MonitorAlertsProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [severityFilter, setSeverityFilter] = useState<AlertSeverityFilter>('all')
  const [focusedGroupKey, setFocusedGroupKey] = useState('')
  const handledFocusToken = useRef<number | undefined>()
  const { data } = useQuery({
    queryKey: ['monitorAlerts', 'all'],
    queryFn: async () => (await monitorApi.getAlerts()).data,
    refetchInterval: 30000,
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['monitorAlerts'] })
    queryClient.invalidateQueries({ queryKey: ['monitorHealth'] })
  }

  const statusMutation = useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: MonitorAlert['status'] }) =>
      monitorApi.updateAlertsStatus(ids, status),
    onSuccess: (response, variables) => {
      if (variables.status === 'ignored') toast.success(t('alerts.ignored', { count: response.data.updated }))
      if (variables.status === 'resolved') toast.success(t('alerts.resolved', { count: response.data.updated }))
      refresh()
    },
    onError: (error: Error) => toast.error(`${t('alerts.actionFailed')}: ${error.message}`),
  })

  const retryMutation = useMutation({
    mutationFn: () => monitorApi.retryFailedJobs(),
    onSuccess: (response) => {
      toast.success(response.data.updated > 0
        ? t('alerts.retrySuccess', { count: response.data.updated })
        : t('alerts.retryEmpty'))
      refresh()
      queryClient.invalidateQueries({ queryKey: ['monitorJobs'] })
    },
    onError: (error: Error) => toast.error(`${t('alerts.actionFailed')}: ${error.message}`),
  })

  const markAllRead = useMutation({
    mutationFn: () => monitorApi.markAllAlertsRead(),
    onSuccess: (response) => {
      toast.success(t('alerts.markedAll', { count: response.data.updated }))
      refresh()
    },
  })

  const groups = useMemo(() => buildAlertGroups(data?.alerts || []), [data])
  const visibleGroups = groups.filter((group) => {
    const matchesView = viewFilter === 'all'
      || (viewFilter === 'open' && group.status !== 'resolved' && group.status !== 'ignored')
      || group.status === viewFilter
    const matchesSeverity = severityFilter === 'all' || group.severity === severityFilter
    return matchesView && matchesSeverity
  })

  useEffect(() => {
    if (!focusAlertId || focusToken === undefined || handledFocusToken.current === focusToken) return
    const group = groups.find((item) => item.alert_ids.includes(focusAlertId))
    if (!group) return
    handledFocusToken.current = focusToken
    onViewFilterChange('all')
    setSeverityFilter('all')
    setFocusedGroupKey(group.key)
    window.setTimeout(() => {
      document.getElementById(`monitor-alert-group-${group.key}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 80)
    window.setTimeout(() => {
      setFocusedGroupKey((current) => current === group.key ? '' : current)
    }, 2600)
  }, [focusAlertId, focusToken, groups, onViewFilterChange])

  const viewTask = (group: AlertGroup) => {
    onOpenTasks(group.alert_type === 'missed_jobs' ? 'missed' : 'failed')
  }

  return (
    <section className="rounded-lg glass-panel float-panel overflow-hidden animate-slide-up">
      <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
        <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center">
          <Bell className="h-4 w-4 text-cyber-neon-orange" />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('alerts.title')}</div>
          <div className="text-[10px] text-cyber-text-muted">{t('alerts.groupedDescription')}</div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[10px] font-mono text-cyber-neon-orange">{t('alerts.unread', { count: data?.unread ?? 0 })}</span>
          <Button type="button" variant="outline" size="sm" onClick={() => markAllRead.mutate()} disabled={markAllRead.isPending || (data?.unread ?? 0) === 0} className="h-8 font-mono text-[10px]">
            <CheckCheck className="w-3.5 h-3.5" />
            {t('alerts.markAllRead')}
          </Button>
        </div>
      </header>

      <div className="p-3 space-y-3">
        <div className="flex flex-col xl:flex-row gap-2 xl:items-center">
          <div className="flex gap-1 overflow-x-auto rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-1">
            {(['open', 'unread', 'resolved', 'ignored', 'all'] as const).map((view) => (
              <button
                key={view}
                type="button"
                onClick={() => onViewFilterChange(view)}
                className={`shrink-0 rounded px-2.5 py-1.5 text-[10px] font-mono transition-colors ${viewFilter === view ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'text-cyber-text-muted hover:bg-cyber-bg-tertiary hover:text-cyber-text-primary'}`}
              >
                {t(`alerts.view.${view}`)}
              </button>
            ))}
          </div>
          <div className="flex gap-1 overflow-x-auto rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-1 xl:ml-auto">
            {(['all', 'error', 'warning', 'info'] as const).map((severity) => (
              <button
                key={severity}
                type="button"
                onClick={() => setSeverityFilter(severity)}
                className={`shrink-0 rounded px-2.5 py-1.5 text-[10px] font-mono transition-colors ${severityFilter === severity ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'text-cyber-text-muted hover:bg-cyber-bg-tertiary hover:text-cyber-text-primary'}`}
              >
                {t(`alerts.severity.${severity}`)}
              </button>
            ))}
          </div>
        </div>

        {visibleGroups.length > 0 ? (
          <div className="max-h-[58vh] space-y-2 overflow-y-auto pr-1">
            {visibleGroups.map((group) => {
              const canManage = group.status !== 'resolved' && group.status !== 'ignored'
              return (
                <div
                  key={group.key}
                  id={`monitor-alert-group-${group.key}`}
                  className={`rounded-md border border-cyber-border-subtle border-l-4 bg-cyber-bg-tertiary/20 p-3 transition-shadow ${SEVERITY_BORDER[group.severity]} ${focusedGroupKey === group.key ? 'ring-1 ring-cyber-neon-cyan/50' : ''}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-mono text-cyber-text-primary">{group.title}</span>
                        <span className={`text-[10px] font-mono ${SEVERITY_TEXT[group.severity]}`}>{t(`alerts.severity.${group.severity}`)}</span>
                        <span className="rounded border border-cyber-border-subtle bg-cyber-bg-panel px-1.5 py-0.5 text-[9px] font-mono text-cyber-text-muted">
                          {t('alerts.occurrences', { count: group.count })}
                        </span>
                        {group.status === 'unread' ? <span className="h-1.5 w-1.5 rounded-full bg-cyber-neon-orange" /> : null}
                      </div>
                      <div className="mt-1 text-[11px] font-mono text-cyber-text-secondary">{group.message}</div>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[9px] font-mono text-cyber-text-muted">
                        <span>{t('alerts.firstAt')}: {formatDateTime(group.first_at)}</span>
                        <span>{t('alerts.lastAt')}: {formatDateTime(group.last_at)}</span>
                        <span>{group.alert_type}</span>
                      </div>
                    </div>
                    <span className="whitespace-nowrap text-[9px] font-mono text-cyber-text-muted">{t(`alerts.status.${group.status}`)}</span>
                  </div>
                  <div className="mt-3 flex flex-wrap justify-end gap-1 border-t border-cyber-border-subtle/50 pt-2">
                    {TASK_ALERT_TYPES.has(group.alert_type) ? (
                      <Button type="button" variant="ghost" size="sm" onClick={() => viewTask(group)} className="h-7 px-2 font-mono text-[10px]">
                        <Eye className="w-3 h-3" />
                        {t('alerts.viewTask')}
                      </Button>
                    ) : null}
                    {RETRYABLE_ALERT_TYPES.has(group.alert_type) ? (
                      <Button type="button" variant="outline" size="sm" onClick={() => retryMutation.mutate()} disabled={retryMutation.isPending} className="h-7 px-2 font-mono text-[10px]">
                        <RefreshCw className="w-3 h-3" />
                        {t('alerts.retry')}
                      </Button>
                    ) : null}
                    {canManage ? (
                      <>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => statusMutation.mutate({ ids: group.alert_ids, status: 'ignored' })}
                          disabled={statusMutation.isPending}
                          className="h-7 px-2 font-mono text-[10px] text-cyber-text-muted"
                        >
                          <XCircle className="w-3 h-3" />
                          {t('alerts.ignore')}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => statusMutation.mutate({ ids: group.alert_ids, status: 'resolved' })}
                          disabled={statusMutation.isPending}
                          className="h-7 px-2 font-mono text-[10px]"
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          {t('alerts.resolve')}
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <StatePanel variant="empty" title={t('alerts.empty')} />
        )}
      </div>
    </section>
  )
}
