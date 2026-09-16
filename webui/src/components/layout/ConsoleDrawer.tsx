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
    <div className={`fixed inset-x-0 bottom-0 z-50 flex flex-col border-t border-cyber-border-default bg-[#0d1117] shadow-[0_-8px_24px_rgba(0,0,0,0.28)] transition-all duration-300 ${isOpen ? 'h-[42vh] max-h-[520px] min-h-[280px]' : 'h-10'}`}>
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="h-10 flex-shrink-0 px-4 flex items-center gap-3 bg-[#161b22] text-left hover:bg-[#1b222c] transition-colors"
      >
        <TerminalSquare className="w-4 h-4 text-cyber-neon-cyan" />
        <span className="text-xs font-mono text-cyber-text-primary">{t('consoleDrawer.title')}</span>
        <span className="text-[10px] font-mono text-cyber-text-muted">{t('consoleDrawer.entries', { count: logs.length })}</span>
        <span className={`text-[10px] font-mono ${status === 'running' ? 'text-cyber-neon-green' : 'text-cyber-text-muted'}`}>{status.toUpperCase()}</span>
        <span className="ml-auto text-cyber-text-muted">
          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </span>
      </button>
      {isOpen ? (
        <div className="flex-1 min-h-0">
          <Terminal embedded />
        </div>
      ) : null}
    </div>
  )
}
