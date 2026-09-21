import { Sun, Moon, Monitor } from 'lucide-react'
import { useThemeStore } from '@/store/themeStore'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type Theme = 'light' | 'dark' | 'system'

const themes: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'Auto', icon: Monitor },
]

export function ThemeToggle() {
  const { theme, setTheme } = useThemeStore()

  const currentTheme = themes.find(t => t.value === theme) || themes[0]
  const Icon = currentTheme.icon

  return (
    <Select value={theme} onValueChange={(value: Theme) => setTheme(value)}>
      <SelectTrigger className="h-11 w-20 border-cyber-border-subtle bg-cyber-bg-tertiary/50 text-xs font-mono transition-colors hover:border-cyber-neon-cyan/50 lg:h-8">
        <Icon className="mr-1 h-3 w-3 text-cyber-text-secondary" aria-hidden="true" />
        <SelectValue>{currentTheme.label}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {themes.map(({ value, label, icon: ItemIcon }) => (
          <SelectItem key={value} value={value} className="text-xs font-mono">
            <div className="flex items-center gap-2">
              <ItemIcon className="w-3 h-3" />
              {label}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
