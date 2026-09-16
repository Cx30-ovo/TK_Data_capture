import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-sans text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyber-neon-cyan disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default:
          'border border-cyber-neon-cyan/50 bg-cyber-neon-cyan/15 text-cyber-neon-cyan hover:bg-cyber-neon-cyan/20 active:bg-cyber-neon-cyan/25',
        destructive:
          'border border-cyber-neon-pink/50 bg-cyber-neon-pink/15 text-cyber-neon-pink hover:bg-cyber-neon-pink/20 active:bg-cyber-neon-pink/25',
        outline:
          'border border-cyber-border-DEFAULT bg-transparent hover:bg-cyber-bg-tertiary hover:border-cyber-border-default',
        secondary:
          'border border-cyber-neon-green/50 bg-cyber-neon-green/15 text-cyber-neon-green hover:bg-cyber-neon-green/20',
        ghost:
          'hover:bg-cyber-bg-tertiary hover:text-cyber-text-primary',
        link:
          'text-cyber-neon-cyan underline-offset-4 hover:underline',
        glow:
          'border border-cyber-neon-cyan/50 bg-cyber-neon-cyan/15 text-cyber-neon-cyan hover:bg-cyber-neon-cyan/20',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-12 rounded-md px-8 text-base',
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
