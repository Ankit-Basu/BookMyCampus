import { useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import type { ReactNode } from 'react'

import { api } from '../lib/api'
import { useTheme } from '../lib/theme'
import { ThemeMenu, Wordmark } from './AppShell'
import { Sparks } from './Backdrop'
import Grainient from './reactbits/bg/Grainient'

// The free backend sleeps when idle and takes up to a minute to wake, so these requests keep retrying.
export const WAKE_RETRY = { retry: 12, retryDelay: 6000 }

function usePublicStats() {
  return useQuery({ queryKey: ['public-stats'], queryFn: () => api.get<{ resources: number; bookings_30d: number }>('/public/stats').then((r) => r.data), ...WAKE_RETRY })
}

/** True once the backend has answered, or once it has stopped retrying, so a form is never blocked for good. */
export function useServerReady() {
  const { isSuccess, isError } = usePublicStats()
  return isSuccess || isError
}

export function ServerWaking() {
  return <p className="auth-switch muted" role="status" style={{ fontSize: 12.5 }}>Waking up the server. On the free plan this can take up to a minute.</p>
}

/** Live numbers from the catalogue, the same ones the landing page shows. */
function AuthStats() {
  const { data } = usePublicStats()
  const tiles = [
    { v: data?.resources ?? '–', l: 'spaces to book' },
    { v: data?.bookings_30d ?? '–', l: 'bookings this month' },
    { v: 0, l: 'double bookings, ever' },
  ]
  return (
    <div className="auth-stats">
      {tiles.map((t) => (
        <div key={t.l} className="auth-tile">
          <strong className="display">{t.v}</strong>
          <span>{t.l}</span>
        </div>
      ))}
    </div>
  )
}

/** The shared frame of the sign-in and sign-up pages: live backdrop, headline on the left, a card on the right. */
export default function AuthLayout({ eyebrow, title, blurb, aside, children }: { eyebrow: string; title: ReactNode; blurb: ReactNode; aside?: ReactNode; children: ReactNode }) {
  const { palette } = useTheme()
  return (
    <div className="login">
      <div className="login-bg">
        <Grainient
          color1={palette.shader[0]}
          color2={palette.shader[1]}
          color3={palette.shader[2]}
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
        <ThemeMenu />
      </div>
      <div className="login-grid">
        <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}>
          <div className="eyebrow">{eyebrow}</div>
          <h1 className="display" style={{ fontSize: 'clamp(46px,6.4vw,92px)', fontWeight: 800, margin: '8px 0 14px' }}>{title}</h1>
          <p style={{ maxWidth: 480, color: 'var(--fg-2)' }}>{blurb}</p>
          <div className="auth-aside">
            <AuthStats />
            {aside}
          </div>
        </motion.div>
        {children}
      </div>
    </div>
  )
}
