import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Activity, Bell, Camera, ChevronRight, ListChecks, Wifi } from 'lucide-react'
import { monitorApi } from '@/lib/api'
import { useCrawlerStore } from '@/store/crawlerStore'


type StatusTone = 'neutral' | 'ok' | 'warning' | 'error' | 'info'


const TONE_CLASSES: Record<StatusTone, string> = {
  neutral: 'border-l-cyber-border-default text-status-neutral',
  ok: 'border-l-status-success text-status-success',
  warning: 'border-l-status-warning text-status-warning',
  error: 'border-l-status-danger text-status-danger',
  info: 'border-l-status-info text-status-info',
}


function formatSnapshotTime(
  timestamp: number | null | undefined,
  t: (key: string) => string,
): string {
  if (!timestamp) return '-'
  const date = new Date(timestamp * 1000)
  const today = new Date()
  const tomorrow = new Date(today)
  tomorrow.setDate(today.getDate() + 1)
  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (date.toDateString() === today.toDateString()) return `${t('statusbar.today')} ${time}`
  if (date.toDateString() === tomorrow.toDateString()) return `${t('statusbar.tomorrow')} ${time}`
  return date.toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}


function StatusItem({
  icon: Icon,
  label,
  value,
  detail,
  tone = 'neutral',
  onClick,
  valueMono = false,
}: {
  icon: typeof Activity
  label: string
  value: string
  detail?: string
  tone?: StatusTone
  onClick?: () => void
  valueMono?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={`group flex min-w-[154px] flex-1 items-center gap-2.5 rounded-md border border-l-2 border-cyber-border-subtle bg-cyber-bg-panel/80 px-2.5 py-0.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-info lg:min-w-0 ${TONE_CLASSES[tone]} ${onClick ? 'cursor-pointer hover:bg-cyber-bg-tertiary/40 hover:shadow-sm' : 'cursor-default'}`}
    >
      <Icon className="h-3.5 w-3.5 flex-shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-[10px] leading-3 uppercase tracking-wide text-cyber-text-muted">{label}</div>
        <div className="flex min-w-0 items-baseline gap-1.5">
          <span className={`truncate text-xs font-semibold leading-4 ${valueMono ? 'numeric-value' : 'font-sans'}`}>{value}</span>
          {detail ? <span className="min-w-0 truncate text-[10px] leading-3 text-cyber-text-muted">{detail}</span> : null}
        </div>
      </div>
      {onClick ? <ChevronRight className="h-3 w-3 flex-shrink-0 text-cyber-text-muted opacity-35 transition-opacity group-hover:opacity-75" /> : null}
    </button>
  )
}


export function GlobalStatusBar({
  onOpenOverview,
  onOpenHealth,
  onOpenPending,
  onOpenAlerts,
  onOpenSnapshot,
}: {
  onOpenOverview?: () => void
  onOpenHealth?: () => void
  onOpenPending?: () => void
  onOpenAlerts?: () => void
  onOpenSnapshot?: () => void
}) {
  const { t } = useTranslation('common')
  const { t: tConfig } = useTranslation('config')
  const crawlerStatus = useCrawlerStore((state) => state.status)
  const platform = useCrawlerStore((state) => state.platform)
  const { data: health } = useQuery({
    queryKey: ['monitorHealth'],
    queryFn: async () => (await monitorApi.getHealth()).data,
    refetchInterval: 30000,
  })
  const { data: overview } = useQuery({
    queryKey: ['monitorOverview'],
    queryFn: async () => (await monitorApi.getOverview()).data,
    refetchInterval: 30000,
  })

  const browserCheck = health?.checks.find((check) => check.key === 'browser')
  const browserStatus = browserCheck?.status || 'warning'
  const browserTone: StatusTone = browserStatus === 'ok' ? 'ok' : browserStatus === 'error' ? 'error' : 'warning'
  const browserValue = tConfig(`health.status.${browserStatus}`)
  const browserDetail = browserCheck?.value && browserCheck.value !== '-' ? t('statusbar.browserPort', { port: browserCheck.value }) : undefined
  const pendingCount = health?.metrics.jobs?.pending ?? overview?.jobs.pending ?? 0
  const unreadCount = health?.metrics.unread_alerts ?? 0
  const nextSnapshot = overview?.next_snapshot

  return (
    <section className="app-statusbar sticky top-0 z-20 h-12 flex-shrink-0 overflow-hidden border-b border-cyber-border-subtle bg-cyber-bg-secondary/90 backdrop-blur">
      <div className="flex h-full gap-2 overflow-x-auto px-2 py-1 lg:grid lg:grid-cols-5 lg:overflow-visible">
        <StatusItem
          icon={Activity}
          label={t('statusbar.collection')}
          value={t(`status.${crawlerStatus}`)}
          detail={platform ? platform.toUpperCase() : undefined}
          tone={crawlerStatus === 'running' ? 'ok' : crawlerStatus === 'error' ? 'error' : 'neutral'}
          onClick={onOpenOverview}
        />
        <StatusItem
          icon={Wifi}
          label={t('statusbar.browser')}
          value={browserValue}
          detail={browserDetail}
          tone={browserTone}
          onClick={onOpenHealth}
        />
        <StatusItem
          icon={ListChecks}
          label={t('statusbar.pendingJobs')}
          value={String(pendingCount)}
          detail={t('statusbar.pendingDetail')}
          tone={pendingCount > 0 ? 'info' : 'neutral'}
          onClick={onOpenPending}
          valueMono
        />
        <StatusItem
          icon={Bell}
          label={t('statusbar.unreadAlerts')}
          value={String(unreadCount)}
          detail={t('statusbar.unreadDetail')}
          tone={unreadCount > 0 ? 'warning' : 'neutral'}
          onClick={onOpenAlerts}
          valueMono
        />
        <StatusItem
          icon={Camera}
          label={t('statusbar.nextSnapshot')}
          value={formatSnapshotTime(nextSnapshot?.due_at, t)}
          detail={nextSnapshot?.stage}
          tone={nextSnapshot ? 'info' : 'neutral'}
          onClick={onOpenSnapshot}
          valueMono
        />
      </div>
    </section>
  )
}
