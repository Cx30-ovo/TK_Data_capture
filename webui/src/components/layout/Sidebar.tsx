import type { ReactNode } from 'react'
import { Github, Plus, Radar, Wifi } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { useCrawlerStore } from '@/store/crawlerStore'
import { useCrawlerStatus } from '@/hooks/useCrawler'
import { LanguageSwitch } from './LanguageSwitch'
import { ThemeToggle } from './ThemeToggle'
import { MonitorAccountSelector } from '@/components/monitor/MonitorAccountSelector'


export function Sidebar({
  navigation,
  onCreateMonitor,
}: {
  navigation: ReactNode
  onCreateMonitor: () => void
}) {
  const { t } = useTranslation()
  const status = useCrawlerStore((state) => state.status)
  useCrawlerStatus()

  const isRunning = status === 'running'

  return (
    <aside className="app-sidebar relative z-20 flex flex-col p-3">
      <div className="flex items-center gap-3 px-1">
        <div className="app-brand-mark flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-white lg:h-10 lg:w-10">
          <Radar className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-cyber-text-primary">MediaCrawler</div>
          <div className="truncate text-[11px] text-cyber-text-muted">{t('sidebar.subtitle')}</div>
        </div>
        {isRunning ? (
          <Badge variant="running" className="h-6 gap-1.5 whitespace-nowrap text-[10px]">
            <span className="h-1.5 w-1.5 rounded-full bg-cyber-neon-green" />
            {t('status.active')}
          </Badge>
        ) : null}
        <button
          type="button"
          onClick={onCreateMonitor}
          className="app-create-button ml-auto flex h-11 w-11 flex-none cursor-pointer items-center justify-center p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-red focus-visible:ring-offset-2 focus-visible:ring-offset-cyber-bg-panel sm:w-auto sm:px-3 lg:hidden"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span className="hidden text-sm font-semibold sm:inline">{t('sidebar.createMonitorTask')}</span>
          <span className="sr-only sm:hidden">{t('sidebar.createMonitorTask')}</span>
        </button>
      </div>

      <button
        type="button"
        onClick={onCreateMonitor}
        className="app-create-button mt-4 hidden w-full cursor-pointer items-center justify-center gap-2 px-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-red focus-visible:ring-offset-2 focus-visible:ring-offset-cyber-bg-panel lg:flex"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        {t('sidebar.createMonitorTask')}
      </button>

      <nav className="mt-3 min-h-0 flex-1 lg:mt-4 lg:overflow-y-auto" aria-label={t('sidebar.primaryNavigation')}>
        {navigation}
      </nav>

      <div className="app-sidebar-tools mt-3 flex items-center gap-2 border-t border-cyber-border-subtle pt-3 lg:mt-4 lg:block lg:space-y-3">
        <MonitorAccountSelector />
        <div className="ml-auto flex items-center gap-2 lg:ml-0 lg:justify-between">
          <ThemeToggle />
          <LanguageSwitch />
          <a
            href="https://github.com/NanmiCoder/MediaCrawler"
            target="_blank"
            rel="noopener noreferrer"
            title={t('sidebar.repository')}
            aria-label={t('sidebar.repository')}
            className="hidden h-11 w-11 items-center justify-center rounded-md border border-cyber-border-subtle text-cyber-text-muted transition-colors hover:border-cyber-border-default hover:text-cyber-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:flex lg:h-8 lg:w-8"
          >
            <Github className="h-4 w-4" aria-hidden="true" />
          </a>
        </div>
        <div className="hidden items-center gap-2 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/35 px-2.5 py-2 text-[10px] text-cyber-text-muted lg:flex">
          <Wifi className="h-3.5 w-3.5 text-status-success" aria-hidden="true" />
          <span>{t('sidebar.local')}</span>
          <span className="status-dot status-dot-online" />
          <span className="ml-auto">{t('sidebar.api')} v1.0.0</span>
        </div>
      </div>
    </aside>
  )
}
