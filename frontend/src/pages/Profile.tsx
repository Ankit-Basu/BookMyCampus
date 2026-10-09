import { CalendarBlank, ShieldWarning, Warning } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { type CSSProperties } from 'react'
import { toast } from 'sonner'

import { Reveal } from '../components/motion'
import { Dial, PageHeader } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { Booking } from '../lib/types'

type Policy = { grace_minutes: number; strike_warn: number; strike_level1: number; restrict_days_level1: number; strike_level2: number; restrict_days_level2: number; noshow_window_days: number }

export default function Profile() {
  const { user } = useAuth()
  const { data: policy } = useQuery({ queryKey: ['policy'], queryFn: () => api.get<Policy>('/policy').then((r) => r.data) })
  const { data: past } = useQuery({ queryKey: ['bookings', 'past'], queryFn: () => api.get<Booking[]>('/bookings', { params: { past: 1 } }).then((r) => r.data) })
  if (!user) return null
  const done = past?.filter((b) => ['completed', 'released'].includes(b.status) && b.requires_checkin) ?? []
  const shows = done.filter((b) => b.status === 'completed').length
  const reliability = done.length ? shows / done.length : 1
  const feed = `${window.location.origin}/api/calendar/${user.calendar_token}.ics`
  const ladder = policy
    ? [
        { n: policy.strike_warn, label: 'Warning', c: 'var(--amber)' },
        { n: policy.strike_level1, label: `${policy.restrict_days_level1}-day pause`, c: 'var(--coral)' },
        { n: policy.strike_level2, label: `${policy.restrict_days_level2}-day pause`, c: 'var(--rose)' },
      ]
    : []

  return (
    <div className="page" style={{ maxWidth: 1080 }}>
      <PageHeader eyebrow={`${user.role_label}${user.department_code ? ` · ${user.department_code}` : ''}`} title={<>{user.first_name} <em>{user.last_name}</em></>} sub={`UMS ID ${user.username}${user.email ? ` · ${user.email}` : ''}`} />

      {user.is_restricted && (
        <div className="glass pad notice-bad" style={{ marginBottom: 18 }}>
          <ShieldWarning size={28} weight="duotone" color="var(--coral)" />
          <div>
            <div className="h2">Booking paused until {format(new Date(user.restricted_until!), 'EEE d MMM, HH:mm')}</div>
            <div className="muted">{user.restriction_reason}. Talk to a facility manager if this was a mistake.</div>
          </div>
        </div>
      )}

      <div className="profile-grid">
        <Reveal className="glass pad" style={{ display: 'grid', placeItems: 'center' }}>
          <Dial value={reliability} label="Show-up rate" color={reliability > 0.85 ? 'var(--mint)' : reliability > 0.6 ? 'var(--amber)' : 'var(--coral)'} size={200} />
          <div className="muted" style={{ fontSize: 13 }}>{shows} of {done.length} check-in bookings attended</div>
        </Reveal>
        <Reveal className="glass pad">
          <div className="eyebrow">No-show ladder · last {policy?.noshow_window_days ?? 30} days</div>
          <div className="display" style={{ fontSize: 56, margin: '6px 0' }}>
            {user.noshow_count}
            <span className="muted" style={{ fontSize: 22 }}> strike{user.noshow_count === 1 ? '' : 's'}</span>
          </div>
          <div className="ladder">
            {ladder.map((l) => (
              <div key={l.n} className={`rung ${user.noshow_count >= l.n ? 'hit' : ''}`} style={{ '--c': l.c } as CSSProperties}>
                <span className="mono">{l.n}</span>
                <span>{l.label}</span>
              </div>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
            <Warning size={13} /> Not checking in within {policy?.grace_minutes ?? 15} minutes of start releases the slot and counts as a strike.
          </p>
        </Reveal>
        <Reveal className="glass pad">
          <div className="eyebrow">Calendar sync</div>
          <div className="h2" style={{ margin: '8px 0' }}>Your bookings in Google, Outlook or Apple Calendar</div>
          <p className="muted" style={{ fontSize: 13 }}>Subscribe once — new bookings, approvals and cancellations show up automatically.</p>
          <div className="input mono" style={{ display: 'flex', alignItems: 'center', fontSize: 11, overflow: 'hidden' }}>
            <span className="truncate">{feed}</span>
          </div>
          <button
            className="key key-amber"
            style={{ marginTop: 12 }}
            onClick={() => {
              navigator.clipboard?.writeText(feed)
              toast.success('Feed URL copied')
            }}
          >
            <CalendarBlank /> Copy feed URL
          </button>
        </Reveal>
      </div>
    </div>
  )
}
