import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Bell, CalendarClock, Camera, ChevronRight, CircleAlert, Play, PlusCircle, Radar } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { monitorApi, type MonitorAlert } from '@/lib/api'
import { MonitorAccountComparison } from '@/components/monitor/MonitorAccountComparison'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'


type EventKind = 'post' | 'snapshot' | 'job' | 'alert'
type IssueKind = 'job' | 'alert'

interface MonitorOverviewProps {
  onOpenTasks: (status?: string, jobId?: number) => void
  onOpenAlerts: (alertId?: number) => void
  onOpenData: (awemeId?: string) => void
  onOpenConfig: () => void
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
  error: 'border-l-status-danger text-status-danger',
  warning: 'border-l-status-warning text-status-warning',
  info: 'border-l-status-info text-status-info',
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
    info: 'border-l-status-info text-status-info',
    warning: 'border-l-status-warning text-status-warning',
    error: 'border-l-status-danger text-status-danger',
    success: 'border-l-status-success text-status-success',
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className={`overview-metric-card group border-cyber-border-subtle border-l-2 bg-cyber-bg-panel ${toneClasses[tone]}`}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/45">
          <Icon className="h-4 w-4" />
        </span>
        <ChevronRight className="h-4 w-4 text-cyber-text-muted opacity-40 transition-opacity group-hover:opacity-80" />
      </div>
      <div className="mt-3">
        <div className="text-xs font-medium text-cyber-text-secondary">{label}</div>
        <div className="mt-1.5 flex min-w-0 items-baseline gap-2">
          <span className="shrink-0 text-2xl font-semibold numeric-value text-cyber-text-primary">{value}</span>
          <span className="min-w-0 truncate text-xs text-cyber-text-muted">{detail}</span>
        </div>
      </div>
    </button>
  )
}


export function MonitorOverview({ onOpenTasks, onOpenAlerts, onOpenData, onOpenConfig }: MonitorOverviewProps) {
  const { t } = useTranslation('config')
  const activeAccountId = useMonitorAccountStore((state) => state.activeAccountId)
  const { data } = useQuery({
    queryKey: ['monitorOverview'],
    queryFn: async () => (await monitorApi.getOverview()).data,
    refetchInterval: 30000,
  })
  const { data: dashboard } = useQuery({
    queryKey: ['monitorDashboard', 50],
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
  const failedJobs = useMemo(() => abnormalJobs.filter((job) => job.status === 'failed'), [abnormalJobs])
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
    const items: OverviewIssue[] = failedJobs.map((job) => ({
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
  }, [alerts, failedJobs])

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
      <section className="overview-banner" aria-labelledby="overview-banner-title">
        <div className="overview-banner-grid" aria-hidden="true" />
        <div className="relative z-10 grid min-h-[var(--banner-min-height)] items-stretch lg:grid-cols-[minmax(0,1.2fr)_minmax(22rem,0.8fr)]">
          <div className="flex flex-col justify-center px-6 py-7 sm:px-8 lg:py-8">
            <div className="overview-banner-kicker">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--banner-brand)]" />
              {t('overview.bannerKicker')}
            </div>
            <h1 id="overview-banner-title" className="overview-banner-title mt-4">
              {t('overview.bannerTitle')}
            </h1>
            <p className="overview-banner-copy mt-3">
              {t('overview.bannerDescription')}
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button type="button" size="lg" onClick={onOpenConfig} className="h-11 px-5">
                <Play className="h-4 w-4" />
                {t('button.initiateScan')}
              </Button>
              <span className="inline-flex items-center gap-2 text-xs text-cyber-text-muted">
                <span className="status-dot status-dot-online" />
                {t('overview.bannerLive')}
              </span>
            </div>
          </div>

          <div className="relative flex items-center justify-center px-5 pb-6 pt-2 lg:py-6">
            <div className="overview-signal-card">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold text-cyber-text-primary">{t('overview.bannerSignal')}</div>
                  <div className="mt-1 text-[11px] text-cyber-text-muted">{t('overview.bannerSignalHint')}</div>
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-status-success/25 bg-status-success/10 px-2 py-1 text-[10px] font-medium text-status-success">
                  <span className="h-1.5 w-1.5 rounded-full bg-status-success" />
                  LIVE
                </span>
              </div>

              <div className="overview-signal-wave mt-4" aria-hidden="true">
                {[30, 44, 38, 58, 46, 70, 62, 84, 68, 92, 76, 100].map((height, index) => (
                  <span
                    key={`${height}-${index}`}
                    className={`overview-signal-bar ${index % 4 === 0 ? 'bg-[var(--banner-tech)]' : 'bg-[var(--banner-brand)]'}`}
                    style={{ height: `${height}%`, opacity: 0.35 + index * 0.045 }}
                  />
                ))}
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/35 p-2.5">
                  <div className="text-[10px] text-cyber-text-muted">{t('overview.todayNewPosts')}</div>
                  <div className="mt-1 text-lg font-semibold numeric-value text-cyber-text-primary">{data?.today_new_posts ?? 0}</div>
                </div>
                <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/35 p-2.5">
                  <div className="text-[10px] text-cyber-text-muted">{t('tasks.status.failed')}</div>
                  <div className={`mt-1 text-lg font-semibold numeric-value ${failedJobs.length > 0 ? 'text-status-danger' : 'text-status-success'}`}>{failedJobs.length}</div>
                </div>
                <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/35 p-2.5">
                  <div className="text-[10px] text-cyber-text-muted">{t('overview.nextSnapshot')}</div>
                  <div className="mt-1 text-sm font-semibold text-cyber-text-primary">{data?.next_snapshot?.stage || '-'}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="overview-panel overflow-hidden">
        <header className="overview-panel-header">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-status-info/20 bg-cyber-bg-primary">
            <Radar className="h-4 w-4 text-status-info" />
          </div>
          <div className="min-w-0">
            <h1 className="overview-panel-title">{t('overview.title')}</h1>
            <div className="overview-panel-description">{t('overview.optimizedDescription')}</div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <div className="text-[10px] uppercase tracking-wide text-cyber-text-muted">{t('dataCenter.lastUpdated')}</div>
              <time className="mt-0.5 block text-[11px] numeric-value text-cyber-text-secondary">{data?.generated_at || '-'}</time>
            </div>
          </div>
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
            label={t('tasks.status.failed')}
            value={String(failedJobs.length)}
            detail={t('overview.failedMissed', { failed: failedJobs.length, missed: jobCounts.missed ?? 0 })}
            tone={failedJobs.length > 0 ? 'error' : 'success'}
            onClick={() => onOpenTasks('failed')}
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
        <section className="overview-panel overflow-hidden xl:col-span-8">
          <header className="overview-panel-header">
            <div className="flex h-8 w-8 items-center justify-center rounded-md border border-status-info/20 bg-cyber-bg-primary">
              <CalendarClock className="h-4 w-4 text-status-info" />
            </div>
            <div className="min-w-0">
              <h2 className="overview-panel-title">{t('overview.timelineTitle')}</h2>
              <div className="overview-panel-description">{t('overview.timelineDescription')}</div>
            </div>
            <span className="ml-auto rounded-full border border-cyber-border-subtle bg-cyber-bg-panel px-2 py-0.5 text-[10px] numeric-value text-cyber-text-muted">{timelineEvents.length}</span>
          </header>
          <div className="overview-scroll p-3">
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
                    <li key={event.id} className="relative pb-2 last:pb-0">
                      <span className={`absolute -left-[27px] top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-cyber-bg-panel bg-cyber-bg-tertiary ${eventColor}`}>
                        <span className="h-1.5 w-1.5 rounded-full bg-current" />
                      </span>
                      <button type="button" onClick={() => openEvent(event)} className="overview-event-row group w-full px-2 py-2.5 text-left transition-colors hover:bg-cyber-bg-tertiary/28">
                        <div className="flex items-start gap-2">
                          <EventIcon className={`mt-0.5 h-3.5 w-3.5 flex-shrink-0 ${eventColor}`} />
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-xs font-medium text-cyber-text-primary">{event.title}</div>
                            <div className="mt-0.5 line-clamp-1 text-[11px] text-cyber-text-muted">{event.detail}</div>
                          </div>
                          <span className="whitespace-nowrap pt-0.5 text-[10px] text-cyber-text-muted">{formatRelativeTime(event.timestamp, t)}</span>
                        </div>
                      </button>
                    </li>
                  )
                })}
              </ol>
            ) : (
              <div className="flex min-h-40 flex-col items-center justify-center gap-2 text-center">
                <CalendarClock className="h-5 w-5 text-cyber-text-muted" />
                <span className="text-xs text-cyber-text-muted">{t('overview.noTimeline')}</span>
              </div>
            )}
          </div>
        </section>

        <section className="overview-panel overflow-hidden xl:col-span-4">
          <header className="overview-panel-header">
            <div className="flex h-8 w-8 items-center justify-center rounded-md border border-status-warning/20 bg-cyber-bg-primary">
              <CircleAlert className="h-4 w-4 text-status-warning" />
            </div>
            <div className="min-w-0">
              <h2 className="overview-panel-title">{t('overview.issuesTitle')}</h2>
              <div className="overview-panel-description">{t('overview.issuesDescription')}</div>
            </div>
            <span className="ml-auto rounded-full border border-cyber-border-subtle bg-cyber-bg-panel px-2 py-0.5 text-[10px] numeric-value text-cyber-text-muted">{issues.length}</span>
          </header>
          <div className="overview-scroll space-y-2 p-3">
            {issues.length > 0 ? issues.map((issue) => (
              <button
                key={issue.id}
                type="button"
                onClick={() => openIssue(issue)}
                className={`overview-issue-row w-full p-3 text-left ${SEVERITY_CLASSES[issue.severity]}`}
              >
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-xs font-medium text-cyber-text-primary">{issue.title}</span>
                      {issue.count && issue.count > 1 ? <span className="rounded bg-cyber-bg-panel px-1.5 py-0.5 text-[10px] numeric-value text-cyber-text-muted">×{issue.count}</span> : null}
                    </div>
                    <div className="mt-1 line-clamp-2 text-[11px] leading-5 text-cyber-text-muted">{issue.detail}</div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="rounded border border-cyber-border-subtle px-1.5 py-0.5 text-[10px]">{t(`alerts.severity.${issue.severity}`)}</span>
                      <span className="text-[10px] text-cyber-text-muted">{formatRelativeTime(issue.timestamp, t)}</span>
                    </div>
                  </div>
                  <ChevronRight className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-cyber-text-muted opacity-60" />
                </div>
              </button>
            )) : (
              <div className="flex min-h-40 flex-col items-center justify-center gap-2 text-center">
                <CircleAlert className="h-5 w-5 text-status-success" />
                <span className="text-xs text-cyber-text-muted">{t('overview.noIssues')}</span>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
