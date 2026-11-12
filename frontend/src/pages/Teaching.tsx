import { CalendarCheck, ChalkboardTeacher, Check, MagnifyingGlass, MapPin, UsersThree, X } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, isToday, isTomorrow } from 'date-fns'
import { useMemo, useState, type CSSProperties } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { Empty, PageHeader, Select, Skeleton } from '../components/ui'
import { api, errorMessage } from '../lib/api'

type WeekItem = {
  kind: 'class' | 'booking'
  start: string
  end: string
  title: string
  subtitle: string
  section: string
  room: { id: number; name: string }
  booking?: number
}
type Week = { items: WeekItem[]; my_sections: string[]; all_sections: string[]; matched_timetable: boolean }
type Option = { start: string; end: string; others: number; room: { id: number; name: string; code: string; capacity: number; location_label: string | null } }
type Request = {
  id: number
  status: 'pending' | 'booked' | 'declined'
  status_label: string
  student: string
  student_username: string
  resource: { id: number; name: string; type_name: string }
  start: string
  end: string
  note: string
  reply: string
  expired: boolean
  taken_by: string | null
}

const dayLabel = (d: Date) => (isToday(d) ? 'Today' : isTomorrow(d) ? 'Tomorrow' : format(d, 'EEEE d MMM'))
const hm = (iso: string) => format(new Date(iso), 'HH:mm')
const LENGTHS = [
  { minutes: 50, label: '1 lecture · 50m' },
  { minutes: 100, label: '2 lectures · 1h 40m' },
  { minutes: 120, label: 'Practical · 2h' },
]

/** Link that opens a room with the booking form already filled in. */
function bookLink(roomId: number, start: string, end: string, extra: Record<string, string | number>) {
  const q = new URLSearchParams({ start, end, ...Object.fromEntries(Object.entries(extra).map(([k, v]) => [k, String(v)])) })
  return `/resources/${roomId}?${q}`
}

function Requests() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['teacher-requests'], queryFn: () => api.get<{ incoming: Request[] }>('/teacher-requests').then((r) => r.data) })
  const [declining, setDeclining] = useState<number | null>(null)
  const [reply, setReply] = useState('')
  const decline = useMutation({
    mutationFn: (id: number) => api.post(`/teacher-requests/${id}/decline`, { reply }),
    onSuccess: () => {
      toast.success('Declined. The student has been told.')
      setDeclining(null)
      setReply('')
      qc.invalidateQueries({ queryKey: ['teacher-requests'] })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const list = data?.incoming ?? []
  const open = list.filter((r) => r.status === 'pending' && !r.expired)
  const past = list.filter((r) => !(r.status === 'pending' && !r.expired)).slice(0, 5)

  return (
    <section className="glass pad col" style={{ gap: 12 }}>
      <div className="spread">
        <div className="h2">Student requests</div>
        {open.length > 0 && <span className="tag" style={{ '--c': 'var(--brand)' } as CSSProperties}>{open.length} waiting</span>}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Students can't book labs or classrooms, so they ask you. Book it and they're told automatically.</p>
      {!data && <Skeleton h={80} />}
      {data && !open.length && <p className="muted" style={{ margin: 0, fontSize: 13.5 }}>No requests waiting.</p>}
      {open.map((r) => (
        <div key={r.id} className="teach-row">
          <div className="grow" style={{ minWidth: 0 }}>
            <strong>{r.student}</strong> <span className="muted mono" style={{ fontSize: 11.5 }}>{r.student_username}</span>
            <div style={{ fontSize: 13.5 }}>{r.resource.name} · {format(new Date(r.start), 'EEE d MMM')}, {hm(r.start)}–{hm(r.end)}</div>
            {r.note && <div className="muted" style={{ fontSize: 13 }}>“{r.note}”</div>}
            {r.taken_by && <div style={{ fontSize: 12.5, color: 'var(--warn)' }}>The room now has {r.taken_by} then. Book it at another time, or decline.</div>}
            {declining === r.id && (
              <form className="row" style={{ gap: 8, marginTop: 8 }} onSubmit={(e) => { e.preventDefault(); decline.mutate(r.id) }}>
                <input className="input grow" autoFocus value={reply} onChange={(e) => setReply(e.target.value)} maxLength={200} placeholder="Reason (optional), e.g. lab is reserved for exams" />
                <button className="key key-coral key-sm" disabled={decline.isPending}>Decline</button>
              </form>
            )}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <Link className="key key-mint key-sm" to={bookLink(r.resource.id, r.start, r.end, { request: r.id, title: `For ${r.student}${r.note ? `: ${r.note}` : ''}`.slice(0, 150) })}>
              <Check weight="bold" /> Book it
            </Link>
            {declining !== r.id && (
              <button className="key key-ghost key-sm" onClick={() => setDeclining(r.id)}><X /> Decline</button>
            )}
          </div>
        </div>
      ))}
      {past.length > 0 && (
        <details className="muted" style={{ fontSize: 13 }}>
          <summary style={{ cursor: 'pointer' }}>Earlier requests</summary>
          {past.map((r) => (
            <div key={r.id} style={{ padding: '6px 0' }}>
              {r.student} · {r.resource.name} · {format(new Date(r.start), 'd MMM HH:mm')} · <strong>{r.expired ? 'Expired' : r.status_label}</strong>
            </div>
          ))}
        </details>
      )}
    </section>
  )
}

function MakeupFinder({ week }: { week?: Week }) {
  const nav = useNavigate()
  const sections = useMemo(() => {
    const mine = week?.my_sections ?? []
    return [...mine, ...(week?.all_sections ?? []).filter((s) => !mine.includes(s))]
  }, [week])
  const [section, setSection] = useState('')
  const [minutes, setMinutes] = useState(50)
  const [size, setSize] = useState('60')
  const chosen = section || sections[0] || ''
  const people = Math.max(parseInt(size, 10) || 1, 1)
  const find = useQuery({
    queryKey: ['makeup', chosen, minutes, people],
    queryFn: () => api.get<{ options: Option[] }>('/teaching/makeup', { params: { section: chosen, minutes, size: people } }).then((r) => r.data),
    enabled: !!chosen,
  })

  return (
    <section className="glass pad col" style={{ gap: 14 }}>
      <div>
        <div className="h2">Make-up class finder</div>
        <p className="muted" style={{ margin: '4px 0 0', fontSize: 13 }}>Times in the next week when the section has no class, you're free, and a classroom that fits them is empty.</p>
      </div>
      <div className="grid teach-form">
        <label className="field">
          <span>Section</span>
          <Select value={chosen} onChange={(e) => setSection(e.target.value)}>
            {sections.map((s) => <option key={s} value={s}>{s}{week?.my_sections.includes(s) ? ' · yours' : ''}</option>)}
          </Select>
        </label>
        <label className="field">
          <span>Students</span>
          <input className="input" type="number" inputMode="numeric" min={1} value={size} onChange={(e) => setSize(e.target.value.replace(/^0+(?=\d)/, ''))} />
        </label>
      </div>
      <div className="row wrap" style={{ gap: 8 }} role="group" aria-label="Length">
        {LENGTHS.map((l) => (
          <button key={l.minutes} className={`chip ${minutes === l.minutes ? 'on' : ''}`} onClick={() => setMinutes(l.minutes)}>{l.label}</button>
        ))}
      </div>
      {find.isFetching && !find.data && <Skeleton h={120} />}
      {find.data && !find.data.options.length && <Empty title="No common free time.">Try a shorter class or fewer students.</Empty>}
      <div className="col" style={{ gap: 8 }}>
        {find.data?.options.map((o) => (
          <div key={o.start} className="teach-row">
            <div className="teach-when">
              <strong>{dayLabel(new Date(o.start))}</strong>
              <span className="mono">{hm(o.start)}–{hm(o.end)}</span>
            </div>
            <div className="grow" style={{ minWidth: 0 }}>
              <div><strong>{o.room.name}</strong> <span className="muted" style={{ fontSize: 12.5 }}><UsersThree size={13} /> {o.room.capacity}</span></div>
              <div className="muted truncate" style={{ fontSize: 12.5 }}>
                <MapPin size={13} /> {o.room.location_label}{o.others ? ` · ${o.others} other room${o.others > 1 ? 's' : ''} free too` : ''}
              </div>
            </div>
            <button
              className="key key-amber key-sm"
              onClick={() => nav(bookLink(o.room.id, o.start, o.end, { for: chosen, size: people, title: `Make-up class for ${chosen}` }))}
            >
              <CalendarCheck weight="bold" /> Book this
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}

function MyWeek({ week }: { week?: Week }) {
  const days = useMemo(() => {
    const out: { label: string; items: WeekItem[] }[] = []
    for (const i of week?.items ?? []) {
      const label = dayLabel(new Date(i.start))
      const last = out[out.length - 1]
      if (last?.label === label) last.items.push(i)
      else out.push({ label, items: [i] })
    }
    return out
  }, [week])
  return (
    <section className="glass pad col" style={{ gap: 12 }}>
      <div className="h2">My week</div>
      {!week && <Skeleton h={160} />}
      {week && !week.matched_timetable && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Your name isn't on the timetable, so only your bookings are shown.</p>
      )}
      {week && !week.items.length && <p className="muted" style={{ margin: 0 }}>Nothing in the next seven days.</p>}
      {days.map((d) => (
        <div key={d.label}>
          <div className="eyebrow" style={{ margin: '6px 0 6px' }}>{d.label}</div>
          {d.items.map((i) => (
            <Link key={`${i.kind}${i.start}${i.room.id}`} to={i.booking ? `/bookings/${i.booking}` : `/resources/${i.room.id}`} className={`week-item ${i.kind}`}>
              <span className="mono">{hm(i.start)}–{hm(i.end)}</span>
              <span className="grow truncate"><strong>{i.title}</strong> <span className="muted">· {i.room.name}</span></span>
              <span className="tag">{i.kind === 'class' ? 'Class' : i.section ? `Booked · ${i.section}` : 'Booked'}</span>
            </Link>
          ))}
        </div>
      ))}
    </section>
  )
}

/** Faculty only: their week, make-up classes, and requests from students. */
export default function Teaching() {
  const { data: week } = useQuery({ queryKey: ['teaching-week'], queryFn: () => api.get<Week>('/teaching/week').then((r) => r.data) })
  return (
    <div className="page">
      <PageHeader
        eyebrow="Teaching"
        title={<>Your <em>teaching</em> week</>}
        sub="Your classes and bookings, a finder for make-up classes, and what students have asked you to book."
        actions={<Link to="/explore?type=classroom" className="key key-ghost"><MagnifyingGlass /> Browse classrooms</Link>}
      />
      <div className="teach-layout">
        <div className="col" style={{ gap: 18 }}>
          <Requests />
          <MakeupFinder week={week} />
        </div>
        <MyWeek week={week} />
      </div>
      <p className="muted" style={{ fontSize: 12.5, marginTop: 18 }}>
        <ChalkboardTeacher size={14} /> Booking a lab or classroom for a class: open it, pick a slot and choose “For a class”.
      </p>
    </div>
  )
}
