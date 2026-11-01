import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { flushSync } from 'react-dom'

import { THEMES, type Mode, type ThemeMeta } from './themes'

const KEY = 'bmc.theme'
const DEFAULT = { theme: 'solar-dusk', mode: 'dark' as Mode }

function read(): { theme: string; mode: Mode } {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (raw && THEMES.some((t) => t.id === raw.theme) && (raw.mode === 'dark' || raw.mode === 'light')) return raw
  } catch {
    /* private mode: fall through to defaults */
  }
  return DEFAULT
}

function apply(theme: string, mode: Mode) {
  const el = document.documentElement
  el.dataset.theme = theme
  el.classList.toggle('dark', mode === 'dark')
}

type Ctx = {
  theme: string
  mode: Mode
  meta: ThemeMeta
  palette: ThemeMeta['modes'][Mode]
  setTheme: (theme: string) => void
  toggleMode: () => void
}

const ThemeCtx = createContext<Ctx>(null as unknown as Ctx)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(() => {
    const s = read()
    apply(s.theme, s.mode)
    return s
  })

  const change = useCallback((next: { theme: string; mode: Mode }) => {
    // A snapshot transition here costs a visible stall on heavy pages; a clean swap is one frame.
    const root = document.documentElement
    root.classList.add('theme-switching')
    flushSync(() => setState(next))
    apply(next.theme, next.mode)
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-switching')))
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      /* preference just won't persist */
    }
  }, [])

  const meta = THEMES.find((t) => t.id === state.theme) ?? THEMES[0]
  const value: Ctx = {
    ...state,
    meta,
    palette: meta.modes[state.mode],
    setTheme: (theme) => change({ theme, mode: state.mode }),
    toggleMode: () => change({ theme: state.theme, mode: state.mode === 'dark' ? 'light' : 'dark' }),
  }
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>
}

export const useTheme = () => useContext(ThemeCtx)
