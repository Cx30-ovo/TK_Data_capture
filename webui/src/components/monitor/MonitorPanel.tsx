import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Clock3, PlayCircle, Radar, RefreshCw, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { monitorApi } from '@/lib/api'


function parseSecUserId(value: string): string {
  const trimmed = value.trim()
  const match = trimmed.match(/\/user\/([^/?]+)/)
  return match ? match[1] : trimmed
}


export function MonitorPanel() {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const { data: status } = useQuery({
    queryKey: ['monitorStatus'],
    queryFn: async () => (await monitorApi.getStatus()).data,
    refetchInterval: 30000,
  })
  const [accountInput, setAccountInput] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [intervalMinutes, setIntervalMinutes] = useState(30)

  useEffect(() => {
    if (!status?.account) return
    setAccountInput(status.account.profile_url || status.account.sec_user_id)
    setEnabled(status.enabled)
    setIntervalMinutes(status.account.discover_interval_minutes)
  }, [status?.account?.id, status?.enabled])

  const saveMutation = useMutation({
    mutationFn: () => monitorApi.updateConfig({
      sec_user_id: parseSecUserId(accountInput),
      profile_url: accountInput.trim(),
      enabled,
      discover_interval_minutes: intervalMinutes,
    }),
    onSuccess: () => {
      toast.success(t('monitor.saved'))
      queryClient.invalidateQueries({ queryKey: ['monitorStatus'] })
    },
    onError: (error: Error) => toast.error(`${t('monitor.failed')}: ${error.message}`),
  })

  const discoverMutation = useMutation({
    mutationFn: () => monitorApi.discover(status?.account?.sec_user_id),
    onSuccess: (response) => {
      const result = response.data
      toast.success(t('monitor.discoverDone', {
        posts: result.created_posts ?? 0,
        jobs: result.created_jobs ?? 0,
      }))
      queryClient.invalidateQueries({ queryKey: ['monitorStatus'] })
    },
    onError: (error: Error) => toast.error(`${t('monitor.discoverFailed')}: ${error.message}`),
  })

  const snapshotMutation = useMutation({
    mutationFn: () => monitorApi.runDueSnapshots(),
    onSuccess: (response) => {
      const result = response.data
      toast.success(t('monitor.snapshotDone', {
        completed: result.completed ?? 0,
        retried: result.retried ?? 0,
        failed: result.failed ?? 0,
      }))
      queryClient.invalidateQueries({ queryKey: ['monitorStatus'] })
    },
    onError: (error: Error) => toast.error(`${t('monitor.snapshotFailed')}: ${error.message}`),
  })

  const hasAccount = Boolean(status?.account)
  const isBusy = saveMutation.isPending || discoverMutation.isPending || snapshotMutation.isPending
  const jobEntries = Object.entries(status?.jobs || {})

  return (
    <section className="rounded-lg glass-panel float-panel overflow-hidden">
      <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
        <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center flex-shrink-0">
          <Radar className="h-4 w-4 text-cyber-neon-cyan" />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-mono font-semibold text-cyber-text-primary tracking-wide">
            {t('monitor.title')}
          </div>
          <div className="text-[10px] text-cyber-text-muted leading-snug truncate">
            {t('monitor.description')}
          </div>
        </div>
      </header>

      <div className="p-4 space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_180px_auto] gap-4 items-end">
          <div className="space-y-2">
            <Label className="text-xs text-cyber-text-secondary font-mono">{t('monitor.account')}</Label>
            <Input
              value={accountInput}
              onChange={(event) => setAccountInput(event.target.value)}
              placeholder="https://www.douyin.com/user/..."
              disabled={isBusy}
              className="h-9 text-xs font-mono"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-cyber-text-secondary font-mono">{t('monitor.interval')}</Label>
            <Select
              value={String(intervalMinutes)}
              onValueChange={(value) => setIntervalMinutes(Number(value))}
              disabled={isBusy}
            >
              <SelectTrigger className="h-9 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="30">30 min</SelectItem>
                <SelectItem value="60">60 min</SelectItem>
                <SelectItem value="120">120 min</SelectItem>
                <SelectItem value="240">240 min</SelectItem>
                <SelectItem value="360">360 min</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-3 h-9">
            <Checkbox
              checked={enabled}
              onCheckedChange={(checked) => setEnabled(checked === true)}
              disabled={isBusy}
            />
            <span className="text-xs font-mono text-cyber-text-primary">{t('monitor.enable')}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={isBusy || !parseSecUserId(accountInput)}
            className="h-9 px-4 bg-cyber-neon-cyan text-cyber-bg-primary font-mono text-xs hover:bg-cyber-neon-cyan/90"
          >
            <Save className="w-4 h-4" />
            {saveMutation.isPending ? t('monitor.saving') : t('monitor.save')}
          </Button>
          <Button
            variant="outline"
            onClick={() => discoverMutation.mutate()}
            disabled={isBusy || !hasAccount}
            className="h-9 px-4 font-mono text-xs"
          >
            <RefreshCw className={`w-4 h-4 ${discoverMutation.isPending ? 'animate-spin' : ''}`} />
            {t('monitor.discover')}
          </Button>
          <Button
            variant="outline"
            onClick={() => snapshotMutation.mutate()}
            disabled={isBusy || !hasAccount}
            className="h-9 px-4 font-mono text-xs"
          >
            <PlayCircle className="w-4 h-4" />
            {t('monitor.runSnapshots')}
          </Button>
          <div className="flex items-center gap-2 text-[10px] font-mono text-cyber-text-muted ml-auto">
            <Clock3 className="w-3.5 h-3.5" />
            {status?.account?.last_discovered_at
              ? t('monitor.lastDiscovered', { time: new Date(status.account.last_discovered_at * 1000).toLocaleString() })
              : t('monitor.notDiscovered')}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono">
          <span className={status?.loop_running ? 'text-cyber-neon-green' : 'text-cyber-neon-orange'}>
            {status?.loop_running ? t('monitor.loopRunning') : t('monitor.loopStopped')}
          </span>
          {jobEntries.length > 0 ? jobEntries.map(([jobStatus, count]) => (
            <span key={jobStatus} className="rounded border border-cyber-border-subtle bg-cyber-bg-tertiary/40 px-2 py-1 text-cyber-text-secondary">
              {jobStatus}: {count}
            </span>
          )) : (
            <span className="text-cyber-text-muted">{t('monitor.noJobs')}</span>
          )}
        </div>
      </div>
    </section>
  )
}
