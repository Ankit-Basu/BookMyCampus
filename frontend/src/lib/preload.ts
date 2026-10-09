import type { QueryClient } from '@tanstack/react-query'
import { addDays, format, startOfWeek } from 'date-fns'

import { api } from './api'

/** Route chunks, so we can warm them before the user clicks. */
export const pages = {
  explore: () => import('../pages/Explore'),
  resource: () => import('../pages/ResourcePage'),
  bookings: () => import('../pages/MyBookings'),
  booking: () => import('../pages/BookingPage'),
  scan: () => import('../pages/Scan'),
  map: () => import('../pages/CampusMap'),
  profile: () => import('../pages/Profile'),
  approvals: () => import('../pages/Approvals'),
  admin: () => import('../pages/admin/Admin'),
}

const idle = (fn: () => void) =>
  'requestIdleCallback' in window ? window.requestIdleCallback(fn, { timeout: 3000 }) : setTimeout(fn, 1200)

/** After first paint, quietly download + parse every page chunk one by one while the CPU is idle. */
export function warmRoutes(isManager: boolean) {
  const order: (keyof typeof pages)[] = ['resource', 'bookings', 'booking', 'scan', 'map', 'profile']
  if (isManager) order.push('approvals', 'admin')
  let i = 0
  const next = () => {
    if (i >= order.length) return
    pages[order[i++]]().finally(() => idle(next))
  }
  idle(next)
}

/** The week the resource calendar opens on — shared so a hover-prefetch hits the same cache key. */
export function initialWeek() {
  const s = startOfWeek(new Date(), { weekStartsOn: 1 })
  return { from: format(s, 'yyyy-MM-dd'), to: format(addDays(s, 7), 'yyyy-MM-dd') }
}

export function prefetchResource(qc: QueryClient, id: number) {
  const w = initialWeek()
  qc.prefetchQuery({ queryKey: ['resource', String(id)], queryFn: () => api.get(`/resources/${id}`).then((x) => x.data), staleTime: 30_000 })
  qc.prefetchQuery({
    queryKey: ['availability', id, w.from, w.to],
    queryFn: () => api.get(`/resources/${id}/availability`, { params: w }).then((x) => x.data),
    staleTime: 15_000,
  })
}
