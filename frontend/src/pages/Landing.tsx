import { ArrowRight, ArrowsClockwise, CalendarCheck, ChartLineUp, Database, QrCode, Stamp, Timer } from '@phosphor-icons/react'
import { useGSAP } from '@gsap/react'
import { useQuery } from '@tanstack/react-query'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { ThemeMenu, Wordmark } from '../components/AppShell'
import Backdrop, { Sparks } from '../components/Backdrop'
import { Counter, Reveal, SmoothScroll } from '../components/motion'
import BlurText from '../components/reactbits/BlurText'
import PrismaticBurst from '../components/reactbits/bg/PrismaticBurst'
import ShinyText from '../components/reactbits/ShinyText'
import SplitFlapText from '../components/reactbits/SplitFlapText'
import TearTicket from '../components/reactbits/TearTicket'
import { TypeIcon } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { inr, pct, WEEKDAYS } from '../lib/format'
import { useTheme } from '../lib/theme'

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

const FLAP_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789&-·' "
const FALLBACK = ['AI & DEEP LEARNING LAB', 'CONFOCAL MICROSCOPE', 'FOOTBALL TURF', 'CSE SEMINAR HALL', 'BADMINTON HALL A', '52-SEATER COACH']
const flapName = (n: string) => n.toUpperCase().slice(0, 24)

/** Hand-drawn squiggle arrow for margin notes. */
function Scribble({ flip, style }: { flip?: boolean; style?: CSSProperties }) {
  return (
    <svg viewBox="0 0 64 40" width="58" height="36" fill="none" style={{ transform: flip ? 'scaleX(-1)' : undefined, ...style }} aria-hidden>
      <path d="M3 6c12 22 30 27 54 22M47 19l11 9-13 7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// decorative pattern on the demo ticket; real passes come from the API
const FAKE_QR = Array.from({ length: 21 * 21 }, (_, i) => {
  const x = i % 21
  const y = Math.floor(i / 21)
  const finder = (cx: number, cy: number) => x >= cx && x < cx + 7 && y >= cy && y < cy + 7
  let on = (x * 7 + y * 13 + x * y) % 5 < 2
  if (finder(0, 0) || finder(14, 0) || finder(0, 14)) {
    const lx = x % 14 < 7 ? x % 14 : x - 14
    const ly = y % 14 < 7 ? y % 14 : y - 14
    on = Math.max(Math.abs(lx - 3), Math.abs(ly - 3)) !== 2
  }
  return on ? `M${x} ${y}h1v1h-1z` : ''
}).join('')

function FakeQR() {
  return (
    <svg viewBox="0 0 21 21" shapeRendering="crispEdges">
      <path d={FAKE_QR} fill="#14121c" />
    </svg>
  )
}

/**
 * Everything under the fold mounts once the hero has settled, or the moment the visitor reaches for it.
 * Measuring the pinned scenes is the slowest part of opening this page, so it must not delay the first paint.
 */
function useBelowFold() {
  const [ready, setReady] = useState(() => window.scrollY > 0)
  useEffect(() => {
    if (ready) return
    const go = () => setReady(true)
    const id = setTimeout(go, 2800)
    const events = ['wheel', 'touchstart', 'pointerdown', 'keydown']
    events.forEach((e) => window.addEventListener(e, go, { once: true, passive: true }))
    return () => {
      clearTimeout(id)
      events.forEach((e) => window.removeEventListener(e, go))
    }
  }, [ready])
  useEffect(() => {
    if (ready) document.fonts.ready.then(() => ScrollTrigger.refresh())
  }, [ready])
  return ready
}

/** A split-flap departure board of real catalogue names. */
function DepartureBoard({ names }: { names: string[] }) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30000)
    return () => clearInterval(id)
  }, [])
  const list = names.length >= 6 ? names.map(flapName) : FALLBACK
  const rows = [0, 1, 2].map((r) => list.filter((_, i) => i % 3 === r))
  return (
    <div className="board-panel">
      <div className="board-head">
        <span className="eyebrow">Now on the catalogue</span>
        <span className="mono board-clock">
          <span className="led pulse" /> {now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })} IST
        </span>
      </div>
      {rows.map((words, i) => (
        <div className="board-line" key={i}>
          <span className="mono board-gate">{'ABC'[i]}{i + 1}</span>
          <SplitFlapText
            words={words}
            cycleDelay={7000 + i * 2300}
            intro={false}
            charset={FLAP_CHARS}
            padTo={24}
            align="left"
            loop
            flipsPerChar={2}
            flipDuration={0.07}
            stagger={0.018}
            fontSize="clamp(10px, 1.02vw, 15px)"
            gap={2}
            tileRadius={3}
            tileColor="#17151f"
            textColor="#f6efe2"
          />
        </div>
      ))}
    </div>
  )
}

function HeroTicket() {
  const [round, setRound] = useState(0)
  const [torn, setTorn] = useState(false)
  useEffect(() => {
    if (!torn) return
    const id = setTimeout(() => {
      setTorn(false)
      setRound((r) => r + 1)
    }, 3200)
    return () => clearTimeout(id)
  }, [torn])
  return (
    <div className="hero-ticket">
      <TearTicket
        key={round}
        width={470}
        height={204}
        stubSize={128}
        holes={11}
        radius={18}
        rotate={-3}
        background="var(--ticket-bg)"
        stubBackground="var(--ticket-stub)"
        color="var(--ticket-ink)"
        onTear={() => setTorn(true)}
        ariaLabel="Demo booking pass. Tear off the stub."
        stub={
          <div className="demo-stub">
            <div className="qr-plate" style={{ width: 84 }}><FakeQR /></div>
            <span className="mono">BMC-7KQ4ZP</span>
          </div>
        }
      >
        <div className="demo-pass">
          <div className="eyebrow" style={{ color: 'inherit', opacity: 0.6 }}>Booking pass · Block 34</div>
          <div className="demo-title">AI &amp; Deep Learning Lab</div>
          <div className="demo-meta">
            <div><span>Date</span><b className="mono">Tue 13 Oct</b></div>
            <div><span>Time</span><b className="mono">16:00–18:00</b></div>
            <div><span>Seats</span><b className="mono">03</b></div>
          </div>
        </div>
      </TearTicket>
      <div className="hand ticket-note">
        {torn ? "you're checked in. (it grows back.)" : 'go on, tear the stub'}
        {!torn && <Scribble flip style={{ position: 'absolute', right: -44, top: -26, rotate: '-68deg' }} />}
      </div>
    </div>
  )
}

const RACERS = ['Aarav S.', 'Diya A.', 'Kabir J.', 'Ananya R.', 'Vihaan S.', 'Saanvi A.', 'Arjun S.', 'Myra B.', 'Reyansh K.', 'Aadhya J.', 'Advait P.', 'Kiara M.', 'Dhruv J.', 'Anika T.']
// scattered start positions around the stage, as % of its size, plus a tilt
const RACE_START: [number, number, number][] = [[3, 14, -9], [34, 11, 5], [68, 13, -4], [1, 36, 7], [72, 34, -8], [3, 55, -5], [71, 54, 6], [30, 62, 8], [62, 66, -6], [2, 68, 4], [36, 74, -7], [69, 72, 5], [15, 26, 10], [56, 24, -11]]
const WINNER = 4

/** Pinned, scroll-scrubbed: booking passes race into one calendar slot; exactly one survives. */
function RaceScene() {
  const ref = useRef<HTMLDivElement>(null)
  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add('(min-width: 861px) and (prefers-reduced-motion: no-preference)', () => {
        const tl = gsap.timeline({ scrollTrigger: { trigger: ref.current, start: 'top top', end: '+=2200', scrub: 0.5, pin: true } })
        const all = gsap.utils.toArray<HTMLElement>('.race-tk')
        const winner = all[WINNER]
        const losers = all.filter((t) => t !== winner)
        const toSlot = (axis: 'x' | 'y') => (_i: number, el: HTMLElement) => {
          const r = el.getBoundingClientRect()
          const s = document.querySelector('.race-slot')!.getBoundingClientRect()
          return axis === 'x' ? s.left + s.width / 2 - (r.left + r.width / 2) : s.top + s.height / 2 - (r.top + r.height / 2)
        }
        const count = { requests: 0, booked: 0, refused: 0 }
        const q = (id: string) => ref.current!.querySelector(id)!
        const paint = () => {
          q('#race-requests').textContent = String(Math.round(count.requests))
          q('#race-booked').textContent = String(Math.round(count.booked))
          q('#race-refused').textContent = String(Math.round(count.refused))
        }
        paint()
        const step = (n: number, at?: string) => tl.to('.race-step', { opacity: 0.28, duration: 0.2 }, at).to(`.race-step-${n}`, { opacity: 1, duration: 0.2 }, '<')

        tl.from('.race-slot', { scale: 0.92, opacity: 0, duration: 0.5 })
        step(0, '<')
        tl.from(all, { opacity: 0, scale: 0.7, stagger: 0.04, duration: 0.5 })
        step(1)
        tl.to(count, { requests: 500, duration: 1.3, ease: 'none', onUpdate: paint }, '<')
        tl.to(all, { x: toSlot('x'), y: toSlot('y'), rotation: 0, duration: 1.1, ease: 'power2.in', stagger: { each: 0.018, from: 'random' } }, '<')
        step(2)
        tl.to('.race-note', { opacity: 1, y: 0, duration: 0.5 }, '<')
        tl.to(losers.map((t) => t.querySelector('.tk-stamp')), { opacity: 1, scale: 1, duration: 0.3, stagger: 0.012 }, '<')
        tl.to(count, { booked: 1, duration: 0.2, onUpdate: paint }, '<')
        tl.to(count, { refused: 499, duration: 0.9, ease: 'none', onUpdate: paint }, '<')
        tl.to(losers, {
          x: (i: number, el: HTMLElement) => Number(gsap.getProperty(el, 'x')) + (i % 2 ? 1 : -1) * (70 + (i * 37) % 170),
          y: (i: number, el: HTMLElement) => Number(gsap.getProperty(el, 'y')) + 120 + (i * 53) % 190,
          rotation: (i: number) => (i % 2 ? 1 : -1) * (14 + (i * 11) % 34),
          opacity: 0,
          duration: 0.8,
          stagger: 0.02,
        }, '<0.1')
        step(3)
        tl.to(winner, { scale: 1.06, duration: 0.3 }, '<')
        tl.to('.race-won', { opacity: 1, duration: 0.3 }, '<')
        tl.to(winner.querySelector('.tk-ok'), { opacity: 1, duration: 0.3 }, '<')
        tl.to('.race-verdict', { opacity: 1, y: 0, duration: 0.4 }, '<')
      })
      return () => mm.revert()
    },
    { scope: ref },
  )
  return (
    <section ref={ref} className="race" id="how">
      <div className="race-inner">
        <div className="race-copy">
          <span className="sticker" style={{ rotate: '2deg' }}>The whole point</span>
          <h2 className="display race-title">
            500 clicks. One slot. <em>Exactly one booking.</em>
          </h2>
          <ol className="race-steps">
            <li className="race-step race-step-0"><span className="mono">01</span> A 10:00 slot in the AI Lab opens up.</li>
            <li className="race-step race-step-1"><span className="mono">02</span> 500 students hit “Book” in the same instant.</li>
            <li className="race-step race-step-2"><span className="mono">03</span> The database checks them all against that one slot.</li>
            <li className="race-step race-step-3"><span className="mono">04</span> One booking is saved. The other 499 instantly see “just taken”.</li>
          </ol>
          <div className="race-note">
            <span className="note-pin" aria-hidden />
            <span className="note-kicker mono">House rule no. 1</span>
            <p className="note-rule">Two bookings can never share the same room at the same time.</p>
            <p className="note-sub">The database itself refuses the second one, so there’s nothing to slip past.</p>
            <span className="note-stamp mono" aria-hidden>Enforced</span>
            <span className="hand note-hand">even if 500 people click at once</span>
          </div>
        </div>
        <div className="race-stage glass">
          <div className="race-head">
            <span className="eyebrow">AI &amp; Deep Learning Lab · Tuesday</span>
            <span className="mono race-live"><span className="led pulse" /> live</span>
          </div>
          <div className="race-day" aria-hidden>
            <div className="race-hour"><b className="mono">09:00</b><i className="race-class mono">CSE326 · class</i></div>
            <div className="race-hour"><b className="mono">10:00</b><div className="race-slot"><i className="race-won" /><span className="mono">Free slot</span></div></div>
            <div className="race-hour"><b className="mono">11:00</b><i className="race-class mono">INT253 · class</i></div>
          </div>
          {RACERS.map((name, i) => (
            <div key={name} className="race-tk" style={{ left: `${RACE_START[i][0]}%`, top: `${RACE_START[i][1]}%`, transform: `rotate(${RACE_START[i][2]}deg)` }}>
              <span className="tk-name">{name}</span>
              <span className="tk-time mono">10:00–11:00</span>
              {i === WINNER ? <em className="tk-ok mono">Booked</em> : <em className="tk-stamp mono">Taken</em>}
            </div>
          ))}
          <div className="race-counts">
            <div><strong className="mono" id="race-requests">500</strong><span>requests</span></div>
            <div className="ok"><strong className="mono" id="race-booked">1</strong><span>booked</span></div>
            <div className="bad"><strong className="mono" id="race-refused">499</strong><span>refused</span></div>
          </div>
          <div className="race-verdict mono"><span className="led" /> Proven by test: 500 attempts, 1 booking</div>
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
      mm.add('(min-width: 861px) and (prefers-reduced-motion: no-preference)', () => {
        const track = ref.current!.querySelector<HTMLElement>('.rail-track')!
        const dist = () => track.scrollWidth - window.innerWidth + 64
        gsap.to(track, {
          x: () => -dist(),
          ease: 'none',
          scrollTrigger: { trigger: ref.current, start: 'top top', end: () => `+=${dist()}`, scrub: 0.5, pin: true, invalidateOnRefresh: true },
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
        <h2 className="display section-title">If it can be <em>booked</em>, it’s here.</h2>
      </div>
      <div className="rail-track">
        {types.map((t, i) => (
          <Link to={`/explore?type=${t.slug}`} key={t.slug} className="rail-card" style={{ '--c': t.color } as CSSProperties}>
            {t.cover && <img src={t.cover.replace('w=1200', 'w=800')} alt="" loading="lazy" decoding="async" />}
            <span className="rail-idx mono">{String(i + 1).padStart(2, '0')}</span>
            <div className="rail-meta">
              <div className="row" style={{ gap: 9 }}>
                <TypeIcon icon={t.icon} size={20} color="#fff" />
                <span className="display" style={{ fontSize: 30 }}>{t.name}</span>
              </div>
              <p>{t.description}</p>
              <span className="rail-count mono">{t.count} bookable <ArrowRight size={13} weight="bold" /></span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}

function Bento({ className, icon: Icon, title, body, children }: { className: string; icon: typeof QrCode; title: string; body: ReactNode; children: ReactNode }) {
  return (
    <article className={`bento-cell glass ${className}`} data-reveal>
      <div className="bento-art" aria-hidden>{children}</div>
      <div className="bento-copy">
        <h3><Icon size={18} weight="duotone" /> {title}</h3>
        <p>{body}</p>
      </div>
    </article>
  )
}

function FeatureBento({ stats }: { stats?: Stats }) {
  const hours = ['09', '10', '11', '12', '13']
  const idle = stats?.idle_top
  return (
    <Reveal className="bento" stagger={0.07}>
      <Bento className="b-wide" icon={CalendarCheck} title="The timetable is law" body="The published LPU timetable is written into the booking ledger. A room teaching CSE326 at 10:00 is simply never offered at 10:00.">
        <div className="mini-week">
          <span />
          {WEEKDAYS.slice(0, 5).map((d) => <b key={d} className="mono">{d}</b>)}
          {hours.map((h, r) => (
            <div key={h} style={{ display: 'contents' }}>
              <b className="mono">{h}</b>
              {[0, 1, 2, 3, 4].map((c) => {
                const cls = (c === 1 && r === 1) || (c === 3 && (r === 0 || r === 1)) || (c === 0 && r === 3) ? 'class' : c === 2 && r === 2 ? 'mine' : ''
                return <i key={c} className={cls}>{cls === 'class' && r !== 0 ? 'CSE326' : cls === 'mine' ? 'You' : ''}</i>
              })}
            </div>
          ))}
        </div>
      </Bento>
      <Bento className="b-tall" icon={QrCode} title="Scan the door, not a form" body="Every room carries a QR poster. Scan it inside the grace window and you’re checked in, from any phone.">
        <div className="mini-scan">
          <div className="viewfinder"><span /><span /><span /><span />
            <div className="qr-plate" style={{ width: 92 }}><FakeQR /></div>
            <i className="scanline" />
          </div>
          <div className="mini-toast"><span className="led" /> You’re in. Room 34-201 until 16:00</div>
        </div>
      </Bento>
      <Bento className="b-third" icon={Timer} title="No-shows give it back" body="Miss the 15-minute grace and the slot returns to everyone. Repeat it and booking pauses.">
        <div className="mini-count">
          <strong className="mono">14:32</strong>
          <div className="strikes"><i className="hit" /><i className="hit" /><i /><i /><i /></div>
          <small className="mono">2 strikes · pause at 3</small>
        </div>
      </Bento>
      <Bento className="b-third" icon={Stamp} title="Approval chains you can edit" body="Requests go to the right HOD, set per resource type and role. Change the chain live, no redeploy.">
        <div className="mini-chain">
          <span className="done">Student</span><i />
          <span className="done">Request</span><i />
          <span className="live">HOD</span>
          <div className="mini-stamp mono">Approved</div>
        </div>
      </Bento>
      <Bento className="b-third" icon={ArrowsClockwise} title="Recurring, honestly" body="A clash in week 3 skips just that date, or rolls the whole series back. Your call.">
        <div className="mini-series">
          {Array.from({ length: 8 }, (_, i) => (
            <span key={i} className={i === 2 ? 'skip' : ''}><small className="mono">W{i + 1}</small></span>
          ))}
        </div>
      </Bento>
      <Bento className="b-idle" icon={ChartLineUp} title="The report that pays for the project" body={idle ? `Across campus, ${inr(stats!.idle_value_inr)} of equipment and space sat unused in the last 28 days. Utilisation: ${pct(stats!.utilisation, 1)}.` : 'Value against use, for every resource.'}>
        <div className="mini-idle">
          {idle?.image && <img src={idle.image.replace('w=1200', 'w=700')} alt="" loading="lazy" decoding="async" />}
          <div className="idle-figure">
            <span className="display">{idle ? inr(idle.value_inr) : '—'}</span>
            <span>{idle ? `${idle.name}, in use ${pct(idle.utilisation)} of the time` : ''}</span>
          </div>
        </div>
      </Bento>
      <Bento className="b-heat" icon={Database} title="Know when campus is busy" body="Occupancy by weekday and hour, from real bookings and classes.">
        <div className="mini-heat">
          {Array.from({ length: 7 * 12 }, (_, i) => {
            const x = i % 12
            const y = Math.floor(i / 12)
            const v = y > 4 ? 0.08 + ((x * 3) % 5) * 0.03 : Math.max(0.1, 1 - Math.abs(x - 5) / 5.4) * (0.55 + ((x * 7 + y * 5) % 5) * 0.11)
            return <i key={i} style={{ '--v': Math.min(1, v) } as CSSProperties} />
          })}
        </div>
      </Bento>
    </Reveal>
  )
}

export default function Landing() {
  const { user } = useAuth()
  const { mode, palette } = useTheme()
  const { data } = useQuery({ queryKey: ['public-stats'], queryFn: () => api.get<Stats>('/public/stats').then((r) => r.data) })
  const hero = useRef<HTMLDivElement>(null)
  const belowFold = useBelowFold()
  // Compiling the burst's shader stalls the page, so the rays wait until the hero's entrance has finished.
  const [burst, setBurst] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setBurst(true), 1800)
    return () => clearTimeout(id)
  }, [])

  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add('(prefers-reduced-motion: no-preference)', () => {
        gsap.from('.hero-line', { yPercent: 105, stagger: 0.1, duration: 1, ease: 'expo.out', delay: 0.1 })
        gsap.from('.hero-side > *', { y: 40, opacity: 0, stagger: 0.14, duration: 1, ease: 'expo.out', delay: 0.3, clearProps: 'all' })
        gsap.from('.hero-cta > *', { y: 16, opacity: 0, stagger: 0.08, duration: 0.7, ease: 'power3.out', delay: 0.6, clearProps: 'transform,opacity' })
        gsap.to('.hero-copy', { yPercent: -12, ease: 'none', scrollTrigger: { trigger: hero.current, start: 'top top', end: 'bottom top', scrub: true } })
        gsap.to('.hero-side', { yPercent: 10, ease: 'none', scrollTrigger: { trigger: hero.current, start: 'top top', end: 'bottom top', scrub: true } })
      })
      return () => mm.revert()
    },
    { scope: hero },
  )

  const cta = user ? '/explore' : '/login'
  const stats: { v: number; l: string }[] = [
    { v: data?.resources ?? 0, l: 'bookable resources' },
    { v: data?.types.length ?? 0, l: 'resource types' },
    { v: data?.bookings_30d ?? 0, l: 'bookings in 30 days' },
    { v: data?.conflicts_blocked ?? 0, l: 'clashes refused by the database' },
  ]
  const marquee = data?.names ?? []

  return (
    <div className="landing">
      <SmoothScroll />
      <Backdrop />
      <Sparks />

      <nav className="topbar glass landing-nav">
        <Wordmark />
        <div className="grow" />
        <a href="#how" className="nav-link hide-sm"><span>How it works</span></a>
        <a href="#features" className="nav-link hide-sm"><span>Features</span></a>
        <ThemeMenu />
        <Link to={cta} className="key key-amber key-sm">{user ? 'Open app' : 'Sign in'}</Link>
      </nav>

      <section className="hero" ref={hero}>
        {/* The burst is drawn once and spun by CSS on the compositor; a live full-screen shader lags laptops. */}
        {mode === 'dark' && (
          <div className="hero-burst">
            <div className="burst-spin">
              {burst && <PrismaticBurst colors={palette.burst} animationType="rotate" intensity={3} distort={0} rayCount={16} mixBlendMode="none" renderScale={0.5} stillAt={4} />}
            </div>
          </div>
        )}
        <div className="hero-grid">
          <div className="hero-copy">
            <span className="sticker hero-sticker"><span className="led" style={{ '--c': 'currentColor' } as CSSProperties} /> Lovely Professional University</span>
            <h1 className="display hero-title">
              <span className="hero-mask"><span className="hero-line">Every lab, hall</span></span>
              <span className="hero-mask"><span className="hero-line">and <em>turf</em> on campus.</span></span>
              <span className="hero-mask"><span className="hero-line">One tap away.</span></span>
            </h1>
            <BlurText
              className="hero-sub"
              text="No more WhatsApp chains, register books or phone calls to Block 34. See what’s free, book it, scan in, and never get double-booked again."
              delay={22}
              animateBy="words"
            />
            <div className="hero-cta">
              <Link to={cta} className="key key-amber key-lg">
                Start booking <ArrowRight weight="bold" />
              </Link>
              <a href="#how" className="key key-ghost key-lg">Why it can’t double-book</a>
            </div>
          </div>
          <div className="hero-side">
            <DepartureBoard names={marquee} />
            <HeroTicket />
          </div>
        </div>
      </section>

      <section className="marquee" aria-hidden>
        <div className="marquee-track">
          {[0, 1].map((copy) => (
            <span key={copy} className="marquee-text">
              {(marquee.length ? marquee : FALLBACK).map((n) => (
                <span key={n}>{n}<i>✦</i></span>
              ))}
            </span>
          ))}
        </div>
      </section>

      <Reveal className="page stats-strip" stagger={0.06}>
        <div className="stats-grid">
          {stats.map((s) => (
            <div key={s.l} data-reveal className="stat-big glass">
              <span className="display"><Counter to={s.v} duration={1.5} /></span>
              <span className="stat-label">{s.l}</span>
            </div>
          ))}
          <div data-reveal className="stat-big glass zero">
            <span className="display">0</span>
            <span className="stat-label">double-bookings. ever.</span>
          </div>
        </div>
      </Reveal>

      {belowFold ? (
        <>
          <RaceScene />
          <TypeRail types={data?.types ?? []} />

          <section id="features" className="page features">
            <Reveal>
              <div className="eyebrow" data-reveal>What you get</div>
              <h2 className="display section-title" data-reveal>Built for how LPU <em>actually</em> runs.</h2>
              <p className="hand" data-reveal style={{ marginTop: 6 }}>(no, really. it knows your timetable.)</p>
            </Reveal>
            <FeatureBento stats={data} />
          </section>

          <section className="page final-cta">
            <Reveal className="final-panel">
              <h2 data-reveal className="display">Book it <em>before</em> someone else does.</h2>
              <div data-reveal>
                <Link to={cta} className="key key-lg final-key">
                  <ShinyText text={user ? 'Open BookMyCampus' : 'Sign in or create an account'} color="var(--primary-foreground)" shineColor="#ffffff" speed={3} />
                  <ArrowRight weight="bold" />
                </Link>
              </div>
            </Reveal>
          </section>

          <footer className="landing-foot">
            <Wordmark small />
            <span className="mono muted" style={{ fontSize: 11 }}>Django · PostgreSQL range types · React · P20, Track P</span>
          </footer>
        </>
      ) : (
        <div style={{ height: '200vh' }} />
      )}
    </div>
  )
}
