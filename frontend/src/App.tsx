import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'

import AppShell from './components/AppShell'
import { ScrollToTop } from './components/motion'
import { useAuth } from './lib/auth'
import { pages } from './lib/preload'

const Landing = lazy(() => import('./pages/Landing'))
const Login = lazy(() => import('./pages/Login'))
const Register = lazy(() => import('./pages/Register'))
const Explore = lazy(pages.explore)
const ResourcePage = lazy(pages.resource)
const MyBookings = lazy(pages.bookings)
const BookingPage = lazy(pages.booking)
const Scan = lazy(pages.scan)
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
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
      <div className="loader-ticket" />
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
          <Route element={<RequireAuth />}>
            <Route element={<Page />}>
              <Route path="/explore" element={<Explore />} />
              <Route path="/resources/:id" element={<ResourcePage />} />
              <Route path="/bookings" element={<MyBookings />} />
              <Route path="/bookings/:id" element={<BookingPage />} />
              <Route path="/scan" element={<Scan />} />
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
