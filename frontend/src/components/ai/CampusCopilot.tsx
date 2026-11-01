import {
  ArrowRight,
  ArrowUp,
  Buildings,
  CalendarCheck,
  ChartBar,
  Check,
  CheckCircle,
  Copy,
  MagnifyingGlass,
  Sparkle,
  Ticket,
  Trash,
  UsersThree,
  Wrench,
  X,
} from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { STATUS_COLOR } from '../../lib/format'
import Markdown from './Markdown'

interface UICard {
  type: string
  title?: string
  rooms?: Array<{
    id: number
    code: string
    name: string
    building: string
    floor: string
    room: string
    capacity: number
    type: string
    features: string[]
    requires_approval: boolean
    image: string
  }>
  booking?: {
    id: number
    reference: string
    title: string
    resource_code: string
    resource_name: string
    building: string
    date: string
    time: string
    status: string
    status_label: string
    attendees: number
  }
  bookings?: Array<{
    id: number
    reference: string
    title: string
    resource_code: string
    resource_name: string
    building: string
    date: string
    time: string
    status: string
    status_label: string
    attendees: number
  }>
  ticket?: {
    id: number
    room_code: string
    room_name: string
    title: string
    kind: string
    status: string
    displaced_bookings: number
  }
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  cards?: UICard[]
  toolCalls?: string[]
  timestamp: string
}

interface Suggestion {
  label: string
  prompt: string
}

/** What each backend tool did, in words a student would use. */
const TOOL_LABEL: Record<string, string> = {
  search_rooms: 'Searched rooms',
  check_room_schedule: 'Checked the schedule',
  get_my_bookings: 'Looked up your bookings',
  book_room: 'Made the booking',
  cancel_booking: 'Cancelled the booking',
  report_maintenance: 'Reported the fault',
  get_campus_overview: 'Checked campus vacancy',
}

function starterIcon(label: string) {
  const l = label.toLowerCase()
  if (/booking/.test(l)) return Ticket
  if (/report|issue|breakdown/.test(l)) return Wrench
  if (/vacan|overview/.test(l)) return ChartBar
  if (/schedule/.test(l)) return CalendarCheck
  return MagnifyingGlass
}

const FIELD_SIZING = CSS.supports('field-sizing', 'content')

/** Holds its own text, so typing never re-renders the conversation above it. */
function Composer({ busy, inputRef, onSend }: { busy: boolean; inputRef: RefObject<HTMLTextAreaElement | null>; onSend: (text: string) => void }) {
  const [text, setText] = useState('')

  const send = () => {
    if (!text.trim() || busy) return
    onSend(text)
    setText('')
    if (inputRef.current) inputRef.current.style.height = 'auto'
  }

  return (
    <form
      className="cp-composer"
      onSubmit={(e) => {
        e.preventDefault()
        send()
      }}
    >
      <div className="cp-input">
        <textarea
          ref={inputRef}
          rows={1}
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            if (FIELD_SIZING) return
            e.target.style.height = 'auto'
            e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          placeholder="Ask about rooms, bookings or faults…"
          aria-label="Message Campus Copilot"
          maxLength={1000}
        />
        <button type="submit" disabled={!text.trim() || busy} className="key key-primary key-icon cp-send" aria-label="Send">
          <ArrowUp size={16} weight="bold" />
        </button>
      </div>
      <div className="cp-hint">Enter to send · Shift + Enter for a new line</div>
    </form>
  )
}

export default function CampusCopilot() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [copiedRef, setCopiedRef] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Fetch contextual suggestions on mount
  useEffect(() => {
    if (!user) return
    api
      .get<{ suggestions: Suggestion[] }>('/ai/suggestions')
      .then((res) => {
        if (res.data?.suggestions) {
          setSuggestions(res.data.suggestions)
        }
      })
      .catch(() => {
        /* fallback to default suggestions */
        setSuggestions([
          { label: 'Find Room in Block 34', prompt: 'Find an available classroom in Block 34 for 30 students today' },
          { label: 'My Bookings', prompt: 'What are my active and upcoming bookings?' },
          { label: 'Campus Vacancy', prompt: 'Which campus blocks have the most vacant rooms right now?' },
          { label: 'Rooms with Projector', prompt: 'Show me rooms that have a projector and AC' },
        ])
      })
  }, [user])

  // Global keyboard shortcut (Ctrl+K or Cmd+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setIsOpen((prev) => !prev)
      } else if (e.key === 'Escape' && isOpen) {
        setIsOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  // Scroll to bottom on new messages
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      inputRef.current?.focus()
    }
  }, [messages, isOpen, isLoading])


  const handleSendMessage = async (textToSend: string) => {
    const query = textToSend.trim()
    if (!query || isLoading) return

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages((prev) => [...prev, userMsg])
    setIsLoading(true)

    // Prepare history for agent context
    const historyPayload = messages.slice(-8).map((m) => ({
      role: m.role,
      content: m.content,
    }))

    try {
      const res = await api.post('/ai/chat', {
        message: query,
        history: historyPayload,
      })

      const assistantMsg: ChatMessage = {
        id: `ast_${Date.now()}`,
        role: 'assistant',
        content: res.data.reply || 'Request completed.',
        cards: res.data.cards || [],
        toolCalls: res.data.tool_calls_executed || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      setMessages((prev) => [...prev, assistantMsg])
    } catch (err: any) {
      toast.error('Copilot request failed: ' + (err.response?.data?.error || err.message))
      setMessages((prev) => [
        ...prev,
        {
          id: `ast_err_${Date.now()}`,
          role: 'assistant',
          content: 'Sorry, I encountered an issue communicating with the campus services. Please try again.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handleCopy = (refText: string) => {
    navigator.clipboard.writeText(refText)
    setCopiedRef(refText)
    toast.success(`Copied ${refText} to clipboard!`)
    setTimeout(() => setCopiedRef(null), 2000)
  }

  const open = (path: string) => {
    setIsOpen(false)
    navigate(path)
  }

  const handleClearChat = () => {
    setMessages([])
    toast.info('Chat history cleared.')
  }

  if (!user) return null

  const firstName = user.name.split(' ')[0]

  return (
    <>
      {/* Floating launcher */}
      <div className="copilot-launcher-container">
        <motion.button
          whileHover={{ y: -2 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => setIsOpen(true)}
          className="copilot-launcher-btn"
          title="Open Campus Copilot (Ctrl + K)"
          aria-label="Open Campus Copilot"
        >
          <span className="cp-orb"><Sparkle size={16} weight="fill" /></span>
          <span className="cp-launch-label">Ask Copilot</span>
          <kbd className="cp-launch-kbd">Ctrl K</kbd>
        </motion.button>
      </div>

      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div className="cp-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setIsOpen(false)} />

            <motion.aside
              className="cp-panel"
              role="dialog"
              aria-label="Campus Copilot"
              initial={{ x: '104%' }}
              animate={{ x: 0 }}
              exit={{ x: '104%' }}
              transition={{ type: 'spring', damping: 32, stiffness: 320 }}
            >
              <header className="cp-head">
                <span className="cp-orb lg"><Sparkle size={19} weight="fill" /></span>
                <div className="grow">
                  <div className="cp-title">Campus Copilot</div>
                  <div className="cp-sub"><span className="led pulse" /> Knows live rooms, bookings and timetables</div>
                </div>
                {messages.length > 0 && (
                  <button onClick={handleClearChat} className="icon-btn" title="Clear conversation" aria-label="Clear conversation">
                    <Trash size={16} />
                  </button>
                )}
                <button onClick={() => setIsOpen(false)} className="icon-btn" title="Close (Esc)" aria-label="Close Copilot">
                  <X size={17} />
                </button>
              </header>

              <div className="cp-feed" data-lenis-prevent>
                {messages.length === 0 ? (
                  <div className="cp-welcome">
                    <h3 className="display">Hey {firstName}, <em>what do you need?</em></h3>
                    <p>Ask in plain words. I can find a free room, book it, check your passes, or report a fault.</p>
                    <div className="cp-starters">
                      {suggestions.map((sug, i) => {
                        const Icon = starterIcon(sug.label)
                        return (
                          <button key={i} className="cp-starter" onClick={() => handleSendMessage(sug.prompt)} title={sug.prompt}>
                            <Icon size={19} weight="duotone" />
                            <strong>{sug.label}</strong>
                            <small>{sug.prompt}</small>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ) : (
                  messages.map((msg) => (
                    <div key={msg.id} className={`cp-msg ${msg.role}`}>
                      {msg.role === 'user' ? (
                        <div className="cp-bubble">{msg.content}</div>
                      ) : (
                        <>
                          {!!msg.toolCalls?.length && (
                            <div className="cp-did">
                              {[...new Set(msg.toolCalls)].map((t) => (
                                <span key={t}><Check size={11} weight="bold" /> {TOOL_LABEL[t] ?? 'Checked campus data'}</span>
                              ))}
                            </div>
                          )}
                          <Markdown text={msg.content} />
                        </>
                      )}

                      {!!msg.cards?.length && (
                        <div className="cp-cards">
                          {msg.cards.map((card, cIdx) => (
                            <div key={cIdx}>
                              {card.type === 'room_list' && card.rooms && (
                                <section className="cp-card">
                                  {card.title && <h5><Buildings size={14} weight="duotone" /> {card.title}</h5>}
                                  {card.rooms.map((r) => (
                                    <button key={r.id} className="cp-room" onClick={() => open(`/resources/${r.id}`)}>
                                      {r.image ? <img src={r.image.replace('w=1200', 'w=160')} alt="" loading="lazy" /> : <span className="cp-room-ph stripes" />}
                                      <span className="grow">
                                        <strong className="truncate">{r.name}</strong>
                                        <small className="truncate">{r.building}{r.floor ? ` · Floor ${r.floor}` : ''}</small>
                                        <small className="cp-room-meta">
                                          <UsersThree size={12} /> {r.capacity}
                                          {r.features?.slice(0, 2).map((f) => <i key={f}>{f}</i>)}
                                        </small>
                                      </span>
                                      <ArrowRight size={15} className="cp-go" />
                                    </button>
                                  ))}
                                </section>
                              )}

                              {card.type === 'booking_success' && card.booking && (
                                <section className="cp-pass">
                                  <div className="cp-pass-main">
                                    <div className="cp-pass-ok"><CheckCircle size={16} weight="fill" /> {card.title || 'Booking reserved'}</div>
                                    <strong>{card.booking.title}</strong>
                                    <small>{card.booking.resource_name} · {card.booking.building}</small>
                                    <div className="cp-pass-when mono">{card.booking.date} · {card.booking.time}</div>
                                  </div>
                                  <div className="cp-pass-stub">
                                    <span className="eyebrow">Ref</span>
                                    <button className="mono" onClick={() => handleCopy(card.booking!.reference)} title="Copy reference">
                                      {card.booking.reference}
                                      {copiedRef === card.booking.reference ? <Check size={12} /> : <Copy size={12} />}
                                    </button>
                                    <span className="tag" style={{ '--c': STATUS_COLOR[card.booking.status] } as CSSProperties}>{card.booking.status_label}</span>
                                  </div>
                                  <button className="key key-primary key-sm cp-pass-open" onClick={() => open(`/bookings/${card.booking!.id}`)}>
                                    Open pass <ArrowRight size={14} weight="bold" />
                                  </button>
                                </section>
                              )}

                              {card.type === 'booking_list' && card.bookings && (
                                <section className="cp-card">
                                  {card.title && <h5><CalendarCheck size={14} weight="duotone" /> {card.title}</h5>}
                                  {card.bookings.map((b) => (
                                    <button key={b.id} className="cp-row" onClick={() => open(`/bookings/${b.id}`)}>
                                      <span className="led" style={{ '--c': STATUS_COLOR[b.status] ?? 'var(--fg-3)' } as CSSProperties} />
                                      <span className="grow">
                                        <strong className="truncate">{b.title}</strong>
                                        <small className="truncate">{b.resource_name} · {b.date}, {b.time}</small>
                                      </span>
                                      <ArrowRight size={15} className="cp-go" />
                                    </button>
                                  ))}
                                </section>
                              )}

                              {card.type === 'maintenance_ticket' && card.ticket && (
                                <section className="cp-card cp-fault">
                                  <h5><Wrench size={14} weight="duotone" /> {card.title}</h5>
                                  <strong>{card.ticket.title}</strong>
                                  <small>{card.ticket.room_name} · sent to the maintenance team</small>
                                </section>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      <time className="cp-time">{msg.timestamp}</time>
                    </div>
                  ))
                )}

                {isLoading && (
                  <div className="cp-thinking" role="status">
                    <span className="cp-dots"><i /><i /><i /></span>
                    Checking the campus…
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              <Composer busy={isLoading} inputRef={inputRef} onSend={handleSendMessage} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
