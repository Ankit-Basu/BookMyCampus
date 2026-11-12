export type Role = 'student' | 'faculty' | 'staff' | 'custodian' | 'dept_head' | 'facility_manager' | 'admin'

export type User = {
  phone: string
  id: number
  username: string
  name: string
  first_name: string
  last_name: string
  email: string
  role: Role
  role_label: string
  department: number | null
  department_code: string | null
  is_restricted: boolean
  restricted_until: string | null
  restriction_reason: string
  is_manager: boolean
  can_book_recurring: boolean
  calendar_token: string
  custodian_of: number[]
  noshow_count: number
}

export type Resource = {
  is_saved: boolean
  id: number
  code: string
  name: string
  description: string
  type: number
  type_name: string
  type_slug: string
  type_color: string
  type_icon: string
  department: number | null
  department_code: string | null
  location: number | null
  location_label: string | null
  building: string | null
  capacity: number
  features: string[]
  cover: string
  value_inr: number
  status: 'active' | 'down' | 'retired'
  requires_approval: boolean
  /** False when the signed-in user's role may not book this type, e.g. a student on a lab. */
  can_book: boolean
}

export type ResourceDetail = Resource & {
  images: { id: number; src: string; caption: string }[]
  attributes: { key: string; value: string }[]
  custodian_list: { id: number; name: string; role: Role }[]
  location_detail: { id: number; building: string; floor: string; room: string; latitude: string | null; longitude: string | null; label: string } | null
  allowed_roles: Role[]
  requires_checkin: boolean
  image_url: string
}

export type Approval = {
  id: number
  order: number
  step_name: string
  approver_role: string
  status: 'waiting' | 'pending' | 'approved' | 'rejected' | 'cancelled'
  decided_by_name: string | null
  decided_at: string | null
  activated_at: string | null
  comment: string
}

export type BookingStatus = 'pending' | 'confirmed' | 'checked_in' | 'completed' | 'rejected' | 'cancelled' | 'released' | 'displaced'

export type Booking = {
  id: number
  reference: string
  resource: number
  resource_name: string
  resource_code: string
  resource_cover: string
  resource_type: string
  resource_color: string
  requires_checkin: boolean
  location: string | null
  user: number
  user_name: string
  title: string
  purpose: string
  on_behalf_of: string
  attendees: number
  start: string
  end: string
  status: BookingStatus
  status_label: string
  status_note: string
  recurrence: number | null
  occurrence_index: number | null
  series_size: number | null
  created_at: string
  decided_at: string | null
  approvals: Approval[]
  checkin: { checked_in_at: string; method: string; checked_out_at: string | null } | null
  qr_token?: string
}

export type Availability = {
  resource: number
  slot_minutes: number
  rules: { weekdays: number[]; open: string; close: string; min_duration: number; max_duration: number; min_lead: number; max_advance_days: number }[]
  open: { start: string; end: string }[]
  busy: { start: string; end: string; kind: 'booking' | 'timetable' | 'maintenance'; label: string; booking_id?: number | null; status?: string; mine?: boolean }[]
  blackouts: { start: string; end: string; title: string }[]
  free: { start: string; end: string }[]
  policy: { grace_minutes: number }
}

export type Notification = {
  id: number
  kind: string
  title: string
  body: string
  link: string
  booking: number | null
  read_at: string | null
  created_at: string
}
