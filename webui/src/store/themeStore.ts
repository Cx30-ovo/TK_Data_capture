import { create } from 'zustand'

type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: Theme) => void
}

const THEME_KEY = 'mediacrawler_theme'

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  let stored: Theme | null = null
  try { stored = localStorage.getItem(THEME_KEY) as Theme | null } catch { /* Keep the document usable when storage is blocked. */ }
  if (stored && ['light', 'dark', 'system'].includes(stored)) {
    return stored
  }
  return 'light' // Default to light
}

function applyTheme(resolved: 'light' | 'dark') {
  const root = document.documentElement
  root.dataset.theme = resolved
  root.style.colorScheme = resolved
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#071322' : '#f1f6fc')
  if (resolved === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
}

function resolveTheme(theme: Theme): 'light' | 'dark' {
  return theme === 'system' ? getSystemTheme() : theme
}

// Initialize theme immediately to prevent flash
const initialTheme = getStoredTheme()
const initialResolved = resolveTheme(initialTheme)
if (typeof window !== 'undefined') {
  applyTheme(initialResolved)
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: initialTheme,
  resolvedTheme: initialResolved,

  setTheme: (theme) => {
    const resolved = resolveTheme(theme)
    try { localStorage.setItem(THEME_KEY, theme) } catch { /* Apply in-memory choice. */ }
    applyTheme(resolved)
    set({ theme, resolvedTheme: resolved })
  },
}))

// Listen for system theme changes
if (typeof window !== 'undefined') {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    const state = useThemeStore.getState()
    if (state.theme === 'system') {
      const resolved = e.matches ? 'dark' : 'light'
      applyTheme(resolved)
      useThemeStore.setState({ resolvedTheme: resolved })
    }
  })
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', event => {
    if (event.key !== THEME_KEY) return
    const theme: Theme = event.newValue === 'dark' || event.newValue === 'system' ? event.newValue : 'light'
    const resolvedTheme = resolveTheme(theme)
    applyTheme(resolvedTheme)
    useThemeStore.setState({ theme, resolvedTheme })
  })
}
