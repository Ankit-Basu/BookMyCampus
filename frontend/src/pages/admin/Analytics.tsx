import { useQuery } from '@tanstack/react-query'
import { format, subDays } from 'date-fns'
import { useMemo, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Reveal } from '../../components/motion'
import { Meter, Skeleton } from '../../components/ui'
import { api } from '../../lib/api'
import { inr, pct, WEEKDAYS } from '../../lib/format'

type Row = {
  resource_id: number
  code: string
  name: string
  type: string
  type_color: string
  department: string | null
  image: string
  value_inr: number
  supply_hours: number
  teaching_hours: number
  booked_hours: number
  used_hours: number
  maintenance_hours: number
  utilisation: number
  idle_value_inr: number
  bookings: number
  no_shows: number
}
type Roll = { key: string; label: string; utilisation: number; supply_hours: number; used_hours: number; teaching_hours: number; resources: number }
type Util = {
  totals: { supply_hours: number; used_hours: number; teaching_hours: number; booked_hours: number; idle_value_inr: number; utilisation: number }
  by_resource: Row[]
  by_type: Roll[]
  by_department: Roll[]
  idle_ranking: Row[]
  daily: { date: string; utilisation: number; used_hours: number }[]
}

const AXIS = { stroke: 'rgba(255,255,255,.35)', fontSize: 11, fontFamily: 'JetBrains Mono' }
const GRID = 'rgba(255,255,255,.06)'

function ChartTip({ active, payload, label, fmt }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string; fmt?: (v: number) => string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      <div className="mono muted" style={{ fontSize: 11 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="mono" style={{ fontSize: 13 }}>{fmt ? fmt(p.value) : p.value}</div>
      ))}
    </div>
  )
}

function Heatmap({ from, to }: { from: string; to: string }) {
  const { data } = useQuery({ queryKey: ['heatmap', from, to], queryFn: () => api.get<{ cells: number[][]; peak: number }>('/analytics/heatmap', { params: { from, to } }).then((r) => r.data) })
  const [hover, setHover] = useState<{ d: number; h: number } | null>(null)
  if (!data) return <Skeleton h={240} />
  const hours = Array.from({ length: 15 }, (_, i) => i + 7)
  return (
    <div className="heatmap">
      <div className="hm-grid" style={{ gridTemplateColumns: `42px repeat(${hours.length}, 1fr)` }}>
        <span />
        {hours.map((h) => (
          <span key={h} className="hm-hour mono">{h}</span>
        ))}
        {data.cells.map((row, d) => (
          <div key={d} style={{ display: 'contents' }}>
            <span className="hm-day mono">{WEEKDAYS[d]}</span>
            {hours.map((h) => {
              const v = row[h] / data.peak
              return (
                <span
                  key={h}
                  className="hm-cell"
                  style={{ '--v': v } as CSSProperties}
                  onMouseEnter={() => setHover({ d, h })}
                  onMouseLeave={() => setHover(null)}
                />
              )
            })}
          </div>
        ))}
      </div>
      <div className="spread" style={{ marginTop: 10, fontSize: 12 }}>
        <span className="mono muted">
          {hover ? `${WEEKDAYS[hover.d]} ${String(hover.h).padStart(2, '0')}:00 · ${data.cells[hover.d][hover.h].toFixed(1)} resource-hours` : 'hover a cell'}
        </span>
        <span className="row" style={{ gap: 6 }}>
          <span className="muted">quiet</span>
          <span className="hm-scale" />
          <span className="muted">busiest</span>
        </span>
      </div>
    </div>
  )
}

function RollBars({ rows }: { rows: Roll[] }) {
  return (
    <div className="col" style={{ gap: 12 }}>
      {rows.map((r) => (
        <div key={r.key}>
          <div className="spread" style={{ fontSize: 13, marginBottom: 6 }}>
            <span>{r.label}</span>
            <span className="mono">
              {pct(r.utilisation)} <span className="muted" style={{ fontSize: 11 }}>· {Math.round(r.used_hours + r.teaching_hours)}/{Math.round(r.supply_hours)}h</span>
            </span>
          </div>
          <Meter value={r.utilisation} />
        </div>
      ))}
    </div>
  )
}

export default function Analytics() {
  const [days, setDays] = useState(30)
  const [type, setType] = useState('')
  const range = useMemo(() => ({ from: format(subDays(new Date(), days), 'yyyy-MM-dd'), to: format(subDays(new Date(), -1), 'yyyy-MM-dd') }), [days])
  const { data: types } = useQuery({ queryKey: ['types'], queryFn: () => api.get<{ id: number; name: string }[]>('/resource-types').then((r) => r.data) })
  const { data: u } = useQuery({ queryKey: ['util', range, type], queryFn: () => api.get<Util>('/analytics/utilisation', { params: { ...range, type: type || undefined } }).then((r) => r.data) })
  const { data: ns } = useQuery({ queryKey: ['noshows-a', range], queryFn: () => api.get('/analytics/noshows', { params: range }).then((r) => r.data) })
  const { data: demand } = useQuery({ queryKey: ['demand', range], queryFn: () => api.get('/analytics/demand', { params: range }).then((r) => r.data) })
  const { data: turn } = useQuery({ queryKey: ['turn', range], queryFn: () => api.get('/analytics/approvals', { params: range }).then((r) => r.data) })
  const { data: down } = useQuery({ queryKey: ['down', range], queryFn: () => api.get('/analytics/downtime', { params: range }).then((r) => r.data) })
  const { data: quotas } = useQuery({ queryKey: ['quotas-a'], queryFn: () => api.get('/analytics/quotas').then((r) => r.data) })

  return (
    <div className="col" style={{ gap: 18 }}>
      <div className="filter-row glass-flat">
        <div className="seg sm">
          {[7, 30, 90].map((d) => (
            <button key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{d}d</button>
          ))}
        </div>
        <select className="input" style={{ width: 'auto', height: 34, fontSize: 13 }} value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All resource types</option>
          {types?.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <span className="mono muted" style={{ fontSize: 12, marginLeft: 'auto' }}>{range.from} → {range.to}</span>
      </div>

      {!u ? (
        <Skeleton h={300} />
      ) : (
        <>
          <div className="kpi-grid four">
            <div className="glass pad kpi"><div className="eyebrow">Utilisation</div><div className="stat-value" style={{ color: 'var(--amber-hi)' }}>{pct(u.totals.utilisation, 1)}</div></div>
            <div className="glass pad kpi"><div className="eyebrow">Open hours (supply)</div><div className="stat-value">{Math.round(u.totals.supply_hours).toLocaleString()}</div></div>
            <div className="glass pad kpi"><div className="eyebrow">Used + taught hours</div><div className="stat-value">{Math.round(u.totals.used_hours + u.totals.teaching_hours).toLocaleString()}</div></div>
            <div className="glass pad kpi"><div className="eyebrow">Idle asset value</div><div className="stat-value" style={{ color: 'var(--coral)' }}>{inr(u.totals.idle_value_inr)}</div></div>
          </div>

          <Reveal className="glass pad">
            <div className="h2">Daily utilisation</div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>Share of open hours in use — campus-wide</div>
            <div style={{ height: 240 }}>
              <ResponsiveContainer>
                <AreaChart data={u.daily.map((d) => ({ ...d, label: format(new Date(d.date), 'd MMM') }))} margin={{ left: -12, right: 8, top: 8 }}>
                  <defs>
                    <linearGradient id="ua" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="#f5a524" stopOpacity={0.45} />
                      <stop offset="1" stopColor="#f5a524" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={48} />
                  <Tooltip content={<ChartTip fmt={(v) => pct(v, 1)} />} cursor={{ stroke: 'rgba(255,255,255,.25)' }} />
                  <Area type="monotone" dataKey="utilisation" stroke="#f5a524" strokeWidth={2} fill="url(#ua)" activeDot={{ r: 5, stroke: '#10132a', strokeWidth: 2 }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Reveal>

          <div className="two-col">
            <Reveal className="glass pad">
              <div className="h2" style={{ marginBottom: 14 }}>By resource type</div>
              <RollBars rows={u.by_type} />
            </Reveal>
            <Reveal className="glass pad">
              <div className="h2" style={{ marginBottom: 14 }}>By department</div>
              <RollBars rows={u.by_department} />
            </Reveal>
          </div>

          <Reveal className="glass pad">
            <div className="spread" style={{ marginBottom: 6 }}>
              <div>
                <div className="h2">Idle capacity ranking</div>
                <div className="muted" style={{ fontSize: 13 }}>Asset value × unused share — expensive things nobody books float to the top.</div>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>#</th><th>Resource</th><th>Type</th><th>Value</th><th style={{ width: '22%' }}>Utilisation</th><th>Idle value</th></tr>
                </thead>
                <tbody>
                  {u.idle_ranking.map((r, i) => (
                    <tr key={r.resource_id}>
                      <td className="mono muted">{String(i + 1).padStart(2, '0')}</td>
                      <td>
                        <Link to={`/resources/${r.resource_id}`} className="row" style={{ gap: 10 }}>
                          <img src={r.image.replace('w=1200', 'w=120')} alt="" className="thumb" />
                          <span><span style={{ display: 'block', fontWeight: 600 }}>{r.name}</span><span className="mono muted" style={{ fontSize: 11 }}>{r.code}</span></span>
                        </Link>
                      </td>
                      <td><span className="tag" style={{ '--c': r.type_color } as CSSProperties}>{r.type}</span></td>
                      <td className="mono">{inr(r.value_inr)}</td>
                      <td><div className="row" style={{ gap: 8 }}><div className="grow"><Meter value={r.utilisation} c1="#7a1f12" c2="#ff6f59" /></div><span className="mono" style={{ fontSize: 12, width: 40 }}>{pct(r.utilisation)}</span></div></td>
                      <td className="mono" style={{ color: 'var(--coral)' }}>{inr(r.idle_value_inr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Reveal>
        </>
      )}

      <div className="two-col">
        <Reveal className="glass pad">
          <div className="h2">When is campus busy?</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>Occupied resource-hours by weekday and hour (classes + bookings)</div>
          <Heatmap from={range.from} to={range.to} />
        </Reveal>
        <Reveal className="glass pad">
          <div className="h2">Demand vs supply</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>Share of requests that hit an already-taken slot — high means “buy another one”.</div>
          {demand ? (
            <div style={{ height: 250 }}>
              <ResponsiveContainer>
                <BarChart data={demand} layout="vertical" margin={{ left: 20, right: 16 }}>
                  <CartesianGrid stroke={GRID} horizontal={false} />
                  <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                  <YAxis type="category" dataKey="type" tick={{ ...AXIS, fill: '#c9c4d6' }} tickLine={false} axisLine={false} width={110} />
                  <Tooltip content={<ChartTip fmt={(v) => `${pct(v, 1)} of requests clashed`} />} cursor={{ fill: 'rgba(255,255,255,.04)' }} />
                  <Bar dataKey="pressure" fill="#f5a524" radius={[0, 4, 4, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Skeleton h={250} />
          )}
        </Reveal>
      </div>

      <div className="two-col">
        <Reveal className="glass pad">
          <div className="spread">
            <div className="h2">No-shows</div>
            {ns && <span className="mono" style={{ color: 'var(--rose)' }}>{pct(ns.rate, 1)} overall</span>}
          </div>
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table className="table">
              <thead><tr><th>Person</th><th>Booked</th><th>Missed</th><th>Rate</th></tr></thead>
              <tbody>
                {ns?.by_user.slice(0, 8).map((x: { user_id: number; name: string; total: number; noshows: number; rate: number; restricted_until: string | null }) => (
                  <tr key={x.user_id}>
                    <td>{x.name} {x.restricted_until && new Date(x.restricted_until) > new Date() && <span className="tag" style={{ '--c': 'var(--coral)' } as CSSProperties}>paused</span>}</td>
                    <td className="mono">{x.total}</td>
                    <td className="mono">{x.noshows}</td>
                    <td className="mono" style={{ color: x.rate > 0.15 ? 'var(--rose)' : undefined }}>{pct(x.rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>
        <Reveal className="glass pad">
          <div className="h2">Approval turnaround</div>
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table className="table">
              <thead><tr><th>Type · step</th><th>Decisions</th><th>Avg wait</th><th>Approved</th></tr></thead>
              <tbody>
                {turn?.map((t: { type: string; step: string; decisions: number; avg_hours: number; approved: number }) => (
                  <tr key={t.type + t.step}>
                    <td>{t.type} <span className="muted">· {t.step}</span></td>
                    <td className="mono">{t.decisions}</td>
                    <td className="mono">{t.avg_hours < 1 ? `${Math.round(t.avg_hours * 60)}m` : `${t.avg_hours.toFixed(1)}h`}</td>
                    <td className="mono">{pct(t.approved / t.decisions)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>
      </div>

      <div className="two-col">
        <Reveal className="glass pad">
          <div className="h2">Maintenance downtime</div>
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table className="table">
              <thead><tr><th>Resource</th><th>Events</th><th>Planned</th><th>Breakdown</th></tr></thead>
              <tbody>
                {down?.map((d: { resource_id: number; name: string; events: number; scheduled_hours: number; breakdown_hours: number }) => (
                  <tr key={d.resource_id}>
                    <td>{d.name}</td>
                    <td className="mono">{d.events}</td>
                    <td className="mono">{d.scheduled_hours}h</td>
                    <td className="mono" style={{ color: d.breakdown_hours ? 'var(--coral)' : undefined }}>{d.breakdown_hours}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>
        <Reveal className="glass pad">
          <div className="h2">Departmental quota · this week</div>
          <div className="col" style={{ gap: 12, marginTop: 14 }}>
            {quotas?.rows.map((q: { department: string; department_name: string; resource_type: string; limit_hours: number; used_hours: number; share: number }) => (
              <div key={q.department + q.resource_type}>
                <div className="spread" style={{ fontSize: 13, marginBottom: 6 }}>
                  <span>{q.department} <span className="muted">· {q.resource_type}</span></span>
                  <span className="mono">{q.used_hours}/{q.limit_hours}h</span>
                </div>
                <Meter value={q.share} c1={q.share > 0.9 ? '#7a1f12' : undefined} c2={q.share > 0.9 ? '#ff6f59' : undefined} />
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </div>
  )
}
