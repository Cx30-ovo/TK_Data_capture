import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Clock3, Plus, RefreshCw, Save, Trash2, UserRound, UsersRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { monitorApi, type MonitorAccount } from '@/lib/api'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'


function parseSecUserId(value: string): string {
  const trimmed = value.trim()
  const match = trimmed.match(/\/user\/([^/?]+)/)
  return match ? match[1] : trimmed
}


interface MonitorPanelProps {
  embedded?: boolean
  onDirtyChange?: (dirty: boolean) => void
  onValidChange?: (valid: boolean) => void
  saveHandlerRef?: { current: (() => void) | null }
}


export function MonitorPanel({ embedded = false, onDirtyChange, onValidChange, saveHandlerRef }: MonitorPanelProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const activeAccountId = useMonitorAccountStore((state) => state.activeAccountId)
  const setActiveAccountId = useMonitorAccountStore((state) => state.setActiveAccountId)
  const { data: accounts = [] } = useQuery({
    queryKey: ['monitorAccounts'],
    queryFn: async () => (await monitorApi.getAccounts()).data.accounts,
    refetchInterval: 30000,
  })
  const { data: status } = useQuery({
    queryKey: ['monitorStatus', activeAccountId],
    queryFn: async () => (await monitorApi.getStatus(typeof activeAccountId === 'number' ? activeAccountId : undefined)).data,
    refetchInterval: 30000,
  })
  const [editingId, setEditingId] = useState<number | null>(typeof activeAccountId === 'number' ? activeAccountId : null)
  const [isCreating, setIsCreating] = useState(false)
  const [accountInput, setAccountInput] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [intervalMinutes, setIntervalMinutes] = useState(30)
  const [savedValues, setSavedValues] = useState({ accountInput: '', displayName: '', enabled: true, intervalMinutes: 30 })

  const activeAccount = accounts.find((account) => account.id === editingId)

  useEffect(() => {
    if (isCreating) return
    if (typeof activeAccountId === 'number' && accounts.some((account) => account.id === activeAccountId)) {
      if (editingId !== activeAccountId) setEditingId(activeAccountId)
      return
    }
    if (editingId !== null && accounts.some((account) => account.id === editingId)) return
    const nextId = accounts[0]?.id ?? null
    if (editingId !== nextId) setEditingId(nextId)
  }, [activeAccountId, accounts, editingId, isCreating])

  useEffect(() => {
    if (editingId === null || !activeAccount) return
    const next = {
      accountInput: activeAccount.profile_url || activeAccount.sec_user_id,
      displayName: activeAccount.display_name || '',
      enabled: activeAccount.enabled,
      intervalMinutes: activeAccount.discover_interval_minutes,
    }
    setAccountInput(next.accountInput)
    setDisplayName(next.displayName)
    setEnabled(next.enabled)
    setIntervalMinutes(next.intervalMinutes)
    setSavedValues(next)
  }, [activeAccount?.id, activeAccount?.updated_at])

  const refreshAccounts = () => {
    queryClient.invalidateQueries({ queryKey: ['monitorAccounts'] })
    queryClient.invalidateQueries({ queryKey: ['monitorStatus'] })
    queryClient.invalidateQueries({ queryKey: ['monitorDashboard'] })
    queryClient.invalidateQueries({ queryKey: ['monitorOverview'] })
    queryClient.invalidateQueries({ queryKey: ['monitorJobs'] })
    queryClient.invalidateQueries({ queryKey: ['monitorAlerts'] })
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = {
        sec_user_id: parseSecUserId(accountInput),
        display_name: displayName.trim(),
        profile_url: accountInput.trim(),
        enabled,
        discover_interval_minutes: intervalMinutes,
      }
      return isCreating || editingId === null
        ? monitorApi.createAccount(payload)
        : monitorApi.updateAccount(editingId, payload)
    },
    onSuccess: (response) => {
      toast.success(t('monitor.saved'))
      const account = response.data
      setIsCreating(false)
      setEditingId(account.id)
      setActiveAccountId(account.id)
      setSavedValues({ accountInput: account.profile_url || account.sec_user_id, displayName: account.display_name, enabled: account.enabled, intervalMinutes: account.discover_interval_minutes })
      refreshAccounts()
    },
    onError: (error: Error) => toast.error(`${t('monitor.failed')}: ${error.message}`),
  })

  const deleteMutation = useMutation({
    mutationFn: (accountId: number) => monitorApi.deleteAccount(accountId),
    onSuccess: (_response, accountId) => {
      toast.success(t('monitor.deleted'))
      const nextId = accounts.find((account) => account.id !== accountId)?.id ?? null
      setIsCreating(false)
      setEditingId(nextId)
      setActiveAccountId(nextId)
      refreshAccounts()
    },
    onError: (error: Error) => toast.error(`${t('monitor.deleteFailed')}: ${error.message}`),
  })

  const discoverMutation = useMutation({
    mutationFn: (accountId: number) => monitorApi.discoverAccount(accountId),
    onSuccess: (response) => {
      const result = response.data
      toast.success(t('monitor.discoverDone', { posts: result.created_posts ?? 0, jobs: result.created_jobs ?? 0 }))
      refreshAccounts()
    },
    onError: (error: Error) => toast.error(`${t('monitor.discoverFailed')}: ${error.message}`),
  })

  const snapshotMutation = useMutation({
    mutationFn: () => monitorApi.runDueSnapshots(),
    onSuccess: (response) => {
      const result = response.data
      toast.success(t('monitor.snapshotDone', { completed: result.completed ?? 0, retried: result.retried ?? 0, failed: result.failed ?? 0 }))
      refreshAccounts()
    },
    onError: (error: Error) => toast.error(`${t('monitor.snapshotFailed')}: ${error.message}`),
  })

  const isBusy = saveMutation.isPending || deleteMutation.isPending || discoverMutation.isPending || snapshotMutation.isPending
  const accountDirty = accountInput.trim() !== savedValues.accountInput.trim()
    || displayName.trim() !== savedValues.displayName.trim()
    || enabled !== savedValues.enabled
    || intervalMinutes !== savedValues.intervalMinutes
  const accountValid = Boolean(parseSecUserId(accountInput))

  useEffect(() => onDirtyChange?.(accountDirty), [accountDirty, onDirtyChange])
  useEffect(() => onValidChange?.(accountValid), [accountValid, onValidChange])
  useEffect(() => {
    if (!saveHandlerRef) return
    saveHandlerRef.current = () => saveMutation.mutate()
    return () => { saveHandlerRef.current = null }
  }, [saveHandlerRef, saveMutation])

  const selectAccount = (account: MonitorAccount) => {
    setIsCreating(false)
    setEditingId(account.id)
    setActiveAccountId(account.id)
  }

  const startCreate = () => {
    setIsCreating(true)
    setEditingId(null)
    setActiveAccountId('all')
    setAccountInput('')
    setDisplayName('')
    setEnabled(true)
    setIntervalMinutes(30)
    setSavedValues({ accountInput: '', displayName: '', enabled: true, intervalMinutes: 30 })
  }

  const formDisabled = isBusy || (!isCreating && !activeAccount)

  const content = (
    <div className={embedded ? 'space-y-4' : 'p-4 space-y-4'}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-cyber-text-primary"><UsersRound className="h-4 w-4 text-cyber-neon-cyan" />{t('monitor.accountList', { count: accounts.length })}</div>
        <span className={`rounded border px-2 py-1 text-[9px] ${isCreating ? 'border-cyber-neon-green/30 bg-cyber-neon-green/5 text-cyber-neon-green' : 'border-cyber-border-subtle bg-cyber-bg-tertiary/30 text-cyber-text-muted'}`}>
          {isCreating
            ? t('monitor.creatingAccount')
            : activeAccount
              ? t('monitor.editingAccount', { name: activeAccount.display_name || activeAccount.sec_user_id })
              : t('monitor.selectAccount')}
        </span>
        <Button type="button" variant="outline" size="sm" onClick={startCreate} disabled={isBusy} className="h-8"><Plus className="h-3.5 w-3.5" />{t('monitor.addAccount')}</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => snapshotMutation.mutate()} disabled={isBusy} className="h-8"><Clock3 className="h-3.5 w-3.5" />{t('monitor.runSnapshots')}</Button>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[280px_minmax(0,1fr)]">
        <div className="max-h-[260px] overflow-y-auto rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-1">
          {accounts.map((account) => <button key={account.id} type="button" onClick={() => selectAccount(account)} className={`mb-1 w-full rounded-md px-3 py-2 text-left ${editingId === account.id ? 'bg-cyber-neon-cyan/10' : 'hover:bg-cyber-bg-tertiary'}`}><div className="flex items-center gap-2"><UserRound className="h-3.5 w-3.5 text-cyber-text-muted" /><span className="truncate text-xs text-cyber-text-primary">{account.display_name || account.sec_user_id}</span><span className={`ml-auto h-2 w-2 rounded-full ${account.enabled ? 'bg-cyber-neon-green' : 'bg-cyber-text-muted'}`} /></div><div className="mt-1 truncate text-[9px] text-cyber-text-muted">{account.sec_user_id} · {account.discover_interval_minutes} min</div></button>)}
          {accounts.length === 0 ? <div className="px-3 py-8 text-center text-xs text-cyber-text-muted">{t('monitor.noAccounts')}</div> : null}
        </div>

        <div className="space-y-3 rounded-md border border-cyber-border-subtle p-3">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div className="space-y-1.5"><Label className="text-xs text-cyber-text-secondary">{t('monitor.displayName')}</Label><Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder={t('monitor.displayNamePlaceholder')} disabled={formDisabled} className="h-9 text-xs" /></div>
            <div className="space-y-1.5"><Label className="text-xs text-cyber-text-secondary">{t('monitor.account')}</Label><Input value={accountInput} onChange={(event) => setAccountInput(event.target.value)} placeholder="https://www.douyin.com/user/..." disabled={formDisabled} className="h-9 text-xs" /></div>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div className="space-y-1.5"><Label className="text-xs text-cyber-text-secondary">{t('monitor.interval')}</Label><Select value={String(intervalMinutes)} onValueChange={(value) => setIntervalMinutes(Number(value))} disabled={formDisabled}><SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger><SelectContent>{[30, 60, 120, 240, 360].map((value) => <SelectItem key={value} value={String(value)}>{value} min</SelectItem>)}</SelectContent></Select></div>
            <label className="flex items-center gap-2 pt-6 text-xs text-cyber-text-primary"><Checkbox checked={enabled} onCheckedChange={(checked) => setEnabled(checked === true)} disabled={formDisabled} />{t('monitor.enable')}</label>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {!embedded ? <Button type="button" size="sm" onClick={() => saveMutation.mutate()} disabled={isBusy || !accountValid} className="h-9"><Save className="h-4 w-4" />{saveMutation.isPending ? t('monitor.saving') : t('monitor.save')}</Button> : null}
            <Button type="button" variant="outline" size="sm" onClick={() => editingId !== null && discoverMutation.mutate(editingId)} disabled={isBusy || isCreating || editingId === null || !activeAccount?.enabled} className="h-9"><RefreshCw className={`h-4 w-4 ${discoverMutation.isPending ? 'animate-spin' : ''}`} />{t('monitor.discover')}</Button>
            <Button type="button" variant="outline" size="sm" onClick={() => editingId !== null && window.confirm(t('monitor.confirmDelete', { name: activeAccount?.display_name || activeAccount?.sec_user_id })) && deleteMutation.mutate(editingId)} disabled={isBusy || editingId === null} className="h-9 text-cyber-neon-pink"><Trash2 className="h-4 w-4" />{t('monitor.delete')}</Button>
            <div className="ml-auto flex items-center gap-2 text-[10px] text-cyber-text-muted"><Clock3 className="h-3.5 w-3.5" />{status?.account?.last_discovered_at ? t('monitor.lastDiscovered', { time: new Date(status.account.last_discovered_at * 1000).toLocaleString() }) : t('monitor.notDiscovered')}</div>
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[10px]"><span className={status?.loop_running ? 'text-cyber-neon-green' : 'text-cyber-neon-orange'}>{status?.loop_running ? t('monitor.loopRunning') : t('monitor.loopStopped')}</span>{Object.entries(status?.jobs || {}).map(([jobStatus, count]) => <span key={jobStatus} className="rounded border border-cyber-border-subtle bg-cyber-bg-tertiary/40 px-2 py-1 text-cyber-text-secondary">{jobStatus}: {count}</span>)}</div>
    </div>
  )

  if (embedded) return content
  return <section className="rounded-lg glass-panel float-panel overflow-hidden"><header className="border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3"><div className="text-xs font-semibold text-cyber-text-primary">{t('monitor.title')}</div><div className="mt-0.5 text-[10px] text-cyber-text-muted">{t('monitor.description')}</div></header>{content}</section>
}
