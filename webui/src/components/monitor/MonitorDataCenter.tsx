import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart3, Flame, RefreshCw, RotateCcw, Tags } from 'lucide-react'
import { MonitorPerformanceOverview } from '@/components/monitor/MonitorPerformanceOverview'
import { MonitorTopicAnalytics } from '@/components/monitor/MonitorTopicAnalytics'
import { MonitorLifecycleAnalytics } from '@/components/monitor/MonitorLifecycleAnalytics'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { StatePanel } from '@/components/ui/state-panel'
import { monitorApi, type MonitorDashboardPost, type MonitorJob } from '@/lib/api'


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


export function MonitorDataCenter({ focusAwemeId: _focusAwemeId }: { focusAwemeId?: string }) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [timeRange, setTimeRange] = useState<TimeRange>('all')
  const [statusFilter, setStatusFilter] = useState<PostStatus>('all')
  const [activeModule, setActiveModule] = useState<DataModule>(() => {
    const value = new URLSearchParams(window.location.search).get('module')
    return value === 'topics' || value === 'lifecycle' ? value : 'overview'
  })
  const { data: dashboard, isLoading, isFetching, error } = useQuery({
    queryKey: ['monitorDashboard'],
    queryFn: async () => (await monitorApi.getDashboard(100)).data,
    refetchInterval: 30000,
  })
  const { data: jobsData } = useQuery({
    queryKey: ['monitorJobs'],
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

  const changeModule = (module: DataModule) => {
    setActiveModule(module)
    const url = new URL(window.location.href)
    url.searchParams.set('module', module)
    window.history.replaceState(null, '', url.toString())
  }

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['monitorDashboard'] })
    queryClient.invalidateQueries({ queryKey: ['monitorJobs'] })
  }

  if (isLoading) return <StatePanel variant="loading" title={t('dataCenter.loading')} />
  if (error) return <StatePanel variant="error" title={t('dataCenter.loadFailed')} description={error.message} />

  return (
    <div className="space-y-3 animate-slide-up">
      <section className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <h1 className="text-lg font-semibold text-cyber-text-primary">{t('dataCenter.title')}</h1>
          <p className="mt-1 text-xs text-cyber-text-muted">{t('dataCenter.redesignedDescription')}</p>
        </div>
        <div className="flex items-center gap-4 text-[10px] text-cyber-text-muted">
          <span>{t('dataCenter.lastUpdated')}: {formatGeneratedAt(dashboard?.generated_at)}</span>
          <Button type="button" variant="outline" size="sm" onClick={refresh} disabled={isFetching} className="h-8"><RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />{t('dataCenter.refresh')}</Button>
        </div>
      </section>

      <section className="sticky top-12 z-10 rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel/95 p-2 shadow-sm backdrop-blur">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={timeRange} onValueChange={(value) => setTimeRange(value as TimeRange)}>
            <SelectTrigger className="h-8 w-[140px] text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>{(['24h', '7d', '30d', 'all'] as const).map((range) => <SelectItem key={range} value={range}>{t(`dataCenter.timeRange.${range}`)}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as PostStatus)}>
            <SelectTrigger className="h-8 w-[150px] text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>{(['all', 'normal', 'insufficient', 'missed', 'abnormal'] as const).map((status) => <SelectItem key={status} value={status}>{t(`dataCenter.status.${status}`)}</SelectItem>)}</SelectContent>
          </Select>
          <Button type="button" variant="ghost" size="sm" onClick={() => { setTimeRange('all'); setStatusFilter('all') }} disabled={timeRange === 'all' && statusFilter === 'all'} className="h-8 px-2 text-[10px]"><RotateCcw className="h-3 w-3" />{t('dataCenter.reset')}</Button>
          <span className="ml-auto text-[10px] text-cyber-text-muted">{t('dataCenter.resultCount', { count: scopedPosts.length })}</span>
        </div>
      </section>

      <nav className="flex gap-1 overflow-x-auto border-b border-cyber-border-subtle px-1" aria-label={t('dataCenter.modules.label')}>
        {([
          { key: 'overview', icon: BarChart3, label: t('dataCenter.modules.overview') },
          { key: 'topics', icon: Tags, label: t('dataCenter.modules.topics') },
          { key: 'lifecycle', icon: Flame, label: t('dataCenter.modules.lifecycle') },
        ] as const).map((module) => (
          <button key={module.key} type="button" onClick={() => changeModule(module.key)} className={`flex shrink-0 items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-medium transition-colors ${activeModule === module.key ? 'border-cyber-neon-cyan text-cyber-neon-cyan' : 'border-transparent text-cyber-text-muted hover:text-cyber-text-primary'}`}><module.icon className="h-3.5 w-3.5" />{module.label}</button>
        ))}
      </nav>

      {activeModule === 'overview' ? <MonitorPerformanceOverview posts={scopedPosts} /> : null}
      {activeModule === 'topics' ? <MonitorTopicAnalytics posts={scopedPosts} /> : null}
      {activeModule === 'lifecycle' ? <MonitorLifecycleAnalytics posts={scopedPosts} /> : null}
    </div>
  )
}
