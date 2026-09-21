import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Cyberpunk color scheme using CSS variables
        cyber: {
          // Background colors
          bg: {
            primary: 'rgb(var(--cyber-bg-primary) / <alpha-value>)',
            secondary: 'rgb(var(--cyber-bg-secondary) / <alpha-value>)',
            tertiary: 'rgb(var(--cyber-bg-tertiary) / <alpha-value>)',
            panel: 'rgb(var(--cyber-bg-panel) / <alpha-value>)',
            elevated: 'rgb(var(--cyber-bg-elevated) / <alpha-value>)',
            glass: 'rgb(var(--glass-bg))',
            glassDark: 'rgb(var(--glass-dark-bg))',
          },
          // Neon colors
          neon: {
            cyan: 'rgb(var(--cyber-neon-cyan) / <alpha-value>)',
            cyanDim: 'rgb(var(--cyber-neon-cyan-dim) / <alpha-value>)',
            pink: 'rgb(var(--cyber-neon-pink) / <alpha-value>)',
            pinkDim: 'rgb(var(--cyber-neon-pink-dim) / <alpha-value>)',
            green: 'rgb(var(--cyber-neon-green) / <alpha-value>)',
            greenDim: 'rgb(var(--cyber-neon-green-dim) / <alpha-value>)',
            orange: 'rgb(var(--cyber-neon-orange) / <alpha-value>)',
            yellow: 'rgb(var(--cyber-neon-yellow) / <alpha-value>)',
            purple: 'rgb(var(--cyber-neon-purple) / <alpha-value>)',
          },
          // Text colors
          text: {
            primary: 'rgb(var(--cyber-text-primary) / <alpha-value>)',
            secondary: 'rgb(var(--cyber-text-secondary) / <alpha-value>)',
            muted: 'rgb(var(--cyber-text-muted) / <alpha-value>)',
          },
          // Border colors
          border: {
            DEFAULT: 'rgb(var(--cyber-border-default) / <alpha-value>)',
            glow: 'rgb(var(--cyber-border-glow) / <alpha-value>)',
            subtle: 'rgb(var(--cyber-border-subtle) / <alpha-value>)',
          },
        },
        status: {
          success: 'rgb(var(--cyber-status-success) / <alpha-value>)',
          warning: 'rgb(var(--cyber-status-warning) / <alpha-value>)',
          danger: 'rgb(var(--cyber-status-danger) / <alpha-value>)',
          info: 'rgb(var(--cyber-status-info) / <alpha-value>)',
          purple: 'rgb(var(--cyber-status-purple) / <alpha-value>)',
          neutral: 'rgb(var(--cyber-status-neutral) / <alpha-value>)',
        },
        console: {
          surface: 'rgb(var(--cyber-console-surface) / <alpha-value>)',
          header: 'rgb(var(--cyber-console-header) / <alpha-value>)',
          foreground: 'rgb(var(--cyber-console-foreground) / <alpha-value>)',
          muted: 'rgb(var(--cyber-console-muted) / <alpha-value>)',
        },
        brand: {
          red: 'rgb(var(--brand-red) / <alpha-value>)',
          redStrong: 'rgb(var(--brand-red-strong) / <alpha-value>)',
          cyan: 'rgb(var(--brand-cyan) / <alpha-value>)',
        },
        // Keep semantic colors for compatibility
        border: 'rgb(var(--color-border) / <alpha-value>)',
        input: 'rgb(var(--color-border) / <alpha-value>)',
        ring: 'rgb(var(--color-primary) / <alpha-value>)',
        background: 'rgb(var(--color-background) / <alpha-value>)',
        foreground: 'rgb(var(--color-foreground) / <alpha-value>)',
        primary: {
          DEFAULT: 'rgb(var(--color-primary) / <alpha-value>)',
          foreground: 'rgb(var(--color-primary-contrast) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--color-surface-muted) / <alpha-value>)',
          foreground: 'rgb(var(--color-foreground) / <alpha-value>)',
        },
        destructive: {
          DEFAULT: 'rgb(var(--color-danger) / <alpha-value>)',
          foreground: 'rgb(var(--color-primary-contrast) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'rgb(var(--color-surface-muted) / <alpha-value>)',
          foreground: 'rgb(var(--color-foreground-muted) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--color-primary) / <alpha-value>)',
          foreground: 'rgb(var(--color-primary-contrast) / <alpha-value>)',
        },
        popover: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          foreground: 'rgb(var(--color-foreground) / <alpha-value>)',
        },
        card: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          foreground: 'rgb(var(--color-foreground) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      boxShadow: {
        // Neon glow shadows - these use CSS variables for theme support
        'glow-cyan': '0 0 var(--shadow-glow-spread, 10px) rgb(var(--cyber-neon-cyan) / var(--shadow-glow-opacity, 0.5)), 0 0 calc(var(--shadow-glow-spread, 10px) * 2) rgb(var(--cyber-neon-cyan) / calc(var(--shadow-glow-opacity, 0.5) * 0.6)), 0 0 calc(var(--shadow-glow-spread, 10px) * 3) rgb(var(--cyber-neon-cyan) / calc(var(--shadow-glow-opacity, 0.5) * 0.2))',
        'glow-cyan-sm': '0 0 5px rgb(var(--cyber-neon-cyan) / 0.4), 0 0 10px rgb(var(--cyber-neon-cyan) / 0.2)',
        'glow-pink': '0 0 var(--shadow-glow-spread, 10px) rgb(var(--cyber-neon-pink) / var(--shadow-glow-opacity, 0.5)), 0 0 calc(var(--shadow-glow-spread, 10px) * 2) rgb(var(--cyber-neon-pink) / calc(var(--shadow-glow-opacity, 0.5) * 0.6))',
        'glow-pink-sm': '0 0 5px rgb(var(--cyber-neon-pink) / 0.4), 0 0 10px rgb(var(--cyber-neon-pink) / 0.2)',
        'glow-green': '0 0 var(--shadow-glow-spread, 10px) rgb(var(--cyber-neon-green) / var(--shadow-glow-opacity, 0.5)), 0 0 calc(var(--shadow-glow-spread, 10px) * 2) rgb(var(--cyber-neon-green) / calc(var(--shadow-glow-opacity, 0.5) * 0.6))',
        'glow-green-sm': '0 0 5px rgb(var(--cyber-neon-green) / 0.4), 0 0 10px rgb(var(--cyber-neon-green) / 0.2)',
        'glow-orange': '0 0 var(--shadow-glow-spread, 10px) rgb(var(--cyber-neon-orange) / var(--shadow-glow-opacity, 0.5)), 0 0 calc(var(--shadow-glow-spread, 10px) * 2) rgb(var(--cyber-neon-orange) / calc(var(--shadow-glow-opacity, 0.5) * 0.6))',
        'cyber-card': '0 0 1px rgb(var(--cyber-neon-cyan) / 0.5), 0 4px 20px rgba(0, 0, 0, 0.3)',
        'cyber-inset': 'inset 0 0 20px rgba(0, 0, 0, 0.5)',
        // Soft shadows for glassmorphism
        'cyber-soft': '0 4px 24px rgba(0, 0, 0, 0.2), 0 0 1px rgb(var(--cyber-neon-cyan) / 0.1)',
        'cyber-float': '0 8px 32px rgba(0, 0, 0, 0.25), 0 0 1px rgb(var(--cyber-neon-cyan) / 0.15)',
        'cyber-elevated': '0 12px 40px rgba(0, 0, 0, 0.3)',
      },
      animation: {
        'slide-up': 'slideUp 0.3s ease-out forwards',
        'pulse-fast': 'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'scanline': 'scanline 8s linear infinite',
        'cursor-blink': 'cursorBlink 1s step-end infinite',
        'border-glow': 'borderGlow 3s linear infinite',
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
      keyframes: {
        slideUp: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': {
            boxShadow: '0 0 5px rgb(var(--cyber-neon-cyan) / 0.5), 0 0 10px rgb(var(--cyber-neon-cyan) / 0.3)'
          },
          '50%': {
            boxShadow: '0 0 15px rgb(var(--cyber-neon-cyan) / 0.8), 0 0 25px rgb(var(--cyber-neon-cyan) / 0.5), 0 0 35px rgb(var(--cyber-neon-cyan) / 0.3)'
          },
        },
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        cursorBlink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        borderGlow: {
          '0%, 100%': { borderColor: 'rgb(var(--cyber-neon-cyan) / 0.3)' },
          '50%': { borderColor: 'rgb(var(--cyber-neon-cyan) / 0.6)' },
        },
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}

export default config
