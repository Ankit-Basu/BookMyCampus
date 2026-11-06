import { IdentificationBadge, LockKey, UserPlus } from '@phosphor-icons/react'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { motion } from 'motion/react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import AuthLayout, { ServerWaking, useServerReady, WAKE_RETRY } from '../components/AuthLayout'
import { Select } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'

type Dept = { id: number; code: string; name: string }
type Errors = Record<string, string>

const EMPTY = { registration_no: '', first_name: '', last_name: '', email: '', department: '', password: '', confirm: '' }

function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {error ? <small className="field-error" role="alert">{error}</small> : hint && <small className="field-hint">{hint}</small>}
    </label>
  )
}

export default function Register() {
  const { user } = useAuth()
  const nav = useNavigate()
  const { search } = useLocation()
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState<Errors>({})
  const ready = useServerReady()
  const { data: depts = [] } = useQuery({ queryKey: ['public-depts'], queryFn: () => api.get<Dept[]>('/auth/departments').then((r) => r.data), ...WAKE_RETRY })

  const set = (k: keyof typeof EMPTY, v: string) => {
    setForm((f) => ({ ...f, [k]: v }))
    setErrors(({ [k]: _cleared, ...rest }) => rest)
  }

  const register = useMutation({
    mutationFn: () => {
      const { confirm: _confirm, department, ...body } = form
      return api.post('/auth/register', { ...body, department: department ? Number(department) : null })
    },
    onSuccess: () => {
      toast.success('Account created. Sign in with your new password.')
      nav(`/login${search}`, { replace: true, state: { username: form.registration_no } })
    },
    onError: (e) => {
      const data = (e as AxiosError<Record<string, unknown>>).response?.data
      const fields = Object.fromEntries(Object.entries(data ?? {}).filter(([k, v]) => k in EMPTY && Array.isArray(v)).map(([k, v]) => [k, String((v as string[])[0])]))
      setErrors(fields)
      if (!Object.keys(fields).length) toast.error(errorMessage(e))
    },
  })

  if (user) return <Navigate to="/explore" replace />

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const found: Errors = {}
    if (!/^[0-9]{8}$/.test(form.registration_no)) found.registration_no = 'Enter your 8-digit registration number.'
    if (depts.length && !form.department) found.department = 'Choose your department.'
    if (form.password !== form.confirm) found.confirm = 'The two passwords do not match.'
    setErrors(found)
    if (!Object.keys(found).length) register.mutate()
  }

  return (
    <AuthLayout
      eyebrow="Create your account"
      title={<>New on campus?<br /><em>Get on the list.</em></>}
      blurb="Sign up once with your registration number, then sign in to book rooms, labs, halls and courts across LPU."
      aside={
        <ol className="auth-list auth-steps">
          <li><i className="mono">1</i><span><strong>Create your account</strong>Takes a minute. Use a new password, not your UMS one.</span></li>
          <li><i className="mono">2</i><span><strong>Pick a free slot</strong>Classes and other bookings are already blocked out.</span></li>
          <li><i className="mono">3</i><span><strong>Scan in at the door</strong>Your pass has the QR. No register book, no phone calls.</span></li>
        </ol>
      }
    >
      <motion.form
        onSubmit={submit}
        noValidate
        className="glass pad-l login-card"
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.9, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="col" style={{ gap: 14 }}>
          <Field label="Registration number" error={errors.registration_no}>
            <div className="input-icon">
              <IdentificationBadge size={18} />
              <input
                className="input"
                value={form.registration_no}
                onChange={(e) => set('registration_no', e.target.value.replace(/[^0-9]/g, ''))}
                placeholder="e.g. 12306448"
                inputMode="numeric"
                maxLength={8}
                autoComplete="username"
                autoFocus
              />
            </div>
          </Field>
          <div className="field-row">
            <Field label="First name" error={errors.first_name}>
              <input className="input" value={form.first_name} onChange={(e) => set('first_name', e.target.value)} autoComplete="given-name" />
            </Field>
            <Field label="Last name" error={errors.last_name}>
              <input className="input" value={form.last_name} onChange={(e) => set('last_name', e.target.value)} autoComplete="family-name" />
            </Field>
          </div>
          <Field label="Email" error={errors.email}>
            <input className="input" type="email" value={form.email} onChange={(e) => set('email', e.target.value)} placeholder="you@lpu.in" autoComplete="email" />
          </Field>
          {depts.length > 0 && (
            <Field label="Department" error={errors.department}>
              <Select value={form.department} onChange={(e) => set('department', e.target.value)}>
                <option value="">Choose your department</option>
                {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </Select>
            </Field>
          )}
          <Field label="Create a password" error={errors.password} hint="At least 8 characters. Make it new for BookMyCampus: don't reuse your UMS password.">
            <div className="input-icon">
              <LockKey size={18} />
              <input className="input" type="password" value={form.password} onChange={(e) => set('password', e.target.value)} autoComplete="new-password" />
            </div>
          </Field>
          <Field label="Confirm password" error={errors.confirm}>
            <div className="input-icon">
              <LockKey size={18} />
              <input className="input" type="password" value={form.confirm} onChange={(e) => set('confirm', e.target.value)} autoComplete="new-password" />
            </div>
          </Field>
          <button
            className="key key-amber key-lg"
            disabled={!form.registration_no || !form.first_name.trim() || !form.email.trim() || !form.password || !form.confirm || !ready || register.isPending}
            style={{ marginTop: 6 }}
          >
            <UserPlus weight="bold" /> {!ready ? 'Waiting for the server…' : register.isPending ? 'Creating your account…' : 'Create account'}
          </button>
          {!ready && <ServerWaking />}
          <p className="auth-switch">Already registered? <Link to={`/login${search}`}>Sign in</Link></p>
        </div>
      </motion.form>
    </AuthLayout>
  )
}
