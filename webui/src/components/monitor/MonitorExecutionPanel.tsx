import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Activity, AlertTriangle, LockKeyhole, Pause, Play, Square } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { collectionErrorMessage, monitorApi } from '@/lib/api'

export function useMonitorExecution() {
  return useQuery({
    queryKey: ['monitorExecution'],
    queryFn: async () => (await monitorApi.getExecution()).data,
    staleTime: 1000,
    refetchInterval: (query) => query.state.data?.execution?.active || query.state.data?.retry_after_seconds || query.state.data?.recovery?.pending ? 1500 : 3000,
  })
}

export function MonitorExecutionPanel() {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const { data, isError, refetch } = useMonitorExecution()
  const execution = data?.execution
  const active = Boolean(execution?.active)
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['monitorExecution'] })
    queryClient.invalidateQueries({ queryKey: ['monitorJobs'] })
    queryClient.invalidateQueries({ queryKey: ['monitorStatus'] })
  }
  const stop = useMutation({
    mutationFn: () => monitorApi.stopExecution(active ? execution?.run_id : undefined),
    onSuccess: () => { toast.info(t('execution.stopAccepted')); refresh() },
    onError: (error) => toast.error(collectionErrorMessage(error)),
  })
  const resume = useMutation({
    mutationFn: () => monitorApi.resumeExecution(),
    onSuccess: () => { toast.success(t('execution.resumed')); refresh() },
    onError: (error) => toast.error(collectionErrorMessage(error)),
  })

  if (!data) return (
    <section className="rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary p-4" aria-live="polite">
      <span className="text-sm text-cyber-text-secondary">{t(isError ? 'execution.unavailable' : 'execution.loading')}</span>
      {isError && <Button variant="outline" className="ml-3 min-h-11" onClick={() => refetch()}>{t('execution.refresh')}</Button>}
    </section>
  )

  const cooling = data.retry_after_seconds > 0
  const recovery = data.recovery
  const recoveredError = Boolean(recovery?.last_recovered_at && execution?.started_at && recovery.last_recovered_at > execution.started_at
    && ['browser_disconnected', 'tab_changed', 'network_timeout'].includes(execution.error?.error_code || ''))
  const state = active ? execution?.state === 'stopping' ? 'stopping' : execution?.phase === 'waiting_tab' ? 'waiting_tab' : 'running'
    : data.paused ? 'paused' : cooling ? 'deferred' : data.crawler_running ? 'crawler' : recovery?.pending ? 'recovering' : recoveredError || execution?.state === 'deferred' ? 'idle' : execution?.state || 'idle'
  const hasTotal = active && execution?.kind === 'snapshots' && execution.total !== null && execution.total > 0
  const percent = hasTotal ? Math.round(execution!.processed / execution!.total! * 100) : undefined
  const heading = active ? t(`execution.kind.${execution?.kind}`) : t('execution.title')
  const error = recoveredError ? null : execution?.error
  const warning = cooling || data.paused || Boolean(error) || Boolean(recovery?.pending)

  return (
    <section className={`rounded-xl border bg-cyber-bg-secondary p-4 ${warning ? 'border-status-warning/40' : 'border-cyber-border-subtle'}`} aria-label={t('execution.title')}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-cyber-neon-cyan/10 text-cyber-neon-cyan">
            {active ? <Activity aria-hidden="true" className="h-5 w-5" /> : warning ? <AlertTriangle aria-hidden="true" className="h-5 w-5" /> : <LockKeyhole aria-hidden="true" className="h-5 w-5" />}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold text-cyber-text-primary">{heading}</h2>
              <Badge variant="secondary">{t(`execution.state.${state}`, { defaultValue: state })}</Badge>
            </div>
            <p className="mt-1 text-xs text-cyber-text-secondary" role="status" aria-live="polite">
              {active ? `${execution?.account_name || t('execution.allAccounts')} · ${t(`execution.phase.${execution?.phase}`, { defaultValue: execution?.phase })}` : t('execution.lockHint')}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.paused && !active ? (
            <Button variant="outline" className="min-h-11" onClick={() => resume.mutate()} disabled={resume.isPending}>
              <Play aria-hidden="true" className="h-4 w-4" />{t('execution.resume')}
            </Button>
          ) : (
            <Button variant="outline" className="min-h-11" onClick={() => stop.mutate()} disabled={stop.isPending || Boolean(execution?.active && execution.stop_requested) || data.paused}>
              {active ? <Square aria-hidden="true" className="h-4 w-4" /> : <Pause aria-hidden="true" className="h-4 w-4" />}
              {t(active ? execution?.stop_requested ? 'execution.stopping' : 'execution.stop' : 'execution.pause')}
            </Button>
          )}
        </div>
      </div>
      {active && (
        <div className="mt-4 space-y-2">
          <div className="flex flex-wrap justify-between gap-2 text-xs text-cyber-text-secondary">
            <span>{execution?.kind === 'discovery' ? t('execution.scanCount', { pages: execution.pages, count: execution.scanned, saved: execution.saved }) : t('execution.jobCount', { done: execution?.processed, total: execution?.total ?? '—', completed: execution?.completed })}</span>
            <span className="tabular-nums">{t('execution.elapsed', { seconds: execution?.elapsed_seconds })}{percent !== undefined ? ` · ${percent}%` : ` · ${t('execution.noTotal')}`}</span>
          </div>
          {hasTotal ? (
            <progress aria-label={t('execution.progress')} value={execution!.processed} max={execution!.total!} className="collection-progress h-2 w-full overflow-hidden rounded-full" />
          ) : (
            <div role="progressbar" aria-label={t('execution.progress')} aria-valuetext={t('execution.indeterminate')} className="h-2 w-full overflow-hidden rounded-full bg-cyber-neon-cyan/10"><div className="collection-indeterminate h-full w-1/4 rounded-full bg-cyber-neon-cyan/60" /></div>
          )}
          {execution?.current_post && <p className="break-all text-xs text-cyber-text-muted">{t('execution.currentPost', { id: execution.current_post })}</p>}
          <p className="text-xs text-cyber-text-muted">{t('execution.safeStopHint')}</p>
        </div>
      )}
      {!active && execution?.result && (
        <p className="mt-3 text-xs text-cyber-text-secondary">
          {execution.kind === 'discovery' ? t('execution.scanResult', { saved: execution.saved, posts: execution.result.created_posts ?? 0, jobs: execution.result.created_jobs ?? 0 }) : t('execution.snapshotResult', { completed: execution.completed, retried: execution.retried, failed: execution.failed, skipped: execution.skipped })}
        </p>
      )}
      {recovery?.pending && (
        <div className="mt-3 rounded-lg border border-status-warning/30 bg-status-warning/5 p-3 text-sm text-cyber-text-secondary" role="status" aria-live="polite">
          <p className="font-medium text-cyber-text-primary">{t(data.paused ? 'execution.recoveryPaused' : cooling ? 'execution.recoveryCooling' : recovery.state === 'recovering' ? 'execution.recoveryRunning' : 'execution.recoveryWaiting', { seconds: recovery.retry_after_seconds })}</p>
          <p className="mt-1 text-xs">{t('execution.recoveryHint', { attempts: recovery.attempts })}</p>
        </div>
      )}
      {recovery?.error && !recovery.pending && recovery.state === 'login_required' && <p className="mt-3 text-sm text-status-warning" role="status">{recovery.error.message} · {recovery.error.action}</p>}
      {error && !recovery?.pending && recovery?.state !== 'login_required' && <div className="mt-3 rounded-lg border border-status-warning/30 bg-status-warning/5 p-3 text-xs text-cyber-text-secondary" role="status"><span className="font-medium text-cyber-text-primary">{error.message}</span><span className="ml-2">{error.action}</span></div>}
      {cooling && <p className="mt-3 text-xs text-status-warning">{t('execution.cooldown', { minutes: Math.max(1, Math.ceil(data.retry_after_seconds / 60)) })}</p>}
      {isError && <p className="mt-3 text-xs text-status-warning" role="status">{t('execution.staleConnection')}</p>}
    </section>
  )
}
