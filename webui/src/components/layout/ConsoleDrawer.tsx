import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, TerminalSquare } from 'lucide-react'
import { Terminal } from '@/components/console/Terminal'
import { useLogWebSocket } from '@/hooks/useWebSocket'
import { useCrawlerStore } from '@/store/crawlerStore'


export function ConsoleDrawer() {
  const { t } = useTranslation('common')
  const [isOpen, setIsOpen] = useState(false)
  const logs = useCrawlerStore((state) => state.logs)
  const status = useCrawlerStore((state) => state.status)

  // Keep the WebSocket connected even while the drawer is collapsed.
  useLogWebSocket()

  return (
    <div className={`app-console-drawer fixed inset-x-0 bottom-0 z-50 flex flex-col border-t border-cyber-border-default bg-console-surface shadow-[0_-10px_28px_rgba(0,0,0,0.24)] transition-[height] duration-300 ${isOpen ? 'h-[42vh] max-h-[520px] min-h-[280px]' : 'h-10'}`}>
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-controls="global-console-panel"
        className="flex h-10 flex-shrink-0 cursor-pointer items-center gap-3 border-b border-white/5 bg-console-header px-4 text-left transition-colors hover:bg-console-header/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyber-neon-cyan"
      >
        <TerminalSquare className="w-4 h-4 text-cyber-neon-cyan" />
        <span className="text-xs font-mono text-console-foreground">{t('consoleDrawer.title')}</span>
        <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-mono text-console-muted">{t('consoleDrawer.entries', { count: logs.length })}</span>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-mono ${status === 'running' ? 'border-status-success/35 bg-status-success/10 text-status-success' : 'border-white/10 bg-white/5 text-console-muted'}`}>{status.toUpperCase()}</span>
        <span className="ml-auto text-console-muted">
          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </span>
      </button>
      {isOpen ? (
        <div id="global-console-panel" className="flex-1 min-h-0">
          <Terminal embedded />
        </div>
      ) : null}
    </div>
  )
}
