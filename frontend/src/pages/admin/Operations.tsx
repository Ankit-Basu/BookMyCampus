import { ArrowCounterClockwise, CheckCircle, Package, Plus, UploadSimple, Wrench, X } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { useState, type CSSProperties } from 'react'
import { toast } from 'sonner'

import { Meter, Modal, StatusTag } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { isPolicyAdmin, useAuth } from '../../lib/auth'
import { fmtRelative, WEEKDAYS } from '../../lib/format'
import type { Resource } from '../../lib/types'

type Tab = 'maintenance' | 'consumables' | 'noshows' | 'timetable'

function useAct(keys: string[], msg: string) {
  const qc = useQueryClient()
  return {
    onSuccess: () => {
      keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      toast.success(msg)
    },
    onError: (e: unknown) => toast.error(errorMessage(e)),
  }
}

function Maintenance() {
  const { data } = useQuery({ queryKey: ['maintenance'], queryFn: () => api.get('/maintenance').then((r) => r.data) })
  const { data: resources } = useQuery({ queryKey: ['resources', 'admin-min'], queryFn: () => api.get<Resource[]>('/resources').then((r) => r.data) })
  const [f, setF] = useState({ resource: '', title: '', start: '', end: '', notes: '' })
  const create = useMutation({ mutationFn: () => api.post('/maintenance', { ...f, start: new Date(f.start).toISOString(), end: new Date(f.end).toISOString() }).then((r) => r.data), ...useAct(['maintenance'], 'Scheduled — affected bookers notified') })
  const act = useMutation({ mutationFn: ({ id, a }: { id: number; a: string }) => api.post(`/maintenance/${id}/${a}`), ...useAct(['maintenance'], 'Updated') })
  return (
    <div className="col" style={{ gap: 18 }}>
      <form className="glass pad" onSubmit={(e) => { e.preventDefault(); create.mutate() }}>
        <div className="h2" style={{ marginBottom: 4 }}>Schedule maintenance</div>
        <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>The window is written into the booking ledger; overlapping bookings are displaced and their owners told.</div>
        <div className="maint-form">
          <select className="input" value={f.resource} onChange={(e) => setF({ ...f, resource: e.target.value })} required>
            <option value="">Resource…</option>
            {resources?.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.name}</option>)}
          </select>
          <input className="input" placeholder="What’s being done" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required />
          <input className="input" type="datetime-local" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} required />
          <input className="input" type="datetime-local" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} required />
          <button className="key key-amber" disabled={create.isPending}><Wrench /> Schedule</button>
        </div>
      </form>
      <div className="glass pad">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Resource</th><th>Work</th><th>Window</th><th>Kind</th><th>Status</th><th>Displaced</th><th /></tr></thead>
            <tbody>
              {data?.map((m: { id: number; resource_name: string; resource_code: string; title: string; start: string; end: string; kind: string; status: string; displaced_bookings: number; reported_by_name: string | null }) => (
                <tr key={m.id}>
                  <td><strong>{m.resource_name}</strong><div className="mono muted" style={{ fontSize: 11 }}>{m.resource_code}</div></td>
                  <td>{m.title}<div className="muted" style={{ fontSize: 12 }}>{m.reported_by_name}</div></td>
                  <td className="mono" style={{ fontSize: 12 }}>{format(new Date(m.start), 'd MMM HH:mm')} → {format(new Date(m.end), 'd MMM HH:mm')}</td>
                  <td><span className="tag" style={{ '--c': m.kind === 'breakdown' ? 'var(--coral)' : 'var(--sky)' } as CSSProperties}>{m.kind}</span></td>
                  <td><StatusTag status={m.status === 'done' ? 'completed' : m.status === 'in_progress' ? 'checked_in' : m.status === 'cancelled' ? 'cancelled' : 'confirmed'} label={m.status.replace('_', ' ')} /></td>
                  <td className="mono">{m.displaced_bookings}</td>
                  <td>
                    {['planned', 'in_progress'].includes(m.status) && (
                      <div className="row" style={{ gap: 6 }}>
                        <button className="key key-mint key-sm" onClick={() => act.mutate({ id: m.id, a: 'resolve' })}><CheckCircle /> Resolve</button>
                        <button className="key key-ghost key-sm key-icon" title="Cancel" onClick={() => act.mutate({ id: m.id, a: 'cancel' })}><X size={14} /></button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function Consumables() {
  const { data } = useQuery({ queryKey: ['consumables'], queryFn: () => api.get('/consumables').then((r) => r.data) })
  const { data: open } = useQuery({ queryKey: ['issuances'], queryFn: () => api.get('/issuances', { params: { open: 1 } }).then((r) => r.data) })
  const restock = useMutation({ mutationFn: ({ id, q }: { id: number; q: number }) => api.post(`/consumables/${id}/restock`, { quantity: q }), ...useAct(['consumables'], 'Restocked') })
  const ret = useMutation({ mutationFn: (id: number) => api.post(`/issuances/${id}/return`), ...useAct(['issuances', 'consumables'], 'Returned to stock') })
  type C = { id: number; name: string; sku: string; kind: string; unit: string; stock: number; reorder_level: number; is_low: boolean; resource_name: string | null; resource_type_name: string | null; issued_out: number }
  return (
    <div className="col" style={{ gap: 18 }}>
      <div className="stock-grid">
        {data?.map((c: C) => (
          <div key={c.id} className={`glass pad stock-card ${c.is_low ? 'low' : ''}`}>
            <div className="spread" style={{ alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <div className="h3 truncate">{c.name}</div>
                <div className="muted truncate" style={{ fontSize: 12 }}>{c.resource_name ?? c.resource_type_name ?? 'General'} · {c.kind}</div>
              </div>
              {c.is_low && <span className="tag" style={{ '--c': 'var(--coral)' } as CSSProperties}>Low</span>}
            </div>
            <div className="row" style={{ alignItems: 'baseline', gap: 6, margin: '12px 0 8px' }}>
              <span className="display" style={{ fontSize: 40 }}>{c.stock}</span>
              <span className="muted">{c.unit}</span>
              {c.issued_out > 0 && <span className="mono muted" style={{ fontSize: 11, marginLeft: 'auto' }}>{c.issued_out} out</span>}
            </div>
            <Meter value={Math.min(1, c.stock / Math.max(c.reorder_level * 3, 1))} c1={c.is_low ? '#7a1f12' : undefined} c2={c.is_low ? '#ff6f59' : undefined} />
            <div className="spread" style={{ marginTop: 12 }}>
              <span className="mono muted" style={{ fontSize: 11 }}>reorder at {c.reorder_level}</span>
              <button className="key key-ghost key-sm" onClick={() => { const q = Number(prompt(`Restock ${c.name} — how many ${c.unit}?`, '10')); if (q > 0) restock.mutate({ id: c.id, q }) }}>
                <Plus /> Restock
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="glass pad">
        <div className="h2" style={{ marginBottom: 10 }}>Out with bookers</div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Item</th><th>Qty</th><th>With</th><th>Booking</th><th>Issued</th><th /></tr></thead>
            <tbody>
              {open?.length ? open.map((i: { id: number; consumable_name: string; quantity: number; unit: string; user_name: string; booking_reference: string | null; issued_at: string; consumable_kind: string }) => (
                <tr key={i.id}>
                  <td><Package size={14} /> {i.consumable_name}</td>
                  <td className="mono">{i.quantity} {i.unit}</td>
                  <td>{i.user_name}</td>
                  <td className="mono">{i.booking_reference ?? '—'}</td>
                  <td className="muted">{fmtRelative(i.issued_at)}</td>
                  <td><button className="key key-ghost key-sm" onClick={() => ret.mutate(i.id)}><ArrowCounterClockwise /> {i.consumable_kind === 'accessory' ? 'Returned' : 'Unused back'}</button></td>
                </tr>
              )) : <tr><td colSpan={6} className="muted">Nothing issued right now.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function NoShows() {
  const { data } = useQuery({ queryKey: ['noshows'], queryFn: () => api.get('/noshows').then((r) => r.data) })
  const { data: restricted } = useQuery({ queryKey: ['restricted'], queryFn: () => api.get('/users/restricted').then((r) => r.data) })
  const waive = useMutation({ mutationFn: (id: number) => api.post(`/noshows/${id}/waive`, { reason: 'Waived by manager' }), ...useAct(['noshows', 'restricted'], 'Strike waived') })
  const lift = useMutation({ mutationFn: (id: number) => api.post(`/users/${id}/lift-restriction`), ...useAct(['restricted'], 'Restriction lifted') })
  return (
    <div className="two-col" style={{ alignItems: 'start' }}>
      <div className="glass pad">
        <div className="h2" style={{ marginBottom: 10 }}>Recent no-shows</div>
        <div className="table-wrap" data-lenis-prevent style={{ maxHeight: 520, overflowY: 'auto' }}>
          <table className="table">
            <thead><tr><th>Person</th><th>Resource</th><th>When</th><th /></tr></thead>
            <tbody>
              {data?.slice(0, 60).map((n: { id: number; user_name: string; resource_name: string; booking_start: string; waived: boolean }) => (
                <tr key={n.id} style={{ opacity: n.waived ? 0.45 : 1 }}>
                  <td>{n.user_name}</td>
                  <td>{n.resource_name}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{format(new Date(n.booking_start), 'd MMM HH:mm')}</td>
                  <td>{n.waived ? <span className="muted">waived</span> : <button className="key key-ghost key-sm" onClick={() => waive.mutate(n.id)}>Waive</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="glass pad">
        <div className="h2" style={{ marginBottom: 10 }}>Booking paused</div>
        {restricted?.length ? restricted.map((u: { id: number; name: string; department_code: string; restricted_until: string; restriction_reason: string }) => (
          <div key={u.id} className="spread list-row">
            <div>
              <strong>{u.name}</strong> <span className="muted">· {u.department_code}</span>
              <div className="muted" style={{ fontSize: 12 }}>{u.restriction_reason} · until {format(new Date(u.restricted_until), 'EEE d MMM')}</div>
            </div>
            <button className="key key-mint key-sm" onClick={() => lift.mutate(u.id)}>Lift</button>
          </div>
        )) : <div className="muted">Nobody is restricted.</div>}
      </div>
    </div>
  )
}

function Timetable() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['timetable'], queryFn: () => api.get('/timetable/current').then((r) => r.data) })
  const [json, setJson] = useState('')
  const [open, setOpen] = useState(false)
  const publish = useMutation({
    mutationFn: () => api.post('/timetable/publish', JSON.parse(json)).then((r) => r.data),
    onSuccess: (d) => {
      toast.success(d.changed ? `Published · ${d.version.displaced_bookings} booking(s) displaced` : 'Identical to current timetable — nothing changed')
      qc.invalidateQueries({ queryKey: ['timetable'] })
      setOpen(false)
    },
    onError: (e) => toast.error(e instanceof SyntaxError ? 'That isn’t valid JSON' : errorMessage(e)),
  })
  const v = data?.version
  return (
    <div className="col" style={{ gap: 18 }}>
      <div className="glass pad spread" style={{ flexWrap: 'wrap' }}>
        <div>
          <div className="eyebrow">Published timetable (from P13)</div>
          <div className="h2" style={{ marginTop: 4 }}>{v?.label ?? 'None published'}</div>
          {v && <div className="mono muted" style={{ fontSize: 12 }}>{v.entries} classes · term {v.term_start} → {v.term_end} · source {v.source} · {fmtRelative(v.published_at)}</div>}
        </div>
        {isPolicyAdmin(user) && <button className="key key-amber" onClick={() => setOpen(true)}><UploadSimple /> Republish</button>}
      </div>
      <div className="glass pad">
        <div className="table-wrap" data-lenis-prevent style={{ maxHeight: 520, overflowY: 'auto' }}>
          <table className="table">
            <thead><tr><th>Room</th><th>Day</th><th>Time</th><th>Course</th><th>Section</th><th>Faculty</th></tr></thead>
            <tbody>
              {data?.entries.map((e: { id: number; resource_code: string; weekday: number; start_time: string; end_time: string; course_code: string; course_name: string; section: string; faculty_name: string }) => (
                <tr key={e.id}>
                  <td className="mono">{e.resource_code}</td>
                  <td>{WEEKDAYS[e.weekday]}</td>
                  <td className="mono">{e.start_time.slice(0, 5)}–{e.end_time.slice(0, 5)}</td>
                  <td><strong>{e.course_code}</strong> <span className="muted">{e.course_name}</span></td>
                  <td className="mono">{e.section}</td>
                  <td className="muted">{e.faculty_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} width={720}>
        <div className="col">
          <div className="h2">Republish timetable</div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Paste the P13 payload. The whole set is swapped atomically; bookings that now collide with a class are displaced and their owners notified. P13 can also POST here with the <span className="mono">X-Timetable-Token</span> header.
          </p>
          <textarea
            className="input mono"
            style={{ minHeight: 240, fontSize: 12 }}
            value={json}
            onChange={(e) => setJson(e.target.value)}
            placeholder={`{"label":"Term v4","term_start":"2026-08-01","term_end":"2026-12-15","entries":[{"resource_code":"CR-34-201","weekday":0,"start":"09:00","end":"09:50","course_code":"CSE326","section":"K22CS"}]}`}
          />
          <button className="key key-amber" disabled={!json || publish.isPending} onClick={() => publish.mutate()}>Publish</button>
        </div>
      </Modal>
    </div>
  )
}

export default function Operations({ initial }: { initial?: Tab }) {
  const fromPath = (window.location.pathname.split('/')[3] as Tab) || undefined
  const [tab, setTab] = useState<Tab>(initial ?? fromPath ?? 'maintenance')
  const tabs: [Tab, string][] = [['maintenance', 'Maintenance'], ['consumables', 'Consumables'], ['noshows', 'No-show monitor'], ['timetable', 'Timetable']]
  return (
    <div className="col" style={{ gap: 18 }}>
      <div className="seg sm">
        {tabs.map(([k, l]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      {tab === 'maintenance' && <Maintenance />}
      {tab === 'consumables' && <Consumables />}
      {tab === 'noshows' && <NoShows />}
      {tab === 'timetable' && <Timetable />}
    </div>
  )
}
