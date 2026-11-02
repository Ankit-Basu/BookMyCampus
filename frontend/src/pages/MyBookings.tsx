import { CalendarBlank, CopySimple, QrCode } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import BookingTicket from '../components/BookingTicket'
import { Reveal } from '../components/motion'
import { Empty, PageHeader, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { Booking } from '../lib/types'

const MyCalendar = lazy(() => import('../components/MyCalendar'))

export default function MyBookings() {
  const { user } = useAuth()
  const [tab, setTab] = useState<'upcoming' | 'past' | 'calendar'>('upcoming')
  const { data, isLoading } = useQuery({
    queryKey: ['bookings', tab],
    queryFn: () => api.get<Booking[]>('/bookings', { params: tab === 'upcoming' ? { upcoming: 1 } : { past: 1 } }).then((r) => r.data),
    refetchInterval: 30000,
    enabled: tab !== 'calendar',
  })
  const feed = `${window.location.origin}/api/calendar/${user?.calendar_token}.ics`

  return (
    <div className="page">
      <PageHeader
        eyebrow="Your passes"
        title={<>My <em>bookings</em></>}
        sub="Every pass carries a QR. Scan the poster at the door when you arrive — or show this to the lab in-charge."
        actions={
          <>
            <Link to="/scan" className="key key-mint">
              <QrCode weight="bold" /> Scan to check in
            </Link>
            <button
              className="key key-ghost"
              onClick={() => {
                navigator.clipboard?.writeText(feed)
                toast.success('Calendar feed copied', { description: 'Add it in Google Calendar → Other calendars → From URL.' })
              }}
            >
              <CalendarBlank /> Subscribe in Google / Outlook
            </button>
          </>
        }
      />
      <div className="seg" style={{ marginBottom: 22 }}>
        {(['upcoming', 'calendar', 'past'] as const).map((t) => (
          <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
            {t === 'upcoming' ? 'Upcoming' : t === 'calendar' ? 'My calendar' : 'History'}
          </button>
        ))}
      </div>
      {tab === 'calendar' ? (
        <Suspense fallback={<Skeleton h={520} />}><MyCalendar /></Suspense>
      ) : isLoading ? (
        <div className="ticket-grid">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} h={190} />)}</div>
      ) : data?.length ? (
        <Reveal className="ticket-grid" stagger={0.06}>
          {data.map((b) => (
            <div data-reveal key={b.id}>
              <BookingTicket b={b} />
            </div>
          ))}
        </Reveal>
      ) : (
        <Empty title={tab === 'upcoming' ? 'No passes yet.' : 'No history yet.'}>
          <Link to="/explore" className="key key-amber" style={{ marginTop: 14 }}>
            Find something to book
          </Link>
        </Empty>
      )}
      <div className="mono muted" style={{ fontSize: 11, marginTop: 30, display: 'flex', gap: 8, alignItems: 'center' }}>
        <CopySimple size={12} /> Personal iCal feed: <span className="truncate">{feed}</span>
      </div>
    </div>
  )
}
