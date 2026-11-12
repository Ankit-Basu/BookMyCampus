import type { DateSelectArg, EventInput } from '@fullcalendar/core'
import interactionPlugin from '@fullcalendar/interaction'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import { ArrowLeft, ArrowRight, BellRinging, CalendarPlus, ChalkboardTeacher, Clock, GraduationCap, LockSimple, MapPin, Printer, Repeat, SealCheck, Stamp, User, UsersThree, Warning, Wrench } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Reveal } from '../components/motion'
import DecryptedText from '../components/reactbits/DecryptedText'
import SaveButton from '../components/SaveButton'
import { Drawer, Modal, Skeleton, TypeTag, Select, Empty } from '../components/ui'
import { api, blobUrl, errorCode, errorDetails, errorMessage, retryUnlessMissing } from '../lib/api'
import { useAuth } from '../lib/auth'
import { durationLabel, inr, WEEKDAYS } from '../lib/format'
import { initialWeek } from '../lib/preload'
import type { Availability, Booking, Resource, ResourceDetail } from '../lib/types'
import { qrPath } from '../lib/shareOrigin'

type Consumable = { id: number; name: string; kind: string; unit: string; stock: number }


/** What people usually book each type for, as the title placeholder. */
const TITLE_HINT: Record<string, string> = {
  Classroom: 'e.g. Make-up class for CSE310',
  Laboratory: 'e.g. CSE408 practical',
  'Seminar Hall': 'e.g. Guest lecture',
  'Sports Facility': 'e.g. Football practice',
  Equipment: 'e.g. Capstone model training',
}
function BookingDrawer({
  resource,
  slot,
  onClose,
}: {
  resource: ResourceDetail
  slot: { start: Date; end: Date } | null
  onClose: () => void
}) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const nav = useNavigate()
  const [title, setTitle] = useState('')
  const [attendees, setAttendees] = useState(1)
  const [purpose, setPurpose] = useState('')
  const [forClass, setForClass] = useState(false)
  const [onBehalf, setOnBehalf] = useState('')
  const [recurring, setRecurring] = useState(false)
  const [days, setDays] = useState<number[]>([])
  const [count, setCount] = useState(8)
  const [policy, setPolicy] = useState<'skip' | 'abort'>('skip')
  const [acc, setAcc] = useState<Record<number, number>>({})
  const [result, setResult] = useState<{ created: Booking[]; skipped: { start: string; reason: string }[]; requested: number } | null>(null)

  const { data: consumables } = useQuery({
    queryKey: ['consumables-for', resource.id],
    queryFn: () => api.get<Consumable[]>('/consumables', { params: { for_resource: resource.id } }).then((r) => r.data),
    enabled: !!slot,
  })

  useEffect(() => {
    if (slot) {
      setResult(null)
      setDays([(slot.start.getDay() + 6) % 7])
    }
  }, [slot])

  const book = useMutation({
    mutationFn: () =>
      api
        .post('/bookings', {
          resource: resource.id,
          start: slot!.start.toISOString(),
          end: slot!.end.toISOString(),
          title: title || `${resource.name} booking`,
          purpose,
          on_behalf_of: forClass ? onBehalf.trim() : '',
          attendees,
          recurrence: recurring ? { freq: 'weekly', interval: 1, weekdays: days, count, conflict_policy: policy } : null,
          accessories: Object.entries(acc).filter(([, q]) => q > 0).map(([id, quantity]) => ({ id: Number(id), quantity })),
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['availability', resource.id] })
      qc.invalidateQueries({ queryKey: ['bookings'] })
      if (recurring) {
        setResult(data)
        toast.success(`${data.created.length} of ${data.requested} dates booked`)
      } else {
        toast.success(data.status === 'pending' ? 'Request sent — slot held while it’s approved' : `Booked! Ref ${data.reference}`)
        onClose()
        nav(`/bookings/${data.id}`)
      }
    },
    onError: (e) => {
      const code = errorCode(e)
      if (code === 'slot_conflict') {
        const d = errorDetails(e)
        toast.error(d.kind === 'timetable' ? `That’s a timetabled class (${d.label}).` : 'Someone grabbed that slot a moment ago.', {
          description: 'The calendar has been refreshed.',
        })
        qc.invalidateQueries({ queryKey: ['availability', resource.id] })
      } else if (code === 'series_conflict') {
        toast.error(errorMessage(e), { description: 'Switch to “skip clashes” to book the free dates.' })
      } else toast.error(errorMessage(e))
    },
  })

  if (!slot) return <Drawer open={false} onClose={onClose} title="">{null}</Drawer>
  const needsApproval = resource.requires_approval
  return (
    <Drawer open={!!slot} onClose={onClose} title={result ? 'Series booked' : 'Reserve this slot'}>
      {result ? (
        <div className="col">
          <div className="glass-flat pad">
            <div className="display" style={{ fontSize: 40 }}>
              {result.created.length}<span className="muted" style={{ fontSize: 24 }}> / {result.requested}</span>
            </div>
            <div className="muted">occurrences reserved</div>
          </div>
          {result.skipped.length > 0 && (
            <div className="glass-flat pad" style={{ borderColor: 'rgba(255,111,89,.35)' }}>
              <div className="row" style={{ marginBottom: 8 }}>
                <Warning color="var(--bad)" /> <strong>Skipped — clashes handled per date</strong>
              </div>
              {result.skipped.map((s) => (
                <div key={s.start} className="spread" style={{ fontSize: 13, padding: '4px 0' }}>
                  <span className="mono">{format(new Date(s.start), 'EEE d MMM HH:mm')}</span>
                  <span className="muted">{s.reason}</span>
                </div>
              ))}
            </div>
          )}
          <button className="key key-amber" onClick={() => { onClose(); nav('/bookings') }}>See my bookings</button>
        </div>
      ) : (
        <form
          className="col"
          style={{ gap: 14 }}
          onSubmit={(e) => {
            e.preventDefault()
            book.mutate()
          }}
        >
          <div className="slot-summary">
            <div>
              <div className="eyebrow">{format(slot.start, 'EEEE')}</div>
              <div className="display" style={{ fontSize: 30 }}>{format(slot.start, 'd MMMM')}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="mono" style={{ fontSize: 22, color: 'var(--brand-ink)' }}>
                {format(slot.start, 'HH:mm')}–{format(slot.end, 'HH:mm')}
              </div>
              <div className="eyebrow">{durationLabel(slot.start.toISOString(), slot.end.toISOString())}</div>
            </div>
          </div>
          {user?.can_book_recurring && (
            <div className="seg audience" role="group" aria-label="Who is this booking for">
              <button type="button" className={forClass ? '' : 'on'} onClick={() => setForClass(false)}><User size={15} /> Just me</button>
              <button type="button" className={forClass ? 'on' : ''} onClick={() => setForClass(true)}><GraduationCap size={15} /> For a class</button>
            </div>
          )}
          {needsApproval && (
            <div className="notice">
              <Stamp size={18} color="var(--brand)" /> This needs approval. The slot is held for you the moment you submit.
            </div>
          )}
          <label className="field">
            <span>What’s it for?</span>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={TITLE_HINT[resource.type_name] ?? 'e.g. Project team meeting'} maxLength={160} required />
          </label>
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <label className="field">
              <span>People (max {resource.capacity})</span>
              <input className="input" type="number" min={1} max={resource.capacity} value={attendees} onChange={(e) => setAttendees(Number(e.target.value))} />
            </label>
            {forClass && (
              <label className="field">
                <span>Class or section</span>
                <input className="input" value={onBehalf} onChange={(e) => setOnBehalf(e.target.value)} placeholder="K22CS-B" maxLength={80} required />
              </label>
            )}
          </div>
          <label className="field">
            <span>Notes for the approver (optional)</span>
            <textarea className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)} rows={2} />
          </label>

          {!!consumables?.length && (
            <div className="field">
              <span>Add accessories & consumables</span>
              <div className="col" style={{ gap: 6 }}>
                {consumables.map((c) => (
                  <div key={c.id} className="acc-row">
                    <span className="grow truncate">{c.name}</span>
                    <span className="mono muted" style={{ fontSize: 11 }}>{c.stock} {c.unit}</span>
                    <div className="stepper">
                      <button type="button" onClick={() => setAcc((a) => ({ ...a, [c.id]: Math.max(0, (a[c.id] ?? 0) - 1) }))}>−</button>
                      <span className="mono">{acc[c.id] ?? 0}</span>
                      <button type="button" onClick={() => setAcc((a) => ({ ...a, [c.id]: Math.min(c.stock, (a[c.id] ?? 0) + 1) }))}>+</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {user?.can_book_recurring && (
            <div className="glass-flat pad" style={{ padding: 16 }}>
              <div className="spread">
                <div className="row" style={{ gap: 10 }}>
                  <Repeat size={18} color="var(--info)" />
                  <div>
                    <div className="h3">Repeat weekly</div>
                    <div className="muted" style={{ fontSize: 12 }}>Each date is claimed independently</div>
                  </div>
                </div>
                <button type="button" className={`rocker ${recurring ? 'on' : ''}`} onClick={() => setRecurring(!recurring)} aria-label="Repeat weekly" />
              </div>
              {recurring && (
                <div className="col" style={{ marginTop: 14, gap: 12 }}>
                  <div className="row wrap" style={{ gap: 6 }}>
                    {WEEKDAYS.map((d, i) => (
                      <button type="button" key={d} className={`chip ${days.includes(i) ? 'on' : ''}`} style={{ height: 30 }} onClick={() => setDays(days.includes(i) ? days.filter((x) => x !== i) : [...days, i])}>
                        {d}
                      </button>
                    ))}
                  </div>
                  <div className="grid" style={{ gridTemplateColumns: '1fr 1.4fr', gap: 12 }}>
                    <label className="field">
                      <span>Occurrences</span>
                      <input className="input" type="number" min={2} max={52} value={count} onChange={(e) => setCount(Number(e.target.value))} />
                    </label>
                    <label className="field">
                      <span>If a date clashes</span>
                      <Select value={policy} onChange={(e) => setPolicy(e.target.value as 'skip' | 'abort')}>
                        <option value="skip">Skip that date, book the rest</option>
                        <option value="abort">Book nothing (all or nothing)</option>
                      </Select>
                    </label>
                  </div>
                </div>
              )}
            </div>
          )}

          <button className="key key-amber key-lg" disabled={book.isPending}>
            <CalendarPlus weight="bold" />
            {book.isPending ? 'Claiming slot…' : needsApproval ? 'Request booking' : recurring ? `Book ${count} weeks` : 'Confirm booking'}
          </button>
          <p className="muted" style={{ fontSize: 12, margin: 0, textAlign: 'center' }}>
            {resource.requires_checkin ? 'Scan the room QR within the grace period after start, or the slot auto-releases.' : 'No check-in needed for this resource.'}
          </p>
        </form>
      )}
    </Drawer>
  )
}

type Taken = { kind: string; label: string; start: Date; end: Date }
type Alternatives = { rooms: Resource[]; next_free: string | null }

type Teacher = { id: number; name: string; department: string | null; same_department: boolean }

/** Students can't book labs or classrooms, so they ask a teacher, who gets a link with the slot filled in. */
function AskTeacher({ resource, open, onClose }: { resource: ResourceDetail; open: boolean; onClose: () => void }) {
  const { data: teachers } = useQuery({ queryKey: ['teachers'], queryFn: () => api.get<Teacher[]>('/teachers').then((r) => r.data), enabled: open, staleTime: 300000 })
  const ask = useMutation({
    mutationFn: (body: { teacher: string; start: string; end: string; note: string }) => api.post<{ sent_to: string }>(`/resources/${resource.id}/ask-teacher`, body).then((r) => r.data),
    onSuccess: (d) => {
      toast.success(`Sent to ${d.sent_to}`, { description: 'They get a notification with a link to book it for you.' })
      onClose()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const tomorrow = format(new Date(Date.now() + 86400000), 'yyyy-MM-dd')
  return (
    <Modal open={open} onClose={onClose}>
      <form
        className="col"
        onSubmit={(e) => {
          e.preventDefault()
          const f = new FormData(e.currentTarget)
          const day = String(f.get('day'))
          ask.mutate({
            teacher: String(f.get('teacher')),
            start: new Date(`${day}T${f.get('from')}`).toISOString(),
            end: new Date(`${day}T${f.get('to')}`).toISOString(),
            note: String(f.get('note') ?? ''),
          })
        }}
      >
        <div className="h2">Ask a teacher to book {resource.name}</div>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          {resource.type_name === 'Laboratory' ? 'Labs' : `${resource.type_name}s`} are booked by faculty. Your teacher gets a notification with this slot ready to book.
        </p>
        <label className="field">
          <span>Teacher</span>
          <Select name="teacher" required defaultValue={teachers?.[0]?.id ?? ''} key={teachers?.length ?? 0}>
            {teachers?.map((t) => (
              <option key={t.id} value={t.id}>{t.name}{t.department ? ` · ${t.department}` : ''}</option>
            ))}
          </Select>
        </label>
        <div className="grid" style={{ gridTemplateColumns: '1.3fr 1fr 1fr', gap: 10 }}>
          <label className="field"><span>Day</span><input name="day" type="date" className="input" defaultValue={tomorrow} min={format(new Date(), 'yyyy-MM-dd')} required /></label>
          <label className="field"><span>From</span><input name="from" type="time" className="input" defaultValue="14:00" required /></label>
          <label className="field"><span>Until</span><input name="to" type="time" className="input" defaultValue="15:00" required /></label>
        </div>
        <textarea name="note" className="input" maxLength={300} placeholder="Why you need it, e.g. finishing the CSE408 project with my group" />
        <button className="key key-amber" disabled={ask.isPending || !teachers?.length}>
          <ChalkboardTeacher weight="bold" /> {ask.isPending ? 'Sending…' : 'Send request'}
        </button>
      </form>
    </Modal>
  )
}

/** Clicking a slot that's taken: never a dead end. Offers the waitlist, the same time elsewhere, and the next free time here. */
function TakenDrawer({ taken, resource, onClose }: { taken: Taken | null; resource: ResourceDetail; onClose: () => void }) {
  const start = taken?.start.toISOString()
  const end = taken?.end.toISOString()
  const future = !!taken && taken.start > new Date()
  const { data } = useQuery({
    queryKey: ['alternatives', resource.id, start, end],
    queryFn: () => api.get<Alternatives>(`/resources/${resource.id}/alternatives`, { params: { start, end } }).then((r) => r.data),
    enabled: future,
  })
  const watch = useMutation({
    mutationFn: () => api.post(`/resources/${resource.id}/watch`, { start, end }),
    onSuccess: () => toast.success('You’re on the waitlist', { description: 'We’ll notify you the moment this slot opens up.' }),
    onError: (e) => toast.error(errorMessage(e)),
  })
  useEffect(() => watch.reset(), [start]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!taken) return <Drawer open={false} onClose={onClose} title="">{null}</Drawer>
  const heading = taken.kind === 'timetable' ? `Class on: ${taken.label}` : taken.kind === 'maintenance' ? `Maintenance: ${taken.label}` : 'Someone has this slot'
  return (
    <Drawer open onClose={onClose} title="This slot is taken">
      <div className="col" style={{ gap: 16 }}>
        <div className="slot-summary">
          <div className="grow" style={{ minWidth: 0 }}>
            <div className="eyebrow">{format(taken.start, 'EEEE d MMMM')}</div>
            <div className="h2" style={{ marginTop: 4 }}>{heading}</div>
          </div>
          <div className="mono" style={{ fontSize: 18, color: 'var(--brand-ink)', whiteSpace: 'nowrap' }}>{format(taken.start, 'HH:mm')}–{format(taken.end, 'HH:mm')}</div>
        </div>
        {!future && <p className="muted" style={{ margin: 0 }}>This time has already passed.</p>}
        {future && taken.kind === 'booking' && resource.can_book !== false && (
          <button className="key key-amber" disabled={watch.isPending || watch.isSuccess} onClick={() => watch.mutate()}>
            <BellRinging weight="bold" /> {watch.isSuccess ? 'On the waitlist' : 'Tell me if it frees up'}
          </button>
        )}
        {data?.next_free && <p className="muted" style={{ margin: 0, fontSize: 13.5 }}>Next free time in {resource.name}: <strong>{format(new Date(data.next_free), 'EEE d MMM, HH:mm')}</strong></p>}
        {future && (
          <div>
            <div className="eyebrow" style={{ marginBottom: 10 }}>Free at this exact time</div>
            {data && !data.rooms.length && <p className="muted" style={{ margin: 0, fontSize: 13.5 }}>Nothing similar is free then. Try another time.</p>}
            <div className="col" style={{ gap: 8 }}>
              {data?.rooms.map((a) => (
                <Link key={a.id} to={`/resources/${a.id}`} className="alt-room" onClick={onClose}>
                  {a.cover ? <img src={a.cover.replace('w=1200', 'w=160')} alt="" /> : <span className="stripes" />}
                  <span className="grow" style={{ minWidth: 0 }}>
                    <strong className="truncate">{a.name}</strong>
                    <small className="truncate">{a.location_label}</small>
                    <small><UsersThree size={12} /> {a.capacity}{a.requires_approval ? ' · needs approval' : ' · instant'}</small>
                  </span>
                  <ArrowRight size={15} />
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </Drawer>
  )
}

/** Four weeks of real usage, hour by hour, so people can aim for a quiet time. */
function BestTimes({ id }: { id: number }) {
  const { data } = useQuery({
    queryKey: ['insights', id],
    queryFn: () => api.get<{ hours: { hour: number; busy: number }[]; quietest: number | null }>(`/resources/${id}/insights`).then((r) => r.data),
    staleTime: 300_000,
  })
  if (!data?.hours.length) return null
  const peak = Math.max(...data.hours.map((h) => h.busy), 0.01)
  const hh = (h: number) => `${String(h).padStart(2, '0')}:00`
  return (
    <Reveal className="glass pad">
      <div className="eyebrow" style={{ marginBottom: 6 }}>Best time to book</div>
      <p style={{ margin: '0 0 14px', fontSize: 14 }}>
        {data.quietest === null ? 'No bookings in the last four weeks. Take your pick.' : <>Usually quietest around <strong>{hh(data.quietest)}</strong>.</>}
      </p>
      <div className="hour-bars" role="img" aria-label={`How busy each hour was over the last four weeks, quietest around ${data.quietest === null ? 'any time' : hh(data.quietest)}`}>
        {data.hours.map((h) => (
          <span key={h.hour} className={h.hour === data.quietest ? 'quiet' : ''} title={`${hh(h.hour)}: taken ${Math.round(h.busy * 100)}% of days`}>
            <i style={{ height: `${Math.max(6, (h.busy / peak) * 100)}%` }} />
          </span>
        ))}
      </div>
      <div className="hour-axis mono"><span>{hh(data.hours[0].hour)}</span><span>{hh(data.hours[data.hours.length - 1].hour)}</span></div>
    </Reveal>
  )
}

export default function ResourcePage() {
  const { id } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const nav = useNavigate()
  const calRef = useRef<FullCalendar>(null)
  // Same first week FullCalendar opens on, so the hover-prefetch from Explore is a cache hit.
  const [range, setRange] = useState(initialWeek)
  const [slot, setSlot] = useState<{ start: Date; end: Date } | null>(null)
  const [taken, setTaken] = useState<Taken | null>(null)
  const [img, setImg] = useState(0)
  const [report, setReport] = useState(false)
  const [qr, setQr] = useState<string | null>(null)
  const [asking, setAsking] = useState(false)
  const [params, setParams] = useSearchParams()
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 760

  const { data: r, isError } = useQuery({ queryKey: ['resource', id], queryFn: () => api.get<ResourceDetail>(`/resources/${id}`).then((x) => x.data), retry: retryUnlessMissing })
  const { data: av, isFetching } = useQuery({
    queryKey: ['availability', Number(id), range.from, range.to],
    queryFn: () => api.get<Availability>(`/resources/${id}/availability`, { params: range }).then((x) => x.data),
    placeholderData: (p) => p,
  })

  const events = useMemo<EventInput[]>(() => {
    if (!av) return []
    const ev: EventInput[] = av.busy.map((b, i) => ({
      id: `b${i}`,
      start: b.start,
      end: b.end,
      title: b.kind === 'timetable' ? `${b.label}` : b.kind === 'maintenance' ? `${b.label}` : b.mine ? `${b.label}` : b.label,
      classNames: [`ev-${b.kind}`, b.mine ? 'ev-mine' : '', b.status === 'pending' ? 'ev-pending' : ''],
      overlap: false,
      editable: false,
      // Not FullCalendar's `url`: it renders `undefined` as a real href, and the click leaves the app.
      extendedProps: { kind: b.kind, label: b.label, link: b.mine && b.booking_id ? `/bookings/${b.booking_id}` : null },
    }))
    av.blackouts.forEach((b, i) => ev.push({ id: `x${i}`, start: b.start, end: b.end, display: 'background', classNames: ['ev-blackout'], title: b.title, overlap: false }))
    return ev
  }, [av])

  const businessHours = useMemo(
    () => av?.rules.map((r) => ({ daysOfWeek: r.weekdays.map((w) => (w + 1) % 7), startTime: r.open, endTime: r.close })) ?? [],
    [av],
  )
  const rule = av?.rules[0]
  const minTime = av?.rules.reduce((m, r) => (r.open < m ? r.open : m), '23:59') ?? '07:00'
  const maxTime = av?.rules.reduce((m, r) => (r.close > m ? r.close : m), '00:00') ?? '22:00'

  const onSelect = (s: DateSelectArg) => {
    calRef.current?.getApi().unselect()
    if (s.start < new Date()) return toast.error('That time has already passed.')
    const mins = (s.end.getTime() - s.start.getTime()) / 60000
    if (rule && mins > rule.max_duration) return toast.error(`Max ${rule.max_duration / 60}h per booking here.`)
    if (rule && mins < rule.min_duration) {
      const end = new Date(s.start.getTime() + rule.min_duration * 60000)
      return setSlot({ start: s.start, end })
    }
    setSlot({ start: s.start, end: s.end })
  }

  // A teacher arriving from a student's request (?start=…&end=…): open the booking form on that slot.
  useEffect(() => {
    const from = params.get('start')
    const to = params.get('end')
    if (!r || !from || !to) return
    setParams({}, { replace: true })
    const s = new Date(from)
    const e = new Date(to)
    if (r.can_book === false || !(s > new Date() && e > s)) return
    setSlot({ start: s, end: e })
    calRef.current?.getApi().gotoDate(s)
  }, [r]) // eslint-disable-line react-hooks/exhaustive-deps

  const showQr = async () => setQr(await blobUrl(qrPath(`/resources/${id}/qr`)))
  const [maintOpen, setMaintOpen] = useState(false)

  type Window = { id: number; kind: string; title: string; start: string; end: string; status: string; reported_by_name: string | null }
  const { data: windows } = useQuery({
    queryKey: ['maintenance', 'resource', id],
    queryFn: () => api.get<Window[]>('/maintenance', { params: { resource: id, status: 'planned,in_progress' } }).then((x) => x.data),
  })
  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['resource', id] })
    qc.invalidateQueries({ queryKey: ['availability', Number(id)] })
    qc.invalidateQueries({ queryKey: ['maintenance', 'resource', id] })
  }
  const resolveMut = useMutation({
    mutationFn: (wid: number) => api.post(`/maintenance/${wid}/resolve`),
    onSuccess: () => {
      toast.success('Marked repaired — the slot is open for booking again.')
      refreshAll()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const scheduleMut = useMutation({
    mutationFn: (b: { title: string; start: string; end: string; notes: string }) => api.post('/maintenance', { resource: id, ...b }),
    onSuccess: (res) => {
      const n = res.data.displaced_bookings
      toast.success(`Maintenance scheduled${n ? ` — ${n} booking${n > 1 ? 's' : ''} moved off and notified` : ''}`)
      setMaintOpen(false)
      refreshAll()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })

  const reportMut = useMutation({
    mutationFn: (body: { title: string; notes: string }) => api.post('/maintenance/report', { resource: id, ...body, hours: 24 }),
    onSuccess: () => {
      toast.success('Reported — custodians notified and the resource is blocked for repair.')
      setReport(false)
      refreshAll()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })

  if (isError && !r) {
    return (
      <div className="page">
        <Empty title="We can’t find that room.">
          <Link to="/explore" className="key key-amber" style={{ marginTop: 14 }}>Back to the catalogue</Link>
        </Empty>
      </div>
    )
  }
  if (!r) return <div className="page"><Skeleton h={420} /></div>
  const gallery = r.images.length ? r.images.map((i) => i.src) : [r.cover]
  const isCustodian = user?.custodian_of.includes(r.id) || user?.role === 'facility_manager' || user?.role === 'admin'
  // Labs, classrooms, seminar halls and vehicles are for staff. Students can still see when they are free, but not book them.
  const canBook = r.can_book !== false
  const staffOnly = `${r.type_name === 'Laboratory' ? 'Labs' : r.type_name + 's'} are booked by faculty and staff.`

  return (
    <div className="page">
      <Link to="/explore" className="chip" style={{ marginBottom: 18 }}>
        <ArrowLeft size={14} /> Catalogue
      </Link>

      <section className="rhero glass" style={{ '--c': r.type_color } as CSSProperties}>
        <div className="rhero-img">
          {gallery[img] && <img key={gallery[img]} src={gallery[img]} alt={r.name} className="fade-in" />}
          <div className="rhero-shade" />
          <div className="rhero-copy">
            <div className="row wrap" style={{ gap: 8 }}>
              <TypeTag name={r.type_name} color={r.type_color} icon={r.type_icon} />
              {r.status === 'down' ? (
                <span className="tag" style={{ '--c': 'var(--bad)' } as CSSProperties}><Wrench size={12} /> Out of service</span>
              ) : !canBook ? (
                <span className="tag" style={{ '--c': 'var(--fg-3)' } as CSSProperties}><LockSimple size={12} /> Faculty and staff only</span>
              ) : r.requires_approval ? (
                <span className="tag" style={{ '--c': 'var(--brand)' } as CSSProperties}><Stamp size={12} /> Approval required</span>
              ) : (
                <span className="tag" style={{ '--c': 'var(--ok)' } as CSSProperties}><SealCheck size={12} /> Instant booking</span>
              )}
            </div>
            <h1 className="display" style={{ fontSize: 'clamp(40px,5.5vw,76px)', margin: '12px 0 6px' }}>{r.name}</h1>
            <div className="row wrap muted" style={{ gap: 18, fontSize: 14 }}>
              <span className="row" style={{ gap: 6 }}><MapPin size={16} /> {r.location_label}</span>
              <span className="row" style={{ gap: 6 }}><UsersThree size={16} /> {r.capacity} capacity</span>
              <span className="mono" style={{ fontSize: 12 }}>
                <DecryptedText text={r.code} animateOn="view" speed={40} maxIterations={14} />
              </span>
            </div>
            <div className="rhero-actions">
              <SaveButton key={String(r.is_saved)} id={r.id} saved={r.is_saved} labelled />
              <button className="key key-coral key-sm" onClick={() => setReport(true)}>
                <Warning size={15} weight="bold" /> Report breakdown
              </button>
              {isCustodian && (
                <>
                  <button className="key key-ghost key-sm" onClick={() => setMaintOpen(true)}>
                    <Wrench size={15} /> Schedule maintenance
                  </button>
                  <button className="key key-ghost key-sm" onClick={showQr}>
                    <Printer size={15} /> Check-in poster
                  </button>
                </>
              )}
            </div>
          </div>
          {gallery.length > 1 && (
            <div className="rhero-thumbs">
              {gallery.map((g, i) => (
                <button key={g} className={i === img ? 'on' : ''} onClick={() => setImg(i)}>
                  <img src={g} alt="" />
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      {!!windows?.length && (
        <div className="maint-banner glass">
          <Wrench size={22} weight="duotone" color="var(--bad)" />
          <div className="grow" style={{ minWidth: 0 }}>
            {windows.map((w) => (
              <div key={w.id} className="spread" style={{ gap: 10, flexWrap: 'wrap', padding: '4px 0' }}>
                <div>
                  <strong>{w.kind === 'breakdown' ? 'Out of service' : 'Maintenance'}: {w.title}</strong>
                  <div className="mono muted" style={{ fontSize: 12 }}>
                    {format(new Date(w.start), 'EEE d MMM HH:mm')} → {format(new Date(w.end), 'EEE d MMM HH:mm')}
                    {w.reported_by_name ? ` · reported by ${w.reported_by_name}` : ''}
                  </div>
                </div>
                {isCustodian && (
                  <button className="key key-mint key-sm" disabled={resolveMut.isPending} onClick={() => resolveMut.mutate(w.id)}>
                    Mark repaired
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rlayout">
        <Reveal className="glass pad cal-card">
          <div className="spread" style={{ marginBottom: 14, flexWrap: 'wrap' }}>
            <div>
              <div className="h2">{canBook ? 'Pick a slot' : 'When it is free'}</div>
              <div className="muted" style={{ fontSize: 13 }}>
                {canBook ? 'Drag across the free time. Classes, maintenance and other bookings are locked.' : `View only. ${staffOnly}`}
              </div>
              {!canBook && r.status === 'active' && (
                <button className="key key-amber key-sm" style={{ marginTop: 10 }} onClick={() => setAsking(true)}>
                  <ChalkboardTeacher size={15} weight="bold" /> Ask a teacher to book it
                </button>
              )}
            </div>
            <div className="legend">
              <span><i className="lg-free" /> Free</span>
              <span><i className="lg-booking" /> Booked</span>
              <span><i className="lg-timetable" /> Class</span>
              <span><i className="lg-maint" /> Maintenance</span>
              <span><i className="lg-mine" /> Yours</span>
              {isFetching && <span className="led pulse" style={{ '--c': 'var(--brand)' } as CSSProperties} />}
            </div>
          </div>
          <div className="fc-shell" data-lenis-prevent>
            <FullCalendar
              ref={calRef}
              plugins={[timeGridPlugin, interactionPlugin]}
              initialView={isMobile ? 'timeGridDay' : 'timeGridWeek'}
              headerToolbar={{ left: 'prev,next today', center: 'title', right: isMobile ? '' : 'timeGridDay,timeGridWeek' }}
              firstDay={1}
              allDaySlot={false}
              nowIndicator
              selectable={r.status === 'active' && canBook}
              selectMirror
              unselectAuto
              selectOverlap={false}
              selectConstraint="businessHours"
              businessHours={businessHours}
              slotMinTime={minTime}
              slotMaxTime={maxTime}
              slotDuration={`00:${String(av?.slot_minutes === 60 ? 30 : av?.slot_minutes ?? 30).padStart(2, '0')}:00`}
              snapDuration={`00:${String(Math.min(av?.slot_minutes ?? 30, 30)).padStart(2, '0')}:00`}
              height="auto"
              expandRows
              events={events}
              select={onSelect}
              eventClick={(info) => {
                const { link, kind, label } = info.event.extendedProps
                if (link) nav(link)
                else if (kind) setTaken({ kind, label, start: info.event.start!, end: info.event.end! })
              }}
              dateClick={(info) => {
                if (info.date < new Date()) return
                const day = (info.date.getDay() + 6) % 7
                const time = format(info.date, 'HH:mm')
                const open = av?.rules.some((r) => r.weekdays.includes(day) && r.open.slice(0, 5) <= time && time < r.close.slice(0, 5))
                if (!canBook) toast.info('View only', { description: `${staffOnly} Use “Ask a teacher to book it” above.` })
                else if (!open) toast.info('Closed at that time', { description: 'Pick a time inside the white opening hours.' })
              }}
              datesSet={(d) => setRange({ from: format(d.start, 'yyyy-MM-dd'), to: format(d.end, 'yyyy-MM-dd') })}
              eventTimeFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
              slotLabelFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
              dayHeaderFormat={{ weekday: 'short', day: 'numeric' }}
              longPressDelay={250}
              selectLongPressDelay={250}
            />
          </div>
        </Reveal>

        <aside className="col" style={{ gap: 18 }}>
          <BestTimes id={r.id} />
          <Reveal className="glass pad">
            <div className="eyebrow" style={{ marginBottom: 10 }}>About</div>
            <p style={{ margin: '0 0 14px', color: 'var(--fg-2)' }}>{r.description}</p>
            {r.attributes.length > 0 && (
              <dl className="attrs">
                {r.attributes.map((a) => (
                  <div key={a.key}>
                    <dt>{a.key}</dt>
                    <dd>{a.value}</dd>
                  </div>
                ))}
                {r.value_inr > 0 && (
                  <div>
                    <dt>Asset value</dt>
                    <dd>{inr(r.value_inr)}</dd>
                  </div>
                )}
              </dl>
            )}
            <div className="row wrap" style={{ gap: 6, marginTop: 14 }}>
              {r.features.map((f) => (
                <span className="tag" key={f}>{f}</span>
              ))}
            </div>
          </Reveal>

          {rule && (
            <Reveal className="glass pad">
              <div className="eyebrow" style={{ marginBottom: 12 }}>House rules</div>
              <div className="rules-grid">
                {av!.rules.map((x, i) => (
                  <div key={i} className="rule-line">
                    <Clock size={15} />
                    <span>{x.weekdays.length === 7 ? 'Every day' : x.weekdays.map((w) => WEEKDAYS[w]).join(' ')}</span>
                    <span className="mono">{x.open}–{x.close}</span>
                  </div>
                ))}
              </div>
              <div className="rule-chips">
                <span>{rule.min_duration}m – {rule.max_duration / 60}h</span>
                <span>book ≤ {rule.max_advance_days}d ahead</span>
                {rule.min_lead > 0 && <span>≥ {rule.min_lead >= 60 ? `${rule.min_lead / 60}h` : `${rule.min_lead}m`} notice</span>}
                {r.requires_checkin && <span>{av!.policy.grace_minutes}m check-in grace</span>}
              </div>
            </Reveal>
          )}

          <Reveal className="glass pad">
            <div className="eyebrow" style={{ marginBottom: 10 }}>Custodians</div>
            {r.custodian_list.map((c) => (
              <div key={c.id} className="row" style={{ marginBottom: 8 }}>
                <span className="avatar sm">{c.name.split(' ').map((p) => p[0]).join('')}</span>
                <span>{c.name}</span>
              </div>
            ))}
            <div className="row wrap" style={{ marginTop: 12, gap: 8 }}>
              <button className="key key-ghost key-sm" onClick={() => setReport(true)}>
                <Warning size={15} /> Report a fault
              </button>
              {isCustodian && (
                <button className="key key-ghost key-sm" onClick={showQr}>
                  <Printer size={15} /> Check-in poster
                </button>
              )}
            </div>
          </Reveal>
        </aside>
      </div>

      <TakenDrawer taken={taken} resource={r} onClose={() => setTaken(null)} />
      {!canBook && <AskTeacher resource={r} open={asking} onClose={() => setAsking(false)} />}
      <BookingDrawer resource={r} slot={slot} onClose={() => setSlot(null)} />

      <Modal open={maintOpen} onClose={() => setMaintOpen(false)} width={500}>
        <form
          className="col"
          onSubmit={(e) => {
            e.preventDefault()
            const f = new FormData(e.currentTarget)
            scheduleMut.mutate({
              title: String(f.get('title')),
              notes: String(f.get('notes')),
              start: new Date(String(f.get('start'))).toISOString(),
              end: new Date(String(f.get('end'))).toISOString(),
            })
          }}
        >
          <div className="h2">Schedule maintenance</div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            The window is written into the booking ledger. Anyone already booked inside it is moved off and notified.
          </p>
          <input name="title" className="input" placeholder="e.g. Annual calibration" required />
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <label className="field"><span>From</span><input name="start" type="datetime-local" className="input" required /></label>
            <label className="field"><span>Until</span><input name="end" type="datetime-local" className="input" required /></label>
          </div>
          <textarea name="notes" className="input" placeholder="Notes for the team (optional)" />
          <button className="key key-amber" disabled={scheduleMut.isPending}><Wrench /> Block the calendar</button>
        </form>
      </Modal>

      <Modal open={report} onClose={() => setReport(false)}>
        <form
          className="col"
          onSubmit={(e) => {
            e.preventDefault()
            const f = new FormData(e.currentTarget)
            reportMut.mutate({ title: String(f.get('title')), notes: String(f.get('notes')) })
          }}
        >
          <div className="h2">Report a fault</div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            The resource is pulled from booking for 24h and anyone affected is told immediately.
          </p>
          <input name="title" className="input" placeholder="e.g. Projector won’t turn on" required />
          <textarea name="notes" className="input" placeholder="Anything the custodian should know" />
          <button className="key key-coral" disabled={reportMut.isPending}>Report & block</button>
        </form>
      </Modal>

      <Modal open={!!qr} onClose={() => setQr(null)} width={420}>
        <div className="col" style={{ alignItems: 'center', textAlign: 'center' }}>
          <div className="eyebrow">Print & stick at the door</div>
          <div className="display" style={{ fontSize: 30 }}>{r.name}</div>
          <div className="qr-plate" style={{ width: 240 }}>{qr && <img src={qr} alt="check-in QR" />}</div>
          <div className="muted" style={{ fontSize: 13 }}>Bookers scan this within the grace window to check in.</div>
          <button className="key key-amber" onClick={() => window.print()}><Printer /> Print</button>
        </div>
      </Modal>
    </div>
  )
}
