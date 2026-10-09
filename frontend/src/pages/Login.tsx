import { ArrowRight, IdentificationBadge, LockKey, SignIn } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Wordmark } from '../components/AppShell'
import Grainient from '../components/reactbits/bg/Grainient'
import { Sparks } from '../components/Backdrop'
import { api, errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ROLE_LABEL } from '../lib/format'

type Demo = { username: string; name: string; role: string; role_label: string; password: string }

const ROLE_BLURB: Record<string, string> = {
  student: 'Browse, book, scan in',
  faculty: 'Recurring & class bookings',
  staff: 'Broader booking rights',
  custodian: 'Approvals, maintenance, stock',
  dept_head: 'Quotas & dept. utilisation',
  facility_manager: 'Campus-wide policy',
  admin: 'Types, workflows, everything',
}

export default function Login() {
  const { user, login } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next') || '/explore'
  const [username, setUsername] = useState('')
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
      toast.error(errorMessage(e) === 'No active account found with the given credentials' ? 'Wrong UMS ID or password' : errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    go(username, password)
  }

  return (
    <div className="login">
      <div className="login-bg">
        <Grainient
          color1="#ff9a2e"
          color2="#6a3dff"
          color3="#0a0b16"
          timeSpeed={0.18}
          warpAmplitude={70}
          blendSoftness={0.18}
          grainAmount={0.06}
          contrast={1.3}
          zoom={0.8}
          renderScale={0.35}
          maxFps={24}
        />
        <div className="login-shade" />
        <div className="grain" />
      </div>
      <Sparks />
      <div className="login-top">
        <Wordmark />
      </div>
      <div className="login-grid">
        <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}>
          <div className="eyebrow">Sign in</div>
          <h1 className="display" style={{ fontSize: 'clamp(46px,6vw,84px)', margin: '8px 0 14px' }}>
            Your campus,
            <br />
            <em>on reservation.</em>
          </h1>
          <p className="muted" style={{ maxWidth: 440 }}>
            Use your UMS registration or employee ID. Demo personas below sign you in instantly — try the student first, then a custodian to approve what they asked for.
          </p>
        </motion.div>

        <motion.form
          onSubmit={submit}
          className="glass pad-l login-card"
          initial={{ opacity: 0, y: 40, rotateX: 8 }}
          animate={{ opacity: 1, y: 0, rotateX: 0 }}
          transition={{ duration: 0.9, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="col" style={{ gap: 14 }}>
            <label className="field">
              <span>UMS ID</span>
              <div className="input-icon">
                <IdentificationBadge size={18} />
                <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="e.g. 12215634 or demo.student" autoComplete="username" />
              </div>
            </label>
            <label className="field">
              <span>Password</span>
              <div className="input-icon">
                <LockKey size={18} />
                <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
              </div>
            </label>
            <button className="key key-amber key-lg" disabled={!username || !password || !!busy} style={{ marginTop: 6 }}>
              <SignIn weight="bold" /> {busy === username ? 'Signing in…' : 'Sign in'}
            </button>
            <button type="button" className="key key-ghost" onClick={() => toast.info('UMS single sign-on plugs in here — the SSO hook is ready in accounts/.')}>
              Continue with LPU UMS SSO
            </button>
          </div>

          {!!demos?.length && (
            <>
              <div className="divider" />
              <div className="eyebrow" style={{ marginBottom: 12 }}>One-click demo personas</div>
              <div className="persona-grid">
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
      </div>
    </div>
  )
}
