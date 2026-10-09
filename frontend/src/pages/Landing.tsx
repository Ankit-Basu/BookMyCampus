import {
  ArrowDown,
  ArrowRight,
  ArrowsClockwise,
  CalendarCheck,
  ChartLineUp,
  Clock,
  Database,
  QrCode,
  Stamp,
  Timer,
} from '@phosphor-icons/react'
import { useGSAP } from '@gsap/react'
import { useQuery } from '@tanstack/react-query'
import gsap from 'gsap'
import { useMemo, useRef, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { Counter, CursorGlow, Reveal, SmoothScroll, Tilt } from '../components/motion'
import PrismaticBurst from '../components/reactbits/bg/PrismaticBurst'
import Backdrop, { Sparks } from '../components/Backdrop'
import BlurText from '../components/reactbits/BlurText'
import Magnet from '../components/reactbits/Magnet'
import ShinyText from '../components/reactbits/ShinyText'
import SpotlightCard from '../components/reactbits/SpotlightCard'
import { Wordmark } from '../components/AppShell'
import { TypeIcon } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { inr, pct } from '../lib/format'

type Stats = {
  resources: number
  types: { name: string; slug: string; color: string; icon: string; count: number; description: string; cover: string }[]
  bookings_30d: number
  conflicts_blocked: number
  double_bookings: number
  utilisation: number
  idle_value_inr: number
  idle_top: { name: string; code: string; value_inr: number; utilisation: number; image: string; type: string } | null
  names: string[]
}

const FEATURES = [
  { icon: CalendarCheck, color: '#f5a524', title: 'Timetable-aware', body: 'The published LPU timetable is written straight into the booking ledger. A room teaching CSE326 at 10:00 is simply never offered at 10:00.' },
  { icon: QrCode, color: '#3ee6c1', title: 'Scan the door, not a form', body: 'Every room and instrument carries a QR poster. Scan it within the grace window and you’re checked in — from any phone.' },
  { icon: Timer, color: '#ff6f59', title: 'No-shows give it back', body: 'Miss the 15-minute grace period and the slot auto-releases to the next person. Repeat no-shows pause booking rights, progressively.' },
  { icon: Stamp, color: '#8b7cff', title: 'Approval chains you can edit', body: 'Custodian → HoD → Facility manager, per resource type and requester role. Change the chain in the control room — no redeploy.' },
  { icon: ArrowsClockwise, color: '#5ab2ff', title: 'Recurring, honestly', body: 'Weekly tutorials expand into real occurrences. A mid-series clash skips just that date — or rolls the whole series back. Your call.' },
  { icon: ChartLineUp, color: '#5fd068', title: 'Know what sits idle', body: 'Utilisation, no-show rates, demand vs supply and the idle-value ranking that finds the ₹1 Cr instrument nobody books.' },
]

function HeroPass() {
  return (
    <div className="hero-pass">
      <div className="ticket" style={{ '--stub': '128px' } as CSSProperties}>
        <div className="ticket-body">
          <div className="ticket-accent" style={{ '--c': '#3ee6c1' } as CSSProperties} />
          <div className="eyebrow">Booking pass · BMC-7KQ4ZP</div>
          <div className="display" style={{ fontSize: 34, margin: '8px 0 2px' }}>AI &amp; Deep Learning Lab</div>
          <div className="muted" style={{ fontSize: 13 }}>Block 34 · Floor 5 · 501</div>
          <div className="row" style={{ marginTop: 16, gap: 22 }}>
            <div>
              <div className="eyebrow">Date</div>
              <div className="mono" style={{ fontSize: 15 }}>Tue 13 Oct</div>
            </div>
            <div>
              <div className="eyebrow">Time</div>
              <div className="mono" style={{ fontSize: 15 }}>16:00–18:00</div>
            </div>
            <div>
              <div className="eyebrow">Seats</div>
              <div className="mono" style={{ fontSize: 15 }}>03</div>
            </div>
          </div>
        </div>
        <div className="ticket-stub">
          <div className="qr-plate" style={{ width: 86 }}>
            <FakeQR />
          </div>
          <span className="tag" style={{ '--c': '#3ee6c1' } as CSSProperties}>
            <span className="led pulse" style={{ width: 6, height: 6 }} /> Confirmed
          </span>
        </div>
      </div>
    </div>
  )
}

function FakeQR() {
  // deterministic decorative QR-ish pattern (the real ones come from the API)
  const cells = Array.from({ length: 21 * 21 }, (_, i) => {
    const x = i % 21
    const y = Math.floor(i / 21)
    const finder = (cx: number, cy: number) => x >= cx && x < cx + 7 && y >= cy && y < cy + 7
    if (finder(0, 0) || finder(14, 0) || finder(0, 14)) {
      const lx = x % 14 < 7 ? x % 14 : x - 14
      const ly = y % 14 < 7 ? y % 14 : y - 14
      const r = Math.max(Math.abs(lx - 3), Math.abs(ly - 3))
      return r !== 2
    }
    return ((x * 7 + y * 13 + x * y) % 5) < 2
  })
  return (
    <svg viewBox="0 0 21 21" shapeRendering="crispEdges">
      {cells.map((on, i) => (on ? <rect key={i} x={i % 21} y={Math.floor(i / 21)} width="1" height="1" fill="#0b0c18" /> : null))}
    </svg>
  )
}

/** Pinned, scroll-scrubbed scene: 500 requests converge on one slot; exactly one survives. */
function RaceScene() {
  const ref = useRef<HTMLDivElement>(null)
  const dots = 240
  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add('(prefers-reduced-motion: no-preference)', () => {
        const tl = gsap.timeline({
          scrollTrigger: { trigger: ref.current, start: 'top top', end: '+=2400', scrub: 0.8, pin: true },
        })
        const all = gsap.utils.toArray<HTMLElement>('.race-dot')
        const winner = all[37]
        tl.from('.race-slot', { scale: 0.6, opacity: 0, duration: 0.6 })
          .to('.race-step', { opacity: 0.25, duration: 0.2 }, '<')
          .to('.race-step-0', { opacity: 1, duration: 0.2 }, '<')
          .from(all, { opacity: 0, scale: 0, stagger: { each: 0.002, from: 'random' }, duration: 0.4 })
          .to('.race-step', { opacity: 0.25, duration: 0.2 })
          .to('.race-step-1', { opacity: 1, duration: 0.2 }, '<')
          .to(all, {
            x: (_i: number, el: HTMLElement) => {
              const r = el.getBoundingClientRect()
              const s = document.querySelector('.race-slot')!.getBoundingClientRect()
              return s.left + s.width / 2 - (r.left + r.width / 2)
            },
            y: (_i: number, el: HTMLElement) => {
              const r = el.getBoundingClientRect()
              const s = document.querySelector('.race-slot')!.getBoundingClientRect()
              return s.top + s.height / 2 - (r.top + r.height / 2)
            },
            duration: 1.2,
            ease: 'power2.in',
            stagger: { each: 0.0015, from: 'random' },
          })
          .to('.race-step', { opacity: 0.25, duration: 0.2 })
          .to('.race-step-2', { opacity: 1, duration: 0.2 }, '<')
          .to('.race-code', { opacity: 1, y: 0, duration: 0.5 }, '<')
          .to(all.filter((d) => d !== winner), { background: '#ff6f59', opacity: 0, scale: 2.6, duration: 0.6, stagger: 0.001 })
          .to(winner, { scale: 3.2, background: '#f5a524', boxShadow: '0 0 30px #f5a524', duration: 0.4 }, '<0.2')
          .to('.race-step', { opacity: 0.25, duration: 0.2 })
          .to('.race-step-3', { opacity: 1, duration: 0.2 }, '<')
          .to('.race-slot', { borderColor: 'rgba(62,230,193,.8)', boxShadow: '0 0 60px -10px rgba(62,230,193,.7)', duration: 0.4 }, '<')
          .to('.race-verdict', { opacity: 1, y: 0, duration: 0.4 }, '<')
      })
      return () => mm.revert()
    },
    { scope: ref },
  )
  return (
    <section ref={ref} className="race">
      <div className="race-inner">
        <div className="race-copy">
          <div className="eyebrow">Conflict prevention · the whole point</div>
          <h2 className="display race-title">
            500 clicks. One slot.
            <br />
            <em>Exactly one booking.</em>
          </h2>
          <ol className="race-steps">
            <li className="race-step race-step-0"><span className="mono">01</span> A 10:00 slot in the AI Lab opens up.</li>
            <li className="race-step race-step-1"><span className="mono">02</span> 500 students hit “Book” in the same instant.</li>
            <li className="race-step race-step-2"><span className="mono">03</span> PostgreSQL’s exclusion constraint compares every range on the GiST index.</li>
            <li className="race-step race-step-3"><span className="mono">04</span> One row is stored. 499 get a clean “just taken” — no lock, no race.</li>
          </ol>
          <pre className="race-code glass-flat mono">{`ExclusionConstraint(
  name="booking_no_overlap",
  expressions=[
    ("resource", RangeOperators.EQUAL),
    ("period",   RangeOperators.OVERLAPS),
  ],
)`}</pre>
        </div>
        <div className="race-stage">
          <div className="race-field">
            {Array.from({ length: dots }, (_, i) => (
              <span key={i} className="race-dot" />
            ))}
          </div>
          <div className="race-slot">
            <span className="mono">LAB-34-AI</span>
            <strong>10:00 – 11:00</strong>
          </div>
          <div className="race-verdict">
            <span className="led" /> 1 booked · 499 × 409 Conflict · proven in CI
          </div>
        </div>
      </div>
    </section>
  )
}

/** Pinned horizontal gallery of resource types, driven by vertical scroll. */
function TypeRail({ types }: { types: Stats['types'] }) {
  const ref = useRef<HTMLDivElement>(null)
  useGSAP(
    () => {
      if (!types.length) return
      const mm = gsap.matchMedia()
      mm.add('(min-width: 761px) and (prefers-reduced-motion: no-preference)', () => {
        const track = ref.current!.querySelector<HTMLElement>('.rail-track')!
        const dist = () => track.scrollWidth - window.innerWidth + 64
        gsap.to(track, {
          x: () => -dist(),
          ease: 'none',
          scrollTrigger: { trigger: ref.current, start: 'top top', end: () => `+=${dist()}`, scrub: 0.6, pin: true, invalidateOnRefresh: true },
        })
        gsap.utils.toArray<HTMLElement>('.rail-card img').forEach((img) => {
          gsap.fromTo(img, { xPercent: -8 }, { xPercent: 8, ease: 'none', scrollTrigger: { trigger: ref.current, start: 'top top', end: () => `+=${dist()}`, scrub: true } })
        })
      })
      return () => mm.revert()
    },
    { scope: ref, dependencies: [types.length] },
  )
  return (
    <section ref={ref} className="rail">
      <div className="rail-head">
        <div className="eyebrow">One catalogue · every department</div>
        <h2 className="display" style={{ fontSize: 'clamp(40px,6vw,84px)', margin: '8px 0 0' }}>
          If it can be <em>booked</em>, it’s here.
        </h2>
      </div>
      <div className="rail-track">
        {types.map((t, i) => (
          <Link to={`/explore?type=${t.slug}`} key={t.slug} className="rail-card" style={{ '--c': t.color } as CSSProperties}>
            <div className="rail-img">{t.cover && <img src={t.cover.replace('w=1200', 'w=900')} alt="" loading="lazy" />}</div>
            <div className="rail-meta">
              <span className="mono rail-idx">{String(i + 1).padStart(2, '0')}</span>
              <div className="row" style={{ gap: 8 }}>
                <TypeIcon icon={t.icon} size={22} color={t.color} />
                <span className="display" style={{ fontSize: 34 }}>{t.name}</span>
              </div>
              <p className="muted" style={{ margin: '6px 0 0', fontSize: 14 }}>{t.description}</p>
              <span className="tag" style={{ marginTop: 12 }}>{t.count} bookable</span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}

export default function Landing() {
  const { user } = useAuth()
  const { data } = useQuery({ queryKey: ['public-stats'], queryFn: () => api.get<Stats>('/public/stats').then((r) => r.data) })
  const hero = useRef<HTMLDivElement>(null)
  // Shader offsets are in drawing-buffer pixels: centre the burst behind the pass on the right.
  const burstOffset = useMemo(() => {
    if (typeof window === 'undefined' || window.innerWidth < 860) return { x: 0, y: 0 }
    const scale = Math.min(window.devicePixelRatio || 1, 2) * 0.4
    return { x: window.innerWidth * 0.22 * scale, y: window.innerHeight * 0.02 * scale }
  }, [])

  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add('(prefers-reduced-motion: no-preference)', () => {
        gsap.from('.hero-line', { yPercent: 110, opacity: 0, stagger: 0.12, duration: 1.1, ease: 'expo.out', delay: 0.15 })
        gsap.from('.hero-pass', { y: 80, rotate: 6, opacity: 0, duration: 1.4, ease: 'expo.out', delay: 0.4 })
        gsap.from('.hero-cta > *', { y: 20, opacity: 0, stagger: 0.1, duration: 0.8, ease: 'power3.out', delay: 0.7 })
        // scroll-away parallax: headline drifts up, pass sinks + rotates, aurora dims
        gsap.to('.hero-copy', { yPercent: -18, opacity: 0.2, ease: 'none', scrollTrigger: { trigger: hero.current, start: 'top top', end: 'bottom top', scrub: true } })
        gsap.to('.hero-pass', { yPercent: 30, rotate: -8, ease: 'none', scrollTrigger: { trigger: hero.current, start: 'top top', end: 'bottom top', scrub: true } })
        gsap.to('.hero-aurora', { opacity: 0.25, ease: 'none', scrollTrigger: { trigger: hero.current, start: 'top top', end: 'bottom top', scrub: true } })
        // pointer parallax on the pass
        const pass = document.querySelector<HTMLElement>('.hero-pass .ticket')
        if (pass && !window.matchMedia('(pointer: coarse)').matches) {
          const rx = gsap.quickTo(pass, 'rotationX', { duration: 0.8, ease: 'power3' })
          const ry = gsap.quickTo(pass, 'rotationY', { duration: 0.8, ease: 'power3' })
          gsap.set(pass, { transformPerspective: 1000 })
          const move = (e: PointerEvent) => {
            ry((e.clientX / window.innerWidth - 0.5) * 18)
            rx(-(e.clientY / window.innerHeight - 0.5) * 14)
          }
          window.addEventListener('pointermove', move)
          return () => window.removeEventListener('pointermove', move)
        }
      })
      return () => mm.revert()
    },
    { scope: hero },
  )

  const cta = user ? '/explore' : '/login'
  return (
    <div className="landing">
      <SmoothScroll />
      <Backdrop />
      <CursorGlow />
      <Sparks />

      <nav className="landing-nav">
        <Wordmark />
        <div className="row">
          <a href="#how" className="chip hide-sm">How it works</a>
          <a href="#features" className="chip hide-sm">Features</a>
          <Link to={cta} className="key key-ghost key-sm">{user ? 'Open app' : 'Sign in'}</Link>
        </div>
      </nav>

      <section className="hero" ref={hero}>
        <div className="hero-aurora">
          <PrismaticBurst
            colors={['#ff6f59', '#f5a524', '#ffd27a', '#8b7cff', '#3ee6c1']}
            animationType="rotate3d"
            intensity={2.2}
            speed={0.35}
            distort={0.25}
            rayCount={16}
            offset={burstOffset}
            mixBlendMode="none"
            renderScale={0.4}
            maxFps={30}
          />
        </div>
        <div className="hero-grid">
          <div className="hero-copy">
            <div className="eyebrow" style={{ marginBottom: 18 }}>
              <span className="led pulse" style={{ display: 'inline-block', marginRight: 10, verticalAlign: 'middle' }} />
              Lovely Professional University · Phagwara
            </div>
            <h1 className="display hero-title">
              <span className="hero-mask"><span className="hero-line">Every lab, hall</span></span>
              <span className="hero-mask"><span className="hero-line">and <em>turf</em> on campus.</span></span>
              <span className="hero-mask"><span className="hero-line">One tap away.</span></span>
            </h1>
            <BlurText
              className="hero-sub"
              text="No more WhatsApp chains, register books or phone calls to Block 34. See what’s free, book it, scan in — and never get double-booked again."
              delay={30}
              animateBy="words"
            />
            <div className="hero-cta row wrap" style={{ marginTop: 30, gap: 14 }}>
              <Magnet padding={60} magnetStrength={4}>
                <Link to={cta} className="key key-amber key-lg">
                  Start booking <ArrowRight weight="bold" />
                </Link>
              </Magnet>
              <a href="#how" className="key key-ghost key-lg">
                See why it can’t double-book
              </a>
            </div>
          </div>
          <HeroPass />
        </div>
        <a href="#how" className="scroll-cue mono">
          <ArrowDown size={14} /> scroll
        </a>
      </section>

      <section className="marquee">
        {/* Pure-CSS marquee: runs on the compositor thread, so it never stutters when JS is busy. */}
        <div className="marquee-track" aria-hidden>
          {[0, 1].map((copy) => (
            <span key={copy} className="marquee-text">
              {(data?.names ?? ['AI & Deep Learning Lab', 'Confocal Microscope', 'Football Turf', 'CSE Seminar Hall', '52-Seater Coach']).map((n) => (
                <span key={n}>
                  {n}
                  <i>✦</i>
                </span>
              ))}
            </span>
          ))}
        </div>
      </section>

      <Reveal className="page stats-strip" style={{ paddingTop: 70, paddingBottom: 40 }}>
        <div className="stats-grid">
          {[
            { v: data?.resources ?? 0, l: 'bookable resources', s: '' },
            { v: data?.types.length ?? 0, l: 'resource types', s: '' },
            { v: data?.bookings_30d ?? 0, l: 'bookings in 30 days', s: '' },
            { v: data?.conflicts_blocked ?? 0, l: 'clashes refused by the DB', s: '' },
          ].map((s) => (
            <div key={s.l} data-reveal className="stat-big">
              <span className="display">
                <Counter to={s.v} duration={1.6} />
              </span>
              <span className="eyebrow">{s.l}</span>
            </div>
          ))}
          <div data-reveal className="stat-big zero">
            <span className="display">0</span>
            <span className="eyebrow">double-bookings. ever.</span>
          </div>
        </div>
      </Reveal>

      <div id="how" />
      <RaceScene />

      <TypeRail types={data?.types ?? []} />

      <section id="features" className="page" style={{ paddingTop: 120 }}>
        <Reveal>
          <div className="eyebrow" data-reveal>What you get</div>
          <h2 className="display" data-reveal style={{ fontSize: 'clamp(40px,6vw,76px)', margin: '10px 0 40px', maxWidth: 900 }}>
            Built for how LPU <em>actually</em> runs.
          </h2>
        </Reveal>
        <Reveal className="feature-grid" stagger={0.1}>
          {FEATURES.map((f) => (
            <div data-reveal key={f.title}>
              <SpotlightCard className="feature-card" spotlightColor={f.color} intensity={0.55} spotlightSize={340} theme="dark">
                <div className="feature-icon" style={{ '--c': f.color } as CSSProperties}>
                  <f.icon size={24} weight="duotone" />
                </div>
                <h3 className="h2" style={{ margin: '18px 0 8px' }}>{f.title}</h3>
                <p className="muted" style={{ margin: 0 }}>{f.body}</p>
              </SpotlightCard>
            </div>
          ))}
        </Reveal>
      </section>

      {data?.idle_top && (
        <section className="page" style={{ paddingTop: 60 }}>
          <Reveal>
            <Tilt className="idle-card glass" max={4}>
              <div className="idle-img" data-reveal>
                <img src={data.idle_top.image} alt="" />
              </div>
              <div className="pad-l" data-reveal>
                <div className="eyebrow">The report that pays for the project</div>
                <h3 className="display" style={{ fontSize: 'clamp(34px,4.4vw,58px)', margin: '10px 0' }}>
                  A <em>{inr(data.idle_top.value_inr)}</em> {data.idle_top.name.toLowerCase()} — busy {pct(data.idle_top.utilisation)} of the time.
                </h3>
                <p className="muted" style={{ maxWidth: 520 }}>
                  The idle-capacity ranking weighs every resource’s value against how much it is actually used. Across campus,{' '}
                  <strong style={{ color: 'var(--amber-hi)' }}>{inr(data.idle_value_inr)}</strong> of equipment and space is sitting unused this month.
                </p>
                <div className="row" style={{ marginTop: 18 }}>
                  <Clock size={16} className="muted" />
                  <span className="mono muted" style={{ fontSize: 12 }}>last 28 days · campus utilisation {pct(data.utilisation, 1)}</span>
                </div>
              </div>
            </Tilt>
          </Reveal>
        </section>
      )}

      <section className="page final-cta">
        <Reveal>
          <div data-reveal className="eyebrow">Ready when you are</div>
          <h2 data-reveal className="display" style={{ fontSize: 'clamp(54px,9vw,140px)', margin: '14px 0 30px' }}>
            Book it <em>before</em>
            <br />
            someone else does.
          </h2>
          <div data-reveal className="row wrap" style={{ justifyContent: 'center', gap: 14 }}>
            <Link to={cta} className="key key-amber key-lg">
              <ShinyText text={user ? 'Open BookMyCampus' : 'Sign in with your UMS ID'} color="#1c1003" shineColor="#fff7e0" speed={3} />
            </Link>
          </div>
        </Reveal>
      </section>

      <footer className="landing-foot">
        <Wordmark small />
        <span className="mono muted" style={{ fontSize: 11 }}>
          <Database size={12} style={{ verticalAlign: '-2px' }} /> Django · PostgreSQL range types · React · built for P20, Track P
        </span>
      </footer>
    </div>
  )
}
