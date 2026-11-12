import { ArrowRight, Clock, MapPin, UsersThree } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { addDays, addHours, format, setHours, setMinutes, startOfMinute } from 'date-fns'
import { useMemo, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { Empty, PageHeader, Skeleton, TypeIcon } from '../components/ui'
import { api } from '../lib/api'

type Spot = {
  id: number
  code: string
  name: string
  type_name: string
  type_icon: string
  type_color: string
  building: string | null
  location_label: string | null
  capacity: number
  features: string[]
  free_until: string
  free_from?: string
  minutes: number
}

const span = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ''}` : `${m}m`)

/** Times a student usually plans around: right now, the next free period, or tomorrow morning. */
function presets(now: Date) {
  const tomorrow = startOfMinute(setMinutes(setHours(addDays(now, 1), 10), 0))
  return [
    { key: 'now', label: 'Now', at: null as Date | null },
    { key: '1h', label: 'In 1 hour', at: startOfMinute(addHours(now, 1)) },
    { key: '3h', label: 'In 3 hours', at: startOfMinute(addHours(now, 3)) },
    { key: 'tomorrow', label: 'Tomorrow 10:00', at: tomorrow },
  ]
}

function SpotCard({ s, soon }: { s: Spot; soon?: boolean }) {
  return (
    <Link to={`/resources/${s.id}`} className="glass study-card" style={{ '--c': s.type_color } as CSSProperties}>
      <div className="spread" style={{ gap: 10 }}>
        <span className="tag"><TypeIcon icon={s.type_icon} size={12} /> {s.type_name}</span>
        <span className="mono muted" style={{ fontSize: 11 }}>{s.code}</span>
      </div>
      <div className="h3" style={{ margin: '10px 0 2px' }}>{s.name}</div>
      {s.location_label && <div className="row muted truncate" style={{ gap: 6, fontSize: 13 }}><MapPin size={14} /> {s.location_label}</div>}
      <div className="study-free">
        <Clock size={16} weight="bold" />
        {soon && s.free_from
          ? <span>Free from <strong>{format(new Date(s.free_from), 'HH:mm')}</strong> until {format(new Date(s.free_until), 'HH:mm')}</span>
          : <span>Free until <strong>{format(new Date(s.free_until), 'HH:mm')}</strong> · {span(s.minutes)}</span>}
      </div>
      <div className="spread muted" style={{ fontSize: 12.5 }}>
        <span className="row" style={{ gap: 5 }}><UsersThree size={14} /> {s.capacity} seats</span>
        <ArrowRight size={14} />
      </div>
    </Link>
  )
}

/** Empty classrooms and labs a student can sit in between classes. Nothing to book: just where to go. */
export default function Study() {
  const now = useMemo(() => new Date(), [])
  const options = useMemo(() => presets(now), [now])
  const [choice, setChoice] = useState('now')
  const at = options.find((o) => o.key === choice)?.at ?? null
  const { data, isLoading } = useQuery({
    queryKey: ['study-spots', choice],
    queryFn: () => api.get<{ at: string; free: Spot[]; soon: Spot[] }>('/study-spots', { params: at ? { at: at.toISOString() } : {} }).then((r) => r.data),
    refetchInterval: choice === 'now' ? 60000 : false,
  })
  const buildings = useMemo(() => new Set(data?.free.map((s) => s.building).filter(Boolean)).size, [data])

  return (
    <div className="page">
      <PageHeader
        eyebrow="Study spots"
        title={<>Find an <em>empty room</em></>}
        sub="Classrooms and labs with no class or booking on, and how long they stay free. Walk in and sit down: there's nothing to book."
      />

      <div className="row wrap" style={{ gap: 8, marginBottom: 22 }} role="group" aria-label="When">
        {options.map((o) => (
          <button key={o.key} className={`chip ${choice === o.key ? 'on' : ''}`} onClick={() => setChoice(o.key)}>
            {o.label}{o.at ? ` · ${format(o.at, o.key === 'tomorrow' ? 'EEE' : 'HH:mm')}` : ''}
          </button>
        ))}
      </div>

      {isLoading && <div className="study-grid">{[0, 1, 2].map((i) => <Skeleton key={i} h={170} />)}</div>}

      {data && (
        <>
          <div className="eyebrow" style={{ marginBottom: 12 }}>
            {data.free.length ? `${data.free.length} free ${choice === 'now' ? 'right now' : `at ${format(new Date(data.at), 'EEE HH:mm')}`} across ${buildings} block${buildings === 1 ? '' : 's'}` : 'Free rooms'}
          </div>
          {data.free.length ? (
            <div className="study-grid">{data.free.map((s) => <SpotCard key={s.id} s={s} />)}</div>
          ) : (
            <Empty title="Nothing free then.">Rooms are closed or all in use. Try another time.</Empty>
          )}
          {data.soon.length > 0 && (
            <>
              <div className="eyebrow" style={{ margin: '28px 0 12px' }}>Freeing up within the hour</div>
              <div className="study-grid">{data.soon.map((s) => <SpotCard key={s.id} s={s} soon />)}</div>
            </>
          )}
        </>
      )}
    </div>
  )
}
