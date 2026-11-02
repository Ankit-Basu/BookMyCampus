import { ArrowRight, CalendarCheck, IdentificationBadge, LockKey, QrCode, SignIn, Sparkle } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import AuthLayout from '../components/AuthLayout'
import { api, errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ROLE_LABEL } from '../lib/format'

type Demo = { username: string; name: string; role: string; role_label: string; password: string }

const ROLE_BLURB: Record<string, string> = {
  student: 'Book for yourself or your class, scan in',
  faculty: 'Book labs and rooms, repeat weekly for a class',
  dept_head: 'Approve requests, add rooms, see usage',
}

export default function Login() {
  const { user, login } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next') || '/explore'
  const { state, search } = useLocation()
  const justRegistered = (state as { username?: string } | null)?.username
  const [username, setUsername] = useState(justRegistered ?? '')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const { data: demos } = useQuery({ queryKey: ['demo'], queryFn: () => api.get<Demo[]>('/auth/demo-accounts').then((r) => r.data) })

  if (user) return <Navigate to={next} replace />

  const go = async (u: string, p: string) => {
    setBusy(u)
    try {
      const me = await login(u, p)
      toast.success(`Welcome, ${me.first_name || me.username}`)
      nav(next, { replace: true })
    } catch (e) {
      toast.error(errorMessage(e) === 'No active account found with the given credentials' ? 'Wrong registration number or password. New here? Create an account first.' : errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    go(username.trim(), password)
  }

  return (
    <AuthLayout
      eyebrow="Sign in"
      title={<>Your campus,<br /><em>on reservation.</em></>}
      blurb="Sign in with your registration number. Trying it out? The demo personas sign you in instantly: request a lab as the student, then approve it as the HOD."
      aside={
        <ul className="auth-list">
          <li><CalendarCheck size={20} weight="duotone" /><span><strong>See what’s free right now</strong>Live availability that already knows the timetable.</span></li>
          <li><QrCode size={20} weight="duotone" /><span><strong>Your pass is on your phone</strong>Scan the door when you arrive and you’re in.</span></li>
          <li><Sparkle size={20} weight="duotone" /><span><strong>Or just ask Copilot</strong>“Find a quiet room in Block 34 for six people.”</span></li>
        </ul>
      }
    >
        <motion.form
          onSubmit={submit}
          className="glass pad-l login-card"
          initial={{ opacity: 0, y: 40, rotateX: 8 }}
          animate={{ opacity: 1, y: 0, rotateX: 0 }}
          transition={{ duration: 0.9, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="col" style={{ gap: 14 }}>
            <label className="field">
              <span>Registration number</span>
              <div className="input-icon">
                <IdentificationBadge size={18} />
                <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="e.g. 12306448" autoComplete="username" />
              </div>
            </label>
            <label className="field">
              <span>Password</span>
              <div className="input-icon">
                <LockKey size={18} />
                <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" autoFocus={!!justRegistered} />
              </div>
            </label>
            <button className="key key-amber key-lg" disabled={!username || !password || !!busy} style={{ marginTop: 6 }}>
              <SignIn weight="bold" /> {busy === username ? 'Signing in…' : 'Sign in'}
            </button>
            <Link to={`/register${search}`} className="key key-ghost">Create an account</Link>
            <p className="auth-switch muted" style={{ fontSize: 12.5 }}>Forgot your password? The facility office can reset it for you.</p>
          </div>

          {!!demos?.length && (
            <>
              <div className="divider" />
              <div className="eyebrow" style={{ marginBottom: 12 }}>One-click demo personas</div>
              <div className="persona-grid persona-list">
                {demos.map((d) => (
                  <button type="button" key={d.username} className="persona" onClick={() => go(d.username, d.password)} disabled={!!busy}>
                    <span className="avatar sm">{d.name.split(' ').map((p) => p[0]).join('')}</span>
                    <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}>
                      <span className="truncate" style={{ display: 'block', fontWeight: 600, fontSize: 13 }}>{ROLE_LABEL[d.role] ?? d.role_label}</span>
                      <span className="truncate muted" style={{ display: 'block', fontSize: 11.5 }}>{busy === d.username ? 'Signing in…' : ROLE_BLURB[d.role]}</span>
                    </span>
                    <ArrowRight size={14} className="muted" />
                  </button>
                ))}
              </div>
            </>
          )}
        </motion.form>
    </AuthLayout>
  )
}
