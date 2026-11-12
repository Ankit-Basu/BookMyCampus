import { useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { api, getTokens, setTokens } from './api'
import type { User } from './types'

type AuthCtx = {
  user: User | null
  ready: boolean
  login: (username: string, password: string) => Promise<User>
  logout: () => void
  refresh: () => Promise<void>
}

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const qc = useQueryClient()

  const refresh = useCallback(async () => {
    if (!getTokens()) {
      setUser(null)
      return
    }
    // Only a real "not signed in" answer signs you out. A sleeping or restarting server is waited for
    // (about a minute), and if it still hasn't answered the saved sign-in is kept for next time.
    for (let attempt = 0; ; attempt++) {
      try {
        const r = await api.get<User>('/me')
        setUser(r.data)
        return
      } catch (e) {
        const status = (e as AxiosError).response?.status
        if (status === 401 || status === 403 || !getTokens()) {
          setTokens(null)
          setUser(null)
          return
        }
        if (attempt >= 11) {
          setUser(null)
          return
        }
        await new Promise((r) => setTimeout(r, 5000))
      }
    }
  }, [])

  useEffect(() => {
    refresh().finally(() => setReady(true))
    const onLogout = () => setUser(null)
    window.addEventListener('bmc:logout', onLogout)
    return () => window.removeEventListener('bmc:logout', onLogout)
  }, [refresh])

  const login = async (username: string, password: string) => {
    const r = await api.post('/auth/login', { username, password })
    setTokens({ access: r.data.access, refresh: r.data.refresh })
    qc.clear()
    setUser(r.data.user)
    return r.data.user as User
  }

  const logout = () => {
    setTokens(null)
    qc.clear()
    setUser(null)
  }

  return <Ctx.Provider value={{ user, ready, login, logout, refresh }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)

export const isPolicyAdmin = (u: User | null) => !!u && (u.role === 'facility_manager' || u.role === 'admin')
