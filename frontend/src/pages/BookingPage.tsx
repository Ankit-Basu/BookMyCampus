import { ArrowLeft, CalendarPlus, CheckCircle, Circle, QrCode, ShareNetwork, SignOut, Timer, XCircle } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { type CSSProperties } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { BookingQR, mmss, useCheckinWindow } from '../components/BookingTicket'
import { Reveal } from '../components/motion'
import { Skeleton, StatusTag, Empty } from '../components/ui'
import { api, download, errorMessage, retryUnlessMissing } from '../lib/api'
import { useAuth } from '../lib/auth'
import { durationLabel, fmtRelative, ROLE_LABEL } from '../lib/format'
import { shareOrigin } from '../lib/shareOrigin'
import type { Booking } from '../lib/types'

function Timeline({ b }: { b: Booking }) {
  const steps = [
    { label: 'Requested', at: b.created_at, done: true },
    ...b.approvals.map((a) => ({
      label: `${a.step_name}${a.decided_by_name ? ` · ${a.decided_by_name}` : ` · ${ROLE_LABEL[a.approver_role] ?? a.approver_role}`}`,
      at: a.decided_at,
      done: a.status === 'approved',
      bad: a.status === 'rejected',
      live: a.status === 'pending',
      note: a.comment,
    })),
    ...(b.checkin ? [{ label: `Checked in (${b.checkin.method.replace('_', ' ')})`, at: b.checkin.checked_in_at, done: true }] : []),
    ...(b.checkin?.checked_out_at ? [{ label: 'Checked out', at: b.checkin.checked_out_at, done: true }] : []),
    ...(['released', 'cancelled', 'displaced', 'rejected'].includes(b.status) ? [{ label: b.status_label, at: b.decided_at, bad: true, note: b.status_note }] : []),
  ] as { label: string; at: string | null; done?: boolean; bad?: boolean; live?: boolean; note?: string }[]
  return (
    <ol className="timeline">
      {steps.map((s, i) => (
        <li key={i} className={s.bad ? 'bad' : s.done ? 'done' : s.live ? 'live' : ''}>
          <span className="tl-icon">{s.bad ? <XCircle weight="fill" /> : s.done ? <CheckCircle weight="fill" /> : <Circle weight={s.live ? 'duotone' : 'regular'} />}</span>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{s.label}</div>
            {s.at && <div className="mono muted" style={{ fontSize: 11 }}>{format(new Date(s.at), 'd MMM, HH:mm')} · {fmtRelative(s.at)}</div>}
            {s.live && <div className="muted" style={{ fontSize: 12 }}>Waiting on this step…</div>}
            {s.note && <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>“{s.note}”</div>}
          </div>
        </li>
      ))}
    </ol>
  )
}

export default function BookingPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const nav = useNavigate()
  const { data: b, isError } = useQuery({ retry: retryUnlessMissing, queryKey: ['booking', id], queryFn: () => api.get<Booking>(`/bookings/${id}`).then((r) => r.data), refetchInterval: 20000 })

  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) => api.post(`/bookings/${id}/${path}`, body ?? {}).then((r) => r.data),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['booking', id] })
      qc.invalidateQueries({ queryKey: ['bookings'] })
      toast.success({ cancel: 'Cancelled — slot released to others', 'check-out': 'Checked out — remaining time handed back', 'check-in': 'Checked in. Enjoy!' }[v.path] ?? 'Done')
    },
    onError: (e) => toast.error(errorMessage(e)),
  })

  if (isError && !b) {
    return (
      <div className="page">
        <Empty title="We can’t find that booking.">
          <Link to="/bookings" className="key key-amber" style={{ marginTop: 14 }}>Back to my bookings</Link>
        </Empty>
      </div>
    )
  }
  if (!b) return <div className="page"><Skeleton h={480} /></div>
  return <BookingView b={b} mine={b.user === user?.id} act={act.mutate} busy={act.isPending} nav={nav} />
}

function BookingView({ b, mine, act, busy, nav }: { b: Booking; mine: boolean; act: (v: { path: string; body?: object }) => void; busy: boolean; nav: (p: string) => void }) {
  const w = useCheckinWindow(b)
  const active = ['pending', 'confirmed', 'checked_in'].includes(b.status)
  const start = new Date(b.start)
  const end = new Date(b.end)
  const untilOpen = w.opens - w.now
  return (
    <div className="page">
      <Link to="/bookings" className="chip" style={{ marginBottom: 18 }}>
        <ArrowLeft size={14} /> My bookings
      </Link>
      <div className="booking-layout">
        <Reveal>
          <div className={`pass-big ${active ? '' : 'is-void'}`} style={{ '--c': b.resource_color } as CSSProperties}>
            <div className="pass-photo">
              {b.resource_cover && <img src={b.resource_cover} alt="" />}
              <div className="rhero-shade" />
              <div className="pass-photo-copy">
                <div className="eyebrow">{b.resource_type} · {b.resource_code}</div>
                <div className="display" style={{ fontSize: 'clamp(36px,4.6vw,58px)' }}>{b.resource_name}</div>
                <div className="muted">{b.location}</div>
              </div>
            </div>
            <div className="pass-perf" />
            <div className="pass-body">
              <div className="pass-grid">
                <div>
                  <div className="eyebrow">Date</div>
                  <div className="display" style={{ fontSize: 30 }}>{format(start, 'EEE d MMM')}</div>
                </div>
                <div>
                  <div className="eyebrow">Time</div>
                  <div className="mono" style={{ fontSize: 22, color: 'var(--brand-ink)' }}>{format(start, 'HH:mm')}–{format(end, 'HH:mm')}</div>
                  <div className="mono muted" style={{ fontSize: 11 }}>{durationLabel(b.start, b.end)}</div>
                </div>
                <div>
                  <div className="eyebrow">Booked by</div>
                  <div>{b.user_name}</div>
                  {b.on_behalf_of && <div className="muted" style={{ fontSize: 12 }}>for {b.on_behalf_of}</div>}
                </div>
                <div>
                  <div className="eyebrow">Status</div>
                  <StatusTag status={b.status} label={b.status_label} />
                </div>
              </div>
              <div className="divider" />
              <div className="spread" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ minWidth: 0 }}>
                  <div className="h2">{b.title}</div>
                  {b.purpose && <p className="muted" style={{ margin: '4px 0 0', fontSize: 13.5 }}>{b.purpose}</p>}
                  <div className="mono muted" style={{ fontSize: 12, marginTop: 10 }}>REF {b.reference} · {b.attendees} people</div>
                </div>
                <div className="col" style={{ alignItems: 'center', gap: 6 }}>
                  <BookingQR b={b} size={150} />
                  {['pending', 'confirmed', 'checked_in'].includes(b.status) && (
                    <span className="muted" style={{ fontSize: 11.5, textAlign: 'center', maxWidth: 150 }}>Show this at the door. Any phone camera can verify it.</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Reveal>

        <aside className="col" style={{ gap: 18 }}>
          {mine && b.status === 'confirmed' && b.requires_checkin && (
            <Reveal className={`glass pad checkin-card ${w.open ? 'live' : ''}`}>
              <div className="row" style={{ gap: 10 }}>
                <Timer size={22} color={w.open ? 'var(--ok)' : 'var(--fg-3)'} weight="duotone" />
                <div className="h2">{w.open ? 'Check-in is open' : untilOpen > 0 ? 'Check-in opens soon' : 'Check-in window'}</div>
              </div>
              {w.open ? (
                <>
                  <div className="countdown mono">{mmss(w.remaining)}</div>
                  <p className="muted" style={{ margin: '0 0 14px', fontSize: 13 }}>until this slot auto-releases to the next person.</p>
                  <button className="key key-mint key-lg" style={{ width: '100%' }} onClick={() => nav('/scan')}>
                    <QrCode weight="bold" /> Scan the room QR
                  </button>
                </>
              ) : (
                <p className="muted" style={{ fontSize: 13 }}>
                  Opens {format(new Date(w.opens), 'HH:mm')} · closes {format(new Date(w.closes), 'HH:mm')}. Scan the poster at the door within that window.
                </p>
              )}
            </Reveal>
          )}

          <Reveal className="glass pad">
            <div className="eyebrow" style={{ marginBottom: 14 }}>Journey</div>
            <Timeline b={b} />
          </Reveal>

          <Reveal className="glass pad col" style={{ gap: 10 }}>
            {active && b.qr_token && <SharePass b={b} />}
            <a className="key key-ghost" href={googleCalendarUrl(b)} target="_blank" rel="noopener noreferrer">
              <CalendarPlus /> Add to Google Calendar
            </a>
            <button className="muted" style={{ fontSize: 12.5, alignSelf: 'center', background: 'none', border: 0, cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: 3 }} onClick={() => download(`/bookings/${b.id}/ics`, `${b.reference}.ics`)}>
              Using Outlook or Apple Calendar? Download the .ics file
            </button>
            {b.status === 'checked_in' && (
              <button className="key key-amber" disabled={busy} onClick={() => act({ path: 'check-out' })}>
                <SignOut /> Done early — check out
              </button>
            )}
            {active && b.status !== 'checked_in' && (
              <button
                className="key key-coral"
                disabled={busy}
                onClick={() => {
                  if (confirm('Cancel this booking and release the slot?')) act({ path: 'cancel' })
                }}
              >
                <XCircle /> Cancel booking
              </button>
            )}
            <Link to={`/resources/${b.resource}`} className={active ? 'key key-ghost' : 'key key-amber'}>{active ? `View ${b.resource_name}` : 'Book this room again'}</Link>
          </Reveal>
        </aside>
      </div>
    </div>
  )
}

/** Send the pass to the people you booked with, so any of them can show it at the door. */
function SharePass({ b }: { b: Booking }) {
  const url = `${shareOrigin()}/pass/${b.qr_token}`
  const share = async () => {
    const text = `${b.resource_name}, ${format(new Date(b.start), 'EEE d MMM HH:mm')}–${format(new Date(b.end), 'HH:mm')} (${b.reference})`
    if (navigator.share) {
      try {
        await navigator.share({ title: 'Booking pass', text, url })
        return
      } catch (e) {
        if ((e as Error).name === 'AbortError') return
      }
    }
    try {
      await navigator.clipboard.writeText(`${text}
${url}`)
      toast.success('Pass link copied', { description: 'Paste it to your group. It opens on any phone.' })
    } catch {
      toast.info('Copy this link', { description: url })
    }
  }
  return (
    <button className="key key-mint" onClick={share}>
      <ShareNetwork weight="bold" /> Share pass with my group
    </button>
  )
}

/** Google Calendar's "add event" page, filled in. Opens in the browser, so nothing is downloaded. */
function googleCalendarUrl(b: Booking) {
  const utc = (iso: string) => new Date(iso).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')
  const pass = b.qr_token ? `\nPass: ${shareOrigin()}/pass/${b.qr_token}` : ''
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: `${b.title} · ${b.resource_name}`,
    dates: `${utc(b.start)}/${utc(b.end)}`,
    details: `BookMyCampus booking ${b.reference}${b.on_behalf_of ? ` for ${b.on_behalf_of}` : ''}.${pass}`,
    location: b.location ?? b.resource_name,
    ctz: 'Asia/Kolkata',
  })
  return `https://calendar.google.com/calendar/render?${params}`
}
