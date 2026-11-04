export function snapshotStatus({ dueAt, now, paused, recovering, cooling, active, loopRunning, loaded, stale }: {
  dueAt?: number | null; now: number; paused?: boolean; recovering?: boolean; cooling?: boolean;
  active?: boolean; loopRunning?: boolean; loaded: boolean; stale?: boolean
}): { label: string; key: string; count?: number; tone: 'neutral' | 'info' | 'warning' } {
  const label = 'statusbar.snapshotSchedule'
  if (!loaded) return { label, key: 'statusbar.snapshotLoading', tone: 'neutral' }
  if (stale) return { label, key: 'statusbar.snapshotStale', tone: 'warning' }
  if (active) return { label, key: 'statusbar.snapshotRunning', tone: 'info' }
  if (paused) return { label, key: 'statusbar.snapshotPaused', tone: 'warning' }
  if (recovering) return { label, key: 'statusbar.snapshotRecovering', tone: 'warning' }
  if (cooling) return { label, key: 'statusbar.snapshotCooling', tone: 'warning' }
  if (!dueAt || !Number.isFinite(dueAt)) return { label, key: 'statusbar.snapshotNone', tone: 'neutral' }
  if (!loopRunning) return { label, key: 'statusbar.snapshotStopped', tone: 'warning' }
  const seconds = dueAt - now
  if (seconds <= 0) return { label, key: seconds > -60 ? 'statusbar.snapshotDue' : 'statusbar.snapshotDelayed',
    count: Math.max(1, Math.floor(-seconds / 60)), tone: 'warning' }
  if (seconds < 60) return { label: 'statusbar.nextSnapshot', key: 'statusbar.snapshotSoon', tone: 'info' }
  if (seconds < 3600) return { label: 'statusbar.nextSnapshot', key: 'statusbar.snapshotMinutes', count: Math.ceil(seconds / 60), tone: 'info' }
  return { label: 'statusbar.nextSnapshot', key: 'statusbar.snapshotHours', count: Math.ceil(seconds / 3600), tone: 'info' }
}
