import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Bell, CalendarClock, Camera, ChevronRight, CircleAlert, PlusCircle, Radar } from 'lucide-react'
import { monitorApi, type MonitorAlert } from '@/lib/api'
import { MonitorAccountComparison } from '@/components/monitor/MonitorAccountComparison'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'


type EventKind = 'post' | 'snapshot' | 'job' | 'alert'
type IssueKind = 'job' | 'alert'

interface MonitorOverviewProps {
  onOpenTasks: (status?: string, jobId?: number) => void
  onOpenAlerts: (alertId?: number) => void
  onOpenData: (awemeId?: string) => void
}

interface TimelineEvent {
  id: string
  kind: EventKind
  title: string
  detail: string
  timestamp: number
  awemeId?: string
  jobId?: number
  alertId?: number
}

interface OverviewIssue {
  id: string
  kind: IssueKind
  severity: MonitorAlert['severity']
  title: string
  detail: string
  timestamp: number
  count?: number
  jobId?: number
  jobStatus?: string
  alertId?: number
}

const SEVERITY_RANK: Record<MonitorAlert['severity'], number> = { info: 1, warning: 2, error: 3 }
const SEVERITY_CLASSES: Record<MonitorAlert['severity'], string> = {
  error: 'border-l-cyber-neon-pink text-cyber-neon-pink',
  warning: 'border-l-cyber-neon-orange text-cyber-neon-orange',
  info: 'border-l-cyber-neon-cyan text-cyber-neon-cyan',
}


function formatDateTime(timestamp?: number | null): string {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleString()
}


function formatRelativeTime(timestamp: number, t: (key: string, options?: Record<string, unknown>) => string): string {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000) - timestamp)
  if (seconds < 60) return t('overview.relative.justNow')
  if (seconds < 3600) return t('overview.relative.minutesAgo', { count: Math.floor(seconds / 60) })
  if (seconds < 86400) return t('overview.relative.hoursAgo', { count: Math.floor(seconds / 3600) })
  return t('overview.relative.daysAgo', { count: Math.floor(seconds / 86400) })
}


function formatCountdown(timestamp: number | null | undefined, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (!timestamp) return t('overview.countdown.none')
  const seconds = timestamp - Math.floor(Date.now() / 1000)
  if (seconds <= 0) return t('overview.countdown.due')
  if (seconds >= 86400) return t('overview.countdown.days', { count: Math.floor(seconds / 86400) })
  if (seconds >= 3600) return t('overview.countdown.hours', { count: Math.floor(seconds / 3600) })
  if (seconds >= 60) return t('overview.countdown.minutes', { count: Math.floor(seconds / 60) })
  return t('overview.countdown.seconds', { count: seconds })
}


function MetricButton({
  icon: Icon,
  label,
  value,
  detail,
  tone,
  onClick,
}: {
  icon: typeof PlusCircle
  label: string
  value: string
  detail: string
  tone: 'info' | 'warning' | 'error' | 'success'
  onClick: () => void
}) {
  const toneClasses = {
    info: 'border-cyber-neon-cyan/30 bg-cyber-neon-cyan/5 text-cyber-neon-cyan',
    warning: 'border-cyber-neon-orange/30 bg-cyber-neon-orange/5 text-cyber-neon-orange',
    error: 'border-cyber-neon-pink/30 bg-cyber-neon-pink/5 text-cyber-neon-pink',
    success: 'border-cyber-neon-green/30 bg-cyber-neon-green/5 text-cyber-neon-green',
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group rounded-lg border p-4 text-left transition-all hover:-translate-y-0.5 hover:border-cyber-border-default ${toneClasses[tone]}`}
    >
      <div className="flex items-center gap-2 text-[10px] font-mono">
        <Icon className="h-4 w-4" />
        <span className="text-cyber-text-muted">{label}</span>
        <ChevronRight className="ml-auto h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
      <div className="mt-3 text-2xl font-mono text-cyber-text-primary">{value}</div>
      <div className="mt-1 truncate text-[10px] font-mono text-cyber-text-muted">{detail}</div>
    </button>
  )
}


export function MonitorOverview({ onOpenTasks, onOpenAlerts, onOpenData }: MonitorOverviewProps) {
  const { t } = useTranslation('config')
  const activeAccountId = useMonitorAccountStore((state) => state.activeAccountId)
  const { data } = useQuery({
    queryKey: ['monitorOverview'],
    queryFn: async () => (await monitorApi.getOverview()).data,
    refetchInterval: 30000,
  })
  const { data: dashboard } = useQuery({
    queryKey: ['monitorDashboard'],
    queryFn: async () => (await monitorApi.getDashboard(50)).data,
    refetchInterval: 30000,
  })
  const { data: alertData } = useQuery({
    queryKey: ['monitorAlerts', 'all'],
    queryFn: async () => (await monitorApi.getAlerts()).data,
    refetchInterval: 30000,
  })

  const jobCounts = data?.jobs || {}
  const abnormalJobs = data?.recent_abnormal_jobs || []
  const posts = dashboard?.posts || []
  const alerts = alertData?.alerts || []
  const startOfDay = new Date().setHours(0, 0, 0, 0) / 1000
  const recentPost = posts.find((post) => post.first_seen_at >= startOfDay) || posts[0]

  const timelineEvents = useMemo(() => {
    const events: TimelineEvent[] = []
    posts.forEach((post) => {
      if (post.first_seen_at) {
        events.push({
          id: `post-${post.aweme_id}`,
          kind: 'post',
          title: post.title || post.aweme_id,
          detail: t('overview.timeline.newPost'),
          timestamp: post.first_seen_at,
          awemeId: post.aweme_id,
        })
      }
      post.snapshots.forEach((snapshot) => {
        events.push({
          id: `snapshot-${post.aweme_id}-${snapshot.stage}-${snapshot.captured_at}`,
          kind: 'snapshot',
          title: post.title || post.aweme_id,
          detail: t('overview.timeline.snapshotComplete', { stage: snapshot.stage }),
          timestamp: snapshot.captured_at,
          awemeId: post.aweme_id,
        })
      })
    })
    abnormalJobs.forEach((job) => {
      events.push({
        id: `job-${job.id}-${job.due_at}`,
        kind: 'job',
        title: job.title || job.aweme_id,
        detail: job.status === 'failed' ? t('overview.timeline.taskFailed') : t('overview.timeline.taskMissed'),
        timestamp: job.due_at,
        jobId: job.id,
      })
    })
    alerts.forEach((alert) => {
      events.push({
        id: `alert-${alert.id}`,
        kind: 'alert',
        title: alert.title,
        detail: alert.message,
        timestamp: alert.created_at,
        alertId: alert.id,
      })
    })
    return events.filter((event) => event.timestamp > 0).sort((left, right) => right.timestamp - left.timestamp).slice(0, 14)
  }, [alerts, abnormalJobs, posts, t])

  const issues = useMemo(() => {
    const items: OverviewIssue[] = abnormalJobs.filter((job) => job.status === 'failed').map((job) => ({
      id: `job-${job.id}`,
      kind: 'job',
      severity: 'error',
      title: job.title || job.aweme_id,
      detail: job.last_error || job.miss_reason || job.stage,
      timestamp: job.due_at,
      jobId: job.id,
      jobStatus: job.status,
    }))
    const alertGroups = new Map<string, OverviewIssue>()
    alerts.filter((alert) => alert.status === 'unread' || alert.status === 'read').forEach((alert) => {
      const key = `${alert.alert_type}:${alert.title}`
      const current = alertGroups.get(key)
      if (current) {
        current.count = (current.count || 1) + 1
        current.timestamp = Math.max(current.timestamp, alert.created_at)
        if (SEVERITY_RANK[alert.severity] > SEVERITY_RANK[current.severity]) current.severity = alert.severity
        current.alertId = alert.id
      } else {
        alertGroups.set(key, {
          id: `alert-${key}`,
          kind: 'alert',
          severity: alert.severity,
          title: alert.title,
          detail: alert.message,
          timestamp: alert.created_at,
          count: 1,
          alertId: alert.id,
        })
      }
    })
    return [...items, ...alertGroups.values()]
      .sort((left, right) => SEVERITY_RANK[right.severity] - SEVERITY_RANK[left.severity] || right.timestamp - left.timestamp)
      .slice(0, 8)
  }, [abnormalJobs, alerts])

  const openEvent = (event: TimelineEvent) => {
    if (event.kind === 'post' || event.kind === 'snapshot') onOpenData(event.awemeId)
    if (event.kind === 'job') onOpenTasks('abnormal', event.jobId)
    if (event.kind === 'alert') onOpenAlerts(event.alertId)
  }

  const openIssue = (issue: OverviewIssue) => {
    if (issue.kind === 'job') onOpenTasks(issue.jobStatus || 'abnormal', issue.jobId)
    if (issue.kind === 'alert') onOpenAlerts(issue.alertId)
  }

  return (
    <div className="space-y-3 animate-slide-up">
      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
          <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center">
            <Radar className="h-4 w-4 text-cyber-neon-cyan" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('overview.title')}</div>
            <div className="text-[10px] text-cyber-text-muted">{t('overview.optimizedDescription')}</div>
          </div>
          <div className="ml-auto text-[10px] font-mono text-cyber-text-muted">{data?.generated_at || '-'}</div>
        </header>
        <div className="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricButton
            icon={PlusCircle}
            label={t('overview.todayNewPosts')}
            value={String(data?.today_new_posts ?? 0)}
            detail={t('overview.todayUnit')}
            tone="success"
            onClick={() => onOpenData(recentPost?.aweme_id)}
          />
          <MetricButton
            icon={CircleAlert}
            label={t('overview.abnormalJobs')}
            value={String(data?.abnormal_total ?? 0)}
            detail={t('overview.failedMissed', { failed: jobCounts.failed ?? 0, missed: jobCounts.missed ?? 0 })}
            tone={(data?.abnormal_total ?? 0) > 0 ? 'error' : 'success'}
            onClick={() => onOpenTasks('abnormal')}
          />
          <MetricButton
            icon={CalendarClock}
            label={t('overview.nextDiscovery')}
            value={formatDateTime(data?.next_discovery_at)}
            detail={formatCountdown(data?.next_discovery_at, t)}
            tone="info"
            onClick={() => onOpenTasks('pending')}
          />
          <MetricButton
            icon={Camera}
            label={t('overview.nextSnapshot')}
            value={formatDateTime(data?.next_snapshot?.due_at)}
            detail={data?.next_snapshot ? `${data.next_snapshot.stage} · ${formatCountdown(data.next_snapshot.due_at, t)}` : t('overview.noPendingSnapshot')}
            tone="warning"
            onClick={() => onOpenTasks('pending', data?.next_snapshot?.id)}
          />
        </div>
      </section>

      {activeAccountId === 'all' ? <MonitorAccountComparison /> : null}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12">
        <section className="rounded-lg glass-panel float-panel overflow-hidden xl:col-span-7">
          <header className="px-4 py-3 border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30">
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('overview.timelineTitle')}</div>
            <div className="mt-0.5 text-[10px] font-mono text-cyber-text-muted">{t('overview.timelineDescription')}</div>
          </header>
          <div className="max-h-[58vh] overflow-y-auto p-3">
            {timelineEvents.length > 0 ? (
              <ol className="relative ml-2 border-l border-cyber-border-subtle pl-5">
                {timelineEvents.map((event) => {
                  const EventIcon = event.kind === 'post' ? PlusCircle : event.kind === 'snapshot' ? Camera : event.kind === 'job' ? CircleAlert : Bell
                  const eventColor = event.kind === 'post'
                    ? 'text-cyber-neon-purple'
                    : event.kind === 'snapshot'
                      ? 'text-cyber-neon-green'
                      : event.kind === 'job'
                        ? 'text-cyber-neon-pink'
                        : 'text-cyber-neon-orange'
                  return (
                    <li key={event.id} className="relative pb-4 last:pb-0">
                      <span className={`absolute -left-[27px] top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-cyber-bg-panel bg-cyber-bg-tertiary ${eventColor}`}>
                        <span className="h-1.5 w-1.5 rounded-full bg-current" />
                      </span>
                      <button type="button" onClick={() => openEvent(event)} className="group w-full rounded-md border border-transparent px-2 py-1.5 text-left transition-colors hover:border-cyber-border-subtle hover:bg-cyber-bg-tertiary/30">
                        <div className="flex items-start gap-2">
                          <EventIcon className={`mt-0.5 h-3.5 w-3.5 flex-shrink-0 ${eventColor}`} />
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-[11px] font-mono text-cyber-text-primary">{event.title}</div>
                            <div className="mt-0.5 line-clamp-1 text-[10px] font-mono text-cyber-text-muted">{event.detail}</div>
                          </div>
                          <span className="whitespace-nowrap text-[9px] font-mono text-cyber-text-muted">{formatRelativeTime(event.timestamp, t)}</span>
                        </div>
                      </button>
                    </li>
                  )
                })}
              </ol>
            ) : (
              <div className="py-12 text-center text-xs font-mono text-cyber-text-muted">{t('overview.noTimeline')}</div>
            )}
          </div>
        </section>

        <section className="rounded-lg glass-panel float-panel overflow-hidden xl:col-span-5">
          <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center bg-cyber-bg-tertiary/30">
            <div>
              <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('overview.issuesTitle')}</div>
              <div className="mt-0.5 text-[10px] font-mono text-cyber-text-muted">{t('overview.issuesDescription')}</div>
            </div>
            <span className="ml-auto text-[10px] font-mono text-cyber-text-muted">{issues.length}</span>
          </header>
          <div className="max-h-[58vh] space-y-2 overflow-y-auto p-3">
            {issues.length > 0 ? issues.map((issue) => (
              <button
                key={issue.id}
                type="button"
                onClick={() => openIssue(issue)}
                className={`w-full rounded-md border border-cyber-border-subtle border-l-4 bg-cyber-bg-tertiary/20 p-3 text-left transition-colors hover:bg-cyber-bg-tertiary/40 ${SEVERITY_CLASSES[issue.severity]}`}
              >
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[11px] font-mono text-cyber-text-primary">{issue.title}</span>
                      {issue.count && issue.count > 1 ? <span className="rounded bg-cyber-bg-panel px-1.5 py-0.5 text-[9px] font-mono text-cyber-text-muted">×{issue.count}</span> : null}
                    </div>
                    <div className="mt-1 line-clamp-2 text-[10px] font-mono text-cyber-text-muted">{issue.detail}</div>
                    <div className="mt-1.5 text-[9px] font-mono text-cyber-text-muted">{formatRelativeTime(issue.timestamp, t)}</div>
                  </div>
                  <ChevronRight className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 opacity-60" />
                </div>
              </button>
            )) : (
              <div className="py-12 text-center text-xs font-mono text-cyber-text-muted">{t('overview.noIssues')}</div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
