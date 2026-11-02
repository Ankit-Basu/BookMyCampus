import { Check, Repeat, Stamp, UsersThree, X } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { Empty, PageHeader, Skeleton } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { durationLabel, fmtRange, fmtRelative } from '../lib/format'
import type { Booking } from '../lib/types'

type QueueItem = Booking & {
  current_step: { id: number; name: string; role: string; activated_at: string }
  requester_department: string | null
  requester_role: string
}

function ApprovalCard({ item }: { item: QueueItem }) {
  const qc = useQueryClient()
  const [comment, setComment] = useState('')
  const [stamp, setStamp] = useState<'approved' | 'rejected' | null>(null)
  const decide = useMutation({
    mutationFn: ({ approve, series }: { approve: boolean; series?: boolean }) =>
      api.post(`/bookings/${item.id}/${approve ? 'approve' : 'reject'}`, { comment, series }).then((r) => r.data),
    onSuccess: (d, v) => {
      setStamp(v.approve ? 'approved' : 'rejected')
      toast.success(v.approve ? `Approved${d.decided > 1 ? ` · ${d.decided} in series` : ''}` : 'Rejected — slot released')
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['approval-queue'] })
      }, 900)
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const step = item.approvals.findIndex((a) => a.id === item.current_step.id)
  return (
    <motion.div layout initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 80, rotate: 3 }} className="glass approval-card" style={{ '--c': item.resource_color } as CSSProperties}>
      <AnimatePresence>
        {stamp && (
          <motion.div className={`rubber-stamp ${stamp}`} initial={{ scale: 2.4, opacity: 0, rotate: -24 }} animate={{ scale: 1, opacity: 1, rotate: -12 }} transition={{ type: 'spring', stiffness: 500, damping: 18 }}>
            {stamp}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="approval-img">{item.resource_cover && <img src={item.resource_cover.replace('w=1200', 'w=500')} alt="" />}</div>
      <div className="pad" style={{ flex: 1, minWidth: 0 }}>
        <div className="spread" style={{ alignItems: 'flex-start' }}>
          <div style={{ minWidth: 0 }}>
            <div className="eyebrow">{item.resource_type} · {item.reference}</div>
            <Link to={`/resources/${item.resource}`} className="h2" style={{ display: 'block', marginTop: 4 }}>{item.resource_name}</Link>
          </div>
          <span className="tag" style={{ '--c': 'var(--brand)' } as CSSProperties}>
            <Stamp size={12} /> Step {step + 1}/{item.approvals.length} · {item.current_step.name}
          </span>
        </div>
        <div className="mono" style={{ marginTop: 10, color: 'var(--brand-ink)' }}>
          {fmtRange(item.start, item.end)} <span className="muted">· {durationLabel(item.start, item.end)}</span>
        </div>
        <div style={{ marginTop: 8, fontWeight: 600 }}>“{item.title}”</div>
        {item.purpose && <p className="muted" style={{ margin: '4px 0 0', fontSize: 13 }}>{item.purpose}</p>}
        <div className="row wrap muted" style={{ gap: 14, fontSize: 12.5, marginTop: 10 }}>
          <span>{item.user_name} · {item.requester_role}{item.requester_department ? ` · ${item.requester_department}` : ''}</span>
          <span className="row" style={{ gap: 4 }}><UsersThree size={13} /> {item.attendees}</span>
          {item.on_behalf_of && <span className="tag" style={{ '--c': 'var(--info)' } as CSSProperties}>For class {item.on_behalf_of}</span>}
          {item.series_size && <span className="row" style={{ gap: 4 }}><Repeat size={13} /> part of a {item.series_size}-date series</span>}
          <span>waiting {fmtRelative(item.current_step.activated_at).replace(' ago', '')}</span>
        </div>
        <div className="row wrap" style={{ marginTop: 14, gap: 8 }}>
          <input className="input grow" style={{ height: 38, minWidth: 160 }} placeholder="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
          <button className="key key-mint key-sm" disabled={decide.isPending} onClick={() => decide.mutate({ approve: true })}>
            <Check weight="bold" /> Approve
          </button>
          {item.recurrence && (
            <button className="key key-ghost key-sm" disabled={decide.isPending} onClick={() => decide.mutate({ approve: true, series: true })}>
              Approve series
            </button>
          )}
          <button className="key key-coral key-sm" disabled={decide.isPending} onClick={() => decide.mutate({ approve: false })}>
            <X weight="bold" /> Reject
          </button>
        </div>
      </div>
    </motion.div>
  )
}

export default function Approvals() {
  const { data, isLoading } = useQuery({ queryKey: ['approval-queue'], queryFn: () => api.get<QueueItem[]>('/approvals/queue').then((r) => r.data) })
  return (
    <div className="page">
      <PageHeader
        eyebrow="HOD desk"
        title={<>Approval <em>queue</em></>}
        sub="Requests waiting on you. The slot is already held for the requester — approving confirms it, rejecting hands it back to everyone."
        actions={<span className="mono muted">{data?.length ?? 0} waiting</span>}
      />
      {isLoading ? (
        <div className="col">{[1, 2, 3].map((i) => <Skeleton key={i} h={180} />)}</div>
      ) : data?.length ? (
        <div className="col" style={{ gap: 16 }}>
          <AnimatePresence mode="popLayout">
            {data.map((item) => (
              <ApprovalCard key={item.current_step.id} item={item} />
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <Empty title="Inbox zero.">Nothing needs your stamp right now.</Empty>
      )}
    </div>
  )
}
