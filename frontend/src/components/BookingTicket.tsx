import { QrCode, Timer } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { blobUrl } from '../lib/api'
import { durationLabel, fmtDay, fmtTime } from '../lib/format'
import type { Booking } from '../lib/types'
import { StatusTag } from './ui'

const GRACE = 15
const OPENS = 15

/** Live check-in window state for a booking. */
export function useCheckinWindow(b: Booking) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const start = new Date(b.start).getTime()
  const opens = start - OPENS * 60000
  const closes = start + GRACE * 60000
  const open = b.status === 'confirmed' && b.requires_checkin && now >= opens && now <= closes
  return { open, now, opens, closes, remaining: Math.max(0, closes - now) }
}

export const mmss = (ms: number) => {
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function BookingQR({ b, size = 92 }: { b: Booking; size?: number }) {
  const active = ['pending', 'confirmed', 'checked_in'].includes(b.status)
  const { data } = useQuery({ queryKey: ['booking-qr', b.id], queryFn: () => blobUrl(`/bookings/${b.id}/qr`), enabled: active, staleTime: Infinity })
  if (!active) return <QrCode size={size * 0.6} weight="thin" className="muted" />
  return <div className="qr-plate" style={{ width: size }}>{data ? <img src={data} alt="booking pass" /> : <div style={{ height: size - 12 }} />}</div>
}

export default function BookingTicket({ b, compact }: { b: Booking; compact?: boolean }) {
  const w = useCheckinWindow(b)
  const inactive = ['cancelled', 'rejected', 'released', 'displaced', 'completed'].includes(b.status)
  return (
    <Link to={`/bookings/${b.id}`} className={`ticket ticket-link ${inactive ? 'is-void' : ''}`} style={{ '--stub': compact ? '118px' : '148px' } as CSSProperties}>
      <div className="ticket-body">
        <div className="ticket-accent" style={{ '--c': b.resource_color } as CSSProperties} />
        <div className="spread">
          <span className="eyebrow">{b.resource_type} · {b.reference}</span>
          <StatusTag status={b.status} label={b.status_label} />
        </div>
        <div className="display ticket-title">{b.resource_name}</div>
        <div className="muted truncate" style={{ fontSize: 13 }}>{b.title}{b.location ? ` · ${b.location}` : ''}</div>
        <div className="row ticket-meta">
          <div>
            <div className="eyebrow">Date</div>
            <div className="mono">{fmtDay(b.start)}</div>
          </div>
          <div>
            <div className="eyebrow">Time</div>
            <div className="mono">{fmtTime(b.start)}–{fmtTime(b.end)}</div>
          </div>
          <div className="hide-sm">
            <div className="eyebrow">Length</div>
            <div className="mono">{durationLabel(b.start, b.end)}</div>
          </div>
          {b.series_size && (
            <div className="hide-sm">
              <div className="eyebrow">Series</div>
              <div className="mono">{(b.occurrence_index ?? 0) + 1}/{b.series_size}</div>
            </div>
          )}
        </div>
        {w.open && (
          <div className="checkin-banner">
            <Timer size={16} weight="bold" />
            Check in now — releases in <span className="mono">{mmss(w.remaining)}</span>
          </div>
        )}
      </div>
      <div className="ticket-stub">
        <BookingQR b={b} size={compact ? 80 : 96} />
        <span className="mono muted" style={{ fontSize: 10 }}>{b.reference}</span>
      </div>
    </Link>
  )
}
