import { differenceInMinutes, format, formatDistanceToNowStrict, isToday, isTomorrow } from 'date-fns'

export const fmtTime = (iso: string) => format(new Date(iso), 'HH:mm')
export const fmtDate = (iso: string) => format(new Date(iso), 'EEE d MMM')
export const fmtDay = (iso: string) => {
  const d = new Date(iso)
  if (isToday(d)) return 'Today'
  if (isTomorrow(d)) return 'Tomorrow'
  return format(d, 'EEE d MMM')
}
export const fmtRange = (s: string, e: string) => `${fmtDay(s)} · ${fmtTime(s)}–${fmtTime(e)}`
export const fmtRelative = (iso: string) => formatDistanceToNowStrict(new Date(iso), { addSuffix: true })
export const durationLabel = (s: string, e: string) => {
  const m = differenceInMinutes(new Date(e), new Date(s))
  return m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ''}` : `${m}m`
}
export const inr = (n: number) =>
  n >= 1e7 ? `₹${(n / 1e7).toFixed(2)} Cr` : n >= 1e5 ? `₹${(n / 1e5).toFixed(1)} L` : `₹${n.toLocaleString('en-IN')}`
export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`

export const STATUS_COLOR: Record<string, string> = {
  pending: 'var(--amber)',
  confirmed: 'var(--sky)',
  checked_in: 'var(--mint)',
  completed: 'var(--muted)',
  rejected: 'var(--coral)',
  cancelled: 'var(--faint)',
  released: 'var(--rose)',
  displaced: 'var(--violet)',
}

export const ROLE_LABEL: Record<string, string> = {
  student: 'Student',
  faculty: 'Faculty',
  staff: 'Staff',
  custodian: 'Custodian',
  dept_head: 'Head of Dept.',
  facility_manager: 'Facility Manager',
  admin: 'Administrator',
}

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
