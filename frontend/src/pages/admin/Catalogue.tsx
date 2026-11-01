import { FileCsv, PencilSimple, Plus, Printer } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { Drawer, Modal, StatusTag, TypeTag, Select } from '../../components/ui'
import { api, blobUrl, errorMessage } from '../../lib/api'
import { inr } from '../../lib/format'
import type { Resource, ResourceDetail } from '../../lib/types'

const SAMPLE = `code,name,type,department,building,floor,room,capacity,features,value_inr,image_url,description
LAB-34-IOT,IoT Studio,Laboratory,CSE,Block 34 · School of CSE,5,508,24,Sensors|Soldering|AC,1800000,,Hands-on IoT studio
EQ-DRONE-01,Survey Drone,Equipment,MEC,Block 26 · Mechanical,1,120,1,4K camera|RTK GPS,350000,,Mapping drone with RTK`

type Opt = { id: number; name?: string; code?: string; label?: string }

function Editor({ id, onClose }: { id: number | 'new' | null; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: r } = useQuery({ queryKey: ['resource', String(id)], queryFn: () => api.get<ResourceDetail>(`/resources/${id}`).then((x) => x.data), enabled: typeof id === 'number' })
  const { data: types } = useQuery({ queryKey: ['types'], queryFn: () => api.get<Opt[]>('/resource-types').then((x) => x.data) })
  const { data: depts } = useQuery({ queryKey: ['depts'], queryFn: () => api.get<Opt[]>('/departments').then((x) => x.data) })
  const { data: locs } = useQuery({ queryKey: ['locations'], queryFn: () => api.get<Opt[]>('/locations').then((x) => x.data) })
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => (id === 'new' ? api.post('/resources', body) : api.patch(`/resources/${id}`, body)),
    onSuccess: () => {
      toast.success('Saved')
      qc.invalidateQueries({ queryKey: ['resources'] })
      qc.invalidateQueries({ queryKey: ['resource'] })
      onClose()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const ready = id === 'new' || r
  return (
    <Drawer open={id !== null} onClose={onClose} title={id === 'new' ? 'New resource' : `Edit ${r?.name ?? ''}`}>
      {ready && (
        <form
          key={String(id)}
          className="col"
          style={{ gap: 12 }}
          onSubmit={(e) => {
            e.preventDefault()
            const f = new FormData(e.currentTarget)
            save.mutate({
              code: f.get('code'),
              name: f.get('name'),
              type: Number(f.get('type')),
              department: f.get('department') ? Number(f.get('department')) : null,
              location: f.get('location') ? Number(f.get('location')) : null,
              capacity: Number(f.get('capacity')),
              value_inr: Number(f.get('value_inr')),
              status: f.get('status'),
              image_url: f.get('image_url'),
              description: f.get('description'),
              features: String(f.get('features')).split(',').map((s) => s.trim()).filter(Boolean),
            })
          }}
        >
          <div className="grid" style={{ gridTemplateColumns: '1fr 2fr', gap: 12 }}>
            <label className="field"><span>Code</span><input name="code" className="input" defaultValue={r?.code} required /></label>
            <label className="field"><span>Name</span><input name="name" className="input" defaultValue={r?.name} required /></label>
          </div>
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <label className="field"><span>Type</span>
              <Select name="type" defaultValue={r?.type}>{types?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>
            </label>
            <label className="field"><span>Department</span>
              <Select name="department" defaultValue={r?.department ?? ''}><option value="">—</option>{depts?.map((d) => <option key={d.id} value={d.id}>{d.code}</option>)}</Select>
            </label>
          </div>
          <label className="field"><span>Location</span>
            <Select name="location" defaultValue={r?.location ?? ''}><option value="">—</option>{locs?.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}</Select>
          </label>
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <label className="field"><span>Capacity</span><input name="capacity" type="number" min={1} className="input" defaultValue={r?.capacity ?? 1} /></label>
            <label className="field"><span>Value (₹)</span><input name="value_inr" type="number" min={0} className="input" defaultValue={r?.value_inr ?? 0} /></label>
            <label className="field"><span>Status</span>
              <Select name="status" defaultValue={r?.status ?? 'active'}><option value="active">Active</option><option value="down">Out of service</option><option value="retired">Retired</option></Select>
            </label>
          </div>
          <label className="field"><span>Features (comma separated)</span><input name="features" className="input" defaultValue={r?.features.join(', ')} /></label>
          <label className="field"><span>Photo URL</span><input name="image_url" className="input" defaultValue={r?.image_url} placeholder="https://…" /></label>
          <label className="field"><span>Description</span><textarea name="description" className="input" defaultValue={r?.description} /></label>
          <button className="key key-amber key-lg" disabled={save.isPending}>Save resource</button>
        </form>
      )}
    </Drawer>
  )
}

export default function Catalogue() {
  const qc = useQueryClient()
  const [edit, setEdit] = useState<number | 'new' | null>(null)
  const [imp, setImp] = useState(false)
  const [csv, setCsv] = useState(SAMPLE)
  const [q, setQ] = useState('')
  const [qr, setQr] = useState<{ url: string; name: string } | null>(null)
  const { data } = useQuery({ queryKey: ['resources', 'admin'], queryFn: () => api.get<Resource[]>('/resources', { params: { include_retired: 1 } }).then((r) => r.data) })
  const doImport = useMutation({
    mutationFn: () => api.post('/resources/bulk-import', { csv }).then((r) => r.data),
    onSuccess: (d) => {
      toast.success(`Imported: ${d.created} new, ${d.updated} updated`, { description: d.errors.length ? `${d.errors.length} row(s) failed — row ${d.errors[0].row}: ${d.errors[0].error}` : undefined })
      qc.invalidateQueries({ queryKey: ['resources'] })
      if (!d.errors.length) setImp(false)
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const rows = data?.filter((r) => !q || `${r.name} ${r.code} ${r.type_name} ${r.building}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <div className="glass pad">
      <div className="spread" style={{ marginBottom: 14, flexWrap: 'wrap' }}>
        <input className="input" style={{ maxWidth: 320 }} placeholder="Filter catalogue…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="row">
          <button className="key key-ghost" onClick={() => setImp(true)}><FileCsv /> Bulk import</button>
          <button className="key key-amber" onClick={() => setEdit('new')}><Plus weight="bold" /> New resource</button>
        </div>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Resource</th><th>Type</th><th>Location</th><th>Cap.</th><th>Value</th><th>Status</th><th /></tr></thead>
          <tbody>
            {rows?.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link to={`/resources/${r.id}`} className="row" style={{ gap: 10 }}>
                    {r.cover ? <img src={r.cover.replace('w=1200', 'w=120')} alt="" className="thumb" /> : <span className="thumb stripes" />}
                    <span><span style={{ display: 'block', fontWeight: 600 }}>{r.name}</span><span className="mono muted" style={{ fontSize: 11 }}>{r.code}</span></span>
                  </Link>
                </td>
                <td><TypeTag name={r.type_name} color={r.type_color} icon={r.type_icon} /></td>
                <td className="muted" style={{ fontSize: 13 }}>{r.location_label}</td>
                <td className="mono">{r.capacity}</td>
                <td className="mono">{inr(r.value_inr)}</td>
                <td><StatusTag status={r.status === 'active' ? 'checked_in' : r.status === 'down' ? 'rejected' : 'cancelled'} label={r.status === 'active' ? 'Active' : r.status === 'down' ? 'Down' : 'Retired'} /></td>
                <td>
                  <div className="row" style={{ gap: 6 }}>
                    <button className="key key-ghost key-sm key-icon" title="Check-in poster" onClick={async () => setQr({ url: await blobUrl(`/resources/${r.id}/qr`), name: r.name })}><Printer size={15} /></button>
                    <button className="key key-ghost key-sm key-icon" title="Edit" onClick={() => setEdit(r.id)}><PencilSimple size={15} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Editor id={edit} onClose={() => setEdit(null)} />
      <Modal open={imp} onClose={() => setImp(false)} width={760}>
        <div className="col">
          <div className="h2">Bulk import catalogue</div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>Paste CSV (or edit the sample). Existing codes update in place; features split on “|”.</p>
          <textarea className="input mono" style={{ minHeight: 200, fontSize: 12 }} value={csv} onChange={(e) => setCsv(e.target.value)} />
          <div className="row">
            <label className="key key-ghost">
              <FileCsv /> Load file
              <input type="file" accept=".csv" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f) setCsv(await f.text()) }} />
            </label>
            <div className="grow" />
            <button className="key key-amber" disabled={doImport.isPending} onClick={() => doImport.mutate()}>Import</button>
          </div>
        </div>
      </Modal>
      <Modal open={!!qr} onClose={() => setQr(null)} width={400}>
        <div className="col" style={{ alignItems: 'center', textAlign: 'center' }}>
          <div className="eyebrow">Check-in poster</div>
          <div className="display" style={{ fontSize: 28 }}>{qr?.name}</div>
          <div className="qr-plate" style={{ width: 230 }}>{qr && <img src={qr.url} alt="" />}</div>
          <button className="key key-amber" onClick={() => window.print()}><Printer /> Print</button>
        </div>
      </Modal>
    </div>
  )
}
