import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

gsap.registerPlugin(ScrollTrigger, useGSAP)

const reduced = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Reset scroll on navigation and let ScrollTrigger re-measure the new page. */
export function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
    const id = setTimeout(() => ScrollTrigger.refresh(), 200)
    return () => clearTimeout(id)
  }, [pathname])
  return null
}

/**
 * Lenis inertial scrolling for the landing page only (its pinned GSAP scenes benefit from it),
 * driven by GSAP's ticker so ScrollTrigger stays in lock-step. App pages keep native scrolling.
 */
export function SmoothScroll() {
  const { pathname } = useLocation()
  const lenisRef = useRef<Lenis | null>(null)

  useEffect(() => {
    if (reduced() || window.matchMedia('(pointer: coarse)').matches) return
    const lenis = new Lenis({ lerp: 0.16, wheelMultiplier: 1, smoothWheel: true })
    lenisRef.current = lenis
    lenis.on('scroll', ScrollTrigger.update)
    const tick = (t: number) => lenis.raf(t * 1000)
    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)
    return () => {
      gsap.ticker.remove(tick)
      lenis.destroy()
      lenisRef.current = null
    }
  }, [])

  useEffect(() => {
    lenisRef.current?.scrollTo(0, { immediate: true })
    window.scrollTo(0, 0)
    const id = setTimeout(() => ScrollTrigger.refresh(), 250)
    return () => clearTimeout(id)
  }, [pathname])

  return null
}

/** Soft amber light that trails the pointer across the glass — makes the panes feel physical. */
export function CursorGlow() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (reduced() || window.matchMedia('(pointer: coarse)').matches) return
    const el = ref.current!
    const xTo = gsap.quickTo(el, 'x', { duration: 0.6, ease: 'power3' })
    const yTo = gsap.quickTo(el, 'y', { duration: 0.6, ease: 'power3' })
    const move = (e: PointerEvent) => {
      xTo(e.clientX)
      yTo(e.clientY)
    }
    window.addEventListener('pointermove', move)
    return () => window.removeEventListener('pointermove', move)
  }, [])
  return <div ref={ref} className="cursor-glow" aria-hidden />
}

/**
 * Children with `[data-reveal]` rise in as they scroll into view, staggered.
 * Wrap a page section with <Reveal> and mark items; or use it bare to reveal itself.
 */
export function Reveal({ children, className, style, stagger = 0.08, y = 28 }: { children: ReactNode; className?: string; style?: CSSProperties; stagger?: number; y?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useGSAP(
    () => {
      if (reduced()) return
      const items = ref.current!.querySelectorAll('[data-reveal]')
      const targets = items.length ? items : [ref.current!]
      gsap.from(targets, {
        y,
        opacity: 0,
        duration: 0.9,
        ease: 'power3.out',
        stagger,
        scrollTrigger: { trigger: ref.current, start: 'top 88%', once: true },
        clearProps: 'transform',
      })
    },
    { scope: ref },
  )
  return (
    <div ref={ref} className={className} style={style}>
      {children}
    </div>
  )
}

/** Mouse-tilt for cards: subtle 3D rotation toward the pointer with a moving sheen. */
export function Tilt({ children, className, style, max = 7 }: { children: ReactNode; className?: string; style?: CSSProperties; max?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || reduced() || window.matchMedia('(pointer: coarse)').matches) return
    const rx = gsap.quickTo(el, 'rotationX', { duration: 0.5, ease: 'power3' })
    const ry = gsap.quickTo(el, 'rotationY', { duration: 0.5, ease: 'power3' })
    gsap.set(el, { transformPerspective: 900 })
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      const px = (e.clientX - r.left) / r.width - 0.5
      const py = (e.clientY - r.top) / r.height - 0.5
      ry(px * max * 2)
      rx(-py * max * 2)
      el.style.setProperty('--mx', `${(px + 0.5) * 100}%`)
      el.style.setProperty('--my', `${(py + 0.5) * 100}%`)
    }
    const leave = () => {
      rx(0)
      ry(0)
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', leave)
    return () => {
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerleave', leave)
    }
  }, [max])
  return (
    <div ref={ref} className={`tilt ${className ?? ''}`} style={style}>
      {children}
    </div>
  )
}

/** Number that counts up (GSAP-driven) the first time it scrolls into view. */
export function Counter({ to, duration = 1.4 }: { to: number; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (reduced()) {
      el.textContent = to.toLocaleString('en-IN')
      return
    }
    const obj = { v: 0 }
    const tween = gsap.to(obj, {
      v: to,
      duration,
      ease: 'power3.out',
      onUpdate: () => {
        el.textContent = Math.round(obj.v).toLocaleString('en-IN')
      },
      scrollTrigger: { trigger: el, start: 'top 95%', once: true },
    })
    return () => {
      tween.scrollTrigger?.kill()
      tween.kill()
    }
  }, [to, duration])
  return <span ref={ref}>0</span>
}
