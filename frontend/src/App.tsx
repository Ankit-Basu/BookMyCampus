import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import AppShell from './components/AppShell'
import { SmoothScroll } from './components/motion'
import { useAuth } from './lib/auth'
import Landing from './pages/Landing'
import Login from './pages/Login'

const Explore = lazy(() => import('./pages/Explore'))
const ResourcePage = lazy(() => import('./pages/ResourcePage'))
const MyBookings = lazy(() => import('./pages/MyBookings'))
const BookingPage = lazy(() => import('./pages/BookingPage'))
const Scan = lazy(() => import('./pages/Scan'))
const Approvals = lazy(() => import('./pages/Approvals'))
const CampusMap = lazy(() => import('./pages/CampusMap'))
const Profile = lazy(() => import('./pages/Profile'))
const Admin = lazy(() => import('./pages/admin/Admin'))

function Protected({ children, manager }: { children: ReactNode; manager?: boolean }) {
  const { user, ready } = useAuth()
  const loc = useLocation()
  if (!ready) return <Splash />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  if (manager && !user.is_manager) return <Navigate to="/explore" replace />
  return <AppShell>{children}</AppShell>
}

function Splash() {
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
      <div className="sky" />
      <div className="loader-ticket" />
    </div>
  )
}

export default function App() {
  return (
    <>
      <SmoothScroll />
      <Suspense fallback={<Splash />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/explore" element={<Protected><Explore /></Protected>} />
          <Route path="/resources/:id" element={<Protected><ResourcePage /></Protected>} />
          <Route path="/bookings" element={<Protected><MyBookings /></Protected>} />
          <Route path="/bookings/:id" element={<Protected><BookingPage /></Protected>} />
          <Route path="/scan" element={<Protected><Scan /></Protected>} />
          <Route path="/map" element={<Protected><CampusMap /></Protected>} />
          <Route path="/me" element={<Protected><Profile /></Protected>} />
          <Route path="/approvals" element={<Protected manager><Approvals /></Protected>} />
          <Route path="/admin/*" element={<Protected manager><Admin /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </>
  )
}
