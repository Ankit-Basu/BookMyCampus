import { ArrowDown, ArrowRight, ArrowUp, Plus, Trash } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { useState, type CSSProperties } from 'react'
import { toast } from 'sonner'

import { Drawer } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { isPolicyAdmin, useAuth } from '../../lib/auth'
import { ROLE_LABEL, WEEKDAYS } from '../../lib/format'

type Type = { id: number; name: string; color: string }
type Step = { name: string; approver_role: string; sla_hours: number }
type Workflow = { id: number; name: string; resource_type: number; resource_type_name: string; requester_roles: string[]; is_active: boolean; priority: number; steps: (Step & { id: number; order: number })[] }
type Draft = Omit<Partial<Workflow>, 'steps'> & { steps: Step[] }
type Rule = { id: number; target: string; resource_type: number | null; name: string; weekdays: number[]; open_time: string; close_time: string; min_duration_minutes: number; max_duration_minutes: number; min_lead_minutes: number; max_advance_days: number; slot_minutes: number }
type Blackout = { id: number; title: string; start: string; end: string; scope: string }
type Quota = { id: number; label: string; department: number | null; role: string; resource_type: number | null; department_hours_per_week: number; user_hours_per_week: number; max_active_bookings: number }

const REQUESTER_ROLES = ['student', 'faculty', 'staff', 'custodian', 'dept_head']
const APPROVER_ROLES = [
  { v: 'custodian', l: 'Resource custodian' },
  { v: 'dept_head', l: 'Department head' },
  { v: 'facility_manager', l: 'Facility manager' },
]

function useCrud<T>(key: string, path: string) {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: [key], queryFn: () => api.get<T[]>(path).then((r) => r.data) })
  const opts = {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [key] })
      toast.success('Saved')
    },
    onError: (e: unknown) => toast.error(errorMessage(e)),
  }
  const create = useMutation({ mutationFn: (b: object) => api.post(path, b), ...opts })
  const update = useMutation({ mutationFn: ({ id, ...b }: { id: number } & Record<string, unknown>) => api.patch(`${path}/${id}`, b), ...opts })
  const remove = useMutation({ mutationFn: (id: number) => api.delete(`${path}/${id}`), ...opts })
  return { list, create, update, remove }
}

function WorkflowBuilder({ types }: { types: Type[] }) {
  const { list, create, update, remove } = useCrud<Workflow>('workflows', '/workflows')
  const [draft, setDraft] = useState<Draft | null>(null)
  const open = (w?: Workflow) => setDraft(w ? { ...w, steps: w.steps.map(({ name, approver_role, sla_hours }) => ({ name, approver_role, sla_hours })) } : { name: '', resource_type: types[0]?.id, requester_roles: [], is_active: true, priority: 0, steps: [{ name: 'Custodian check', approver_role: 'custodian', sla_hours: 24 }] })
  const move = (i: number, d: number) => {
    if (!draft) return
    const s = [...draft.steps]
    ;[s[i], s[i + d]] = [s[i + d], s[i]]
    setDraft({ ...draft, steps: s })
  }
  const save = () => {
    if (!draft) return
    const body = { name: draft.name, resource_type: draft.resource_type, requester_roles: draft.requester_roles, is_active: draft.is_active, priority: draft.priority, steps: draft.steps }
    if (draft.id) update.mutate({ id: draft.id, ...body }, { onSuccess: () => setDraft(null) })
    else create.mutate(body, { onSuccess: () => setDraft(null) })
  }
  return (
    <section className="glass pad">
      <div className="spread" style={{ marginBottom: 16 }}>
        <div>
          <div className="h2">Approval workflows</div>
          <div className="muted" style={{ fontSize: 13 }}>Live the moment you save — no deployment. Highest priority match wins.</div>
        </div>
        <button className="key key-amber" onClick={() => open()}><Plus weight="bold" /> New workflow</button>
      </div>
      <div className="col" style={{ gap: 12 }}>
        {list.data?.map((w) => (
          <div key={w.id} className={`wf-row ${w.is_active ? '' : 'off'}`} style={{ '--c': types.find((t) => t.id === w.resource_type)?.color } as CSSProperties}>
            <div className="wf-head">
              <div className="h3">{w.name}</div>
              <div className="muted" style={{ fontSize: 12 }}>
                {w.resource_type_name} · {w.requester_roles.length ? w.requester_roles.map((r) => ROLE_LABEL[r]).join(', ') : 'everyone'} {w.priority ? `· priority ${w.priority}` : ''}
              </div>
            </div>
            <div className="wf-chain">
              <span className="wf-node start">Request</span>
              {w.steps.map((s) => (
                <span key={s.id} className="row" style={{ gap: 6 }}>
                  <ArrowRight size={14} className="muted" />
                  <span className="wf-node">{s.name}<small>{ROLE_LABEL[s.approver_role]}</small></span>
                </span>
              ))}
              <ArrowRight size={14} className="muted" />
              <span className="wf-node end">Confirmed</span>
            </div>
            <div className="row" style={{ gap: 6 }}>
              <button className={`rocker ${w.is_active ? 'on' : ''}`} onClick={() => update.mutate({ id: w.id, is_active: !w.is_active })} title="Active" />
              <button className="key key-ghost key-sm" onClick={() => open(w)}>Edit</button>
            </div>
          </div>
        ))}
      </div>
      <Drawer open={!!draft} onClose={() => setDraft(null)} title={draft?.id ? 'Edit workflow' : 'New workflow'} width={560}>
        {draft && (
          <div className="col" style={{ gap: 14 }}>
            <label className="field"><span>Name</span><input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <div className="grid" style={{ gridTemplateColumns: '2fr 1fr', gap: 12 }}>
              <label className="field"><span>Resource type</span>
                <select className="input" value={draft.resource_type} onChange={(e) => setDraft({ ...draft, resource_type: Number(e.target.value) })}>{types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
              </label>
              <label className="field"><span>Priority</span><input className="input" type="number" value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) })} /></label>
            </div>
            <div className="field">
              <span>Applies to requesters (none = everyone)</span>
              <div className="row wrap" style={{ gap: 6 }}>
                {REQUESTER_ROLES.map((r) => (
                  <button type="button" key={r} className={`chip ${draft.requester_roles?.includes(r) ? 'on' : ''}`} onClick={() => setDraft({ ...draft, requester_roles: draft.requester_roles?.includes(r) ? draft.requester_roles.filter((x) => x !== r) : [...(draft.requester_roles ?? []), r] })}>
                    {ROLE_LABEL[r]}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <span>Steps, in order</span>
              <div className="col" style={{ gap: 8 }}>
                {draft.steps.map((s, i) => (
                  <div key={i} className="step-edit">
                    <span className="mono step-n">{i + 1}</span>
                    <input className="input" value={s.name} onChange={(e) => setDraft({ ...draft, steps: draft.steps.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
                    <select className="input" value={s.approver_role} onChange={(e) => setDraft({ ...draft, steps: draft.steps.map((x, j) => (j === i ? { ...x, approver_role: e.target.value } : x)) })}>
                      {APPROVER_ROLES.map((r) => <option key={r.v} value={r.v}>{r.l}</option>)}
                    </select>
                    <div className="row" style={{ gap: 4 }}>
                      <button type="button" className="key key-ghost key-sm key-icon" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={14} /></button>
                      <button type="button" className="key key-ghost key-sm key-icon" disabled={i === draft.steps.length - 1} onClick={() => move(i, 1)}><ArrowDown size={14} /></button>
                      <button type="button" className="key key-ghost key-sm key-icon" onClick={() => setDraft({ ...draft, steps: draft.steps.filter((_, j) => j !== i) })}><Trash size={14} /></button>
                    </div>
                  </div>
                ))}
                <button type="button" className="key key-ghost key-sm" onClick={() => setDraft({ ...draft, steps: [...draft.steps, { name: 'Facility manager', approver_role: 'facility_manager', sla_hours: 24 }] })}>
                  <Plus /> Add step
                </button>
              </div>
            </div>
            <div className="row">
              {draft.id && <button className="key key-coral" onClick={() => { remove.mutate(draft.id!); setDraft(null) }}><Trash /> Delete</button>}
              <div className="grow" />
              <button className="key key-amber" onClick={save} disabled={!draft.name || !draft.steps.length}>Save workflow</button>
            </div>
          </div>
        )}
      </Drawer>
    </section>
  )
}

function Rules({ types }: { types: Type[] }) {
  const { list, create, update, remove } = useCrud<Rule>('rules', '/availability-rules')
  const [edit, setEdit] = useState<Partial<Rule> | null>(null)
  const save = () => {
    if (!edit) return
    const body = { ...edit }
    if (edit.id) update.mutate(body as Rule & Record<string, unknown>, { onSuccess: () => setEdit(null) })
    else create.mutate(body, { onSuccess: () => setEdit(null) })
  }
  return (
    <section className="glass pad">
      <div className="spread" style={{ marginBottom: 14 }}>
        <div>
          <div className="h2">Availability rules</div>
          <div className="muted" style={{ fontSize: 13 }}>Opening hours, duration limits, notice and booking window per type (or a single resource).</div>
        </div>
        <button className="key key-amber" onClick={() => setEdit({ resource_type: types[0]?.id, name: 'Standard hours', weekdays: [0, 1, 2, 3, 4], open_time: '08:00', close_time: '20:00', min_duration_minutes: 30, max_duration_minutes: 180, min_lead_minutes: 0, max_advance_days: 14, slot_minutes: 30 })}>
          <Plus weight="bold" /> Rule
        </button>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Applies to</th><th>Days</th><th>Hours</th><th>Duration</th><th>Notice</th><th>Window</th><th /></tr></thead>
          <tbody>
            {list.data?.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.target}</strong><div className="muted" style={{ fontSize: 12 }}>{r.name}</div></td>
                <td className="mono" style={{ fontSize: 12 }}>{r.weekdays.length === 7 ? 'daily' : r.weekdays.map((d) => WEEKDAYS[d].slice(0, 2)).join(' ')}</td>
                <td className="mono">{r.open_time.slice(0, 5)}–{r.close_time.slice(0, 5)}</td>
                <td className="mono">{r.min_duration_minutes}m–{r.max_duration_minutes / 60}h</td>
                <td className="mono">{r.min_lead_minutes ? `${r.min_lead_minutes}m` : '—'}</td>
                <td className="mono">{r.max_advance_days}d</td>
                <td><button className="key key-ghost key-sm" onClick={() => setEdit(r)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Drawer open={!!edit} onClose={() => setEdit(null)} title="Availability rule">
        {edit && (
          <div className="col" style={{ gap: 12 }}>
            {!edit.id && (
              <label className="field"><span>Resource type</span>
                <select className="input" value={edit.resource_type ?? ''} onChange={(e) => setEdit({ ...edit, resource_type: Number(e.target.value) })}>{types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
              </label>
            )}
            <label className="field"><span>Name</span><input className="input" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></label>
            <div className="row wrap" style={{ gap: 6 }}>
              {WEEKDAYS.map((d, i) => (
                <button type="button" key={d} className={`chip ${edit.weekdays?.includes(i) ? 'on' : ''}`} onClick={() => setEdit({ ...edit, weekdays: edit.weekdays?.includes(i) ? edit.weekdays.filter((x) => x !== i) : [...(edit.weekdays ?? []), i].sort() })}>{d}</button>
              ))}
            </div>
            <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <label className="field"><span>Opens</span><input className="input" type="time" value={edit.open_time?.slice(0, 5)} onChange={(e) => setEdit({ ...edit, open_time: e.target.value })} /></label>
              <label className="field"><span>Closes</span><input className="input" type="time" value={edit.close_time?.slice(0, 5)} onChange={(e) => setEdit({ ...edit, close_time: e.target.value })} /></label>
              <label className="field"><span>Min duration (min)</span><input className="input" type="number" value={edit.min_duration_minutes} onChange={(e) => setEdit({ ...edit, min_duration_minutes: Number(e.target.value) })} /></label>
              <label className="field"><span>Max duration (min)</span><input className="input" type="number" value={edit.max_duration_minutes} onChange={(e) => setEdit({ ...edit, max_duration_minutes: Number(e.target.value) })} /></label>
              <label className="field"><span>Min notice (min)</span><input className="input" type="number" value={edit.min_lead_minutes} onChange={(e) => setEdit({ ...edit, min_lead_minutes: Number(e.target.value) })} /></label>
              <label className="field"><span>Booking window (days)</span><input className="input" type="number" value={edit.max_advance_days} onChange={(e) => setEdit({ ...edit, max_advance_days: Number(e.target.value) })} /></label>
            </div>
            <div className="row">
              {edit.id && <button className="key key-coral" onClick={() => { remove.mutate(edit.id!); setEdit(null) }}><Trash /></button>}
              <div className="grow" />
              <button className="key key-amber" onClick={save}>Save rule</button>
            </div>
          </div>
        )}
      </Drawer>
    </section>
  )
}

function Blackouts({ types }: { types: Type[] }) {
  const { list, create, remove } = useCrud<Blackout>('blackouts', '/blackouts')
  const [f, setF] = useState({ title: '', start_at: '', end_at: '', resource_type: '' })
  return (
    <section className="glass pad">
      <div className="h2">Blackout periods</div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>Holidays, exams, events — nothing in scope can be booked.</div>
      <form
        className="blackout-form"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate({ title: f.title, start_at: new Date(f.start_at).toISOString(), end_at: new Date(f.end_at).toISOString(), resource_type: f.resource_type ? Number(f.resource_type) : null }, { onSuccess: () => setF({ title: '', start_at: '', end_at: '', resource_type: '' }) })
        }}
      >
        <input className="input" placeholder="e.g. Diwali break" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required />
        <input className="input" type="datetime-local" value={f.start_at} onChange={(e) => setF({ ...f, start_at: e.target.value })} required />
        <input className="input" type="datetime-local" value={f.end_at} onChange={(e) => setF({ ...f, end_at: e.target.value })} required />
        <select className="input" value={f.resource_type} onChange={(e) => setF({ ...f, resource_type: e.target.value })}>
          <option value="">Entire campus</option>
          {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <button className="key key-amber"><Plus weight="bold" /> Add</button>
      </form>
      <div className="col" style={{ gap: 8, marginTop: 14 }}>
        {list.data?.map((b) => (
          <div key={b.id} className="spread list-row">
            <div>
              <strong>{b.title}</strong> <span className="muted">· {b.scope}</span>
              <div className="mono muted" style={{ fontSize: 12 }}>{format(new Date(b.start), 'EEE d MMM HH:mm')} → {format(new Date(b.end), 'EEE d MMM HH:mm')}</div>
            </div>
            <button className="key key-ghost key-sm key-icon" onClick={() => remove.mutate(b.id)}><Trash size={14} /></button>
          </div>
        ))}
      </div>
    </section>
  )
}

function Quotas({ types }: { types: Type[] }) {
  const { list, create, update, remove } = useCrud<Quota>('quotas', '/quotas')
  const { data: depts } = useQuery({ queryKey: ['depts'], queryFn: () => api.get<{ id: number; code: string }[]>('/departments').then((r) => r.data) })
  const num = (q: Quota, k: keyof Quota) => (
    <input className="input mono" style={{ height: 34, width: 80 }} type="number" min={0} defaultValue={q[k] as number} onBlur={(e) => Number(e.target.value) !== q[k] && update.mutate({ id: q.id, [k]: Number(e.target.value) })} />
  )
  return (
    <section className="glass pad">
      <div className="spread" style={{ marginBottom: 12 }}>
        <div>
          <div className="h2">Quotas</div>
          <div className="muted" style={{ fontSize: 13 }}>Weekly hours per department, per person, and max simultaneous bookings. 0 = unlimited. Edit inline.</div>
        </div>
        <button className="key key-amber" onClick={() => create.mutate({ department: depts?.[0]?.id, department_hours_per_week: 40 })}><Plus weight="bold" /> Quota</button>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Department</th><th>Role</th><th>Type</th><th>Dept h/wk</th><th>User h/wk</th><th>Max active</th><th /></tr></thead>
          <tbody>
            {list.data?.map((q) => (
              <tr key={q.id}>
                <td>
                  <select className="input" style={{ height: 34, fontSize: 13 }} value={q.department ?? ''} onChange={(e) => update.mutate({ id: q.id, department: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">All</option>{depts?.map((d) => <option key={d.id} value={d.id}>{d.code}</option>)}
                  </select>
                </td>
                <td>
                  <select className="input" style={{ height: 34, fontSize: 13 }} value={q.role} onChange={(e) => update.mutate({ id: q.id, role: e.target.value })}>
                    <option value="">All roles</option>{REQUESTER_ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                  </select>
                </td>
                <td>
                  <select className="input" style={{ height: 34, fontSize: 13 }} value={q.resource_type ?? ''} onChange={(e) => update.mutate({ id: q.id, resource_type: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">All types</option>{types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </td>
                <td>{num(q, 'department_hours_per_week')}</td>
                <td>{num(q, 'user_hours_per_week')}</td>
                <td>{num(q, 'max_active_bookings')}</td>
                <td><button className="key key-ghost key-sm key-icon" onClick={() => remove.mutate(q.id)}><Trash size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function PolicyCard() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['policy'], queryFn: () => api.get<Record<string, number>>('/policy').then((r) => r.data) })
  const save = useMutation({
    mutationFn: (b: Record<string, number>) => api.patch('/policy', b),
    onSuccess: () => {
      toast.success('Policy updated — applies to the next sweep')
      qc.invalidateQueries({ queryKey: ['policy'] })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const fields: [string, string][] = [
    ['checkin_open_minutes', 'Check-in opens (min before)'],
    ['grace_minutes', 'Grace period (min)'],
    ['reminder_minutes', 'Reminder (min before)'],
    ['noshow_window_days', 'No-show window (days)'],
    ['strike_warn', 'Warn at strikes'],
    ['strike_level1', 'Pause at strikes'],
    ['restrict_days_level1', '…for days'],
    ['strike_level2', 'Long pause at strikes'],
    ['restrict_days_level2', '…for days'],
  ]
  return (
    <section className="glass pad">
      <div className="h2">Campus policy</div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>Check-in timing and the progressive no-show ladder.</div>
      {data && (
        <form
          className="policy-grid"
          onSubmit={(e) => {
            e.preventDefault()
            const f = new FormData(e.currentTarget)
            save.mutate(Object.fromEntries(fields.map(([k]) => [k, Number(f.get(k))])))
          }}
        >
          {fields.map(([k, l]) => (
            <label key={k} className="field"><span>{l}</span><input name={k} className="input mono" type="number" min={0} defaultValue={data[k]} /></label>
          ))}
          <button className="key key-amber" style={{ alignSelf: 'end' }}>Save policy</button>
        </form>
      )}
    </section>
  )
}

export default function Config() {
  const { user } = useAuth()
  const { data: types } = useQuery({ queryKey: ['types'], queryFn: () => api.get<Type[]>('/resource-types').then((r) => r.data) })
  if (!types) return null
  const admin = isPolicyAdmin(user)
  return (
    <div className="col" style={{ gap: 18 }}>
      {admin && <WorkflowBuilder types={types} />}
      <Rules types={types} />
      <div className="two-col">
        <Blackouts types={types} />
        {admin ? <PolicyCard /> : <section className="glass pad muted">Policy and quotas are managed by facility managers.</section>}
      </div>
      {admin && <Quotas types={types} />}
    </div>
  )
}
