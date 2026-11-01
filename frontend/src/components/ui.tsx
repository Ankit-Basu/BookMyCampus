import {
  Basketball,
  Camera,
  ChalkboardTeacher,
  Cube,
  Desktop,
  Flask,
  Microscope,
  MusicNotes,
  Printer,
  PresentationChart,
  Robot,
  SwimmingPool,
  UsersThree,
  Van,
} from '@phosphor-icons/react'
import { Children, isValidElement, useState, type CSSProperties, type ReactElement, type ReactNode } from 'react'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/shadcn/dialog'
import {
  Select as RSelect,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/shadcn/sheet'

import { STATUS_COLOR } from '../lib/format'

const ICONS: Record<string, typeof Cube> = {
  chalkboard: ChalkboardTeacher,
  flask: Flask,
  microscope: Microscope,
  presentation: PresentationChart,
  basketball: Basketball,
  'users-three': UsersThree,
  van: Van,
  desktop: Desktop,
  printer: Printer,
  camera: Camera,
  robot: Robot,
  music: MusicNotes,
  pool: SwimmingPool,
  cube: Cube,
}

export const ICON_KEYS = Object.keys(ICONS)

export function TypeIcon({ icon, size = 18, color }: { icon?: string; size?: number; color?: string }) {
  const I = (icon && ICONS[icon]) || Cube
  return <I size={size} weight="duotone" color={color} />
}

export function StatusTag({ status, label }: { status: string; label?: string }) {
  return (
    <span className="tag" style={{ '--c': STATUS_COLOR[status] ?? 'var(--foreground)' } as CSSProperties}>
      <span className="led" style={{ '--c': STATUS_COLOR[status], width: 6, height: 6 } as CSSProperties} />
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

/** Side panel (shadcn Sheet: focus trap, Esc, scroll lock). Same API as before. */
export function Drawer({ open, onClose, title, children, width = 520 }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: number }) {
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="drawer-panel" style={{ width: `min(${width}px, 100vw)`, maxWidth: '100vw' }} data-lenis-prevent aria-describedby={undefined}>
        <SheetTitle className="h2" style={{ marginBottom: 18, paddingRight: 34 }}>{title}</SheetTitle>
        <SheetDescription className="sr-only">Details panel</SheetDescription>
        {children}
      </SheetContent>
    </Sheet>
  )
}

export function Modal({ open, onClose, children, width = 460 }: { open: boolean; onClose: () => void; children: ReactNode; width?: number }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="modal-panel" style={{ width: `min(${width}px, calc(100vw - 32px))`, maxWidth: 'calc(100vw - 32px)' }} aria-describedby={undefined}>
        <DialogTitle className="sr-only">Dialog</DialogTitle>
        <DialogDescription className="sr-only">Dialog content</DialogDescription>
        {children}
      </DialogContent>
    </Dialog>
  )
}

const NONE = '__none__'
type OptionEl = ReactElement<{ value?: string | number; children?: ReactNode; label?: string }>

/**
 * Glass dropdown (shadcn Select) that is a drop-in for `<select>`: takes the same `<option>` /
 * `<optgroup>` children, `value` + `onChange(e => e.target.value)`, or `name` + `defaultValue` for
 * forms read with FormData (a hidden input carries the real value, including the empty "none").
 */
export function Select({ value, defaultValue, onChange, name, children, style, className, required }: {
  value?: string | number | null
  defaultValue?: string | number | null
  onChange?: (e: { target: { value: string } }) => void
  name?: string
  children: ReactNode
  style?: CSSProperties
  className?: string
  required?: boolean
}) {
  const [inner, setInner] = useState(String(defaultValue ?? ''))
  const current = value !== undefined ? String(value ?? '') : inner
  const renderOption = (o: OptionEl) => {
    const v = String(o.props.value ?? '')
    return <SelectItem key={v} value={v === '' ? NONE : v} className="select-item">{o.props.children}</SelectItem>
  }
  const nodes = Children.toArray(children).filter(isValidElement) as OptionEl[]
  return (
    <>
      {name && <input type="hidden" name={name} value={current} required={required} />}
      <RSelect
        value={current === '' ? NONE : current}
        onValueChange={(v) => {
          const real = v === NONE ? '' : v
          setInner(real)
          onChange?.({ target: { value: real } })
        }}
      >
        <SelectTrigger className={`input select-trigger ${className ?? ''}`} style={style}>
          <SelectValue placeholder="Choose…" />
        </SelectTrigger>
        <SelectContent className="pop-glass" position="popper" sideOffset={6}>
          {nodes.map((n, i) =>
            n.type === 'optgroup' ? (
              <SelectGroup key={i}>
                <SelectLabel className="select-label">{n.props.label}</SelectLabel>
                {(Children.toArray(n.props.children).filter(isValidElement) as OptionEl[]).map(renderOption)}
              </SelectGroup>
            ) : (
              renderOption(n)
            ),
          )}
        </SelectContent>
      </RSelect>
    </>
  )
}

/** Analog instrument dial — utilisation reads like a gauge on a lab bench. */
export function Dial({ value, label, size = 168, color = 'var(--brand)' }: { value: number; label: string; size?: number; color?: string }) {
  const v = Math.max(0, Math.min(1, value))
  const start = -220
  const sweep = 260
  const angle = start + sweep * v
  const r = 72
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
  const [nx, ny] = polar(angle, 60)
  return (
    <svg viewBox="0 0 200 200" width={size} height={size} role="img" aria-label={`${label} ${Math.round(v * 100)}%`}>
      <circle cx="100" cy="100" r="97" fill="var(--dial-rim)" />
      <circle cx="100" cy="100" r="91" fill="var(--dial-face)" />
      <path d={arc(start, start + sweep, r)} stroke="var(--line-2)" strokeWidth="9" fill="none" strokeLinecap="round" />
      {v > 0.003 && <path d={arc(start, angle, r)} stroke={color} strokeWidth="9" fill="none" strokeLinecap="round" />}
      {ticks.map((i) => {
        const deg = start + (sweep / 26) * i
        const [x1, y1] = polar(deg, 86)
        const [x2, y2] = polar(deg, i % 5 === 0 ? 80 : 83)
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--fg-3)" strokeWidth={i % 5 === 0 ? 1.4 : 0.7} />
      })}
      <line x1="100" y1="100" x2={nx} y2={ny} stroke="var(--foreground)" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="100" cy="100" r="6.5" fill="var(--dial-face)" stroke="var(--foreground)" strokeWidth="2" />
      <text x="100" y="140" textAnchor="middle" fill="var(--foreground)" fontFamily="Bricolage Grotesque" fontSize="26" fontWeight="700">
        {Math.round(v * 100)}%
      </text>
      <text x="100" y="157" textAnchor="middle" fill="var(--fg-3)" fontFamily="Geist Mono" fontSize="7.2" letterSpacing="1.4">
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
