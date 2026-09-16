import { create } from 'zustand'


const ACTIVE_ACCOUNT_KEY = 'mediacrawler_active_monitor_account'


export type ActiveMonitorAccountId = number | 'all' | null


function loadActiveAccountId(): ActiveMonitorAccountId {
  const value = localStorage.getItem(ACTIVE_ACCOUNT_KEY)
  if (!value) return null
  if (value === 'all') return 'all'
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}


interface MonitorAccountState {
  activeAccountId: ActiveMonitorAccountId
  setActiveAccountId: (accountId: ActiveMonitorAccountId) => void
}


export const useMonitorAccountStore = create<MonitorAccountState>((set) => ({
  activeAccountId: loadActiveAccountId(),
  setActiveAccountId: (accountId) => {
    if (accountId === null) {
      localStorage.removeItem(ACTIVE_ACCOUNT_KEY)
    } else {
      localStorage.setItem(ACTIVE_ACCOUNT_KEY, String(accountId))
    }
    set({ activeAccountId: accountId })
  },
}))


export function getActiveMonitorAccountId(): ActiveMonitorAccountId {
  return useMonitorAccountStore.getState().activeAccountId
}
