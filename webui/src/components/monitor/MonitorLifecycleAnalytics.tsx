import { LifecycleAIReport } from '@/components/monitor/LifecycleAIReport'
import type { MonitorDashboardPost } from '@/lib/api'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'


export function MonitorLifecycleAnalytics({ posts, timeRange }: { posts: MonitorDashboardPost[]; timeRange: '24h' | '7d' | '30d' | 'all' }) {
  const activeAccountId = useMonitorAccountStore((state) => state.activeAccountId)

  return (
    <LifecycleAIReport
      accountId={typeof activeAccountId === 'number' ? activeAccountId : null}
      timeRange={timeRange}
      postLimit={Math.min(Math.max(posts.length, 6), 6)}
      posts={posts}
    />
  )
}
