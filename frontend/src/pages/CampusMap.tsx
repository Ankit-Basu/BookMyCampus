import { Buildings, Crosshair, MapPin } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { addHours, startOfHour } from 'date-fns'
import L from 'leaflet'
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { MapContainer, Marker, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { Link } from 'react-router-dom'

import { PageHeader, TypeIcon } from '../components/ui'
import { api } from '../lib/api'
import type { Resource } from '../lib/types'

// Lovely Professional University, Phagwara (NH-44). Block pins are approximate and editable in the
// catalogue (Location.latitude / longitude).
const LPU_CENTER: [number, number] = [31.2552, 75.7046]

type Loc = { id: number; building: string; latitude: string | null; longitude: string | null; label: string }

function pin(count: number, free: number, active: boolean) {
  return L.divIcon({
    className: '',
    html: `<div class="map-pin ${active ? 'active' : ''}"><span>${count}</span><i style="--f:${count ? free / count : 0}"></i></div>`,
    iconSize: [44, 52],
    iconAnchor: [22, 50],
  })
}

function FlyTo({ to }: { to: [number, number] | null }) {
  const map = useMap()
  useEffect(() => {
    if (to) map.flyTo(to, to === LPU_CENTER ? 16 : 18, { duration: 0.9 })
  }, [map, to])
  return null
}

export default function CampusMap() {
  const [selected, setSelected] = useState<string | null>(null)
  const [fly, setFly] = useState<[number, number] | null>(null)
  const window_ = useMemo(() => {
    const s = startOfHour(new Date())
    return { free_from: s.toISOString(), free_to: addHours(s, 1).toISOString() }
  }, [])
  const { data: locations } = useQuery({ queryKey: ['locations'], queryFn: () => api.get<Loc[]>('/locations').then((r) => r.data) })
  const { data: all } = useQuery({ queryKey: ['resources', 'map'], queryFn: () => api.get<Resource[]>('/resources').then((r) => r.data) })
  const { data: free } = useQuery({ queryKey: ['resources', 'map-free'], queryFn: () => api.get<Resource[]>('/resources', { params: window_ }).then((r) => r.data) })
  const freeIds = new Set(free?.map((r) => r.id))

  const buildings = useMemo(() => {
    const m = new Map<string, { name: string; lat: number; lng: number; resources: Resource[] }>()
    locations?.forEach((l) => {
      if (!l.latitude || !l.longitude) return
      if (!m.has(l.building)) m.set(l.building, { name: l.building, lat: Number(l.latitude), lng: Number(l.longitude), resources: [] })
    })
    all?.forEach((r) => r.building && m.get(r.building)?.resources.push(r))
    return [...m.values()]
  }, [locations, all])

  const current = buildings.find((b) => b.name === selected)

  return (
    <div className="page">
      <PageHeader
        eyebrow="LPU · Phagwara · Punjab"
        title={<>Campus <em>map</em></>}
        sub="Every block with bookable space. The ring on each pin shows how much is free this hour."
      />
      <div className="map-layout">
        <div className="glass map-shell" data-lenis-prevent>
          <MapContainer center={LPU_CENTER} zoom={16} scrollWheelZoom style={{ height: '100%', width: '100%' }} zoomControl={false}>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              className="night-tiles"
              maxZoom={19}
            />
            {buildings.map((b) => (
              <Marker
                key={b.name}
                position={[b.lat, b.lng]}
                icon={pin(b.resources.length, b.resources.filter((r) => freeIds.has(r.id)).length, b.name === selected)}
                eventHandlers={{ click: () => setSelected(b.name) }}
              >
                <Tooltip direction="top" offset={[0, -46]} className="map-tip">
                  {b.name}
                </Tooltip>
              </Marker>
            ))}
            <FlyTo to={fly} />
          </MapContainer>
          <button className="key key-ghost key-sm map-recenter" onClick={() => { setSelected(null); setFly(LPU_CENTER) }}>
            <Crosshair /> Recenter
          </button>
        </div>
        <aside className="glass pad map-side" data-lenis-prevent>
          {current ? (
            <>
              <div className="eyebrow">Block</div>
              <div className="display" style={{ fontSize: 34, margin: '4px 0 14px' }}>{current.name}</div>
              <div className="col" style={{ gap: 10 }}>
                {current.resources.map((r) => (
                  <Link key={r.id} to={`/resources/${r.id}`} className="map-res" style={{ '--c': r.type_color } as CSSProperties}>
                    <img src={r.cover.replace('w=1200', 'w=200')} alt="" />
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div className="truncate" style={{ fontWeight: 600 }}>{r.name}</div>
                      <div className="row muted" style={{ gap: 6, fontSize: 12 }}>
                        <TypeIcon icon={r.type_icon} size={13} color={r.type_color} /> {r.type_name}
                      </div>
                    </div>
                    {freeIds.has(r.id) ? (
                      <span className="tag" style={{ '--c': 'var(--mint)' } as CSSProperties}>Free now</span>
                    ) : (
                      <span className="tag" style={{ '--c': 'var(--coral)' } as CSSProperties}>Busy</span>
                    )}
                  </Link>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className="eyebrow">Blocks</div>
              <div className="col" style={{ gap: 8, marginTop: 12 }}>
                {buildings.map((b) => (
                  <button
                    key={b.name}
                    className="map-block"
                    onClick={() => {
                      setSelected(b.name)
                      setFly([b.lat, b.lng])
                    }}
                  >
                    <Buildings size={18} weight="duotone" color="var(--amber)" />
                    <span className="grow" style={{ textAlign: 'left' }}>{b.name}</span>
                    <span className="mono muted" style={{ fontSize: 12 }}>
                      {b.resources.filter((r) => freeIds.has(r.id)).length}/{b.resources.length} free
                    </span>
                  </button>
                ))}
              </div>
              <p className="muted" style={{ fontSize: 12, marginTop: 16 }}>
                <MapPin size={12} /> Pins are approximate; custodians can adjust coordinates in the catalogue.
              </p>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
