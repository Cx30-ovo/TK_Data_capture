import { TitleStrategyAIReport } from '@/components/monitor/TitleStrategyAIReport'
import type { MonitorDashboardPost } from '@/lib/api'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'


export function MonitorTitleStrategyAnalytics({ posts, timeRange }: { posts: MonitorDashboardPost[]; timeRange: '24h' | '7d' | '30d' | 'all' }) {
  const activeAccountId = useMonitorAccountStore((state) => state.activeAccountId)

  return (
    <TitleStrategyAIReport
      accountId={typeof activeAccountId === 'number' ? activeAccountId : null}
      timeRange={timeRange}
      postLimit={Math.max(posts.length, 3)}
    />
  )
}
