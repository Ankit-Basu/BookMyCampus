import { MagnifyingGlass, PencilSimple, ShieldWarning, UserPlus } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { useDeferredValue, useState, type CSSProperties } from 'react'
import { toast } from 'sonner'

import { Drawer, Empty, Skeleton, Select } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { isPolicyAdmin, useAuth } from '../../lib/auth'
import { fmtRelative, ROLE_LABEL } from '../../lib/format'

type Person = {
  id: number
  username: string
  name: string
  first_name: string
  last_name: string
  email: string
  phone: string
  role: string
  role_label: string
  department: number | null
  department_code: string | null
  is_active: boolean
  is_restricted: boolean
  restricted_until: string | null
  restriction_reason: string
  booking_count: number
  noshows_30d: number
  last_login: string | null
}
type Dept = { id: number; code: string; name: string }

const ROLE_COLOR: Record<string, string> = {
  student: 'var(--info)',
  faculty: 'var(--ok)',
  staff: 'var(--chart-4)',
  custodian: 'var(--brand)',
  dept_head: 'var(--bad)',
  facility_manager: 'var(--bad)',
  admin: 'var(--brand)',
}

function Editor({ person, depts, onClose }: { person: Person | 'new' | null; depts: Dept[]; onClose: () => void }) {
  const qc = useQueryClient()
  const isNew = person === 'new'
  const p = isNew ? null : person
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => (isNew ? api.post('/users', body) : api.patch(`/users/${p!.id}`, body)),
    onSuccess: () => {
      toast.success(isNew ? 'Account created' : 'Saved')
      qc.invalidateQueries({ queryKey: ['people'] })
      onClose()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <Drawer open={person !== null} onClose={onClose} title={isNew ? 'New account' : p?.name ?? ''}>
      {person !== null && (
        <form
          key={isNew ? 'new' : p!.id}
          className="col"
          style={{ gap: 12 }}
          onSubmit={(e) => {
            e.preventDefault()
            const f = new FormData(e.currentTarget)
            const body: Record<string, unknown> = {
              first_name: f.get('first_name'),
              last_name: f.get('last_name'),
              email: f.get('email'),
              phone: f.get('phone'),
              role: f.get('role'),
              department: f.get('department') ? Number(f.get('department')) : null,
              is_active: f.get('is_active') === 'on',
            }
            if (isNew) body.username = f.get('username')
            if (f.get('password')) body.password = f.get('password')
            save.mutate(body)
          }}
        >
          {isNew ? (
            <label className="field"><span>UMS ID (username)</span><input name="username" className="input mono" placeholder="12215634" required /></label>
          ) : (
            <div className="mono muted" style={{ fontSize: 12 }}>UMS ID {p!.username}{p!.last_login ? ` · last seen ${fmtRelative(p!.last_login)}` : ' · never signed in'}</div>
          )}
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <label className="field"><span>First name</span><input name="first_name" className="input" defaultValue={p?.first_name} required /></label>
            <label className="field"><span>Last name</span><input name="last_name" className="input" defaultValue={p?.last_name} /></label>
          </div>
          <div className="grid" style={{ gridTemplateColumns: '1.4fr 1fr', gap: 12 }}>
            <label className="field"><span>Email (for notifications)</span><input name="email" type="email" className="input" defaultValue={p?.email} /></label>
            <label className="field"><span>Phone</span><input name="phone" className="input" defaultValue={p?.phone} /></label>
          </div>
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <label className="field">
              <span>Role · what they can do</span>
              <Select name="role" defaultValue={p?.role ?? 'student'}>
                {Object.entries(ROLE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </label>
            <label className="field">
              <span>Department</span>
              <Select name="department" defaultValue={p?.department ?? ''}>
                <option value="">—</option>
                {depts.map((d) => <option key={d.id} value={d.id}>{d.code} · {d.name}</option>)}
              </Select>
            </label>
          </div>
          <label className="field">
            <span>{isNew ? 'Initial password (leave blank for SSO-only)' : 'Reset password (optional)'}</span>
            <input name="password" type="password" className="input" autoComplete="new-password" minLength={8} />
          </label>
          <label className="row" style={{ gap: 10, marginTop: 4 }}>
            <input type="checkbox" name="is_active" defaultChecked={p?.is_active ?? true} style={{ width: 18, height: 18, accentColor: 'var(--brand)' }} />
            <span>Account active (inactive users can’t sign in)</span>
          </label>
          {p?.is_restricted && (
            <div className="notice"><ShieldWarning size={18} color="var(--bad)" /> Booking paused until {format(new Date(p.restricted_until!), 'd MMM')} — {p.restriction_reason}. Lift it from the No-show monitor.</div>
          )}
          <button className="key key-amber key-lg" disabled={save.isPending}>{isNew ? 'Create account' : 'Save changes'}</button>
        </form>
      )}
    </Drawer>
  )
}

export default function People() {
  const { user } = useAuth()
  const admin = isPolicyAdmin(user)
  const [q, setQ] = useState('')
  const dq = useDeferredValue(q)
  const [role, setRole] = useState('')
  const [dept, setDept] = useState('')
  const [active, setActive] = useState('')
  const [edit, setEdit] = useState<Person | 'new' | null>(null)
  const { data: depts = [] } = useQuery({ queryKey: ['depts'], queryFn: () => api.get<Dept[]>('/departments').then((r) => r.data) })
  const { data, isLoading } = useQuery({
    queryKey: ['people', dq, role, dept, active],
    queryFn: () =>
      api
        .get<Person[]>('/users', { params: { directory: 1, search: dq || undefined, role: role || undefined, department: dept || undefined, is_active: active || undefined } })
        .then((r) => r.data),
    placeholderData: (p) => p,
  })
  const counts = data?.reduce<Record<string, number>>((m, p) => ({ ...m, [p.role]: (m[p.role] ?? 0) + 1 }), {}) ?? {}

  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="filter-row glass-flat">
        <div className="row grow" style={{ gap: 8, minWidth: 220 }}>
          <MagnifyingGlass size={16} className="muted" />
          <input className="input" style={{ height: 36 }} placeholder="Search name, UMS ID or email…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select style={{ width: 'auto', height: 36 }} value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">All roles</option>
          {Object.entries(ROLE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </Select>
        <Select style={{ width: 'auto', height: 36 }} value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">All departments</option>
          {depts.map((d) => <option key={d.id} value={d.id}>{d.code}</option>)}
        </Select>
        <Select style={{ width: 'auto', height: 36 }} value={active} onChange={(e) => setActive(e.target.value)}>
          <option value="">Active + inactive</option>
          <option value="true">Active</option>
          <option value="false">Deactivated</option>
        </Select>
        {admin && (
          <button className="key key-amber key-sm" onClick={() => setEdit('new')}><UserPlus weight="bold" /> New account</button>
        )}
      </div>

      <div className="row wrap" style={{ gap: 8 }}>
        {Object.entries(counts).map(([r, n]) => (
          <span key={r} className="tag" style={{ '--c': ROLE_COLOR[r] } as CSSProperties}>{ROLE_LABEL[r]} · {n}</span>
        ))}
      </div>

      <div className="glass pad">
        {isLoading && !data ? (
          <Skeleton h={300} />
        ) : data?.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Person</th><th>Role</th><th>Dept</th><th>Bookings</th><th>No-shows 30d</th><th>Status</th><th /></tr></thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} style={{ opacity: p.is_active ? 1 : 0.5 }}>
                    <td>
                      <div className="row" style={{ gap: 10 }}>
                        <span className="avatar sm" style={{ background: `color-mix(in oklab, ${ROLE_COLOR[p.role]} 80%, black)` }}>{p.name.split(' ').map((x) => x[0]).slice(0, 2).join('')}</span>
                        <span style={{ minWidth: 0 }}>
                          <span style={{ display: 'block', fontWeight: 600 }}>{p.name}</span>
                          <span className="mono muted" style={{ fontSize: 11 }}>{p.username}{p.email ? ` · ${p.email}` : ''}</span>
                        </span>
                      </div>
                    </td>
                    <td><span className="tag" style={{ '--c': ROLE_COLOR[p.role] } as CSSProperties}>{p.role_label}</span></td>
                    <td className="mono">{p.department_code ?? '—'}</td>
                    <td className="mono">{p.booking_count}</td>
                    <td className="mono" style={{ color: p.noshows_30d >= 3 ? 'var(--bad)' : undefined }}>{p.noshows_30d}</td>
                    <td>
                      {!p.is_active ? <span className="muted">Deactivated</span> : p.is_restricted ? <span className="tag" style={{ '--c': 'var(--bad)' } as CSSProperties}>Paused</span> : <span className="tag" style={{ '--c': 'var(--ok)' } as CSSProperties}>Active</span>}
                    </td>
                    <td>
                      {admin && (
                        <button className="key key-ghost key-sm key-icon" title="Edit" onClick={() => setEdit(p)}><PencilSimple size={15} /></button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="Nobody matches.">Try a different name or clear a filter.</Empty>
        )}
      </div>
      {admin && <Editor person={edit} depts={depts} onClose={() => setEdit(null)} />}
    </div>
  )
}
