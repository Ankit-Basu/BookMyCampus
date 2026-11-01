import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { lazy, type CSSProperties } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'

import { Counter, Reveal } from '../../components/motion'
import { Dial, PageHeader, Skeleton, StatusTag } from '../../components/ui'
import { api } from '../../lib/api'
import { isPolicyAdmin, useAuth } from '../../lib/auth'
import type { Booking } from '../../lib/types'

const Analytics = lazy(() => import('./Analytics'))
const Catalogue = lazy(() => import('./Catalogue'))
const Config = lazy(() => import('./Config'))
const Operations = lazy(() => import('./Operations'))
const People = lazy(() => import('./People'))
const MasterData = lazy(() => import('./MasterData'))

type Dash = {
  resources: number
  down: number
  bookings_today: number
  live_now: number
  pending_approvals: number
  noshows_week: number
  restricted_users: number
  low_stock: number
}

function LiveBoard() {
  const { data } = useQuery({ queryKey: ['board'], queryFn: () => api.get<Booking[]>('/bookings/board').then((r) => r.data), refetchInterval: 30000 })
  if (!data) return <Skeleton h={300} />
  const byResource = new Map<string, Booking[]>()
  data.forEach((b) => byResource.set(b.resource_name, [...(byResource.get(b.resource_name) ?? []), b]))
  const dayStart = 7
  const dayEnd = 22
  const span = (dayEnd - dayStart) * 60
  const pos = (iso: string) => {
    const d = new Date(iso)
    return Math.max(0, Math.min(100, (((d.getHours() - dayStart) * 60 + d.getMinutes()) / span) * 100))
  }
  const now = pos(new Date().toISOString())
  return (
    <div className="board" data-lenis-prevent>
      <div className="board-hours">
        {Array.from({ length: dayEnd - dayStart + 1 }, (_, i) => (
          <span key={i} style={{ left: `${(i / (dayEnd - dayStart)) * 100}%` }} className="mono">{String(dayStart + i).padStart(2, '0')}</span>
        ))}
      </div>
      {[...byResource.entries()].map(([name, list]) => (
        <div key={name} className="board-row">
          <div className="board-label truncate">{name}</div>
          <div className="board-track">
            {list.map((b) => (
              <Link
                to={`/bookings/${b.id}`}
                key={b.id}
                className={`board-bar s-${b.status}`}
                style={{ left: `${pos(b.start)}%`, width: `${Math.max(1.2, pos(b.end) - pos(b.start))}%`, '--c': b.resource_color } as CSSProperties}
                title={`${b.title} · ${b.user_name} · ${format(new Date(b.start), 'HH:mm')}–${format(new Date(b.end), 'HH:mm')} · ${b.status_label}`}
              />
            ))}
            <span className="board-now" style={{ left: `${now}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

type Health = {
  database: boolean
  redis: boolean
  sweeper: { last_run: string | null; age_seconds: number | null; healthy: boolean }
  email: { backend: string; live: boolean }
  realtime: string
  timetable: { label: string; published_at: string } | null
}

/** What's actually running behind the UI — the "is automation alive?" question, answered. */
function SystemHealth() {
  const { data } = useQuery({ queryKey: ['health'], queryFn: () => api.get<Health>('/system/health').then((r) => r.data), refetchInterval: 20000 })
  if (!data) return null
  const age = data.sweeper.age_seconds
  const items: { label: string; value: string; ok: boolean; warn?: boolean }[] = [
    { label: 'Database', value: data.database ? 'PostgreSQL · connected' : 'unreachable', ok: data.database },
    {
      label: 'Auto-release sweeper',
      value: age == null ? 'never ran' : age < 90 ? `ran ${Math.round(age)}s ago` : `ran ${Math.round(age / 60)} min ago`,
      ok: data.sweeper.healthy,
    },
    { label: 'Live notifications', value: 'Server-Sent Events', ok: true },
    { label: 'Email', value: data.email.live ? 'SMTP · live delivery' : `${data.email.backend} (dev)`, ok: data.email.live, warn: !data.email.live },
    { label: 'Redis / Celery', value: data.redis ? 'broker reachable' : 'not running (sweeper runs in-process)', ok: data.redis, warn: !data.redis },
  ]
  return (
    <div className="health-strip">
      {items.map((i) => (
        <div key={i.label} className="health-item">
          <span className={`led ${i.ok ? 'pulse' : ''}`} style={{ '--c': i.ok ? 'var(--ok)' : i.warn ? 'var(--brand)' : 'var(--bad)' } as CSSProperties} />
          <span>
            <span className="eyebrow" style={{ display: 'block' }}>{i.label}</span>
            <span style={{ fontSize: 13 }}>{i.value}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

function Overview() {
  const { data } = useQuery({ queryKey: ['dash'], queryFn: () => api.get<Dash>('/analytics/dashboard').then((r) => r.data), refetchInterval: 30000 })
  const { data: util } = useQuery({
    queryKey: ['util-overview'],
    queryFn: () => api.get('/analytics/utilisation').then((r) => r.data as { totals: { utilisation: number; idle_value_inr: number } }),
  })
  const { data: today } = useQuery({ queryKey: ['board'], queryFn: () => api.get<Booking[]>('/bookings/board').then((r) => r.data) })
  const kpis: { l: string; v: number; c?: string; to?: string }[] = data
    ? [
        { l: 'Bookings today', v: data.bookings_today },
        { l: 'Checked in right now', v: data.live_now, c: 'var(--ok)' },
        { l: 'Awaiting approval', v: data.pending_approvals, c: 'var(--brand)', to: '/approvals' },
        { l: 'No-shows this week', v: data.noshows_week, c: 'var(--bad)', to: '/admin/operations/noshows' },
        { l: 'Users restricted', v: data.restricted_users, c: 'var(--bad)', to: '/admin/operations/noshows' },
        { l: 'Out of service', v: data.down, c: 'var(--chart-4)', to: '/admin/operations/maintenance' },
        { l: 'Low-stock items', v: data.low_stock, c: 'var(--brand)', to: '/admin/operations/consumables' },
        { l: 'Bookable resources', v: data.resources },
      ]
    : []
  return (
    <>
      <SystemHealth />
      <div className="overview-top">
        <Reveal className="glass pad dial-card">
          {util ? <Dial value={util.totals.utilisation} label="30-day utilisation" size={220} /> : <Skeleton h={220} style={{ width: 220, borderRadius: '50%' }} />}
          <div className="muted" style={{ fontSize: 12.5, textAlign: 'center' }}>teaching + checked-in use ÷ open hours</div>
        </Reveal>
        <Reveal className="kpi-grid" stagger={0.05}>
          {kpis.map((k) => {
            const body = (
              <>
                <div className="eyebrow">{k.l}</div>
                <div className="stat-value" style={{ color: k.c }}>
                  <Counter to={k.v} duration={1.2} />
                </div>
              </>
            )
            return k.to ? (
              <Link key={k.l} to={k.to} className="glass pad kpi" data-reveal>{body}</Link>
            ) : (
              <div key={k.l} className="glass pad kpi" data-reveal>{body}</div>
            )
          })}
        </Reveal>
      </div>
      <Reveal className="glass pad" style={{ marginTop: 18 }}>
        <div className="spread" style={{ marginBottom: 14 }}>
          <div>
            <div className="h2">Live booking board</div>
            <div className="muted" style={{ fontSize: 13 }}>Today across campus · {today?.length ?? 0} bookings · hover a bar for details</div>
          </div>
          <div className="legend">
            {['confirmed', 'checked_in', 'pending', 'completed', 'released'].map((s) => (
              <StatusTag key={s} status={s} />
            ))}
          </div>
        </div>
        <LiveBoard />
      </Reveal>
    </>
  )
}

export default function Admin() {
  const { user } = useAuth()
  const tabs = [
    { to: '/admin', label: 'Overview', end: true },
    { to: '/admin/analytics', label: 'Analytics' },
    { to: '/admin/catalogue', label: 'Catalogue' },
    { to: '/admin/config', label: isPolicyAdmin(user) ? 'Rules & workflows' : 'Rules' },
    { to: '/admin/operations', label: 'Operations' },
    { to: '/admin/people', label: 'People' },
    { to: '/admin/master', label: 'Master data' },
  ]
  return (
    <div className="page">
      <PageHeader
        eyebrow={user?.role === 'dept_head' ? `Department · ${user.department_code}` : 'Facility control room'}
        title={<>Control <em>room</em></>}
        sub="Live board, utilisation, policy and the boring-but-vital stuff: maintenance, stock and no-shows."
      />
      <nav className="seg admin-tabs" style={{ marginBottom: 24 }}>
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => (isActive ? 'on' : '')}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Overview />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="catalogue" element={<Catalogue />} />
        <Route path="config/*" element={<Config />} />
        <Route path="operations/*" element={<Operations />} />
        <Route path="people" element={<People />} />
        <Route path="master" element={<MasterData />} />
        <Route path="maintenance" element={<Operations initial="maintenance" />} />
        <Route path="consumables" element={<Operations initial="consumables" />} />
      </Routes>
    </div>
  )
}
