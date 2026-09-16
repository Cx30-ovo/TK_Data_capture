import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Bell, CheckCheck, Inbox } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { monitorApi } from '@/lib/api'


function formatDateTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}


export function MonitorAlerts() {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<'all' | 'unread' | 'read'>('unread')
  const { data } = useQuery({
    queryKey: ['monitorAlerts', statusFilter],
    queryFn: async () => (await monitorApi.getAlerts(statusFilter === 'all' ? undefined : statusFilter)).data,
    refetchInterval: 30000,
  })

  const markRead = useMutation({
    mutationFn: (alertId: number) => monitorApi.markAlertRead(alertId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitorAlerts'] })
      queryClient.invalidateQueries({ queryKey: ['monitorHealth'] })
    },
  })

  const markAllRead = useMutation({
    mutationFn: () => monitorApi.markAllAlertsRead(),
    onSuccess: (response) => {
      toast.success(t('alerts.markedAll', { count: response.data.updated }))
      queryClient.invalidateQueries({ queryKey: ['monitorAlerts'] })
      queryClient.invalidateQueries({ queryKey: ['monitorHealth'] })
    },
  })

  const alerts = data?.alerts || []

  return (
    <section className="rounded-lg glass-panel float-panel overflow-hidden animate-slide-up">
      <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
        <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center">
          <Bell className="h-4 w-4 text-cyber-neon-orange" />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('alerts.title')}</div>
          <div className="text-[10px] text-cyber-text-muted">{t('alerts.description')}</div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[10px] font-mono text-cyber-neon-orange">{t('alerts.unread', { count: data?.unread ?? 0 })}</span>
          <Button type="button" variant="outline" size="sm" onClick={() => markAllRead.mutate()} disabled={markAllRead.isPending || (data?.unread ?? 0) === 0} className="h-8 font-mono text-[10px]">
            <CheckCheck className="w-3.5 h-3.5" />
            {t('alerts.markAllRead')}
          </Button>
        </div>
      </header>

      <div className="p-4 space-y-4">
        <div className="flex flex-wrap gap-1">
          {(['unread', 'read', 'all'] as const).map((status) => (
            <Button
              key={status}
              type="button"
              variant={statusFilter === status ? 'default' : 'outline'}
              size="sm"
              onClick={() => setStatusFilter(status)}
              className="h-8 px-3 font-mono text-[10px]"
            >
              {t(`alerts.filter.${status}`)}
            </Button>
          ))}
        </div>

        {alerts.length > 0 ? (
          <div className="space-y-2">
            {alerts.map((alert) => (
              <div key={alert.id} className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3 flex items-start gap-3">
                <div className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${alert.severity === 'error' ? 'bg-cyber-neon-pink' : alert.severity === 'warning' ? 'bg-cyber-neon-orange' : 'bg-cyber-neon-cyan'}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-mono text-cyber-text-primary">{alert.title}</span>
                    <span className="text-[10px] font-mono text-cyber-text-muted">{alert.alert_type}</span>
                    <span className="text-[10px] font-mono text-cyber-text-muted">{formatDateTime(alert.created_at)}</span>
                  </div>
                  <div className="mt-1 text-[11px] font-mono text-cyber-text-secondary">{alert.message}</div>
                </div>
                {alert.status === 'unread' ? (
                  <Button type="button" variant="ghost" size="sm" onClick={() => markRead.mutate(alert.id)} className="h-7 px-2 font-mono text-[10px]">
                    {t('alerts.markRead')}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="py-12 flex flex-col items-center gap-2 text-cyber-text-muted">
            <Inbox className="w-8 h-8 opacity-50" />
            <span className="text-xs font-mono">{t('alerts.empty')}</span>
          </div>
        )}
      </div>
    </section>
  )
}
