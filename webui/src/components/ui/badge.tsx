import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex min-h-6 items-center gap-1.5 whitespace-nowrap rounded-[var(--badge-radius)] border px-2.5 py-0.5 text-[var(--badge-font-size)] font-semibold leading-4 shadow-[inset_0_1px_0_rgb(var(--color-surface)/0.72)] transition-[color,background-color,border-color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-cyber-bg-panel',
  {
    variants: {
      variant: {
        default:
          'border-status-info/25 bg-status-info/10 text-status-info',
        secondary:
          'border-cyber-border-default bg-cyber-bg-tertiary text-cyber-text-secondary',
        destructive:
          'border-status-danger/25 bg-status-danger/10 text-status-danger',
        outline:
          'border-cyber-border-default bg-cyber-bg-panel/70 text-cyber-text-secondary',
        success:
          'border-status-success/25 bg-status-success/10 text-status-success',
        warning:
          'border-status-warning/25 bg-status-warning/10 text-status-warning',
        idle:
          'border-cyber-border-default bg-cyber-bg-tertiary/70 text-cyber-text-muted',
        running:
          'border-status-success/25 bg-status-success/10 text-status-success',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
