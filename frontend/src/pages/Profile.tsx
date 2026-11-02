import { CalendarBlank, ShieldWarning, Warning } from '@phosphor-icons/react'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { format } from 'date-fns'
import { useState, type CSSProperties, type FormEvent } from 'react'
import { toast } from 'sonner'

import { Reveal } from '../components/motion'
import { Dial, PageHeader, Select } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { Booking } from '../lib/types'

type Policy = { grace_minutes: number; strike_warn: number; strike_level1: number; restrict_days_level1: number; strike_level2: number; restrict_days_level2: number; noshow_window_days: number }

const fieldErrors = (e: unknown): Record<string, string> => {
  const data = (e as AxiosError<Record<string, unknown>>).response?.data ?? {}
  return Object.fromEntries(Object.entries(data).filter(([, v]) => Array.isArray(v)).map(([k, v]) => [k, String((v as string[])[0])]))
}

function EditDetails() {
  const { user, refresh } = useAuth()
  const [form, setForm] = useState({ first_name: user!.first_name, last_name: user!.last_name, email: user!.email, phone: user!.phone ?? '', department: String(user!.department ?? '') })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const { data: depts = [] } = useQuery({ queryKey: ['public-depts'], queryFn: () => api.get<{ id: number; name: string }[]>('/auth/departments').then((r) => r.data) })
  const save = useMutation({
    mutationFn: () => api.patch('/me', { ...form, department: form.department ? Number(form.department) : null }),
    onSuccess: async () => {
      setErrors({})
      await refresh()
      toast.success('Details saved')
    },
    onError: (e) => {
      const f = fieldErrors(e)
      setErrors(f)
      if (!Object.keys(f).length) toast.error(errorMessage(e))
    },
  })
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))
  return (
    <Reveal className="glass pad">
      <div className="eyebrow" style={{ marginBottom: 12 }}>Your details</div>
      <form className="col" style={{ gap: 12 }} onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate() }}>
        <div className="field-row">
          <label className="field"><span>First name</span><input className="input" value={form.first_name} onChange={set('first_name')} autoComplete="given-name" required /></label>
          <label className="field"><span>Last name</span><input className="input" value={form.last_name} onChange={set('last_name')} autoComplete="family-name" /></label>
        </div>
        <label className="field">
          <span>Email</span><input className="input" type="email" value={form.email} onChange={set('email')} autoComplete="email" />
          {errors.email && <small className="field-error" role="alert">{errors.email}</small>}
        </label>
        <label className="field">
          <span>Phone</span><input className="input" type="tel" maxLength={20} value={form.phone} onChange={set('phone')} autoComplete="tel" />
          {errors.phone && <small className="field-error" role="alert">{errors.phone}</small>}
        </label>
        {depts.length > 0 && (
          <label className="field">
            <span>Department</span>
            <Select value={form.department} onChange={set('department')}>
              <option value="">Not set</option>
              {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          </label>
        )}
        <button className="key key-amber" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save details'}</button>
      </form>
    </Reveal>
  )
}

function ChangePassword() {
  const empty = { current_password: '', new_password: '', confirm: '' }
  const [form, setForm] = useState(empty)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const change = useMutation({
    mutationFn: () => api.post('/me/password', { current_password: form.current_password, new_password: form.new_password }),
    onSuccess: () => {
      setForm(empty)
      setErrors({})
      toast.success('Password changed. Use the new one next time you sign in.')
    },
    onError: (e) => {
      const f = fieldErrors(e)
      setErrors(f)
      if (!Object.keys(f).length) toast.error(errorMessage(e))
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (form.new_password !== form.confirm) return setErrors({ confirm: 'The two passwords do not match.' })
    change.mutate()
  }
  const input = (k: keyof typeof empty, label: string, auto: string) => (
    <label className="field">
      <span>{label}</span>
      <input className="input" type="password" value={form[k]} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} autoComplete={auto} />
      {errors[k] && <small className="field-error" role="alert">{errors[k]}</small>}
    </label>
  )
  return (
    <Reveal className="glass pad">
      <div className="eyebrow" style={{ marginBottom: 12 }}>Change password</div>
      <form className="col" style={{ gap: 12 }} onSubmit={submit}>
        {input('current_password', 'Current password', 'current-password')}
        {input('new_password', 'New password', 'new-password')}
        {input('confirm', 'Confirm new password', 'new-password')}
        <button className="key key-ghost" disabled={!form.current_password || !form.new_password || !form.confirm || change.isPending}>
          {change.isPending ? 'Changing…' : 'Change password'}
        </button>
      </form>
    </Reveal>
  )
}

export default function Profile() {
  const { user } = useAuth()
  const { data: policy } = useQuery({ queryKey: ['policy'], queryFn: () => api.get<Policy>('/policy').then((r) => r.data) })
  const { data: past } = useQuery({ queryKey: ['bookings', 'past'], queryFn: () => api.get<Booking[]>('/bookings', { params: { past: 1 } }).then((r) => r.data) })
  if (!user) return null
  const done = past?.filter((b) => ['completed', 'released'].includes(b.status) && b.requires_checkin) ?? []
  const shows = done.filter((b) => b.status === 'completed').length
  const reliability = done.length ? shows / done.length : 1
  const feed = `${window.location.origin}/api/calendar/${user.calendar_token}.ics`
  const ladder = policy
    ? [
        { n: policy.strike_warn, label: 'Warning', c: 'var(--brand)' },
        { n: policy.strike_level1, label: `${policy.restrict_days_level1}-day pause`, c: 'var(--bad)' },
        { n: policy.strike_level2, label: `${policy.restrict_days_level2}-day pause`, c: 'var(--bad)' },
      ]
    : []

  return (
    <div className="page" style={{ maxWidth: 1080 }}>
      <PageHeader eyebrow={`${user.role_label}${user.department_code ? ` · ${user.department_code}` : ''}`} title={<>{user.first_name} <em>{user.last_name}</em></>} sub={`Reg. no. ${user.username}${user.email ? ` · ${user.email}` : ''}`} />

      {user.is_restricted && (
        <div className="glass pad notice-bad" style={{ marginBottom: 18 }}>
          <ShieldWarning size={28} weight="duotone" color="var(--bad)" />
          <div>
            <div className="h2">Booking paused until {format(new Date(user.restricted_until!), 'EEE d MMM, HH:mm')}</div>
            <div className="muted">{user.restriction_reason}. Talk to a facility manager if this was a mistake.</div>
          </div>
        </div>
      )}

      <div className="profile-grid">
        <Reveal className="glass pad" style={{ display: 'grid', placeItems: 'center' }}>
          <Dial value={reliability} label="Show-up rate" color={reliability > 0.85 ? 'var(--ok)' : reliability > 0.6 ? 'var(--brand)' : 'var(--bad)'} size={200} />
          <div className="muted" style={{ fontSize: 13 }}>{shows} of {done.length} check-in bookings attended</div>
        </Reveal>
        <Reveal className="glass pad">
          <div className="eyebrow">No-show ladder · last {policy?.noshow_window_days ?? 30} days</div>
          <div className="display" style={{ fontSize: 56, margin: '6px 0' }}>
            {user.noshow_count}
            <span className="muted" style={{ fontSize: 22 }}> strike{user.noshow_count === 1 ? '' : 's'}</span>
          </div>
          <div className="ladder">
            {ladder.map((l) => (
              <div key={l.n} className={`rung ${user.noshow_count >= l.n ? 'hit' : ''}`} style={{ '--c': l.c } as CSSProperties}>
                <span className="mono">{l.n}</span>
                <span>{l.label}</span>
              </div>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
            <Warning size={13} /> Not checking in within {policy?.grace_minutes ?? 15} minutes of start releases the slot and counts as a strike.
          </p>
        </Reveal>
        <Reveal className="glass pad">
          <div className="eyebrow">Calendar sync</div>
          <div className="h2" style={{ margin: '8px 0' }}>Your bookings in Google, Outlook or Apple Calendar</div>
          <p className="muted" style={{ fontSize: 13 }}>Subscribe once — new bookings, approvals and cancellations show up automatically.</p>
          <div className="input mono" style={{ display: 'flex', alignItems: 'center', fontSize: 11, overflow: 'hidden' }}>
            <span className="truncate">{feed}</span>
          </div>
          <button
            className="key key-amber"
            style={{ marginTop: 12 }}
            onClick={() => {
              navigator.clipboard?.writeText(feed)
              toast.success('Feed URL copied')
            }}
          >
            <CalendarBlank /> Copy feed URL
          </button>
        </Reveal>
        <EditDetails />
        <ChangePassword />
      </div>
    </div>
  )
}
