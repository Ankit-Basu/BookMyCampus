import { Buildings, Lightning, MagnifyingGlass, SealCheck, Stamp, UsersThree } from '@phosphor-icons/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { addHours, startOfHour } from 'date-fns'
import { memo, useDeferredValue, useMemo, type CSSProperties } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Reveal, Tilt } from '../components/motion'
import GlareHover from '../components/reactbits/GlareHover'
import { Empty, PageHeader, Skeleton, TypeIcon } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { prefetchResource } from '../lib/preload'
import type { Resource } from '../lib/types'

type Facets = {
  types: { type__id: number; type__name: string; type__slug: string; type__color: string; type__icon: string; n: number }[]
  departments: { department__code: string; department__name: string; n: number }[]
  buildings: { location__building: string; n: number }[]
  features: { name: string; n: number }[]
  max_capacity: number
}

/** Memoised: filtering re-renders the grid, but unchanged cards skip reconciliation entirely. */
export const ResourceCard = memo(function ResourceCard({ r, index = 0 }: { r: Resource; index?: number }) {
  const qc = useQueryClient()
  // Warm the detail page + its first calendar week while the pointer is still travelling.
  const prefetch = () => prefetchResource(qc, r.id)
  return (
    // CSS entrance (compositor-only) instead of JS layout animation: no per-card measuring on filter.
    <div className="rcell card-in" style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}>
      <Tilt max={5}>
        <Link to={`/resources/${r.id}`} className="rcard" onPointerEnter={prefetch} onFocus={prefetch} style={{ '--c': r.type_color } as CSSProperties}>
          <GlareHover glareColor="#ffffff" glareOpacity={0.18} glareAngle={-35} glareSize={260} transitionDuration={700} background="transparent" borderColor="transparent" borderRadius="20px" width="100%" height="auto">
            <div className="rcard-inner">
              <div className="rcard-img">
                {r.cover ? <img src={r.cover.replace('w=1200', 'w=640')} alt="" loading="lazy" decoding="async" /> : <div className="stripes" style={{ height: '100%' }} />}
                <span className="rcard-type">
                  <TypeIcon icon={r.type_icon} size={14} /> {r.type_name}
                </span>
                {r.status === 'down' && <span className="rcard-down">Out of service</span>}
              </div>
              <div className="rcard-body">
                <div className="spread" style={{ alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="h3 truncate" style={{ fontSize: 16.5 }}>{r.name}</div>
                    <div className="muted truncate" style={{ fontSize: 12.5 }}>{r.location_label}</div>
                  </div>
                  <span className="mono muted" style={{ fontSize: 10.5, whiteSpace: 'nowrap' }}>{r.code}</span>
                </div>
                <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
                  <span className="tag"><UsersThree size={12} /> {r.capacity}</span>
                  {r.requires_approval ? (
                    <span className="tag" style={{ '--c': 'var(--amber)' } as CSSProperties}><Stamp size={12} /> Approval</span>
                  ) : (
                    <span className="tag" style={{ '--c': 'var(--mint)' } as CSSProperties}><SealCheck size={12} /> Instant</span>
                  )}
                  {r.features.slice(0, 2).map((f) => (
                    <span key={f} className="tag hide-sm">{f}</span>
                  ))}
                </div>
              </div>
            </div>
          </GlareHover>
        </Link>
      </Tilt>
    </div>
  )
})

export default function Explore() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const dq = useDeferredValue(q)
  const types = params.get('type')?.split(',').filter(Boolean) ?? []
  const building = params.get('building') ?? ''
  const minCap = Number(params.get('min_capacity') ?? 0)
  const freeNow = params.get('free') === '1'

  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params)
    if (v) p.set(k, v)
    else p.delete(k)
    setParams(p, { replace: true })
  }
  const toggleType = (slug: string) => {
    const next = types.includes(slug) ? types.filter((t) => t !== slug) : [...types, slug]
    set('type', next.join(','))
  }

  const window_ = useMemo(() => {
    const s = startOfHour(new Date())
    return { from: s.toISOString(), to: addHours(s, 1).toISOString() }
  }, [])

  const { data: facets } = useQuery({ queryKey: ['facets'], queryFn: () => api.get<Facets>('/resources/facets').then((r) => r.data) })
  const { data, isLoading } = useQuery({
    queryKey: ['resources', dq, types.join(','), building, minCap, freeNow],
    queryFn: () =>
      api
        .get<Resource[]>('/resources', {
          params: {
            q: dq || undefined,
            type: types.join(',') || undefined,
            building: building || undefined,
            min_capacity: minCap || undefined,
            free_from: freeNow ? window_.from : undefined,
            free_to: freeNow ? window_.to : undefined,
          },
        })
        .then((r) => r.data),
    placeholderData: (prev) => prev,
  })

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${greeting}, ${user?.first_name || user?.username}`}
        title={<>What do you need <em>today?</em></>}
        sub="Rooms, labs, instruments, halls, courts and vehicles across LPU — live availability, timetable-aware."
      />

      <Reveal>
        <div className="glass search-bar" data-reveal>
          <MagnifyingGlass size={20} className="muted" />
          <input
            className="search-input"
            value={q}
            onChange={(e) => set('q', e.target.value)}
            placeholder="Try “GPU”, “Block 34”, “microscope”, “turf”…"
            autoFocus
          />
          <div className="row" style={{ gap: 10 }}>
            <Lightning size={16} weight={freeNow ? 'fill' : 'regular'} color={freeNow ? 'var(--amber)' : undefined} className={freeNow ? '' : 'muted'} />
            <span className="hide-sm" style={{ fontSize: 13 }}>Free this hour</span>
            <button className={`rocker ${freeNow ? 'on' : ''}`} onClick={() => set('free', freeNow ? null : '1')} aria-label="Only free this hour" />
          </div>
        </div>

        <div className="facet-row" data-reveal>
          <button className={`chip ${types.length === 0 ? 'on' : ''}`} onClick={() => set('type', null)}>
            All
          </button>
          {facets?.types.map((t) => (
            <button
              key={t.type__slug}
              className={`chip ${types.includes(t.type__slug) ? 'on' : ''}`}
              onClick={() => toggleType(t.type__slug)}
              style={types.includes(t.type__slug) ? undefined : ({ '--c': t.type__color } as CSSProperties)}
            >
              <TypeIcon icon={t.type__icon} size={15} color={t.type__color} />
              {t.type__name}
              <span className="count">{t.n}</span>
            </button>
          ))}
        </div>

        <div className="facet-row" data-reveal style={{ marginTop: 0 }}>
          <div className="row" style={{ gap: 8 }}>
            <Buildings size={16} className="muted" />
            <select className="input" style={{ height: 34, width: 'auto', minWidth: 210, fontSize: 13 }} value={building} onChange={(e) => set('building', e.target.value || null)}>
              <option value="">All blocks & buildings</option>
              {facets?.buildings.map((b) => (
                <option key={b.location__building} value={b.location__building}>
                  {b.location__building} ({b.n})
                </option>
              ))}
            </select>
          </div>
          <div className="row" style={{ gap: 10 }}>
            <UsersThree size={16} className="muted" />
            <span className="mono" style={{ fontSize: 12, width: 64 }}>{minCap ? `≥ ${minCap}` : 'any size'}</span>
            <input
              type="range"
              className="slider"
              min={0}
              max={Math.min(facets?.max_capacity ?? 200, 200)}
              step={5}
              value={minCap}
              onChange={(e) => set('min_capacity', e.target.value === '0' ? null : e.target.value)}
            />
          </div>
          <span className="mono muted" style={{ fontSize: 12, marginLeft: 'auto' }}>
            {data ? `${data.length} result${data.length === 1 ? '' : 's'}` : ''}
          </span>
        </div>
      </Reveal>

      {isLoading && !data ? (
        <div className="rgrid">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} h={300} />)}</div>
      ) : data?.length ? (
        <div className="rgrid">
          {data.map((r, i) => (
            <ResourceCard key={r.id} r={r} index={i} />
          ))}
        </div>
      ) : (
        <Empty title="Nothing matches that.">Loosen a filter — or turn off “free this hour”.</Empty>
      )}
    </div>
  )
}
