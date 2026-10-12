import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, TerminalSquare } from 'lucide-react'
import { Terminal } from '@/components/console/Terminal'
import { useLogWebSocket } from '@/hooks/useWebSocket'
import { useCrawlerStore } from '@/store/crawlerStore'


export function ConsoleDrawer() {
  const { t } = useTranslation('common')
  const [isOpen, setIsOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const logs = useCrawlerStore((state) => state.logs)
  const status = useCrawlerStore((state) => state.status)

  // Keep the WebSocket connected even while the drawer is collapsed.
  useLogWebSocket()

  useEffect(() => {
    if (!isOpen) return
    panelRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return
      setIsOpen(false)
      triggerRef.current?.focus()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [isOpen])

  return (
    <div className="app-console-drawer flex h-11 w-full flex-col overflow-hidden rounded-lg border border-cyber-border-default bg-console-surface">
      <button
        type="button"
        ref={triggerRef}
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-controls="global-console-panel"
        className="flex h-11 min-w-11 flex-shrink-0 cursor-pointer items-center gap-2 border-b border-white/5 bg-console-header px-3 text-left transition-colors hover:bg-console-header/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyber-neon-cyan"
      >
        <TerminalSquare aria-hidden="true" className="h-4 w-4 shrink-0 text-cyber-neon-cyan" />
        <span className="whitespace-nowrap font-mono text-xs text-console-foreground">{t('consoleDrawer.title')}</span>
        <span className="whitespace-nowrap rounded-full border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-xs text-console-muted">{t('consoleDrawer.entries', { count: logs.length })}</span>
        <span className="ml-auto text-console-muted">
          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </span>
      </button>
      {isOpen ? createPortal(
        <div id="global-console-panel" ref={panelRef} tabIndex={-1} role="dialog" aria-label={t('consoleDrawer.title')} className="fixed bottom-4 right-4 z-50 flex h-[min(62vh,560px)] w-[min(720px,calc(100vw-32px))] flex-col overflow-hidden rounded-xl border border-cyber-border-default bg-console-surface shadow-[0_16px_50px_rgba(0,0,0,0.28)] focus:outline-none focus-visible:ring-2 focus-visible:ring-cyber-neon-cyan">
          <button type="button" onClick={() => { setIsOpen(false); triggerRef.current?.focus() }} className="flex h-11 shrink-0 cursor-pointer items-center gap-2 bg-console-header px-3 text-xs text-console-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyber-neon-cyan">
            <TerminalSquare aria-hidden="true" className="h-4 w-4 text-cyber-neon-cyan" />
            <span>{t('consoleDrawer.title')}</span>
            <span className="text-console-muted">{status.toUpperCase()}</span>
            <ChevronDown aria-hidden="true" className="ml-auto h-4 w-4" />
          </button>
          <div className="min-h-0 flex-1"><Terminal embedded /></div>
        </div>, document.body,
      ) : null}
    </div>
  )
}
