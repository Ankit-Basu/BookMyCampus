import {
  Bell,
  CaretDown,
  ChartPieSlice,
  Check,
  MagnifyingGlass,
  MapTrifold,
  Moon,
  QrCode,
  SignOut,
  Stamp,
  Sun,
  Ticket,
  UserCircle,
} from '@phosphor-icons/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/shadcn/popover'

import { api, getTokens } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmtRelative } from '../lib/format'
import { warmRoutes } from '../lib/preload'
import { useTheme } from '../lib/theme'
import { THEMES } from '../lib/themes'
import type { Notification } from '../lib/types'
import CampusCopilot from './ai/CampusCopilot'
import Backdrop, { Sparks } from './Backdrop'
import CommandPalette, { type NavEntry } from './CommandPalette'

export function Wordmark({ small }: { small?: boolean }) {
  return (
    <Link to="/" className={`wordmark ${small ? 'small' : ''}`}>
      <svg viewBox="0 0 34 24" width={small ? 27 : 32} height={small ? 19 : 23} aria-hidden>
        <path
          d="M4 0h26a4 4 0 0 1 4 4v4.2a3.8 3.8 0 0 0 0 7.6V20a4 4 0 0 1-4 4H4a4 4 0 0 1-4-4v-4.2a3.8 3.8 0 0 0 0-7.6V4a4 4 0 0 1 4-4Z"
          fill="var(--brand)"
        />
        <path d="M23 4v16" stroke="var(--brand-fg)" strokeWidth="1.6" strokeDasharray="2 2.4" />
        <path d="M9 7v10m0-10h4.2a2.5 2.5 0 0 1 0 5H9m0 0h5a2.5 2.5 0 0 1 0 5H9" fill="none" stroke="var(--brand-fg)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="wordmark-text">
        BookMy<i>Campus</i>
      </span>
      <span className="lpu-badge">LPU</span>
    </Link>
  )
}

/** Six tweakcn palettes + light/dark. Switching recolours the UI and re-renders the shader backdrop. */
export function ThemeMenu() {
  const { theme, mode, meta, setTheme, toggleMode } = useTheme()
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className="theme-btn" aria-label={`Colour theme: ${meta.label}`}>
          <span className="swatch-stack">
            {meta.modes[mode].swatches.map((c) => (
              <i key={c} style={{ background: c }} />
            ))}
          </span>
          <span className="theme-name">{meta.label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={10} className="pop-glass theme-pop">
        <div className="spread" style={{ marginBottom: 12 }}>
          <span className="eyebrow">Colour theme</span>
          <button className="mode-toggle" onClick={() => toggleMode()} aria-label="Toggle light and dark mode">
            <span className={mode === 'light' ? 'on' : ''}><Sun size={14} weight="bold" /></span>
            <span className={mode === 'dark' ? 'on' : ''}><Moon size={14} weight="bold" /></span>
          </button>
        </div>
        <div className="theme-grid">
          {THEMES.map((t) => (
            <button key={t.id} className={`theme-card ${t.id === theme ? 'on' : ''}`} onClick={() => setTheme(t.id)}>
              <span className="swatch-stack">
                {t.modes[mode].swatches.map((c) => (
                  <i key={c} style={{ background: c }} />
                ))}
              </span>
              <strong>{t.label}</strong>
              <small>{t.blurb}</small>
              {t.id === theme && <Check className="theme-check" size={13} weight="bold" />}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

/** Subscribe to /api/notifications/stream (SSE). Reconnects with a fresh token if the stream drops. */
function useLiveNotifications(onEvent: (n: Notification) => void) {
  const handler = useRef(onEvent)
  handler.current = onEvent
  useEffect(() => {
    let es: EventSource | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let closed = false
    const connect = () => {
      const token = getTokens()?.access
      if (!token || closed) return
      es = new EventSource(`/api/notifications/stream?token=${encodeURIComponent(token)}`)
      es.addEventListener('notification', (e) => {
        try {
          handler.current(JSON.parse((e as MessageEvent).data))
        } catch {
          /* ignore malformed event */
        }
      })
      es.onerror = () => {
        // A stream that ends normally reconnects by itself and resumes from its last event.
        // Only a refused one (expired token, server full) needs a fresh start.
        if (es?.readyState !== EventSource.CLOSED) return
        if (!closed) timer = setTimeout(connect, 8000)
      }
    }
    connect()
    return () => {
      closed = true
      clearTimeout(timer)
      es?.close()
    }
  }, [])
}

function Notifications() {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  const ref = useRef<HTMLDivElement>(null)
  const { data } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api.get<{ unread: number; items: Notification[] }>('/notifications').then((r) => r.data),
    refetchInterval: 120000, // fallback only — live updates arrive over Server-Sent Events below
  })
  useLiveNotifications((n) => {
    qc.invalidateQueries({ queryKey: ['notifications'] })
    if (n.kind === 'approval_required') qc.invalidateQueries({ queryKey: ['approval-queue'] })
    if (n.booking) {
      qc.invalidateQueries({ queryKey: ['bookings'] })
      qc.invalidateQueries({ queryKey: ['booking', String(n.booking)] })
    }
    toast(n.title, { description: n.body, action: n.link ? { label: 'Open', onClick: () => nav(n.link) } : undefined })
  })
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const readAll = async () => {
    await api.post('/notifications/read-all')
    qc.invalidateQueries({ queryKey: ['notifications'] })
  }
  const go = async (n: Notification) => {
    if (!n.read_at) await api.post(`/notifications/${n.id}/read`)
    qc.invalidateQueries({ queryKey: ['notifications'] })
    setOpen(false)
    if (n.link) nav(n.link)
  }
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button className="icon-btn" onClick={() => setOpen((o) => !o)} aria-label="Notifications">
        <Bell size={18} weight={data?.unread ? 'fill' : 'regular'} />
        {!!data?.unread && <span className="bell-count mono">{data.unread > 9 ? '9+' : data.unread}</span>}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="glass notif-pop"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            data-lenis-prevent
          >
            <div className="spread" style={{ padding: '14px 16px 10px' }}>
              <div className="h3">Notifications</div>
              <button className="chip" style={{ height: 26 }} onClick={readAll}>
                Mark all read
              </button>
            </div>
            <div className="notif-list">
              {data?.items.length ? (
                data.items.map((n) => (
                  <button key={n.id} className={`notif ${n.read_at ? '' : 'unread'}`} onClick={() => go(n)}>
                    <span className={`notif-dot k-${n.kind}`} />
                    <span className="grow" style={{ textAlign: 'left' }}>
                      <span className="notif-title">{n.title}</span>
                      <span className="notif-body">{n.body}</span>
                      <span className="mono muted" style={{ fontSize: 10.5 }}>{fmtRelative(n.created_at)}</span>
                    </span>
                  </button>
                ))
              ) : (
                <div className="empty" style={{ padding: 28 }}>All quiet.</div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** Persistent layout: backdrop and nav stay mounted while pages swap underneath. */
export default function AppShell() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [palette, setPalette] = useState(false)
  const { data: queue } = useQuery({
    queryKey: ['approval-queue'],
    queryFn: () => api.get<unknown[]>('/approvals/queue').then((r) => r.data),
    enabled: !!user?.is_manager,
    refetchInterval: 45000,
  })

  useEffect(() => {
    if (user) warmRoutes(user.is_manager)
  }, [user])

  const links = useMemo<NavEntry[]>(() => {
    const base: NavEntry[] = [
      { to: '/explore', label: 'Explore', icon: MagnifyingGlass },
      { to: '/map', label: 'Map', icon: MapTrifold },
      { to: '/bookings', label: 'Bookings', icon: Ticket },
      { to: '/scan', label: 'Scan', icon: QrCode },
    ]
    if (user?.is_manager) {
      base.push({ to: '/approvals', label: 'Approvals', icon: Stamp })
      base.push({ to: '/admin', label: 'Control room', icon: ChartPieSlice })
    }
    return base
  }, [user?.is_manager])

  const isActive = (to: string) => pathname === to || pathname.startsWith(to + '/') || (to === '/explore' && pathname.startsWith('/resources'))
  const pending = queue?.length ?? 0
  const initials = user?.name.split(' ').map((p) => p[0]).slice(0, 2).join('')

  return (
    <>
      <Backdrop />
      <Sparks />
      <header className="topbar glass">
        <Wordmark />
        <nav className="nav-links" aria-label="Main">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={`nav-link ${isActive(l.to) ? 'on' : ''}`}>
              {isActive(l.to) && <motion.span layoutId="nav-pill" className="nav-pill" transition={{ type: 'spring', stiffness: 420, damping: 36 }} />}
              <l.icon size={16} weight={isActive(l.to) ? 'fill' : 'regular'} />
              <span>{l.label}</span>
              {l.to === '/approvals' && pending > 0 && <em className="nav-count mono">{pending}</em>}
            </NavLink>
          ))}
        </nav>
        <div className="grow" />
        <button className="search-pill" onClick={() => setPalette(true)} aria-label="Search">
          <MagnifyingGlass size={15} />
          <span>Search</span>
          <kbd>/</kbd>
        </button>
        <ThemeMenu />
        {user && (
          <>
            <Notifications />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="user-chip" aria-label="Account">
                  <span className="avatar sm">{initials}</span>
                  <CaretDown size={12} weight="bold" className="hide-sm" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={10} className="pop-glass" style={{ minWidth: 230 }}>
                <DropdownMenuLabel>
                  <div style={{ fontWeight: 650 }}>{user.name}</div>
                  <div className="mono muted" style={{ fontSize: 10.5, fontWeight: 400 }}>
                    {user.role_label}
                    {user.department_code ? ` · ${user.department_code}` : ''}
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator className="menu-sep" />
                <DropdownMenuItem className="select-item" onSelect={() => nav('/me')}>
                  <UserCircle size={16} /> Profile
                </DropdownMenuItem>
                <DropdownMenuItem className="select-item" onSelect={() => { logout(); nav('/') }}>
                  <SignOut size={16} /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
      </header>
      <motion.main
        key={pathname.split('/').slice(0, 3).join('/')}
        className="route"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      >
        <Outlet />
      </motion.main>
      {user && (
        <>
          <CampusCopilot />
          <CommandPalette open={palette} onOpenChange={setPalette} links={links} />
          <nav className="tabbar glass" aria-label="Main (mobile)">
            {[...links.slice(0, 4), user.is_manager ? links[5] : { to: '/me', label: 'Profile', icon: UserCircle }].map((l) => (
              <NavLink key={l.to} to={l.to} className={`tab ${isActive(l.to) ? 'on' : ''}`}>
                <l.icon size={21} weight={isActive(l.to) ? 'fill' : 'regular'} />
                <span>{l.label === 'Control room' ? 'Admin' : l.label}</span>
              </NavLink>
            ))}
          </nav>
        </>
      )}
    </>
  )
}
