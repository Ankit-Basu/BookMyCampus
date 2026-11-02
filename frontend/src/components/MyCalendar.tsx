import type { EventInput } from '@fullcalendar/core'
import interactionPlugin from '@fullcalendar/interaction'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../lib/api'
import type { Booking } from '../lib/types'

/** Your own bookings laid out as a week, so a clash with the rest of your day is easy to spot. */
export default function MyCalendar() {
  const nav = useNavigate()
  const [range, setRange] = useState<{ from: string; to: string } | null>(null)
  const { data } = useQuery({
    queryKey: ['bookings', 'calendar', range?.from, range?.to],
    queryFn: () => api.get<Booking[]>('/bookings', { params: { ...range, status: 'pending,confirmed,checked_in,completed' } }).then((r) => r.data),
    enabled: !!range,
    placeholderData: (p) => p,
  })
  const events = useMemo<EventInput[]>(
    () =>
      (data ?? []).map((b) => ({
        id: String(b.id),
        start: b.start,
        end: b.end,
        title: `${b.title} · ${b.resource_name}`,
        classNames: ['ev-mine', b.status === 'pending' ? 'ev-pending' : ''],
      })),
    [data],
  )
  const isMobile = window.innerWidth < 760

  return (
    <div className="glass pad cal-card">
      <div className="fc-shell">
        <FullCalendar
          plugins={[timeGridPlugin, interactionPlugin]}
          initialView={isMobile ? 'timeGridDay' : 'timeGridWeek'}
          headerToolbar={{ left: 'prev,next today', center: 'title', right: isMobile ? '' : 'timeGridDay,timeGridWeek' }}
          firstDay={1}
          allDaySlot={false}
          nowIndicator
          slotMinTime="07:00:00"
          slotMaxTime="22:00:00"
          height="auto"
          events={events}
          eventClick={(info) => nav(`/bookings/${info.event.id}`)}
          datesSet={(d) => setRange({ from: d.start.toISOString(), to: d.end.toISOString() })}
          eventTimeFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
          slotLabelFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
          dayHeaderFormat={{ weekday: 'short', day: 'numeric' }}
        />
      </div>
    </div>
  )
}
