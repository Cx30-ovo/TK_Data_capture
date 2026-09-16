import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Bell, ListChecks, Server } from 'lucide-react'
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
      onClick={onClick}
      className={`rounded-md border p-3 text-left transition-colors ${TONE_CLASSES[tone]} ${active ? 'ring-1 ring-cyber-neon-cyan/50' : 'hover:border-cyber-border-default'}`}
    >
      <div className="flex items-center gap-2 text-[10px] font-mono text-cyber-text-muted">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-1.5 text-xl font-mono text-cyber-text-primary">{value}</div>
      {detail ? <div className="mt-0.5 truncate text-[9px] font-mono text-cyber-text-muted">{detail}</div> : null}
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
    <Tabs value={section} onValueChange={setSection} className="space-y-3 animate-slide-up">
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

      <TabsList className="h-auto w-fit max-w-full flex-wrap justify-start gap-1 p-1">
        <TabsTrigger value="tasks" className="gap-2 px-3 py-1.5 text-xs">
          <ListChecks className="w-3.5 h-3.5" />
          {t('opsCenter.tasks')}
        </TabsTrigger>
        <TabsTrigger value="alerts" className="gap-2 px-3 py-1.5 text-xs">
          <Bell className="w-3.5 h-3.5" />
          {t('opsCenter.alerts')}
          {unreadCount > 0 ? <span className={`text-[10px] ${statusColor}`}>{unreadCount}</span> : null}
        </TabsTrigger>
        <TabsTrigger value="health" className="gap-2 px-3 py-1.5 text-xs">
          <Server className="w-3.5 h-3.5" />
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
