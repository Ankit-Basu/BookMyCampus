import {
  Basketball,
  ChalkboardTeacher,
  Cube,
  Flask,
  Microscope,
  PresentationChart,
  UsersThree,
  Van,
  X,
} from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { STATUS_COLOR } from '../lib/format'

const ICONS: Record<string, typeof Cube> = {
  chalkboard: ChalkboardTeacher,
  flask: Flask,
  microscope: Microscope,
  presentation: PresentationChart,
  basketball: Basketball,
  'users-three': UsersThree,
  van: Van,
}

export function TypeIcon({ icon, size = 18, color }: { icon?: string; size?: number; color?: string }) {
  const I = (icon && ICONS[icon]) || Cube
  return <I size={size} weight="duotone" color={color} />
}

export function StatusTag({ status, label }: { status: string; label?: string }) {
  return (
    <span className="tag" style={{ '--c': STATUS_COLOR[status] ?? 'var(--paper)' } as CSSProperties}>
      <span className={`led ${status === 'checked_in' ? 'pulse' : ''}`} style={{ '--c': STATUS_COLOR[status], width: 6, height: 6 } as CSSProperties} />
      {label ?? status.replace('_', ' ')}
    </span>
  )
}

export function TypeTag({ name, color, icon }: { name: string; color: string; icon?: string }) {
  return (
    <span className="tag" style={{ '--c': color } as CSSProperties}>
      <TypeIcon icon={icon} size={13} />
      {name}
    </span>
  )
}

export function PageHeader({ eyebrow, title, sub, actions }: { eyebrow: string; title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="spread fade-in" style={{ alignItems: 'flex-end', marginBottom: 28, flexWrap: 'wrap' }}>
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="h1">{title}</h1>
        {sub && <p className="muted" style={{ margin: 0, maxWidth: 620 }}>{sub}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </header>
  )
}

/** Side drawer on desktop, bottom sheet on phones. */
export function Drawer({ open, onClose, title, children, width = 520 }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: number }) {
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open, onClose])
  return createPortal(
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="drawer-scrim"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.aside
            className="drawer glass"
            style={{ width: `min(${width}px, 100vw)` }}
            initial={{ x: '105%' }}
            animate={{ x: 0 }}
            exit={{ x: '105%' }}
            transition={{ type: 'spring', stiffness: 260, damping: 30 }}
            data-lenis-prevent
          >
            <div className="spread" style={{ marginBottom: 18 }}>
              <div className="h2">{title}</div>
              <button className="key key-ghost key-icon key-sm" onClick={onClose} aria-label="Close">
                <X size={16} />
              </button>
            </div>
            {children}
          </motion.aside>
        </>
      )}
    </AnimatePresence>,
    document.body,
  )
}

export function Modal({ open, onClose, children, width = 460 }: { open: boolean; onClose: () => void; children: ReactNode; width?: number }) {
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="modal-scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div
            className="glass pad-l"
            style={{ width: `min(${width}px, calc(100vw - 32px))` }}
            onClick={(e) => e.stopPropagation()}
            initial={{ y: 30, scale: 0.96, opacity: 0 }}
            animate={{ y: 0, scale: 1, opacity: 1 }}
            exit={{ y: 20, scale: 0.97, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 26 }}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

/** Analog instrument dial — utilisation reads like a gauge on a lab bench. */
export function Dial({ value, label, size = 168, color = 'var(--amber)' }: { value: number; label: string; size?: number; color?: string }) {
  const v = Math.max(0, Math.min(1, value))
  const start = -220
  const sweep = 260
  const angle = start + sweep * v
  const r = 70
  const ticks = Array.from({ length: 27 }, (_, i) => i)
  const polar = (deg: number, rad: number) => {
    const a = ((deg + 90) * Math.PI) / 180
    return [100 + rad * Math.cos(a), 100 + rad * Math.sin(a)]
  }
  const arc = (from: number, to: number, rad: number) => {
    const [x1, y1] = polar(from, rad)
    const [x2, y2] = polar(to, rad)
    return `M ${x1} ${y1} A ${rad} ${rad} 0 ${to - from > 180 ? 1 : 0} 1 ${x2} ${y2}`
  }
  const [nx, ny] = polar(angle, 58)
  return (
    <svg viewBox="0 0 200 200" width={size} height={size} role="img" aria-label={`${label} ${Math.round(v * 100)}%`}>
      <defs>
        <radialGradient id="dial-face" cx="50%" cy="40%" r="65%">
          <stop offset="0" stopColor="#1d2140" />
          <stop offset="1" stopColor="#07080f" />
        </radialGradient>
        <linearGradient id="dial-rim" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#4b4f73" />
          <stop offset="1" stopColor="#0b0c18" />
        </linearGradient>
      </defs>
      <circle cx="100" cy="100" r="96" fill="url(#dial-rim)" />
      <circle cx="100" cy="100" r="90" fill="url(#dial-face)" stroke="rgba(0,0,0,.6)" />
      <path d={arc(start, start + sweep, r)} stroke="rgba(255,255,255,.08)" strokeWidth="8" fill="none" strokeLinecap="round" />
      {v > 0.003 && (
        <path d={arc(start, angle, r)} stroke={color} strokeWidth="8" fill="none" strokeLinecap="round" style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
      )}
      {ticks.map((i) => {
        const deg = start + (sweep / 26) * i
        const [x1, y1] = polar(deg, 82)
        const [x2, y2] = polar(deg, i % 5 === 0 ? 74 : 78)
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(255,255,255,.35)" strokeWidth={i % 5 === 0 ? 1.6 : 0.8} />
      })}
      <line x1="100" y1="100" x2={nx} y2={ny} stroke="#ffe7b8" strokeWidth="2.4" strokeLinecap="round" style={{ transition: 'all 1s cubic-bezier(.22,1,.36,1)' }} />
      <circle cx="100" cy="100" r="7" fill="#2a2e4a" stroke="#ffd27a" strokeWidth="1.5" />
      <text x="100" y="138" textAnchor="middle" fill="#f4efe6" fontFamily="JetBrains Mono" fontSize="22" fontWeight="700">
        {Math.round(v * 100)}%
      </text>
      <text x="100" y="156" textAnchor="middle" fill="#8d8aa3" fontFamily="JetBrains Mono" fontSize="8.5" letterSpacing="2">
        {label.toUpperCase()}
      </text>
    </svg>
  )
}

export function Meter({ value, c1, c2 }: { value: number; c1?: string; c2?: string }) {
  return (
    <div className="meter">
      <i style={{ width: `${Math.min(100, value * 100)}%`, '--c1': c1, '--c2': c2 } as CSSProperties} />
    </div>
  )
}

export function Skeleton({ h = 120, style }: { h?: number; style?: CSSProperties }) {
  return <div className="skeleton" style={{ height: h, ...style }} />
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="display">{title}</div>
      {children && <div style={{ marginTop: 8 }}>{children}</div>}
    </div>
  )
}

export function Stat({ label, value, hint, color }: { label: string; value: ReactNode; hint?: ReactNode; color?: string }) {
  return (
    <div className="glass pad stat">
      <div className="eyebrow">{label}</div>
      <div className="stat-value" style={{ color }}>{value}</div>
      {hint && <div className="muted" style={{ fontSize: 12.5 }}>{hint}</div>}
    </div>
  )
}
