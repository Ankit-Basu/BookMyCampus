import { Buildings, MapPin, PencilSimple, Plus, Trash } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import L from 'leaflet'
import { useState, type CSSProperties } from 'react'
import { MapContainer, Marker, TileLayer, useMapEvents } from 'react-leaflet'
import { toast } from 'sonner'

import { Drawer, ICON_KEYS, TypeIcon, Select } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { isPolicyAdmin, useAuth } from '../../lib/auth'
import { ROLE_LABEL } from '../../lib/format'

type RType = { id: number; name: string; slug: string; description: string; icon: string; color: string; allowed_roles: string[]; requires_checkin: boolean; resource_count: number }
type Loc = { id: number; campus: string; building: string; floor: string; room: string; latitude: string | null; longitude: string | null; label: string }
type Dept = { id: number; code: string; name: string; head: number | null; head_name: string | null }
type Person = { id: number; name: string; role: string; department: number | null }

const LPU_CENTER: [number, number] = [31.2552, 75.7046]
const SWATCHES = ['#F5B544', '#3EE6C1', '#8B7CFF', '#FF7A59', '#5FD068', '#5AB2FF', '#E66BD3', '#FFD27A', '#FF5D8F', '#9AE6FF']
const BOOKER_ROLES = ['student', 'faculty', 'staff', 'custodian', 'dept_head']

function useCrud<T extends { id: number }>(key: string, path: string) {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: [key], queryFn: () => api.get<T[]>(path).then((r) => r.data) })
  const done = (msg: string) => () => {
    qc.invalidateQueries({ queryKey: [key] })
    qc.invalidateQueries({ queryKey: ['facets'] })
    toast.success(msg)
  }
  const onError = (e: unknown) => toast.error(errorMessage(e))
  const save = useMutation({
    mutationFn: (b: Partial<T>) => (b.id ? api.patch(`${path}/${b.id}`, b) : api.post(path, b)),
    onSuccess: done('Saved'),
    onError,
  })
  const remove = useMutation({ mutationFn: (id: number) => api.delete(`${path}/${id}`), onSuccess: done('Deleted'), onError })
  return { list, save, remove }
}

const pinIcon = L.divIcon({ className: '', html: '<div class="map-pin active"><span>●</span></div>', iconSize: [44, 52], iconAnchor: [22, 50] })

function PickPoint({ value, onChange }: { value: [number, number] | null; onChange: (p: [number, number]) => void }) {
  useMapEvents({ click: (e) => onChange([Number(e.latlng.lat.toFixed(6)), Number(e.latlng.lng.toFixed(6))]) })
  return value ? <Marker position={value} icon={pinIcon} draggable eventHandlers={{ dragend: (e) => { const ll = (e.target as L.Marker).getLatLng(); onChange([Number(ll.lat.toFixed(6)), Number(ll.lng.toFixed(6))]) } }} /> : null
}

// ---------------------------------------------------------------- resource types

function Types({ canEdit }: { canEdit: boolean }) {
  const { list, save, remove } = useCrud<RType>('types-admin', '/resource-types')
  const [draft, setDraft] = useState<Partial<RType> | null>(null)
  return (
    <section className="glass pad">
      <div className="spread" style={{ marginBottom: 14 }}>
        <div>
          <div className="h2">Resource types</div>
          <div className="muted" style={{ fontSize: 13 }}>Each type carries its colour, icon, who may book it and whether check-in is required.</div>
        </div>
        {canEdit && (
          <button className="key key-amber" onClick={() => setDraft({ name: '', icon: 'cube', color: SWATCHES[0], allowed_roles: [], requires_checkin: true, description: '' })}>
            <Plus weight="bold" /> New type
          </button>
        )}
      </div>
      <div className="md-grid">
        {list.data?.map((t) => (
          <div key={t.id} className="md-card" style={{ '--c': t.color } as CSSProperties}>
            <div className="md-icon"><TypeIcon icon={t.icon} size={22} /></div>
            <div className="grow" style={{ minWidth: 0 }}>
              <div className="h3">{t.name}</div>
              <div className="muted truncate" style={{ fontSize: 12 }}>
                {t.resource_count} resources · {t.requires_checkin ? 'check-in' : 'no check-in'} · {t.allowed_roles.length ? t.allowed_roles.map((r) => ROLE_LABEL[r]).join(', ') : 'everyone'}
              </div>
            </div>
            {canEdit && <button className="key key-ghost key-sm key-icon" onClick={() => setDraft(t)}><PencilSimple size={15} /></button>}
          </div>
        ))}
      </div>
      <Drawer open={!!draft} onClose={() => setDraft(null)} title={draft?.id ? `Edit ${draft.name}` : 'New resource type'}>
        {draft && (
          <div className="col" style={{ gap: 14 }}>
            <label className="field"><span>Name</span><input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="e.g. Robotics Bay" /></label>
            <label className="field"><span>Description</span><textarea className="input" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
            <div className="field">
              <span>Icon</span>
              <div className="row wrap" style={{ gap: 6 }}>
                {ICON_KEYS.map((k) => (
                  <button type="button" key={k} className={`chip ${draft.icon === k ? 'on' : ''}`} style={{ width: 42, justifyContent: 'center', padding: 0 }} onClick={() => setDraft({ ...draft, icon: k })}>
                    <TypeIcon icon={k} size={17} />
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <span>Colour</span>
              <div className="row wrap" style={{ gap: 8 }}>
                {SWATCHES.map((c) => (
                  <button type="button" key={c} className={`swatch ${draft.color?.toLowerCase() === c.toLowerCase() ? 'on' : ''}`} style={{ background: c }} onClick={() => setDraft({ ...draft, color: c })} aria-label={c} />
                ))}
                <input type="color" value={draft.color} onChange={(e) => setDraft({ ...draft, color: e.target.value })} className="swatch-input" />
              </div>
            </div>
            <div className="field">
              <span>Who may book (none selected = everyone)</span>
              <div className="row wrap" style={{ gap: 6 }}>
                {BOOKER_ROLES.map((r) => (
                  <button type="button" key={r} className={`chip ${draft.allowed_roles?.includes(r) ? 'on' : ''}`} onClick={() => setDraft({ ...draft, allowed_roles: draft.allowed_roles?.includes(r) ? draft.allowed_roles.filter((x) => x !== r) : [...(draft.allowed_roles ?? []), r] })}>
                    {ROLE_LABEL[r]}
                  </button>
                ))}
              </div>
            </div>
            <div className="spread glass-flat" style={{ padding: 14 }}>
              <div>
                <div className="h3">Require QR check-in</div>
                <div className="muted" style={{ fontSize: 12 }}>Unchecked bookings auto-release after the grace period</div>
              </div>
              <button type="button" className={`rocker ${draft.requires_checkin ? 'on' : ''}`} onClick={() => setDraft({ ...draft, requires_checkin: !draft.requires_checkin })} />
            </div>
            <div className="row">
              {draft.id && (
                <button className="key key-coral" onClick={() => { if (confirm(`Delete type “${draft.name}”?`)) remove.mutate(draft.id!, { onSuccess: () => setDraft(null) }) }}>
                  <Trash /> Delete
                </button>
              )}
              <div className="grow" />
              <button className="key key-amber" disabled={!draft.name || save.isPending} onClick={() => save.mutate(draft, { onSuccess: () => setDraft(null) })}>Save type</button>
            </div>
          </div>
        )}
      </Drawer>
    </section>
  )
}

// ---------------------------------------------------------------- locations with a map pin picker

function Locations() {
  const { list, save, remove } = useCrud<Loc>('locations', '/locations')
  const [draft, setDraft] = useState<Partial<Loc> | null>(null)
  const point: [number, number] | null = draft?.latitude && draft?.longitude ? [Number(draft.latitude), Number(draft.longitude)] : null
  const buildings = [...new Set(list.data?.map((l) => l.building))]
  return (
    <section className="glass pad">
      <div className="spread" style={{ marginBottom: 14 }}>
        <div>
          <div className="h2">Locations</div>
          <div className="muted" style={{ fontSize: 13 }}>Blocks, floors and rooms. The pin you drop here is what the campus map shows.</div>
        </div>
        <button className="key key-amber" onClick={() => setDraft({ campus: 'LPU · Phagwara', building: '', floor: '', room: '', latitude: null, longitude: null })}>
          <Plus weight="bold" /> New location
        </button>
      </div>
      <div className="table-wrap" data-lenis-prevent style={{ maxHeight: 420, overflowY: 'auto' }}>
        <table className="table">
          <thead><tr><th>Building</th><th>Floor</th><th>Room</th><th>Map pin</th><th /></tr></thead>
          <tbody>
            {list.data?.map((l) => (
              <tr key={l.id}>
                <td><Buildings size={14} color="var(--brand)" /> {l.building}</td>
                <td className="mono">{l.floor || '—'}</td>
                <td className="mono">{l.room || '—'}</td>
                <td className="mono muted" style={{ fontSize: 12 }}>{l.latitude ? `${Number(l.latitude).toFixed(4)}, ${Number(l.longitude).toFixed(4)}` : <span style={{ color: 'var(--bad)' }}>not placed</span>}</td>
                <td><button className="key key-ghost key-sm key-icon" onClick={() => setDraft(l)}><PencilSimple size={15} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Drawer open={!!draft} onClose={() => setDraft(null)} title={draft?.id ? 'Edit location' : 'New location'} width={600}>
        {draft && (
          <div className="col" style={{ gap: 12 }}>
            <label className="field">
              <span>Building / block</span>
              <input className="input" list="bmc-buildings" value={draft.building} onChange={(e) => setDraft({ ...draft, building: e.target.value })} placeholder="Block 37 · School of Design" />
              <datalist id="bmc-buildings">{buildings.map((b) => <option key={b} value={b} />)}</datalist>
            </label>
            <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <label className="field"><span>Floor</span><input className="input" value={draft.floor} onChange={(e) => setDraft({ ...draft, floor: e.target.value })} /></label>
              <label className="field"><span>Room</span><input className="input" value={draft.room} onChange={(e) => setDraft({ ...draft, room: e.target.value })} /></label>
            </div>
            <div className="field">
              <span><MapPin size={12} /> Click the map to drop the pin (drag to fine-tune)</span>
              <div className="picker-map" data-lenis-prevent>
                <MapContainer center={point ?? LPU_CENTER} zoom={17} style={{ height: '100%', width: '100%' }}>
                  <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className="night-tiles" maxZoom={19} />
                  <PickPoint value={point} onChange={([lat, lng]) => setDraft({ ...draft, latitude: String(lat), longitude: String(lng) })} />
                </MapContainer>
              </div>
              <div className="mono muted" style={{ fontSize: 11 }}>{point ? `${point[0]}, ${point[1]}` : 'No pin yet'}</div>
            </div>
            <div className="row">
              {draft.id && (
                <button className="key key-coral" onClick={() => { if (confirm('Delete this location?')) remove.mutate(draft.id!, { onSuccess: () => setDraft(null) }) }}>
                  <Trash />
                </button>
              )}
              <div className="grow" />
              <button className="key key-amber" disabled={!draft.building || save.isPending} onClick={() => save.mutate(draft, { onSuccess: () => setDraft(null) })}>Save location</button>
            </div>
          </div>
        )}
      </Drawer>
    </section>
  )
}

// ---------------------------------------------------------------- departments

function Departments({ canEdit }: { canEdit: boolean }) {
  const { list, save, remove } = useCrud<Dept>('depts', '/departments')
  const { data: people } = useQuery({ queryKey: ['people-heads'], queryFn: () => api.get<Person[]>('/users').then((r) => r.data) })
  const [draft, setDraft] = useState<Partial<Dept> | null>(null)
  return (
    <section className="glass pad">
      <div className="spread" style={{ marginBottom: 14 }}>
        <div>
          <div className="h2">Departments</div>
          <div className="muted" style={{ fontSize: 13 }}>The head receives department-level approvals and sees department utilisation.</div>
        </div>
        {canEdit && <button className="key key-amber" onClick={() => setDraft({ code: '', name: '', head: null })}><Plus weight="bold" /> New department</button>}
      </div>
      <div className="md-grid">
        {list.data?.map((d) => (
          <div key={d.id} className="md-card" style={{ '--c': 'var(--chart-4)' } as CSSProperties}>
            <div className="md-icon mono" style={{ fontSize: 13, fontWeight: 700 }}>{d.code}</div>
            <div className="grow" style={{ minWidth: 0 }}>
              <div className="h3 truncate">{d.name}</div>
              <div className="muted truncate" style={{ fontSize: 12 }}>Head: {d.head_name || <span style={{ color: 'var(--bad)' }}>not assigned</span>}</div>
            </div>
            {canEdit && <button className="key key-ghost key-sm key-icon" onClick={() => setDraft(d)}><PencilSimple size={15} /></button>}
          </div>
        ))}
      </div>
      <Drawer open={!!draft} onClose={() => setDraft(null)} title={draft?.id ? `Edit ${draft.code}` : 'New department'}>
        {draft && (
          <div className="col" style={{ gap: 12 }}>
            <div className="grid" style={{ gridTemplateColumns: '1fr 2fr', gap: 12 }}>
              <label className="field"><span>Code</span><input className="input mono" value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value.toUpperCase() })} placeholder="SOD" /></label>
              <label className="field"><span>Name</span><input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="School of Design" /></label>
            </div>
            <label className="field">
              <span>Head of department</span>
              <Select value={draft.head ?? ''} onChange={(e) => setDraft({ ...draft, head: e.target.value ? Number(e.target.value) : null })}>
                <option value="">— not assigned —</option>
                {people?.filter((p) => ['dept_head', 'faculty', 'facility_manager', 'admin'].includes(p.role)).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} · {ROLE_LABEL[p.role]}</option>
                ))}
              </Select>
            </label>
            <div className="row">
              {draft.id && (
                <button className="key key-coral" onClick={() => { if (confirm(`Delete ${draft.code}?`)) remove.mutate(draft.id!, { onSuccess: () => setDraft(null) }) }}>
                  <Trash />
                </button>
              )}
              <div className="grow" />
              <button className="key key-amber" disabled={!draft.code || !draft.name || save.isPending} onClick={() => save.mutate(draft, { onSuccess: () => setDraft(null) })}>Save department</button>
            </div>
          </div>
        )}
      </Drawer>
    </section>
  )
}

export default function MasterData() {
  const { user } = useAuth()
  const admin = isPolicyAdmin(user)
  return (
    <div className="col" style={{ gap: 18 }}>
      <Types canEdit={admin} />
      <Locations />
      <Departments canEdit={admin} />
    </div>
  )
}
