import 'leaflet/dist/leaflet.css'
import './styles/tailwind.css'
import './styles/themes.css'
import './styles/foundation.css'
import './styles/shell.css'
import './styles/pages.css'
import './styles/landing.css'
import './styles/copilot.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'

import App from './App'
import { AuthProvider } from './lib/auth'
import { ThemeProvider, useTheme } from './lib/theme'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 20_000, refetchOnWindowFocus: false, retry: 1 } },
})

function ThemedToaster() {
  const { mode } = useTheme()
  return (
    <Toaster
      theme={mode}
      position="top-center"
      toastOptions={{
        style: {
          background: 'var(--glass-strong)',
          backdropFilter: 'blur(18px)',
          border: '1px solid var(--glass-edge)',
          color: 'var(--foreground)',
          fontFamily: 'var(--font-ui)',
          borderRadius: 14,
        },
      }}
    />
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <App />
            <ThemedToaster />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
