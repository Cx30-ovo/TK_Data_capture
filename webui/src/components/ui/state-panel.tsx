import type { ReactNode } from 'react'
import { AlertTriangle, Inbox, Loader2 } from 'lucide-react'


type StateVariant = 'empty' | 'loading' | 'error'


export function StatePanel({
  variant,
  title,
  description,
  action,
}: {
  variant: StateVariant
  title: string
  description?: string
  action?: ReactNode
}) {
  const Icon = variant === 'loading' ? Loader2 : variant === 'error' ? AlertTriangle : Inbox
  const color = variant === 'error'
    ? 'text-cyber-neon-pink'
    : variant === 'loading'
      ? 'text-cyber-neon-cyan'
      : 'text-cyber-text-muted'

  return (
    <div className={`state-panel state-panel-${variant}`}>
      <Icon className={`state-panel-icon h-7 w-7 ${color}`} />
      <div className="font-sans text-sm font-medium text-cyber-text-primary">{title}</div>
      {description ? <div className="max-w-md text-xs text-cyber-text-muted">{description}</div> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  )
}
