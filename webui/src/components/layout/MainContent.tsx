import { Terminal } from '@/components/console/Terminal'
import { useLogWebSocket } from '@/hooks/useWebSocket'

export function MainContent() {
  // Connect to WebSocket for logs
  useLogWebSocket()

  return (
    <main className="flex-1 min-h-[28vh] flex flex-col overflow-hidden relative z-10">
      <Terminal />
    </main>
  )
}
