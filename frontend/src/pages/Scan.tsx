import { Camera, CheckCircle, Keyboard, WarningCircle } from '@phosphor-icons/react'
import { Html5Qrcode } from 'html5-qrcode'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { PageHeader } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { fmtTime } from '../lib/format'
import type { Booking } from '../lib/types'

type Result = { ok: true; booking: Booking } | { ok: false; message: string }

export default function Scan() {
  const [params, setParams] = useSearchParams()
  const [result, setResult] = useState<Result | null>(null)
  const [camera, setCamera] = useState<'idle' | 'on' | 'denied'>('idle')
  const [manual, setManual] = useState('')
  const busy = useRef(false)
  const scanner = useRef<Html5Qrcode | null>(null)

  const submit = async (code: string) => {
    if (busy.current) return
    busy.current = true
    try {
      const r = await api.post<Booking>('/bookings/scan', { code })
      setResult({ ok: true, booking: r.data })
      navigator.vibrate?.(80)
      await stop()
    } catch (e) {
      setResult({ ok: false, message: errorMessage(e) })
      navigator.vibrate?.([40, 60, 40])
    } finally {
      setTimeout(() => (busy.current = false), 1500)
    }
  }

  const stop = async () => {
    try {
      if (scanner.current?.isScanning) await scanner.current.stop()
    } catch {
      /* already stopped */
    }
    setCamera('idle')
  }

  const start = async () => {
    setResult(null)
    try {
      scanner.current ??= new Html5Qrcode('qr-reader', { verbose: false })
      await scanner.current.start(
        { facingMode: 'environment' },
        { fps: 12, qrbox: (w, h) => ({ width: Math.min(w, h) * 0.7, height: Math.min(w, h) * 0.7 }) },
        (text) => submit(text),
        () => undefined,
      )
      setCamera('on')
    } catch {
      setCamera('denied')
    }
  }

  // Deep link from a phone's native camera: /scan?r=<resource token>
  useEffect(() => {
    const r = params.get('r')
    if (r) {
      submit(r)
      setParams({}, { replace: true })
    }
    return () => {
      stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <PageHeader eyebrow="Check in" title={<>Scan the <em>door</em></>} sub="Point your camera at the QR poster by the room or instrument. We’ll find your booking there and check you in." />

      <div className="scanner glass">
        <div id="qr-reader" className={camera === 'on' ? 'on' : ''} />
        {camera !== 'on' && (
          <div className="scanner-idle">
            <div className="scanner-frame">
              <span /><span /><span /><span />
            </div>
            <button className="key key-mint key-lg" onClick={start}>
              <Camera weight="bold" /> Open camera
            </button>
            {camera === 'denied' && <p className="muted" style={{ fontSize: 13 }}>Camera unavailable — allow access or type the code below.</p>}
          </div>
        )}
        {camera === 'on' && <div className="scan-line" />}
      </div>

      <AnimatePresence mode="wait">
        {result && (
          <motion.div
            key={result.ok ? 'ok' : result.message}
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            className={`glass pad scan-result ${result.ok ? 'ok' : 'bad'}`}
          >
            {result.ok ? (
              <>
                <CheckCircle size={44} weight="fill" color="var(--mint)" />
                <div>
                  <div className="display" style={{ fontSize: 34 }}>You’re in.</div>
                  <div className="muted">
                    {result.booking.resource_name} · until {fmtTime(result.booking.end)} · {result.booking.reference}
                  </div>
                  <Link to={`/bookings/${result.booking.id}`} className="key key-ghost key-sm" style={{ marginTop: 12 }}>
                    View pass
                  </Link>
                </div>
              </>
            ) : (
              <>
                <WarningCircle size={44} weight="fill" color="var(--coral)" />
                <div>
                  <div className="h2">Couldn’t check in</div>
                  <div className="muted">{result.message}</div>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <form
        className="glass pad row"
        style={{ marginTop: 18 }}
        onSubmit={(e) => {
          e.preventDefault()
          if (manual.trim()) submit(manual.trim())
        }}
      >
        <Keyboard size={20} className="muted" />
        <input className="input grow" value={manual} onChange={(e) => setManual(e.target.value)} placeholder="No camera? Paste the code printed under the QR" />
        <button className="key key-amber">Check in</button>
      </form>
    </div>
  )
}
