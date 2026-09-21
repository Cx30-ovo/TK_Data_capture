import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, BarChart3, Clock3, Database, Filter, Flame, RefreshCw, RotateCcw, Tags } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { StatePanel } from '@/components/ui/state-panel'
import { monitorApi, type MonitorDashboardPost, type MonitorJob } from '@/lib/api'

const MonitorPerformanceOverview = lazy(() => import('@/components/monitor/MonitorPerformanceOverview').then((module) => ({ default: module.MonitorPerformanceOverview })))
const MonitorTopicAnalytics = lazy(() => import('@/components/monitor/MonitorTopicAnalytics').then((module) => ({ default: module.MonitorTopicAnalytics })))
const MonitorLifecycleAnalytics = lazy(() => import('@/components/monitor/MonitorLifecycleAnalytics').then((module) => ({ default: module.MonitorLifecycleAnalytics })))


type TimeRange = '24h' | '7d' | '30d' | 'all'
type DataModule = 'overview' | 'topics' | 'lifecycle'
type PostStatus = 'all' | 'normal' | 'insufficient' | 'missed' | 'abnormal'

const TIME_RANGE_SECONDS: Record<Exclude<TimeRange, 'all'>, number> = {
  '24h': 24 * 60 * 60,
  '7d': 7 * 24 * 60 * 60,
  '30d': 30 * 24 * 60 * 60,
}


function classifyPost(post: MonitorDashboardPost, jobs: MonitorJob[]): PostStatus {
  const now = Math.floor(Date.now() / 1000)
  if (jobs.some((job) => job.status === 'failed')) return 'abnormal'
  if (jobs.some((job) => job.status === 'missed')) return 'missed'
  const dueJobs = jobs.filter((job) => job.due_at <= now)
  if (dueJobs.length === 0) return post.snapshots.length > 0 ? 'normal' : 'insufficient'
  const completed = new Set(post.snapshots.map((snapshot) => snapshot.stage))
  const outstanding = dueJobs.some((job) => job.status === 'pending' || job.status === 'running')
  const missing = dueJobs.some((job) => job.status === 'done' && !completed.has(job.stage))
  return outstanding || missing ? 'insufficient' : 'normal'
}


function formatGeneratedAt(value?: string): string {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}


export function MonitorDataCenter({ focusAwemeId, focusToken }: { focusAwemeId?: string; focusToken?: number }) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [timeRange, setTimeRange] = useState<TimeRange>('all')
  const [statusFilter, setStatusFilter] = useState<PostStatus>('all')
  const [activeModule, setActiveModule] = useState<DataModule>(() => {
    const value = new URLSearchParams(window.location.search).get('module')
    return value === 'topics' || value === 'lifecycle' ? value : 'overview'
  })
  const { data: dashboard, isLoading, isFetching, error } = useQuery({
    queryKey: ['monitorDashboard', 'all'],
    queryFn: async () => (await monitorApi.getDashboard()).data,
    refetchInterval: 30000,
  })
  const { data: jobsData } = useQuery({
    queryKey: ['monitorJobs', 'all'],
    queryFn: async () => (await monitorApi.getJobs()).data,
    refetchInterval: 30000,
  })

  const allPosts = dashboard?.posts || []
  const allJobs = jobsData?.jobs || []
  const jobsByPost = useMemo(() => allJobs.reduce<Record<string, MonitorJob[]>>((result, job) => {
    result[job.aweme_id] = [...(result[job.aweme_id] || []), job]
    return result
  }, {}), [allJobs])

  const scopedPosts = useMemo(() => {
    const cutoff = timeRange === 'all' ? 0 : Math.floor(Date.now() / 1000) - TIME_RANGE_SECONDS[timeRange]
    return allPosts.filter((post) => {
      if (post.first_seen_at < cutoff) return false
      if (statusFilter !== 'all' && classifyPost(post, jobsByPost[post.aweme_id] || []) !== statusFilter) return false
      return true
    })
  }, [allPosts, jobsByPost, statusFilter, timeRange])
  const scopedSummary = useMemo(() => ({
    snapshots: scopedPosts.reduce((sum, post) => sum + post.snapshots.length, 0),
    attention: scopedPosts.filter((post) => {
      const status = classifyPost(post, jobsByPost[post.aweme_id] || [])
      return status === 'missed' || status === 'abnormal'
    }).length,
  }), [jobsByPost, scopedPosts])

  const changeModule = (module: DataModule) => {
    setActiveModule(module)
    const url = new URL(window.location.href)
    url.searchParams.set('module', module)
    window.history.pushState(null, '', url.toString())
  }

  useEffect(() => {
    const handlePopState = () => {
      const value = new URLSearchParams(window.location.search).get('module')
      setActiveModule(value === 'topics' || value === 'lifecycle' ? value : 'overview')
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (!focusAwemeId) return
    setActiveModule('overview')
  }, [focusAwemeId, focusToken])

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['monitorDashboard'] })
    queryClient.invalidateQueries({ queryKey: ['monitorJobs'] })
  }

  if (isLoading) return <StatePanel variant="loading" title={t('dataCenter.loading')} />
  if (error) return <StatePanel variant="error" title={t('dataCenter.loadFailed')} description={error.message} />

  return (
    <div className="space-y-4 animate-slide-up">
      <section className="data-center-hero p-4 sm:p-5">
        <div className="relative z-10 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary shadow-sm">
              <Database aria-hidden="true" className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <Badge variant="secondary" className="mb-2">{t('dataCenter.workspaceLabel')}</Badge>
              <h1 className="text-xl font-semibold tracking-tight text-cyber-text-primary">{t('dataCenter.title')}</h1>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-cyber-text-secondary">{t('dataCenter.redesignedDescription')}</p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-3 sm:min-w-[420px]">
            <div className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel/80 px-3 py-2 shadow-sm">
              <div className="text-[11px] text-cyber-text-muted">{t('performance.posts')}</div>
              <div className="mt-1 text-lg font-semibold numeric-value text-cyber-text-primary">{dashboard?.counts.posts ?? allPosts.length}</div>
            </div>
            <div className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel/80 px-3 py-2 shadow-sm">
              <div className="text-[11px] text-cyber-text-muted">{t('monitorDashboard.snapshots')}</div>
              <div className="mt-1 text-lg font-semibold numeric-value text-status-info">{scopedSummary.snapshots}</div>
            </div>
            <div className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel/80 px-3 py-2 shadow-sm">
              <div className="text-[11px] text-cyber-text-muted">{t('dataCenter.attentionPosts')}</div>
              <div className={`mt-1 text-lg font-semibold numeric-value ${scopedSummary.attention ? 'text-status-warning' : 'text-status-success'}`}>{scopedSummary.attention}</div>
            </div>
          </div>
        </div>
        <div className="relative z-10 mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-cyber-border-subtle/70 pt-3 text-xs text-cyber-text-muted">
          <span className="inline-flex items-center gap-1.5"><Clock3 aria-hidden="true" className="h-3.5 w-3.5" />{t('dataCenter.lastUpdated')}: {formatGeneratedAt(dashboard?.generated_at)}</span>
          <Button type="button" variant="outline" size="sm" onClick={refresh} disabled={isFetching} className="min-h-9"><RefreshCw aria-hidden="true" className={isFetching ? 'animate-spin' : ''} />{t('dataCenter.refresh')}</Button>
        </div>
      </section>

      <section className="overview-panel z-20 p-3 backdrop-blur lg:sticky lg:top-12" aria-labelledby="data-center-filter-title">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <div className="flex min-w-40 items-center gap-2 lg:self-center">
            <span className="grid h-8 w-8 place-items-center rounded-md bg-cyber-bg-tertiary text-cyber-text-secondary"><Filter aria-hidden="true" className="h-4 w-4" /></span>
            <div><h2 id="data-center-filter-title" className="text-xs font-semibold text-cyber-text-primary">{t('dataCenter.filters')}</h2><p className="mt-0.5 text-[11px] text-cyber-text-muted">{t('dataCenter.filterHint')}</p></div>
          </div>
          <div className="grid gap-1 text-[11px] font-medium text-cyber-text-secondary">
            <span id="data-center-time-range-label">{t('dataCenter.timeRangeLabel')}</span>
            <Select value={timeRange} onValueChange={(value) => setTimeRange(value as TimeRange)}>
              <SelectTrigger aria-labelledby="data-center-time-range-label" className="h-9 w-full min-w-[160px] text-xs sm:w-[180px]"><SelectValue /></SelectTrigger>
              <SelectContent>{(['24h', '7d', '30d', 'all'] as const).map((range) => <SelectItem key={range} value={range}>{t(`dataCenter.timeRange.${range}`)}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid gap-1 text-[11px] font-medium text-cyber-text-secondary">
            <span id="data-center-status-label">{t('dataCenter.statusLabel')}</span>
            <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as PostStatus)}>
              <SelectTrigger aria-labelledby="data-center-status-label" className="h-9 w-full min-w-[160px] text-xs sm:w-[180px]"><SelectValue /></SelectTrigger>
              <SelectContent>{(['all', 'normal', 'insufficient', 'missed', 'abnormal'] as const).map((status) => <SelectItem key={status} value={status}>{t(`dataCenter.status.${status}`)}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={() => { setTimeRange('all'); setStatusFilter('all') }} disabled={timeRange === 'all' && statusFilter === 'all'} className="min-h-9 self-start px-3 text-xs lg:self-end"><RotateCcw aria-hidden="true" className="h-3.5 w-3.5" />{t('dataCenter.reset')}</Button>
          <Badge variant="outline" aria-live="polite" className="lg:ml-auto lg:self-end">{t('dataCenter.resultCount', { count: scopedPosts.length })}</Badge>
        </div>
      </section>

      <nav className="data-center-module-nav" aria-label={t('dataCenter.modules.label')}>
        {([
          { key: 'overview', icon: BarChart3, label: t('dataCenter.modules.overview') },
          { key: 'topics', icon: Tags, label: t('dataCenter.modules.topics') },
          { key: 'lifecycle', icon: Flame, label: t('dataCenter.modules.lifecycle') },
        ] as const).map((module) => (
          <button key={module.key} type="button" aria-current={activeModule === module.key ? 'page' : undefined} data-active={activeModule === module.key ? 'true' : 'false'} onClick={() => changeModule(module.key)} className="data-center-module-tab"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-cyber-bg-tertiary"><module.icon aria-hidden="true" className="h-4 w-4" /></span><span className="truncate">{module.label}</span>{module.key === 'overview' && scopedSummary.attention > 0 ? <AlertTriangle aria-label={t('dataCenter.attentionPosts')} className="ml-auto h-3.5 w-3.5 text-status-warning" /> : null}</button>
        ))}
      </nav>

      <Suspense fallback={<StatePanel variant="loading" title={t('dataCenter.loading')} />}>
        {activeModule === 'overview' ? <MonitorPerformanceOverview posts={scopedPosts} focusAwemeId={focusAwemeId} focusToken={focusToken} /> : null}
        {activeModule === 'topics' ? <MonitorTopicAnalytics posts={scopedPosts} timeRange={timeRange} /> : null}
        {activeModule === 'lifecycle' ? <MonitorLifecycleAnalytics posts={scopedPosts} timeRange={timeRange} /> : null}
      </Suspense>
    </div>
  )
}
