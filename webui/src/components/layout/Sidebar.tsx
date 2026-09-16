import { Github, Radar, Wifi } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { useCrawlerStore } from '@/store/crawlerStore'
import { useCrawlerStatus } from '@/hooks/useCrawler'
import { LanguageSwitch } from './LanguageSwitch'
import { ThemeToggle } from './ThemeToggle'
import { MonitorAccountSelector } from '@/components/monitor/MonitorAccountSelector'


export function Sidebar() {
  const { t } = useTranslation()
  const status = useCrawlerStore((state) => state.status)
  useCrawlerStatus()

  const isRunning = status === 'running'
  return (
    <header className="relative z-10 h-14 flex-shrink-0 border-b border-cyber-border-subtle bg-cyber-bg-panel">
      <div className="flex h-full items-center justify-between gap-4 px-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary">
            <Radar className="h-4 w-4 text-cyber-neon-cyan" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-wide text-cyber-text-primary">MediaCrawler</div>
            <div className="truncate text-[9px] text-cyber-text-muted">{t('sidebar.subtitle')}</div>
          </div>
          <a
            href="https://github.com/NanmiCoder/MediaCrawler"
            target="_blank"
            rel="noopener noreferrer"
            title={t('sidebar.repository')}
            className="hidden items-center gap-1.5 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary px-2 py-1 text-cyber-text-secondary transition-colors hover:border-cyber-border-default hover:text-cyber-text-primary xl:flex"
          >
            <Github className="h-3.5 w-3.5" />
            <span className="text-[10px]">Star</span>
          </a>
          {isRunning ? (
            <Badge variant="running" className="gap-1.5 whitespace-nowrap text-[9px]">
              <span className="h-1.5 w-1.5 rounded-full bg-cyber-neon-green" />
              {t('status.active')}
            </Badge>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <MonitorAccountSelector />
          <div className="hidden items-center gap-2 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary px-2.5 py-1.5 text-[10px] text-cyber-text-secondary lg:flex">
            <Wifi className="h-3.5 w-3.5" />
            <span>{t('sidebar.local')}</span>
            <span className="status-dot status-dot-online" />
            <span className="text-cyber-border-default">|</span>
            <span className="text-cyber-text-muted">{t('sidebar.api')} v1.0.0</span>
          </div>
          <ThemeToggle />
          <LanguageSwitch />
        </div>
      </div>
    </header>
  )
}
