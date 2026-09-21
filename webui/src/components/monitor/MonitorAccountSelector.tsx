import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { UserRound } from 'lucide-react'
import { monitorApi } from '@/lib/api'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useMonitorAccountStore } from '@/store/monitorAccountStore'


export function MonitorAccountSelector() {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const activeAccountId = useMonitorAccountStore((state) => state.activeAccountId)
  const setActiveAccountId = useMonitorAccountStore((state) => state.setActiveAccountId)
  const { data } = useQuery({
    queryKey: ['monitorAccounts'],
    queryFn: async () => (await monitorApi.getAccounts()).data.accounts,
    refetchInterval: 30000,
  })
  const accounts = data || []

  useEffect(() => {
    if (accounts.length === 0) {
      if (activeAccountId !== null) setActiveAccountId(null)
      return
    }
    const activeAccountIsValid = activeAccountId === 'all'
      || (typeof activeAccountId === 'number' && accounts.some((account) => account.id === activeAccountId))
    if (!activeAccountIsValid) {
      setActiveAccountId((accounts.find((account) => account.enabled) || accounts[0]).id)
    }
  }, [accounts, activeAccountId, setActiveAccountId])

  return (
    <div className="flex min-h-11 min-w-0 flex-1 items-center gap-1.5 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary px-2 py-1 lg:min-h-0">
      <UserRound className="h-3.5 w-3.5 text-cyber-text-muted" aria-hidden="true" />
      <Select
        value={activeAccountId ? String(activeAccountId) : ''}
        onValueChange={(value) => {
          setActiveAccountId(value === 'all' ? 'all' : Number(value))
          queryClient.invalidateQueries({
            predicate: (query) => String(query.queryKey[0] || '').startsWith('monitor') && query.queryKey[0] !== 'monitorAccounts',
          })
        }}
      >
        <SelectTrigger className="h-9 min-w-0 flex-1 border-0 bg-transparent px-1 text-[10px] shadow-none lg:h-7">
          <SelectValue placeholder="选择监控账号" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t('monitor.allAccounts')}</SelectItem>
          {accounts.map((account) => (
            <SelectItem key={account.id} value={String(account.id)}>
              {account.display_name || account.sec_user_id}{account.enabled ? '' : '（已停用）'}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
