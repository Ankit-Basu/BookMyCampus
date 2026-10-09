import 'leaflet/dist/leaflet.css'
import './index.css'
import './app.css'
import './glass.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'

import App from './App'
import { AuthProvider } from './lib/auth'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 20_000, refetchOnWindowFocus: false, retry: 1 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
          <Toaster
            theme="dark"
            position="top-center"
            toastOptions={{
              style: {
                background: 'rgba(16,19,42,.82)',
                backdropFilter: 'blur(18px)',
                border: '1px solid rgba(255,255,255,.14)',
                color: '#f4efe6',
                fontFamily: 'Bricolage Grotesque, system-ui',
              },
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
