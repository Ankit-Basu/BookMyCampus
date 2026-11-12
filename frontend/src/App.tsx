import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'

import AppShell from './components/AppShell'
import { ScrollToTop } from './components/motion'
import { useAuth } from './lib/auth'
import { pages } from './lib/preload'

const Landing = lazy(() => import('./pages/Landing'))
const Login = lazy(() => import('./pages/Login'))
const Register = lazy(() => import('./pages/Register'))
const PassPage = lazy(() => import('./pages/PassPage'))
const Explore = lazy(pages.explore)
const ResourcePage = lazy(pages.resource)
const MyBookings = lazy(pages.bookings)
const BookingPage = lazy(pages.booking)
const Scan = lazy(pages.scan)
const Study = lazy(pages.study)
const Approvals = lazy(pages.approvals)
const CampusMap = lazy(pages.map)
const Profile = lazy(pages.profile)
const Admin = lazy(pages.admin)

function RequireAuth() {
  const { user, ready } = useAuth()
  const loc = useLocation()
  if (!ready) return <Splash />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  return <AppShell />
}

function ManagerOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  return user?.is_manager ? <>{children}</> : <Navigate to="/explore" replace />
}

function Page() {
  return (
    <Suspense fallback={<div className="page"><div className="skeleton" style={{ height: 320 }} /></div>}>
      <Outlet />
    </Suspense>
  )
}

function Splash() {
  // Only mention the wait if there is one: the free server can take up to a minute to wake.
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 4000)
    return () => clearTimeout(t)
  }, [])
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', alignContent: 'center', gap: 18 }}>
      <div className="loader-ticket" />
      {slow && <p className="muted fade-in" role="status" style={{ fontSize: 13, margin: 0 }}>Waking up the server. On the free plan this can take up to a minute.</p>}
    </div>
  )
}

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Suspense fallback={<Splash />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          {/* Public: opened by scanning a booking pass with any phone camera. */}
          <Route path="/pass/:token" element={<PassPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<Page />}>
              <Route path="/explore" element={<Explore />} />
              <Route path="/resources/:id" element={<ResourcePage />} />
              <Route path="/bookings" element={<MyBookings />} />
              <Route path="/bookings/:id" element={<BookingPage />} />
              <Route path="/scan" element={<Scan />} />
              <Route path="/study" element={<Study />} />
              <Route path="/map" element={<CampusMap />} />
              <Route path="/me" element={<Profile />} />
              <Route path="/approvals" element={<ManagerOnly><Approvals /></ManagerOnly>} />
              <Route path="/admin/*" element={<ManagerOnly><Admin /></ManagerOnly>} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </>
  )
}
