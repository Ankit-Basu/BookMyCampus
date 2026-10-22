import {
  Bell,
  ChartPieSlice,
  MagnifyingGlass,
  MapTrifold,
  QrCode,
  SignOut,
  Stamp,
  Ticket,
  UserCircle,
} from '@phosphor-icons/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { api, getTokens } from '../lib/api'
import { useAuth } from '../lib/auth'
import { warmRoutes } from '../lib/preload'
import { fmtRelative } from '../lib/format'
import type { Notification } from '../lib/types'
import Backdrop, { Sparks } from './Backdrop'
import Dock, { type DockItemData } from './reactbits/Dock'

export function Wordmark({ small }: { small?: boolean }) {
  return (
    <Link to="/" className="wordmark" style={small ? { fontSize: 15 } : undefined}>
      <img src="/favicon.svg" width={small ? 26 : 30} height={small ? 26 : 30} alt="" />
      <span>
        BookMy<i>Campus</i>
      </span>
      <span className="lpu-badge">LPU</span>
    </Link>
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
        es?.close()
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
      <button className="key key-ghost key-icon" onClick={() => setOpen((o) => !o)} aria-label="Notifications">
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

/** Persistent layout: backdrop, top bar and dock stay mounted while pages swap underneath. */
export default function AppShell() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const { pathname } = useLocation()
  const { data: queue } = useQuery({
    queryKey: ['approval-queue'],
    queryFn: () => api.get<unknown[]>('/approvals/queue').then((r) => r.data),
    enabled: !!user?.is_manager,
    refetchInterval: 45000,
  })

  useEffect(() => {
    if (user) warmRoutes(user.is_manager)
  }, [user])

  const at = (p: string) => pathname === p || pathname.startsWith(p + '/')
  const items: DockItemData[] = [
    { icon: <MagnifyingGlass weight="duotone" color="#ffd27a" />, label: 'Explore', onClick: () => nav('/explore'), active: at('/explore') || at('/resources') },
    { icon: <MapTrifold weight="duotone" color="#5ab2ff" />, label: 'Campus map', onClick: () => nav('/map'), active: at('/map') },
    { icon: <Ticket weight="duotone" color="#3ee6c1" />, label: 'My bookings', onClick: () => nav('/bookings'), active: at('/bookings') },
    { icon: <QrCode weight="duotone" color="#f4efe6" />, label: 'Scan to check in', onClick: () => nav('/scan'), active: at('/scan') },
  ]
  if (user?.is_manager) {
    items.push({ separator: true })
    items.push({
      icon: <Stamp weight="duotone" color="#ff6f59" />,
      label: 'Approvals',
      onClick: () => nav('/approvals'),
      active: at('/approvals'),
      badge: queue?.length ? String(queue.length) : undefined,
    })
    items.push({ icon: <ChartPieSlice weight="duotone" color="#8b7cff" />, label: 'Control room', onClick: () => nav('/admin'), active: at('/admin') })
  }
  items.push({ separator: true })
  items.push({ icon: <UserCircle weight="duotone" color="#c9c4d6" />, label: 'Profile', onClick: () => nav('/me'), active: at('/me') })

  return (
    <>
      <Backdrop />
      <Sparks />
      <header className="topbar glass">
        <Wordmark />
        <div className="grow" />
        {user && (
          <>
            <Notifications />
            <Link to="/me" className="user-chip hide-sm">
              <span className="avatar">{user.name.split(' ').map((p) => p[0]).slice(0, 2).join('')}</span>
              <span style={{ lineHeight: 1.15 }}>
                <span style={{ display: 'block', fontWeight: 600, fontSize: 13.5 }}>{user.name}</span>
                <span className="mono muted" style={{ fontSize: 10.5, letterSpacing: '.08em' }}>
                  {user.role_label.toUpperCase()}
                  {user.department_code ? ` · ${user.department_code}` : ''}
                </span>
              </span>
            </Link>
            <button className="key key-ghost key-icon" onClick={() => { logout(); nav('/') }} aria-label="Sign out" title="Sign out">
              <SignOut size={18} />
            </button>
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
        <div className="dock-host">
          <Dock
            items={items}
            baseItemSize={46}
            magnification={66}
            panelHeight={62}
            accentColor="#f5a524"
            badgeColor="#ff6f59"
            distance={170}
          />
        </div>
      )}
    </>
  )
}
