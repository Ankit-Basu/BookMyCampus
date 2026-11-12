import { Megaphone, PaperPlaneTilt, Warning } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { useState, type CSSProperties } from 'react'
import { toast } from 'sonner'

import { Skeleton } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { fmtRelative } from '../../lib/format'

type Overview = {
  department: { code: string; name: string }
  counts: { faculty: number; students: number; bookings_this_week: number; noshows_30d: number }
  faculty: { id: number; name: string; role: string; classes_per_week: number; teaching_hours: number; upcoming_bookings: number; makeups_30d: number; noshows_30d: number }[]
  students_to_watch: { id: number; name: string; username: string; noshows_30d: number; restricted_until: string | null }[]
}
type Notice = { id: number; audience: string; audience_label: string; title: string; body: string; recipients: number; author: string | null; created_at: string }

const AUDIENCES = [
  { v: 'everyone', l: 'Everyone' },
  { v: 'faculty', l: 'Faculty' },
  { v: 'students', l: 'Students' },
]

function SendNotice({ dept }: { dept: string }) {
  const qc = useQueryClient()
  const [audience, setAudience] = useState('everyone')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const { data: sent } = useQuery({ queryKey: ['dept-notices'], queryFn: () => api.get<Notice[]>('/department/notices').then((r) => r.data) })
  const send = useMutation({
    mutationFn: () => api.post<Notice>('/department/notices', { audience, title, body }).then((r) => r.data),
    onSuccess: (n) => {
      toast.success(`Sent to ${n.recipients} ${n.recipients === 1 ? 'person' : 'people'}`)
      setTitle('')
      setBody('')
      qc.invalidateQueries({ queryKey: ['dept-notices'] })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <section className="glass pad col" style={{ gap: 12 }}>
      <div className="row" style={{ gap: 10 }}>
        <Megaphone size={22} weight="duotone" color="var(--brand)" />
        <div className="h2">Send a notice to {dept}</div>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>It appears in their notifications straight away, e.g. a lab closing or a room change.</p>
      <form className="col" style={{ gap: 10 }} onSubmit={(e) => { e.preventDefault(); send.mutate() }}>
        <div className="row wrap" style={{ gap: 8 }} role="group" aria-label="Who it's for">
          {AUDIENCES.map((a) => (
            <button type="button" key={a.v} className={`chip ${audience === a.v ? 'on' : ''}`} onClick={() => setAudience(a.v)}>{a.l}</button>
          ))}
        </div>
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required placeholder="Title, e.g. AI Lab closed on Friday" />
        <textarea className="input" value={body} onChange={(e) => setBody(e.target.value)} maxLength={500} placeholder="Details (optional), e.g. GPU servers are being upgraded. Use the Networks Lab instead." />
        <button className="key key-amber" disabled={send.isPending || !title.trim()}>
          <PaperPlaneTilt weight="bold" /> {send.isPending ? 'Sending…' : 'Send notice'}
        </button>
      </form>
      {!!sent?.length && (
        <div className="col" style={{ gap: 6, marginTop: 4 }}>
          <div className="eyebrow">Sent</div>
          {sent.slice(0, 5).map((n) => (
            <div key={n.id} className="teach-row" style={{ padding: '8px 12px' }}>
              <div className="grow" style={{ minWidth: 0 }}>
                <strong className="truncate" style={{ display: 'block' }}>{n.title}</strong>
                <span className="muted" style={{ fontSize: 12.5 }}>{n.audience_label} · {n.recipients} people · {fmtRelative(n.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

/** The HOD's view of their own department: teaching load, students who need a word, and notices. */
export default function Department() {
  const { data } = useQuery({ queryKey: ['dept-overview'], queryFn: () => api.get<Overview>('/department/overview').then((r) => r.data) })
  if (!data) return <Skeleton h={420} />
  const tiles = [
    { l: 'Faculty', v: data.counts.faculty },
    { l: 'Students', v: data.counts.students },
    { l: 'Bookings this week', v: data.counts.bookings_this_week },
    { l: 'No-shows, last 30 days', v: data.counts.noshows_30d, bad: data.counts.noshows_30d > 0 },
  ]
  return (
    <div className="col" style={{ gap: 18 }}>
      <div>
        <div className="eyebrow">{data.department.code}</div>
        <div className="h2" style={{ fontSize: 24 }}>{data.department.name}</div>
      </div>
      <div className="dept-tiles">
        {tiles.map((t) => (
          <div key={t.l} className="glass pad">
            <div className="display" style={{ fontSize: 32, color: t.bad ? 'var(--bad)' : undefined }}>{t.v}</div>
            <div className="muted" style={{ fontSize: 13 }}>{t.l}</div>
          </div>
        ))}
      </div>

      <div className="teach-layout">
        <section className="glass pad col" style={{ gap: 10, minWidth: 0 }}>
          <div className="h2">Faculty workload</div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>Timetabled classes each week, plus their own bookings. Make-up classes are bookings made for a class.</p>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Classes / week</th><th>Hours</th><th>Booked, next 7 days</th><th>Make-ups, 30 days</th><th>No-shows</th></tr>
              </thead>
              <tbody>
                {data.faculty.map((f) => (
                  <tr key={f.id}>
                    <td><strong>{f.name}</strong>{f.role === 'dept_head' && <span className="muted"> · HOD</span>}</td>
                    <td className="mono">{f.classes_per_week}</td>
                    <td className="mono">{f.teaching_hours}h</td>
                    <td className="mono">{f.upcoming_bookings}</td>
                    <td className="mono">{f.makeups_30d}</td>
                    <td className="mono" style={{ color: f.noshows_30d ? 'var(--bad)' : undefined }}>{f.noshows_30d}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <SendNotice dept={data.department.code} />
      </div>

      <section className="glass pad col" style={{ gap: 10 }}>
        <div className="row" style={{ gap: 10 }}>
          <Warning size={20} weight="duotone" color="var(--bad)" />
          <div className="h2">Students to watch</div>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Students who missed check-ins in the last 30 days, or whose booking is paused. Waive a no-show from Operations, No-show monitor.</p>
        {!data.students_to_watch.length && <p className="muted" style={{ margin: 0 }}>Nobody. Everyone checked in.</p>}
        <div className="dept-students">
          {data.students_to_watch.map((s) => (
            <div key={s.id} className="teach-row" style={{ '--c': 'var(--bad)' } as CSSProperties}>
              <div className="grow" style={{ minWidth: 0 }}>
                <strong>{s.name}</strong> <span className="muted mono" style={{ fontSize: 11.5 }}>{s.username}</span>
                <div className="muted" style={{ fontSize: 12.5 }}>
                  {s.noshows_30d} no-show{s.noshows_30d === 1 ? '' : 's'}
                  {s.restricted_until ? ` · paused until ${format(new Date(s.restricted_until), 'd MMM')}` : ''}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
