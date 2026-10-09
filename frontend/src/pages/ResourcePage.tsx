import type { DateSelectArg, EventInput } from '@fullcalendar/core'
import interactionPlugin from '@fullcalendar/interaction'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import {
  ArrowLeft,
  CalendarPlus,
  Clock,
  MapPin,
  Printer,
  Repeat,
  SealCheck,
  Stamp,
  UsersThree,
  Warning,
  Wrench,
} from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addDays, format } from 'date-fns'
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Reveal } from '../components/motion'
import DecryptedText from '../components/reactbits/DecryptedText'
import { Drawer, Modal, Skeleton, TypeTag } from '../components/ui'
import { api, blobUrl, errorCode, errorDetails, errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { durationLabel, inr, WEEKDAYS } from '../lib/format'
import type { Availability, Booking, ResourceDetail } from '../lib/types'

type Consumable = { id: number; name: string; kind: string; unit: string; stock: number }

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
          on_behalf_of: onBehalf,
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
                <Warning color="var(--coral)" /> <strong>Skipped — clashes handled per date</strong>
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
              <div className="mono" style={{ fontSize: 22, color: 'var(--amber-hi)' }}>
                {format(slot.start, 'HH:mm')}–{format(slot.end, 'HH:mm')}
              </div>
              <div className="eyebrow">{durationLabel(slot.start.toISOString(), slot.end.toISOString())}</div>
            </div>
          </div>
          {resource.requires_approval && (
            <div className="notice">
              <Stamp size={18} color="var(--amber)" /> This needs approval. The slot is held for you the moment you submit.
            </div>
          )}
          <label className="field">
            <span>What’s it for?</span>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Capstone model training" maxLength={160} required />
          </label>
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <label className="field">
              <span>People (max {resource.capacity})</span>
              <input className="input" type="number" min={1} max={resource.capacity} value={attendees} onChange={(e) => setAttendees(Number(e.target.value))} />
            </label>
            {user?.can_book_recurring && (
              <label className="field">
                <span>On behalf of class</span>
                <input className="input" value={onBehalf} onChange={(e) => setOnBehalf(e.target.value)} placeholder="K22CS-B" />
              </label>
            )}
          </div>
          <label className="field">
            <span>Notes for the custodian (optional)</span>
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
                  <Repeat size={18} color="var(--sky)" />
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
                      <select className="input" value={policy} onChange={(e) => setPolicy(e.target.value as 'skip' | 'abort')}>
                        <option value="skip">Skip that date, book the rest</option>
                        <option value="abort">Book nothing (all or nothing)</option>
                      </select>
                    </label>
                  </div>
                </div>
              )}
            </div>
          )}

          <button className="key key-amber key-lg" disabled={book.isPending}>
            <CalendarPlus weight="bold" />
            {book.isPending ? 'Claiming slot…' : resource.requires_approval ? 'Request booking' : recurring ? `Book ${count} weeks` : 'Confirm booking'}
          </button>
          <p className="muted" style={{ fontSize: 12, margin: 0, textAlign: 'center' }}>
            {resource.requires_checkin ? 'Scan the room QR within the grace period after start, or the slot auto-releases.' : 'No check-in needed for this resource.'}
          </p>
        </form>
      )}
    </Drawer>
  )
}

export default function ResourcePage() {
  const { id } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const nav = useNavigate()
  const calRef = useRef<FullCalendar>(null)
  const [range, setRange] = useState(() => {
    const s = new Date()
    return { from: format(s, 'yyyy-MM-dd'), to: format(addDays(s, 7), 'yyyy-MM-dd') }
  })
  const [slot, setSlot] = useState<{ start: Date; end: Date } | null>(null)
  const [img, setImg] = useState(0)
  const [report, setReport] = useState(false)
  const [qr, setQr] = useState<string | null>(null)
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 760

  const { data: r } = useQuery({ queryKey: ['resource', id], queryFn: () => api.get<ResourceDetail>(`/resources/${id}`).then((x) => x.data) })
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
      title: b.kind === 'timetable' ? `🎓 ${b.label}` : b.kind === 'maintenance' ? `🔧 ${b.label}` : b.mine ? `★ ${b.label}` : b.label,
      classNames: [`ev-${b.kind}`, b.mine ? 'ev-mine' : '', b.status === 'pending' ? 'ev-pending' : ''],
      overlap: false,
      editable: false,
      url: b.mine && b.booking_id ? `/bookings/${b.booking_id}` : undefined,
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

  const showQr = async () => setQr(await blobUrl(`/resources/${id}/qr`))

  const reportMut = useMutation({
    mutationFn: (body: { title: string; notes: string }) => api.post('/maintenance/report', { resource: id, ...body, hours: 24 }),
    onSuccess: () => {
      toast.success('Reported — custodians notified and the resource is blocked for repair.')
      setReport(false)
      qc.invalidateQueries({ queryKey: ['resource', id] })
      qc.invalidateQueries({ queryKey: ['availability', Number(id)] })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })

  if (!r) return <div className="page"><Skeleton h={420} /></div>
  const gallery = r.images.length ? r.images.map((i) => i.src) : [r.cover]
  const isCustodian = user?.custodian_of.includes(r.id) || user?.role === 'facility_manager' || user?.role === 'admin'

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
                <span className="tag" style={{ '--c': 'var(--coral)' } as CSSProperties}><Wrench size={12} /> Out of service</span>
              ) : r.requires_approval ? (
                <span className="tag" style={{ '--c': 'var(--amber)' } as CSSProperties}><Stamp size={12} /> Approval required</span>
              ) : (
                <span className="tag" style={{ '--c': 'var(--mint)' } as CSSProperties}><SealCheck size={12} /> Instant booking</span>
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

      <div className="rlayout">
        <Reveal className="glass pad cal-card">
          <div className="spread" style={{ marginBottom: 14, flexWrap: 'wrap' }}>
            <div>
              <div className="h2">Pick a slot</div>
              <div className="muted" style={{ fontSize: 13 }}>Drag across the free time. Classes, maintenance and other bookings are locked.</div>
            </div>
            <div className="legend">
              <span><i className="lg-free" /> Free</span>
              <span><i className="lg-booking" /> Booked</span>
              <span><i className="lg-timetable" /> Class</span>
              <span><i className="lg-maint" /> Maintenance</span>
              <span><i className="lg-mine" /> Yours</span>
              {isFetching && <span className="led pulse" style={{ '--c': 'var(--amber)' } as CSSProperties} />}
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
              selectable={r.status === 'active'}
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
                if (info.event.url) {
                  info.jsEvent.preventDefault()
                  nav(info.event.url)
                }
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
          <Reveal className="glass pad">
            <div className="eyebrow" style={{ marginBottom: 10 }}>About</div>
            <p style={{ margin: '0 0 14px', color: 'var(--paper-dim)' }}>{r.description}</p>
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

      <BookingDrawer resource={r} slot={slot} onClose={() => setSlot(null)} />

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
