import { TopicAIReport } from '@/components/monitor/TopicAIReport'
import type { MonitorDashboardPost } from '@/lib/api'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'


export function MonitorTopicAnalytics({ posts, timeRange }: { posts: MonitorDashboardPost[]; timeRange: '24h' | '7d' | '30d' | 'all' }) {
  const activeAccountId = useMonitorAccountStore((state) => state.activeAccountId)

  return (
    <TopicAIReport
      accountId={typeof activeAccountId === 'number' ? activeAccountId : null}
      timeRange={timeRange}
      postLimit={Math.min(Math.max(posts.length, 10), 10)}
    />
  )
}
