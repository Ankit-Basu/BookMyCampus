import { useEffect, useRef, useState } from 'react'

import { useTheme } from '../lib/theme'
import Grainient from './reactbits/bg/Grainient'

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * The app-wide backdrop: React Bits' Grainient shader in LPU orange + violet under an ink vignette.
 * It is rendered ONCE, as a still frame at low resolution. That matters: every glass panel's
 * backdrop-filter is recomputed whenever the pixels behind it change, so an animated backdrop
 * would re-blur every panel on screen every frame. A still one costs nothing after first paint.
 */
export default function Backdrop() {
  const { palette } = useTheme()
  return (
    <div className="backdrop" aria-hidden>
      <Grainient
        color1={palette.shader[0]}
        color2={palette.shader[1]}
        color3={palette.shader[2]}
        timeSpeed={0.12}
        warpStrength={1.1}
        warpFrequency={4}
        warpSpeed={1.2}
        warpAmplitude={60}
        blendSoftness={0.25}
        rotationAmount={420}
        noiseScale={1.6}
        grainAmount={0}
        contrast={1.25}
        saturation={1.1}
        zoom={0.85}
        renderScale={0.3}
        frozenAt={9.5}
      />
      <div className="backdrop-shade" />
      <div className="grain" />
    </div>
  )
}

/** Click sparks on a viewport-sized canvas that only animates while sparks are alive. */
export function Sparks() {
  const color = useTheme().palette.burst[3]
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (reducedMotion()) return
    const canvas = ref.current!
    const ctx = canvas.getContext('2d')!
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const size = () => {
      canvas.width = innerWidth * dpr
      canvas.height = innerHeight * dpr
    }
    size()
    window.addEventListener('resize', size)
    type S = { x: number; y: number; a: number; t: number }
    let sparks: S[] = []
    let raf = 0
    const DUR = 420
    const draw = (now: number) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      sparks = sparks.filter((s) => now - s.t < DUR)
      for (const s of sparks) {
        const p = (now - s.t) / DUR
        const e = p * (2 - p)
        const d = e * 20 * dpr
        const len = 9 * dpr * (1 - e)
        const x1 = s.x + d * Math.cos(s.a)
        const y1 = s.y + d * Math.sin(s.a)
        ctx.strokeStyle = color
        ctx.globalAlpha = 1 - p
        ctx.lineWidth = 2 * dpr
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x1 + len * Math.cos(s.a), y1 + len * Math.sin(s.a))
        ctx.stroke()
      }
      raf = sparks.length ? requestAnimationFrame(draw) : 0
    }
    const click = (e: PointerEvent) => {
      if (e.button !== 0) return
      const now = performance.now()
      for (let i = 0; i < 8; i++) sparks.push({ x: e.clientX * dpr, y: e.clientY * dpr, a: (Math.PI * 2 * i) / 8, t: now })
      if (!raf) raf = requestAnimationFrame(draw)
    }
    window.addEventListener('pointerdown', click)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('pointerdown', click)
      window.removeEventListener('resize', size)
    }
  }, [color])
  return <canvas ref={ref} className="sparks" aria-hidden />
}

/** Mount children only once the element has been near the viewport (keeps heavy WebGL off-screen). */
export function useNearViewport<T extends HTMLElement>(margin = '200px') {
  const ref = useRef<T>(null)
  const [near, setNear] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setNear(e.isIntersecting), { rootMargin: margin })
    io.observe(el)
    return () => io.disconnect()
  }, [margin])
  return [ref, near] as const
}
