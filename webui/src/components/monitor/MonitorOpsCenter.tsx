import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, Bell, ListChecks, Server, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { MonitorTasks } from '@/components/monitor/MonitorTasks'
import { MonitorHealth } from '@/components/monitor/MonitorHealth'
import { MonitorAlerts, type AlertViewFilter } from '@/components/monitor/MonitorAlerts'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { monitorApi } from '@/lib/api'


type Tone = 'neutral' | 'ok' | 'warning' | 'error' | 'info'

export interface MonitorOpsTarget {
  section: 'tasks' | 'alerts' | 'health'
  taskStatus?: string
  alertView?: AlertViewFilter
  jobId?: number
  alertId?: number
  token: number
}


const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'border-cyber-border-subtle bg-cyber-bg-tertiary/20',
  ok: 'border-cyber-neon-green/35 bg-cyber-neon-green/5',
  warning: 'border-cyber-neon-orange/35 bg-cyber-neon-orange/5',
  error: 'border-cyber-neon-pink/35 bg-cyber-neon-pink/5',
  info: 'border-cyber-neon-cyan/35 bg-cyber-neon-cyan/5',
}


function MetricButton({
  active,
  icon: Icon,
  label,
  value,
  detail,
  tone,
  onClick,
}: {
  active: boolean
  icon: typeof ListChecks
  label: string
  value: string
  detail?: string
  tone: Tone
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      data-active={active ? 'true' : 'false'}
      data-tone={tone}
      onClick={onClick}
      className={`ops-metric-card ${TONE_CLASSES[tone]}`}
    >
      <div className="flex items-center gap-2 text-[11px] font-medium text-cyber-text-muted">
        <span className="ops-metric-icon"><Icon aria-hidden="true" className="h-4 w-4" /></span>
        {label}
      </div>
      <div className="mt-3 text-2xl font-semibold numeric-value text-cyber-text-primary">{value}</div>
      {detail ? <div className="mt-1 text-[10px] leading-4 text-cyber-text-muted">{detail}</div> : null}
    </button>
  )
}


export function MonitorOpsCenter({ target }: { target?: MonitorOpsTarget }) {
  const { t } = useTranslation('config')
  const [section, setSection] = useState('tasks')
  const [taskStatus, setTaskStatus] = useState('pending')
  const [alertView, setAlertView] = useState<AlertViewFilter>('open')
  const { data: health } = useQuery({
    queryKey: ['monitorHealth'],
    queryFn: async () => (await monitorApi.getHealth()).data,
    refetchInterval: 30000,
  })

  const jobs = health?.metrics.jobs || {}
  const pendingCount = jobs.pending || 0
  const failedCount = jobs.failed || 0
  const missedCount = jobs.missed || 0
  const abnormalCount = failedCount + missedCount
  const unreadCount = health?.metrics.unread_alerts || 0
  const overallStatus = health?.overall_status || 'warning'
  const statusColor = overallStatus === 'ok'
    ? 'text-cyber-neon-green'
    : overallStatus === 'warning'
      ? 'text-cyber-neon-orange'
      : 'text-cyber-neon-pink'

  useEffect(() => {
    if (!target) return
    setSection(target.section)
    if (target.taskStatus) setTaskStatus(target.taskStatus)
    if (target.alertView) setAlertView(target.alertView)
  }, [target])

  const openTasks = (status: string) => {
    setTaskStatus(status)
    setSection('tasks')
  }
  const openAlerts = (view: AlertViewFilter) => {
    setAlertView(view)
    setSection('alerts')
  }

  return (
    <Tabs value={section} onValueChange={setSection} className="workspace-page space-y-3 animate-slide-up">
      <section className="workspace-hero p-4 sm:p-5">
        <div className="workspace-hero-grid" aria-hidden="true" />
        <div className="relative z-10 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="workspace-hero-icon"><ShieldCheck aria-hidden="true" className="h-5 w-5" /></span>
            <div className="min-w-0">
              <Badge variant="secondary" className="mb-2"><Activity aria-hidden="true" className="h-3 w-3" />{t('opsCenter.workspaceLabel')}</Badge>
              <h1 className="workspace-title">{t('opsCenter.title')}</h1>
              <p className="workspace-description">{t('opsCenter.description')}</p>
            </div>
          </div>
          <div className="workspace-status-card">
            <span className={`workspace-status-dot ${overallStatus === 'ok' ? 'bg-status-success' : overallStatus === 'error' ? 'bg-status-danger' : 'bg-status-warning'}`} />
            <div><div className="text-[10px] text-cyber-text-muted">{t('opsCenter.systemSummary')}</div><div className="mt-0.5 text-sm font-semibold text-cyber-text-primary">{t(`health.status.${overallStatus}`)}</div></div>
            <div className="ml-auto text-right"><div className="text-[10px] text-cyber-text-muted">{t('opsCenter.attentionSummary')}</div><div className="mt-0.5 text-sm font-semibold numeric-value text-cyber-text-primary">{abnormalCount + unreadCount}</div></div>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        <MetricButton
          active={section === 'tasks' && taskStatus === 'pending'}
          icon={ListChecks}
          label={t('opsCenter.metrics.pending')}
          value={String(pendingCount)}
          detail={t('opsCenter.metrics.pendingDetail')}
          tone="info"
          onClick={() => openTasks('pending')}
        />
        <MetricButton
          active={section === 'tasks' && taskStatus === 'abnormal'}
          icon={AlertTriangle}
          label={t('opsCenter.metrics.abnormal')}
          value={String(abnormalCount)}
          detail={t('opsCenter.metrics.abnormalDetail', { failed: failedCount, missed: missedCount })}
          tone={abnormalCount > 0 ? 'error' : 'ok'}
          onClick={() => openTasks('abnormal')}
        />
        <MetricButton
          active={section === 'alerts'}
          icon={Bell}
          label={t('opsCenter.metrics.unread')}
          value={String(unreadCount)}
          detail={t('opsCenter.metrics.unreadDetail')}
          tone={unreadCount > 0 ? 'warning' : 'ok'}
          onClick={() => openAlerts('unread')}
        />
        <MetricButton
          active={section === 'health'}
          icon={Server}
          label={t('opsCenter.metrics.system')}
          value={t(`health.status.${overallStatus}`)}
          detail={t('opsCenter.metrics.systemDetail')}
          tone={overallStatus === 'ok' ? 'ok' : overallStatus === 'error' ? 'error' : 'warning'}
          onClick={() => setSection('health')}
        />
      </div>

      <TabsList className="ops-section-nav h-auto w-full flex-wrap justify-start gap-1 p-1" aria-label={t('opsCenter.navigationLabel')}>
        <TabsTrigger value="tasks" className="min-h-10 gap-2 px-4 py-2 text-xs">
          <ListChecks aria-hidden="true" className="h-4 w-4" />
          {t('opsCenter.tasks')}
        </TabsTrigger>
        <TabsTrigger value="alerts" className="min-h-10 gap-2 px-4 py-2 text-xs">
          <Bell aria-hidden="true" className="h-4 w-4" />
          {t('opsCenter.alerts')}
          {unreadCount > 0 ? <span className={`text-[10px] ${statusColor}`}>{unreadCount}</span> : null}
        </TabsTrigger>
        <TabsTrigger value="health" className="min-h-10 gap-2 px-4 py-2 text-xs">
          <Server aria-hidden="true" className="h-4 w-4" />
          {t('opsCenter.health')}
        </TabsTrigger>
      </TabsList>

      <TabsContent value="tasks" className="mt-0">
        <MonitorTasks
          statusFilter={taskStatus}
          onStatusFilterChange={setTaskStatus}
          focusJobId={target?.section === 'tasks' ? target.jobId : undefined}
          focusToken={target?.section === 'tasks' ? target.token : undefined}
        />
      </TabsContent>
      <TabsContent value="alerts" className="mt-0">
        <MonitorAlerts
          viewFilter={alertView}
          onViewFilterChange={setAlertView}
          onOpenTasks={openTasks}
          focusAlertId={target?.section === 'alerts' ? target.alertId : undefined}
          focusToken={target?.section === 'alerts' ? target.token : undefined}
        />
      </TabsContent>
      <TabsContent value="health" className="mt-0">
        <MonitorHealth />
      </TabsContent>
    </Tabs>
  )
}
