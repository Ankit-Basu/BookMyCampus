import { CheckCircle, Clock, HourglassMedium, MapPin, SealCheck, UsersThree, XCircle } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { ThemeMenu, Wordmark } from '../components/AppShell'
import { WAKE_RETRY } from '../components/AuthLayout'
import { api, errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'

type PassInfo = {
  reference: string
  resource: string
  resource_type: string
  location: string | null
  start: string
  end: string
  status: string
  status_label: string
  state: 'valid_now' | 'checked_in' | 'upcoming' | 'pending' | 'ended' | 'void'
  booked_by: string
  on_behalf_of: string
  attendees: number
  title: string
  requires_checkin: boolean
  checked_in_at: string | null
  booking_id: number | null
  can_check_in: boolean
}

/** The banner the person at the door reads first. */
function verdict(p: PassInfo): { tone: string; icon: ReactNode; title: string; sub: string } {
  const day = format(new Date(p.start), 'EEE d MMM')
  const time = `${format(new Date(p.start), 'HH:mm')}–${format(new Date(p.end), 'HH:mm')}`
  switch (p.state) {
    case 'valid_now':
      return { tone: 'var(--ok)', icon: <SealCheck size={40} weight="fill" />, title: 'Valid now', sub: `Booked for today, ${time}.` }
    case 'checked_in':
      return { tone: 'var(--ok)', icon: <CheckCircle size={40} weight="fill" />, title: 'Checked in', sub: p.checked_in_at ? `Arrived at ${format(new Date(p.checked_in_at), 'HH:mm')}. Booked until ${format(new Date(p.end), 'HH:mm')}.` : `Booked until ${format(new Date(p.end), 'HH:mm')}.` }
    case 'upcoming':
      return { tone: 'var(--warn)', icon: <Clock size={40} weight="fill" />, title: 'Not yet', sub: `This booking is for ${day}, ${time}.` }
    case 'pending':
      return { tone: 'var(--warn)', icon: <HourglassMedium size={40} weight="fill" />, title: 'Waiting for approval', sub: 'Not valid until the HOD approves it.' }
    case 'ended':
      return { tone: 'var(--fg-3)', icon: <Clock size={40} weight="fill" />, title: 'Ended', sub: `This booking was for ${day}, ${time}.` }
    default:
      return { tone: 'var(--bad)', icon: <XCircle size={40} weight="fill" />, title: 'Not valid', sub: `This booking is ${p.status_label.toLowerCase()}.` }
  }
}

/** Opened by scanning a booking pass with any phone camera. Shows whether the pass is good right now. */
export default function PassPage() {
  const { token = '' } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const key = ['public-pass', token, user?.id ?? 0]
  const { data: p, isError, error } = useQuery({
    queryKey: key,
    queryFn: () => api.get<PassInfo>(`/public/pass/${token}`).then((r) => r.data),
    ...WAKE_RETRY,
    retry: (n, e) => (e as { response?: { status?: number } }).response?.status !== 404 && n < WAKE_RETRY.retry,
  })
  const checkIn = useMutation({
    mutationFn: () => api.post('/bookings/scan', { code: window.location.href }),
    onSuccess: () => {
      toast.success('Checked in')
      qc.invalidateQueries({ queryKey: key })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })

  let body: ReactNode
  if (isError) {
    body = (
      <div className="glass pad pass-verdict" style={{ '--c': 'var(--bad)' } as CSSProperties}>
        <XCircle size={40} weight="fill" />
        <div>
          <div className="display" style={{ fontSize: 30 }}>Unknown pass</div>
          <div className="muted">{errorMessage(error)}</div>
        </div>
      </div>
    )
  } else if (!p) {
    body = (
      <div className="glass pad">
        <div className="skeleton" style={{ height: 220 }} />
        <p className="muted" style={{ fontSize: 13, margin: '12px 0 0' }}>Checking the pass. On the free plan the server can take up to a minute to wake.</p>
      </div>
    )
  } else {
    const v = verdict(p)
    body = (
      <>
        <div className="glass pad pass-verdict" style={{ '--c': v.tone } as CSSProperties} role="status">
          {v.icon}
          <div>
            <div className="display" style={{ fontSize: 34 }}>{v.title}</div>
            <div className="muted">{v.sub}</div>
          </div>
        </div>
        <div className="glass pad col" style={{ gap: 14 }}>
          <div>
            <div className="eyebrow">{p.resource_type} · {p.reference}</div>
            <div className="display" style={{ fontSize: 30, margin: '4px 0 2px' }}>{p.resource}</div>
            {p.location && <div className="row muted" style={{ gap: 6, fontSize: 14 }}><MapPin size={15} /> {p.location}</div>}
          </div>
          <dl className="attrs">
            <div><dt>Booked by</dt><dd>{p.booked_by}</dd></div>
            {p.on_behalf_of && <div><dt>For class</dt><dd>{p.on_behalf_of}</dd></div>}
            <div><dt>Date</dt><dd>{format(new Date(p.start), 'EEEE d MMMM')}</dd></div>
            <div><dt>Time</dt><dd className="mono">{format(new Date(p.start), 'HH:mm')}–{format(new Date(p.end), 'HH:mm')}</dd></div>
            <div><dt>Purpose</dt><dd>{p.title}</dd></div>
            <div><dt>People</dt><dd className="row" style={{ gap: 6 }}><UsersThree size={15} /> {p.attendees}</dd></div>
          </dl>
          {p.can_check_in && (
            <button className="key key-mint" disabled={checkIn.isPending} onClick={() => checkIn.mutate()}>
              <CheckCircle weight="bold" /> {checkIn.isPending ? 'Checking in…' : 'Check them in'}
            </button>
          )}
          {p.booking_id && (
            <Link to={`/bookings/${p.booking_id}`} className="key key-ghost">Open the booking</Link>
          )}
          {!user && p.requires_checkin && p.state === 'valid_now' && (
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>
              Staff can <Link to={`/login?next=${encodeURIComponent(`/pass/${token}`)}`}>sign in</Link> to check them in.
            </p>
          )}
        </div>
      </>
    )
  }

  return (
    <div className="pass-page">
      <div className="login-top">
        <Wordmark />
        <ThemeMenu />
      </div>
      <main className="col" style={{ gap: 14, maxWidth: 520, margin: '0 auto', padding: '24px 16px 48px' }}>
        <div className="eyebrow">Booking pass check</div>
        {body}
      </main>
    </div>
  )
}
