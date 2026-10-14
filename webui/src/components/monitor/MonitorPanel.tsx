import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronRight, Clock3, ExternalLink, Info, Plus, RefreshCw, Save, Search, Trash2, UsersRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { collectionErrorMessage, monitorApi, type MonitorAccount, type MonitorRunResult } from '@/lib/api'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'
import { MonitorExecutionPanel, useMonitorExecution } from './MonitorExecutionPanel'

export function parseSecUserId(value: string): string {
  const trimmed = value.trim()
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      const url = new URL(trimmed)
      if (!['douyin.com', 'www.douyin.com'].includes(url.hostname.toLowerCase())) return ''
      return url.pathname.match(/^\/user\/([A-Za-z0-9_-]{6,255})\/?$/)?.[1] || ''
    } catch { return '' }
  }
  return /^[A-Za-z0-9_-]{6,255}$/.test(trimmed) ? trimmed : ''
}

interface Draft {
  accountInput: string
  displayName: string
  mode: 'active' | 'discoveryOff' | 'paused'
  intervalMinutes: number
}
const emptyDraft: Draft = { accountInput: '', displayName: '', mode: 'active', intervalMinutes: 30 }
const intervalOptions = [30, 60, 120, 240, 360]
function accountDraft(account: MonitorAccount): Draft {
  return { accountInput: account.profile_url || account.sec_user_id, displayName: account.display_name || '',
    mode: account.snapshots_paused ? 'paused' : account.enabled ? 'active' : 'discoveryOff',
    intervalMinutes: account.discover_interval_minutes }
}
function sameDraft(left: Draft, right: Draft) {
  return left.accountInput.trim() === right.accountInput.trim() && left.displayName.trim() === right.displayName.trim()
    && left.mode === right.mode && left.intervalMinutes === right.intervalMinutes
}
type Navigation = { type: 'select'; id: number } | { type: 'create' }
interface MonitorPanelProps {
  embedded?: boolean
  onOpenAbnormalTasks?: (accountId: number) => void
  onDirtyChange?: (dirty: boolean) => void
  onValidChange?: (valid: boolean) => void
  saveHandlerRef?: { current: (() => void) | null }
}

export function MonitorPanel({ embedded = false, onOpenAbnormalTasks, onDirtyChange, onValidChange, saveHandlerRef }: MonitorPanelProps) {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const activeAccountId = useMonitorAccountStore(state => state.activeAccountId)
  const setActiveAccountId = useMonitorAccountStore(state => state.setActiveAccountId)
  const { data: executionStatus, isError: executionError } = useMonitorExecution()
  const accountsQuery = useQuery({
    queryKey: ['monitorAccounts'],
    queryFn: async () => (await monitorApi.getAccounts()).data,
    refetchInterval: 30000,
  })
  const accounts = accountsQuery.data?.accounts || []
  const [editingId, setEditingId] = useState<number | null>(typeof activeAccountId === 'number' ? activeAccountId : null)
  const editingIdRef = useRef(editingId)
  const [isCreating, setIsCreating] = useState(false)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [savedValues, setSavedValues] = useState<Draft>(emptyDraft)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [sort, setSort] = useState('attention')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [batchInterval, setBatchInterval] = useState(30)
  const [batchOpen, setBatchOpen] = useState(false)
  const [navigation, setNavigation] = useState<Navigation | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const activeAccount = accounts.find(account => account.id === editingId)
  const accountDirty = !sameDraft(draft, savedValues)
  const parsedId = parseSecUserId(draft.accountInput)
  const duplicate = isCreating && !!parsedId && accounts.some(account => account.sec_user_id === parsedId)
  const accountValid = !!parsedId && !duplicate
  const configKey = activeAccount ? JSON.stringify(accountDraft(activeAccount)) : ''
  const externalChange = !!activeAccount && accountDirty && !sameDraft(accountDraft(activeAccount), savedValues)

  function loadAccount(account: MonitorAccount) {
    editingIdRef.current = account.id
    const values = accountDraft(account)
    setDraft(values); setSavedValues(values); setEditingId(account.id); setIsCreating(false)
    setActiveAccountId(account.id)
  }
  function navigate(action: Navigation) {
    setNavigation(null)
    if (action.type === 'select') {
      const account = accounts.find(item => item.id === action.id)
      if (account) loadAccount(account)
    } else {
      editingIdRef.current = null
      setIsCreating(true); setEditingId(null); setDraft(emptyDraft); setSavedValues(emptyDraft)
    }
  }
  function requestNavigation(action: Navigation) {
    if (isBusy) return
    if (action.type === 'select' && action.id === editingId && !isCreating) return
    if (accountDirty) setNavigation(action)
    else navigate(action)
  }

  useEffect(() => {
    // An external-store update can flush an older render while switching.
    // Never let that render restore the previous account or reopen the guard.
    if (editingId !== editingIdRef.current) return
    if (isCreating || !accountsQuery.data) return
    const target = typeof activeAccountId === 'number' ? accounts.find(account => account.id === activeAccountId) : undefined
    if (target && target.id !== editingId) {
      if (accountDirty) {
        setNavigation({ type: 'select', id: target.id })
        if (editingId !== null) setActiveAccountId(editingId)
      } else loadAccount(target)
      return
    }
    if (!activeAccount) {
      if (!accountDirty && accounts[0]) loadAccount(accounts[0])
      return
    }
    if (!accountDirty) {
      const values = accountDraft(activeAccount)
      setDraft(values); setSavedValues(values)
    }
    // Configuration changes are separate from discovery timestamps. Dirty drafts stay intact.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeAccountId, editingId, isCreating, configKey, accountsQuery.data !== undefined])

  useEffect(() => { onDirtyChange?.(accountDirty) }, [accountDirty, onDirtyChange])
  useEffect(() => { onValidChange?.(accountValid) }, [accountValid, onValidChange])
  useEffect(() => {
    if (!accountDirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [accountDirty])

  function refreshAccounts() {
    for (const key of ['monitorAccounts', 'monitorStatus', 'monitorDashboard', 'monitorOverview', 'monitorJobs', 'monitorAlerts', 'monitorHealth', 'monitorExecution']) {
      queryClient.invalidateQueries({ queryKey: [key] })
    }
  }
  const saveMutation = useMutation({
    mutationFn: () => {
      if (!accountValid) throw new Error(t(duplicate ? 'accountManager.duplicate' : 'accountManager.invalid'))
      const settings = { display_name: draft.displayName.trim(), enabled: draft.mode === 'active',
        snapshots_paused: draft.mode === 'paused', discover_interval_minutes: draft.intervalMinutes }
      return isCreating || editingId === null
        ? monitorApi.createAccount({ ...settings, sec_user_id: parsedId, profile_url: `https://www.douyin.com/user/${parsedId}` })
        : monitorApi.updateAccount(editingId, settings)
    },
    onSuccess: response => {
      loadAccount(response.data)
      // Update only configuration here; refresh preserves the full runtime summary.
      queryClient.setQueryData<{ accounts: MonitorAccount[]; loop_running?: boolean }>(['monitorAccounts'], current => current
        ? { ...current, accounts: current.accounts.some(item => item.id === response.data.id)
          ? current.accounts.map(item => item.id === response.data.id ? { ...item, ...response.data } : item)
          : [...current.accounts, response.data] } : { accounts: [response.data] })
      toast.success(t('monitor.saved')); refreshAccounts()
    },
    onError: error => toast.error(collectionErrorMessage(error)),
  })
  useEffect(() => {
    if (!saveHandlerRef) return
    saveHandlerRef.current = () => { saveMutation.mutate() }
    return () => { saveHandlerRef.current = null }
  }, [saveHandlerRef, saveMutation])

  const deleteMutation = useMutation({
    mutationFn: (id: number) => monitorApi.deleteAccount(id),
    onSuccess: (_response, id) => {
      setDeleteOpen(false)
      const next = accounts.find(account => account.id !== id)
      if (next) loadAccount(next)
      else { editingIdRef.current = null; setEditingId(null); setActiveAccountId(null); setDraft(emptyDraft); setSavedValues(emptyDraft) }
      toast.success(t('monitor.deleted')); refreshAccounts()
    },
    onError: error => toast.error(collectionErrorMessage(error)),
  })
  function showResult(result: MonitorRunResult, accountId?: number) {
    const message = result.reason || (result.created_posts !== undefined
      ? t('accountManager.discoveryCounts', { posts: result.created_posts || 0, jobs: result.created_jobs || 0 })
      : t('accountManager.snapshotsCompleted', { count: result.completed || 0 }))
    if (result.status === 'ok') toast.success(message)
    else toast.warning(message)
    if (accountId !== undefined) {
      queryClient.setQueryData<{ accounts: MonitorAccount[]; loop_running?: boolean }>(['monitorAccounts'], current => current
        ? { ...current, accounts: current.accounts.map(account => account.id === accountId
          ? { ...account, last_discovery_result: result, last_discovery_finished_at: Math.floor(Date.now() / 1000) }
          : account) }
        : current)
    }
    refreshAccounts()
  }
  const discoverMutation = useMutation({
    mutationFn: (id: number) => monitorApi.discoverAccount(id),
    onSuccess: (response, id) => showResult(response.data, id),
    onError: error => toast.error(collectionErrorMessage(error)),
  })
  const snapshotMutation = useMutation({
    mutationFn: () => monitorApi.runDueSnapshots(),
    onSuccess: response => showResult(response.data),
    onError: error => toast.error(collectionErrorMessage(error)),
  })
  const batchMutation = useMutation({
    mutationFn: () => monitorApi.updateAccountIntervals(selectedIds, batchInterval),
    onSuccess: response => {
      toast.success(t('accountManager.batchSaved', { count: response.data.updated }))
      setBatchOpen(false); setSelectedIds([]); refreshAccounts()
    },
    onError: error => toast.error(collectionErrorMessage(error)),
  })
  const isBusy = saveMutation.isPending || deleteMutation.isPending || discoverMutation.isPending || snapshotMutation.isPending || batchMutation.isPending

  function stateOf(account: MonitorAccount): string {
    if (account.snapshots_paused) return 'paused'
    if (!account.enabled) return 'discoveryOff'
    if (executionStatus?.paused) return 'paused'
    if (executionStatus?.retry_after_seconds) return 'cooling'
    if (executionStatus?.recovery?.pending) return 'recovering'
    if (executionStatus?.execution?.active && executionStatus.execution.sec_user_id === account.sec_user_id) return 'collecting'
    if (account.retry_after_seconds) return 'retrying'
    if (executionStatus?.crawler_running) return 'crawler'
    if (accountsQuery.data?.loop_running === false) return 'stopped'
    if (!executionStatus || executionError || accountsQuery.isError) return 'unknown'
    if (account.abnormal_jobs || ['error', 'blocked', 'partial'].includes(account.last_discovery_result?.status || '')) return 'attention'
    return 'monitoring'
  }
  function isAttention(account: MonitorAccount) {
    return !!account.abnormal_jobs || ['attention', 'cooling', 'recovering', 'retrying', 'stopped', 'unknown'].includes(stateOf(account))
  }
  const filteredAccounts = useMemo(() => accounts.filter(account => {
    const state = stateOf(account)
    const term = search.trim().toLowerCase()
    return (!term || `${account.display_name} ${account.sec_user_id}`.toLowerCase().includes(term))
      && (filter === 'all' || filter === 'attention' && isAttention(account)
        || filter === 'paused' && ['paused', 'discoveryOff'].includes(state)
        || filter === 'active' && account.enabled && !account.snapshots_paused)
  }).sort((left, right) => sort === 'name' ? left.display_name.localeCompare(right.display_name)
    : sort === 'recent' ? (right.last_discovered_at || 0) - (left.last_discovered_at || 0)
    : Number(isAttention(right)) - Number(isAttention(left)) || left.id - right.id),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [accountsQuery.data, executionStatus, executionError, accountsQuery.isError, search, filter, sort])
  const selectedVisible = filteredAccounts.length > 0 && filteredAccounts.every(account => selectedIds.includes(account.id))
  const formatTime = (value?: number | null) => value ? new Date(value * 1000).toLocaleString() : t('accountManager.notYet')
  const formatNextDiscovery = (account: MonitorAccount) => {
    if (!account.enabled) return t('accountManager.next', { time: '—' })
    if (account.next_discovery_at != null) return t('accountManager.next', { time: formatTime(account.next_discovery_at) })
    const now = Math.floor(Date.now() / 1000)
    const intervalTime = account.last_discovered_at
      ? account.last_discovered_at + Math.max(1, account.discover_interval_minutes) * 60
      : now
    const cooldown = Math.max(account.retry_after_seconds || 0, executionStatus?.retry_after_seconds || 0)
    return t('accountManager.nextEstimated', { time: formatTime(Math.max(intervalTime, now + cooldown)) })
  }
  const activeState = activeAccount ? stateOf(activeAccount) : 'unknown'
  const hasDiscoveryHistory = !!(activeAccount?.last_discovery_finished_at || activeAccount?.last_discovered_at)
  const collectionReason = !executionStatus || executionError ? t('accountManager.connectionRequired')
    : executionStatus.paused ? t('accountManager.globalPaused')
    : executionStatus.retry_after_seconds ? t('accountManager.sharedCooldown', { minutes: Math.ceil(executionStatus.retry_after_seconds / 60) })
    : executionStatus.recovery?.pending ? t('accountManager.sharedRecovery')
    : executionStatus.execution?.active || executionStatus.crawler_running ? t('accountManager.busy') : ''
  const discoverReason = collectionReason || (isCreating || !activeAccount ? t('accountManager.saveFirst')
    : !activeAccount.enabled ? t('accountManager.discoveryStopped') : accountDirty ? t('accountManager.saveChangesFirst')
    : activeAccount.retry_after_seconds ? t('accountManager.retryAfter', { seconds: activeAccount.retry_after_seconds }) : '')
  const lastResult = activeAccount?.last_discovery_result
  const intervalChoices = [...new Set([...intervalOptions, draft.intervalMinutes])].sort((a, b) => a - b)
  const stateLabel = (state: string) => t(`accountManager.state.${state}`)
  const stateVariant = (state: string): 'success' | 'warning' | 'running' | 'idle' =>
    state === 'monitoring' ? 'success' : state === 'collecting' ? 'running'
      : ['attention', 'cooling', 'retrying', 'recovering', 'unknown', 'stopped'].includes(state) ? 'warning' : 'idle'
  const formDisabled = isBusy || (!isCreating && !activeAccount)

  const content = (
    <div className={embedded ? 'space-y-4' : 'space-y-4 p-4'}>
      <MonitorExecutionPanel />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-cyber-text-primary">
          <UsersRound aria-hidden="true" className="h-4 w-4 text-cyber-neon-cyan" />
          {t('monitor.accountList', { count: accounts.length })}
          {accountDirty && <Badge variant="warning">{t('accountManager.unsaved')}</Badge>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="min-h-11" onClick={() => requestNavigation({ type: 'create' })} disabled={isBusy}>
            <Plus aria-hidden="true" className="h-4 w-4" />{t('monitor.addAccount')}
          </Button>
          <Button variant="outline" className="min-h-11" onClick={() => snapshotMutation.mutate()} disabled={isBusy || !!collectionReason}>
            <Clock3 aria-hidden="true" className="h-4 w-4" />{t('accountManager.runAllSnapshots')}
          </Button>
        </div>
      </div>
      {collectionReason && <p className="flex items-start gap-2 text-xs text-status-warning" role="status"><Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />{collectionReason}</p>}
      {accountsQuery.isError && <div role="alert" className="flex items-center gap-3 text-sm text-status-warning">
        {t('accountManager.loadFailed')}<Button variant="outline" onClick={() => accountsQuery.refetch()}>{t('execution.refresh')}</Button>
      </div>}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
        <section className="flex h-[480px] min-w-0 flex-col rounded-xl border border-cyber-border-subtle bg-cyber-bg-tertiary/20" aria-label={t('accountManager.accounts')}>
          <div className="space-y-2 border-b border-cyber-border-subtle p-3">
            <div className="relative"><Search aria-hidden="true" className="absolute left-3 top-3 h-4 w-4 text-cyber-text-muted" />
              <Input aria-label={t('accountManager.search')} placeholder={t('accountManager.search')} value={search} onChange={event => setSearch(event.target.value)} className="min-h-11 pl-9" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Select value={filter} onValueChange={setFilter}><SelectTrigger aria-label={t('accountManager.filter')} className="min-h-11 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{['all', 'active', 'paused', 'attention'].map(value => <SelectItem key={value} value={value}>{t(`accountManager.filterOptions.${value}`)}</SelectItem>)}</SelectContent>
              </Select>
              <Select value={sort} onValueChange={setSort}><SelectTrigger aria-label={t('accountManager.sort')} className="min-h-11 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{['attention', 'name', 'recent'].map(value => <SelectItem key={value} value={value}>{t(`accountManager.sortOptions.${value}`)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between gap-2 text-xs text-cyber-text-secondary">
              <div className="flex items-center gap-1 [&>label]:min-h-11 [&>label]:min-w-11"><Checkbox aria-label={t('accountManager.selectVisible')} checked={selectedVisible} disabled={!filteredAccounts.length || isBusy} onCheckedChange={checked =>
                setSelectedIds(current => checked ? [...new Set([...current, ...filteredAccounts.map(account => account.id)])] : current.filter(id => !filteredAccounts.some(account => account.id === id)))} /><span>{t('accountManager.selectVisible')}</span></div>
              <Button variant="ghost" className="min-h-11 px-2 text-xs" disabled={!selectedIds.length || isBusy || accountDirty} onClick={() => setBatchOpen(true)}>{t('accountManager.batch', { count: selectedIds.length })}</Button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2">
            {accountsQuery.isLoading ? <p className="p-4 text-sm text-cyber-text-muted">{t('execution.loading')}</p>
              : filteredAccounts.length === 0 ? <p className="p-4 text-sm text-cyber-text-muted">{t(accounts.length ? 'accountManager.noMatches' : 'monitor.noAccounts')}</p>
              : filteredAccounts.map(account => {
                const state = stateOf(account)
                return <div key={account.id} className={`mb-1 flex items-start gap-2 rounded-lg border p-2 ${editingId === account.id && !isCreating ? 'border-cyber-neon-cyan/30 bg-cyber-neon-cyan/10' : 'border-transparent hover:bg-cyber-bg-tertiary'}`}>
                  <div className="flex shrink-0 items-center [&>label]:min-h-11 [&>label]:min-w-11"><Checkbox aria-label={t('accountManager.selectAccount', { name: account.display_name })} checked={selectedIds.includes(account.id)} disabled={isBusy}
                    onCheckedChange={checked => setSelectedIds(current => checked ? [...new Set([...current, account.id])] : current.filter(id => id !== account.id))} /></div>
                  <button type="button" disabled={isBusy} aria-pressed={editingId === account.id && !isCreating} onClick={() => requestNavigation({ type: 'select', id: account.id })} className="min-h-11 min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-neon-cyan disabled:opacity-50">
                    <div className="flex flex-wrap items-center gap-1"><span className="min-w-0 truncate text-sm font-medium text-cyber-text-primary">{account.display_name}</span></div>
                    <p className="mt-1 text-xs text-cyber-text-secondary">{t('accountManager.accountCounts', { posts: account.today_new_posts ?? 0, due: account.due_jobs ?? 0 })}</p>
                    <p className="mt-1 truncate text-xs text-cyber-text-muted">{formatNextDiscovery(account)}</p>
                  </button>
                  {(account.abnormal_jobs ?? 0) > 0 && onOpenAbnormalTasks ? (
                    <Button
                      type="button"
                      variant="ghost"
                      className="min-h-11 shrink-0 px-1"
                      aria-label={t('accountManager.viewAbnormalFor', { name: account.display_name })}
                      title={t('accountManager.viewAbnormal')}
                      onClick={() => onOpenAbnormalTasks(account.id)}
                    >
                      <Badge variant="warning">{t('accountManager.state.attention')} · {account.abnormal_jobs ?? 0}</Badge>
                      <ChevronRight aria-hidden="true" className="h-3.5 w-3.5 text-cyber-text-muted" />
                    </Button>
                  ) : <Badge variant={stateVariant(state)}>{stateLabel(state)}</Badge>}
                </div>
              })}
          </div>
        </section>
        <section className="flex h-[480px] min-w-0 flex-col rounded-xl border border-cyber-border-subtle" aria-label={t('accountManager.settings')}>
          <div className="flex items-center justify-between gap-2 border-b border-cyber-border-subtle px-4 py-3">
            <span className="truncate text-sm font-semibold text-cyber-text-primary">{isCreating ? t('monitor.creatingAccount') : activeAccount?.display_name || t('monitor.selectAccount')}</span>
            {activeAccount && !isCreating && ((activeAccount.abnormal_jobs ?? 0) > 0 && onOpenAbnormalTasks ? (
              <Button
                type="button"
                variant="ghost"
                className="min-h-10 shrink-0 px-1"
                aria-label={t('accountManager.viewAbnormalFor', { name: activeAccount.display_name })}
                title={t('accountManager.viewAbnormal')}
                onClick={() => onOpenAbnormalTasks(activeAccount.id)}
              >
                <Badge variant="warning">{t('accountManager.state.attention')} · {activeAccount.abnormal_jobs ?? 0}</Badge>
                <ChevronRight aria-hidden="true" className="h-3.5 w-3.5 text-cyber-text-muted" />
              </Button>
            ) : <Badge variant={stateVariant(activeState)}>{stateLabel(activeState)}</Badge>)}
          </div>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain p-4">
            {!isCreating && activeAccount && <div className="grid grid-cols-3 gap-2">
              {[
                [t('accountManager.today'), activeAccount.today_new_posts ?? 0],
                [t('accountManager.due'), activeAccount.due_jobs ?? 0],
                [t('accountManager.abnormal'), activeAccount.abnormal_jobs ?? 0],
              ].map(([label, value]) => <div key={label} className="rounded-lg bg-cyber-bg-tertiary/40 p-3"><p className="text-xs text-cyber-text-muted">{label}</p><p className="mt-1 text-xl font-semibold tabular-nums text-cyber-text-primary">{value}</p></div>)}
            </div>}
            {externalChange && <p className="text-xs text-status-warning" role="status">{t('accountManager.externalChange')}</p>}
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <div className="space-y-1.5"><Label htmlFor="monitor-account-name">{t('monitor.displayName')}</Label><Input id="monitor-account-name" value={draft.displayName} onChange={event => setDraft(current => ({ ...current, displayName: event.target.value }))} disabled={formDisabled} className="min-h-11" /></div>
              <div className="space-y-1.5"><Label htmlFor="monitor-account-identity">{t('monitor.account')}</Label><Input id="monitor-account-identity" value={draft.accountInput} onChange={event => setDraft(current => ({ ...current, accountInput: event.target.value }))} readOnly={!isCreating} disabled={formDisabled} aria-invalid={!!draft.accountInput && !accountValid} aria-describedby="monitor-account-identity-hint" className="min-h-11" placeholder="https://www.douyin.com/user/..." />
                <p id="monitor-account-identity-hint" className={`text-xs ${isCreating && draft.accountInput && !accountValid ? 'text-status-warning' : 'text-cyber-text-muted'}`}>{t(!isCreating ? 'accountManager.identityLocked' : duplicate ? 'accountManager.duplicate' : draft.accountInput && !parsedId ? 'accountManager.invalid' : 'accountManager.identityHint')}</p>
              </div>
              <div className="space-y-1.5"><Label>{t('monitor.interval')}</Label><Select value={String(draft.intervalMinutes)} disabled={formDisabled} onValueChange={value => setDraft(current => ({ ...current, intervalMinutes: Number(value) }))}><SelectTrigger aria-label={t('monitor.interval')} className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{intervalChoices.map(value => <SelectItem key={value} value={String(value)}>{t('accountManager.minutes', { count: value })}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-1.5"><Label>{t('accountManager.mode')}</Label><Select value={draft.mode} disabled={formDisabled} onValueChange={value => setDraft(current => ({ ...current, mode: value as Draft['mode'] }))}><SelectTrigger aria-label={t('accountManager.mode')} className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{['active', 'discoveryOff', 'paused'].map(value => <SelectItem key={value} value={value}>{t(`accountManager.modeOptions.${value}`)}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <p className="text-xs leading-relaxed text-cyber-text-secondary">{t(`accountManager.modeHints.${draft.mode}`)}</p>
            {!isCreating && activeAccount && <div className="space-y-2 border-t border-cyber-border-subtle pt-3 text-xs text-cyber-text-secondary">
              <p>{t('accountManager.lastSuccess', { time: formatTime(activeAccount.last_discovered_at) })}</p>
              <p>{formatNextDiscovery(activeAccount)}</p>
              <div className="flex items-center justify-between gap-2"><span>{lastResult ? t('accountManager.lastResult', { posts: lastResult.created_posts || 0, jobs: lastResult.created_jobs || 0 }) : hasDiscoveryHistory ? t('accountManager.legacyNoResult') : t('accountManager.noResult')}</span>
                <Button variant="ghost" className="min-h-11 shrink-0 px-2 text-xs" disabled={!lastResult && !hasDiscoveryHistory} onClick={() => setDetailsOpen(true)}>{t('accountManager.details')}</Button>
              </div>
            </div>}
          </div>
          <div className="space-y-2 border-t border-cyber-border-subtle p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button className="min-h-11" onClick={() => saveMutation.mutate()} disabled={isBusy || !accountValid || !accountDirty}><Save aria-hidden="true" className="h-4 w-4" />{t(saveMutation.isPending ? 'monitor.saving' : 'monitor.save')}</Button>
              <Button variant="outline" className="min-h-11" onClick={() => editingId !== null && discoverMutation.mutate(editingId)} disabled={isBusy || !!discoverReason}><RefreshCw aria-hidden="true" className={`h-4 w-4 ${discoverMutation.isPending ? 'animate-spin' : ''}`} />{t('monitor.discover')}</Button>
              <Button variant="ghost" className="ml-auto min-h-11 text-cyber-neon-pink" aria-label={t('monitor.delete')} disabled={isBusy || isCreating || !activeAccount} onClick={() => setDeleteOpen(true)}><Trash2 aria-hidden="true" className="h-4 w-4" /></Button>
            </div>
            <p className="text-xs text-cyber-text-muted" role="status">{discoverReason || t('accountManager.discoveryHint')}</p>
          </div>
        </section>
      </div>
      <Dialog open={!!navigation} onOpenChange={open => { if (!open) setNavigation(null) }}>
        <DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-lg"><DialogHeader><DialogTitle>{t('accountManager.unsavedTitle')}</DialogTitle><DialogDescription>{t('accountManager.unsavedHint')}</DialogDescription></DialogHeader>
          <DialogFooter className="gap-2"><Button variant="outline" className="min-h-11" disabled={isBusy} onClick={() => setNavigation(null)}>{t('accountManager.keepEditing')}</Button>
            <Button variant="outline" className="min-h-11" disabled={isBusy} onClick={() => navigation && navigate(navigation)}>{t('accountManager.discard')}</Button>
            <Button className="min-h-11" disabled={isBusy || !accountValid} onClick={async () => { const target = navigation; try { await saveMutation.mutateAsync(); if (target) navigate(target) } catch { /* Mutation displays the failure and keeps the draft. */ } }}>{t('accountManager.saveSwitch')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}><DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-lg"><DialogHeader><DialogTitle>{t('monitor.delete')}</DialogTitle><DialogDescription>{t('monitor.confirmDelete', { name: activeAccount?.display_name })}</DialogDescription></DialogHeader><p className="text-sm text-cyber-text-secondary">{t('accountManager.deleteHint')}</p><DialogFooter><Button variant="outline" disabled={isBusy} onClick={() => setDeleteOpen(false)}>{t('accountManager.cancel')}</Button><Button variant="destructive" disabled={isBusy || editingId === null} onClick={() => editingId !== null && deleteMutation.mutate(editingId)}>{t('monitor.delete')}</Button></DialogFooter></DialogContent></Dialog>
      <Dialog open={batchOpen} onOpenChange={setBatchOpen}><DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-lg"><DialogHeader><DialogTitle>{t('accountManager.batchTitle')}</DialogTitle><DialogDescription>{t('accountManager.batchHint', { count: selectedIds.length })}</DialogDescription></DialogHeader><Select value={String(batchInterval)} onValueChange={value => setBatchInterval(Number(value))}><SelectTrigger aria-label={t('monitor.interval')} className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{intervalOptions.map(value => <SelectItem key={value} value={String(value)}>{t('accountManager.minutes', { count: value })}</SelectItem>)}</SelectContent></Select><DialogFooter><Button variant="outline" disabled={isBusy} onClick={() => setBatchOpen(false)}>{t('accountManager.cancel')}</Button><Button disabled={isBusy || !selectedIds.length} onClick={() => batchMutation.mutate()}>{t('monitor.save')}</Button></DialogFooter></DialogContent></Dialog>
      <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}><DialogContent className="left-auto right-0 top-0 h-dvh w-full max-w-md translate-x-0 translate-y-0 overflow-y-auto rounded-none"><DialogHeader><DialogTitle>{t('accountManager.resultTitle')}</DialogTitle><DialogDescription>{activeAccount?.display_name} · {formatTime(activeAccount?.last_discovery_finished_at || activeAccount?.last_discovered_at)}</DialogDescription></DialogHeader>
        <div className="space-y-3 text-sm text-cyber-text-secondary">{lastResult
          ? <><p>{t('accountManager.resultStatus', { status: t(`execution.state.${lastResult.status === 'ok' ? 'completed' : lastResult.status || 'idle'}`, { defaultValue: lastResult.status }) })}</p><p>{t('accountManager.discoveryCounts', { posts: lastResult.created_posts || 0, jobs: lastResult.created_jobs || 0 })}</p>
            {lastResult.reason && <p role="status">{lastResult.reason}</p>}{lastResult.action && <p>{lastResult.action}</p>}</>
          : <p role="status">{t('accountManager.legacyNoResult')}</p>}
          <p>{t('accountManager.discoveryHint')}</p>
          {activeAccount && <a className="inline-flex min-h-11 items-center gap-2 text-cyber-neon-cyan" href={`https://www.douyin.com/user/${activeAccount.sec_user_id}`} target="_blank" rel="noopener noreferrer"><ExternalLink aria-hidden="true" className="h-4 w-4" />{t('accountManager.openProfile')}</a>}
        </div>
      </DialogContent></Dialog>
    </div>
  )
  return embedded ? content : <section className="overflow-hidden rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary">{content}</section>
}
