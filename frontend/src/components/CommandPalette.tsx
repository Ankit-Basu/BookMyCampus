import { useQuery } from '@tanstack/react-query'
import { Moon, Palette, Sun, type Icon } from '@phosphor-icons/react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/shadcn/command'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/shadcn/dialog'

import { api } from '../lib/api'
import { useTheme } from '../lib/theme'
import { THEMES } from '../lib/themes'
import type { Resource } from '../lib/types'
import { TypeIcon } from './ui'

export type NavEntry = { to: string; label: string; icon: Icon }

/** Jump anywhere: press / (Ctrl+K stays with Campus Copilot). Navigation and theme only. */
export default function CommandPalette({ open, onOpenChange, links }: { open: boolean; onOpenChange: (o: boolean) => void; links: NavEntry[] }) {
  const nav = useNavigate()
  const { setTheme, toggleMode, mode } = useTheme()
  const { data: resources } = useQuery({
    queryKey: ['resources', 'palette'],
    queryFn: () => api.get<Resource[]>('/resources').then((r) => r.data),
    enabled: open,
    staleTime: 60_000,
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      const emptySearch = el.classList.contains('search-input') && !(el as HTMLInputElement).value
      const typing = !emptySearch && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))
      if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        onOpenChange(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onOpenChange])

  const go = (to: string) => {
    onOpenChange(false)
    nav(to)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="palette" showCloseButton={false} aria-describedby={undefined}>
        <DialogTitle className="sr-only">Search BookMyCampus</DialogTitle>
        <DialogDescription className="sr-only">Find a page, a resource or a theme</DialogDescription>
        <Command className="palette-cmd">
          <CommandInput placeholder="Jump to a page, a room, a lab, a theme…" />
          <CommandList data-lenis-prevent>
            <CommandEmpty>Nothing by that name on campus.</CommandEmpty>
            <CommandGroup heading="Go to">
              {links.map((l) => (
                <CommandItem key={l.to} value={`page ${l.label}`} onSelect={() => go(l.to)}>
                  <l.icon size={17} weight="duotone" /> {l.label}
                </CommandItem>
              ))}
            </CommandGroup>
            {!!resources?.length && (
              <CommandGroup heading="Resources">
                {resources.map((r) => (
                  <CommandItem key={r.id} value={`${r.name} ${r.code} ${r.type_name} ${r.building ?? ''}`} onSelect={() => go(`/resources/${r.id}`)}>
                    <TypeIcon icon={r.type_icon} size={17} color={r.type_color} />
                    <span className="truncate">{r.name}</span>
                    <span className="palette-meta mono">{r.code}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            <CommandGroup heading="Theme">
              <CommandItem value="theme toggle light dark mode" onSelect={() => { toggleMode(); onOpenChange(false) }}>
                {mode === 'dark' ? <Sun size={17} weight="duotone" /> : <Moon size={17} weight="duotone" />}
                Switch to {mode === 'dark' ? 'light' : 'dark'} mode
              </CommandItem>
              {THEMES.map((t) => (
                <CommandItem key={t.id} value={`theme ${t.label}`} onSelect={() => { setTheme(t.id); onOpenChange(false) }}>
                  <Palette size={17} weight="duotone" color={t.modes.dark.swatches[0]} /> {t.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  )
}
