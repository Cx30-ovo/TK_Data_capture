import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-lg font-sans text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-cyber-bg-panel disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default:
          'border border-primary bg-[var(--button-bg)] text-[var(--button-fg)] hover:bg-[var(--button-hover-bg)] active:bg-primary',
        destructive:
          'border border-destructive bg-destructive text-white hover:bg-destructive/90 active:bg-destructive',
        outline:
          'border border-cyber-border-default bg-cyber-bg-panel text-cyber-text-secondary hover:bg-cyber-bg-tertiary hover:text-cyber-text-primary',
        secondary:
          'border border-status-info/20 bg-status-info/10 text-status-info hover:bg-status-info/15',
        ghost:
          'text-cyber-text-secondary hover:bg-cyber-bg-tertiary hover:text-cyber-text-primary',
        link:
          'text-primary underline-offset-4 hover:underline',
        glow:
          'border border-primary bg-primary text-primary-foreground hover:bg-primary/90',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-lg px-3',
        lg: 'h-12 rounded-lg px-8 text-base',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }
