import {
  ArrowSquareOut,
  ArrowUp,
  Buildings,
  CalendarCheck,
  Check,
  CheckCircle,
  Copy,
  Lightning,
  PaperPlaneTilt,
  Robot,
  Sparkle,
  Trash,
  UsersThree,
  Wrench,
  X,
} from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'

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

export default function CampusCopilot() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [copiedRef, setCopiedRef] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

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

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || input).trim()
    if (!query || isLoading) return

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages((prev) => [...prev, userMsg])
    setInput('')
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

  const handleClearChat = () => {
    setMessages([])
    toast.info('Chat history cleared.')
  }

  if (!user) return null

  return (
    <>
      {/* Floating Copilot Launcher Button */}
      <div className="copilot-launcher-container" style={{ position: 'fixed', bottom: 28, right: 28, zIndex: 90 }}>
        <motion.button
          whileHover={{ scale: 1.05, y: -2 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => setIsOpen(true)}
          className="copilot-launcher-btn"
          title="Open Campus Copilot AI (Ctrl + K)"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 18px 10px 14px',
            background: 'linear-gradient(135deg, rgba(245, 165, 36, 0.25) 0%, rgba(139, 124, 255, 0.3) 100%), #10132a',
            border: '1px solid rgba(255, 255, 255, 0.22)',
            borderRadius: 30,
            boxShadow: '0 12px 35px -8px rgba(245, 165, 36, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.1)',
            backdropFilter: 'blur(16px)',
            cursor: 'pointer',
            color: 'var(--paper)',
          }}
        >
          <div
            style={{
              position: 'relative',
              display: 'grid',
              placeItems: 'center',
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #f5a524, #8b7cff)',
              color: '#05060c',
            }}
          >
            <Sparkle size={18} weight="fill" />
            <span
              style={{
                position: 'absolute',
                top: -1,
                right: -1,
                width: 9,
                height: 9,
                borderRadius: '50%',
                background: '#3ee6c1',
                boxShadow: '0 0 8px #3ee6c1',
              }}
            />
          </div>
          <div style={{ textAlign: 'left', lineHeight: 1.15 }}>
            <div style={{ fontWeight: 700, fontSize: 13.5, letterSpacing: '-0.01em', display: 'flex', alignItems: 'center', gap: 6 }}>
              Campus Copilot
              <span
                style={{
                  fontSize: 9.5,
                  fontWeight: 800,
                  padding: '2px 5px',
                  borderRadius: 6,
                  background: 'rgba(245, 165, 36, 0.25)',
                  color: 'var(--amber)',
                  letterSpacing: '0.04em',
                }}
              >
                GROQ AI
              </span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>Ask anything</span>
              <span style={{ opacity: 0.6 }}>·</span>
              <kbd
                style={{
                  fontSize: 10,
                  fontFamily: 'var(--font-mono)',
                  background: 'rgba(255,255,255,0.08)',
                  padding: '1px 4px',
                  borderRadius: 4,
                }}
              >
                Ctrl+K
              </kbd>
            </div>
          </div>
        </motion.button>
      </div>

      {/* Slide-over Copilot Drawer */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop Dimmer */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(5, 6, 12, 0.65)',
                backdropFilter: 'blur(8px)',
                zIndex: 100,
              }}
            />

            {/* Slide Drawer Panel */}
            <motion.div
              initial={{ x: '100%', opacity: 0.5 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: '100%', opacity: 0 }}
              transition={{ type: 'spring', damping: 28, stiffness: 280 }}
              style={{
                position: 'fixed',
                top: 0,
                right: 0,
                bottom: 0,
                width: '100%',
                maxWidth: 480,
                background: 'linear-gradient(180deg, #0e1124 0%, #080a14 100%)',
                borderLeft: '1px solid rgba(255, 255, 255, 0.15)',
                boxShadow: '-20px 0 60px rgba(0, 0, 0, 0.8)',
                zIndex: 101,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {/* Header */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '18px 20px',
                  borderBottom: '1px solid var(--hairline)',
                  background: 'rgba(255, 255, 255, 0.02)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: 12,
                      background: 'linear-gradient(135deg, #f5a524, #8b7cff)',
                      display: 'grid',
                      placeItems: 'center',
                      color: '#05060c',
                      boxShadow: '0 4px 16px rgba(245, 165, 36, 0.3)',
                    }}
                  >
                    <Robot size={22} weight="duotone" />
                  </div>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontWeight: 700, fontSize: 16 }}>Campus Copilot</span>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '2px 7px',
                          borderRadius: 8,
                          background: 'rgba(62, 230, 193, 0.15)',
                          color: 'var(--mint)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                        }}
                      >
                        <span
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: 'var(--mint)',
                            display: 'inline-block',
                          }}
                        />
                        Online
                      </span>
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                      Powered by Groq High-Speed LPU & PostgreSQL
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {messages.length > 0 && (
                    <button
                      onClick={handleClearChat}
                      className="key key-ghost key-icon"
                      title="Clear Conversation"
                      style={{ padding: 6, fontSize: 13 }}
                    >
                      <Trash size={16} />
                    </button>
                  )}
                  <button
                    onClick={() => setIsOpen(false)}
                    className="key key-ghost key-icon"
                    title="Close Copilot (Esc)"
                    style={{ padding: 6, fontSize: 13 }}
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>

              {/* Chat Message Feed */}
              <div
                style={{
                  flex: 1,
                  overflowY: 'auto',
                  padding: '20px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 18,
                }}
              >
                {messages.length === 0 ? (
                  <div style={{ margin: 'auto 0', textAlign: 'center', padding: '10px 10px 30px' }}>
                    <div
                      style={{
                        width: 58,
                        height: 58,
                        borderRadius: 20,
                        background: 'linear-gradient(135deg, rgba(245, 165, 36, 0.2), rgba(139, 124, 255, 0.2))',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        display: 'grid',
                        placeItems: 'center',
                        margin: '0 auto 16px',
                        color: 'var(--amber)',
                      }}
                    >
                      <Sparkle size={30} weight="fill" />
                    </div>
                    <h3 style={{ fontSize: 19, fontWeight: 700, margin: '0 0 6px' }}>
                      Welcome, {user.name.split(' ')[0]}!
                    </h3>
                    <p style={{ fontSize: 13.5, color: 'var(--muted)', maxWidth: 360, margin: '0 auto 24px', lineHeight: 1.5 }}>
                      I am your autonomous campus concierge. Ask me to find vacant rooms, book a slot, check schedules, or file maintenance issues.
                    </p>

                    {/* Quick Suggestion Chips */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, textAlign: 'left' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                        Suggested Quick Actions
                      </div>
                      {suggestions.map((sug, i) => (
                        <button
                          key={i}
                          onClick={() => handleSendMessage(sug.prompt)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '11px 14px',
                            background: 'rgba(255, 255, 255, 0.04)',
                            border: '1px solid var(--hairline)',
                            borderRadius: 'var(--radius-s)',
                            cursor: 'pointer',
                            textAlign: 'left',
                            transition: 'all 0.15s ease',
                            color: 'var(--paper)',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)'
                            e.currentTarget.style.borderColor = 'rgba(245, 165, 36, 0.4)'
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)'
                            e.currentTarget.style.borderColor = 'var(--hairline)'
                          }}
                        >
                          <span style={{ fontSize: 13, fontWeight: 500 }}>{sug.prompt}</span>
                          <PaperPlaneTilt size={14} color="var(--amber)" style={{ opacity: 0.8 }} />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  messages.map((msg) => (
                    <div
                      key={msg.id}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        gap: 4,
                      }}
                    >
                      <div
                        style={{
                          maxWidth: '88%',
                          padding: '12px 16px',
                          borderRadius: msg.role === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                          background:
                            msg.role === 'user'
                              ? 'linear-gradient(135deg, #f5a524, #d4830c)'
                              : 'rgba(255, 255, 255, 0.06)',
                          color: msg.role === 'user' ? '#05060c' : 'var(--paper)',
                          border: msg.role === 'user' ? 'none' : '1px solid rgba(255, 255, 255, 0.1)',
                          boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
                          fontSize: 14,
                          lineHeight: 1.5,
                          whiteSpace: 'pre-wrap',
                          fontWeight: msg.role === 'user' ? 500 : 400,
                        }}
                      >
                        {msg.content}
                      </div>

                      {/* Tool Calls Indicator Badge */}
                      {msg.toolCalls && msg.toolCalls.length > 0 && (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 5,
                            marginTop: 3,
                            fontSize: 11,
                            color: 'var(--muted)',
                          }}
                        >
                          <Lightning size={12} color="var(--amber)" weight="fill" />
                          <span>Executed: {msg.toolCalls.join(', ')}</span>
                        </div>
                      )}

                      {/* Render UI Cards if returned by tools */}
                      {msg.cards && msg.cards.length > 0 && (
                        <div style={{ width: '100%', marginTop: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
                          {msg.cards.map((card, cIdx) => (
                            <div key={cIdx}>
                              {/* 1. Room List Card */}
                              {card.type === 'room_list' && card.rooms && (
                                <div
                                  style={{
                                    background: 'rgba(255, 255, 255, 0.03)',
                                    border: '1px solid var(--hairline)',
                                    borderRadius: 'var(--radius)',
                                    padding: '12px',
                                  }}
                                >
                                  {card.title && (
                                    <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--amber)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                                      <Buildings size={15} />
                                      {card.title}
                                    </div>
                                  )}
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    {card.rooms.map((r) => (
                                      <div
                                        key={r.id}
                                        style={{
                                          display: 'flex',
                                          alignItems: 'center',
                                          justifyContent: 'space-between',
                                          padding: '10px 12px',
                                          background: 'rgba(255, 255, 255, 0.04)',
                                          border: '1px solid rgba(255, 255, 255, 0.07)',
                                          borderRadius: 12,
                                        }}
                                      >
                                        <div>
                                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <span style={{ fontWeight: 700, fontSize: 13.5 }}>{r.name}</span>
                                            <span className="mono" style={{ fontSize: 11, padding: '2px 6px', borderRadius: 4, background: 'rgba(255,255,255,0.08)' }}>
                                              {r.code}
                                            </span>
                                          </div>
                                          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <span>{r.building} · Floor {r.floor}</span>
                                            <span>·</span>
                                            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                              <UsersThree size={12} /> {r.capacity} seats
                                            </span>
                                          </div>
                                          {r.features && r.features.length > 0 && (
                                            <div style={{ display: 'flex', gap: 4, marginTop: 5, flexWrap: 'wrap' }}>
                                              {r.features.slice(0, 3).map((f, fi) => (
                                                <span key={fi} style={{ fontSize: 10, padding: '1px 5px', borderRadius: 4, background: 'rgba(139, 124, 255, 0.15)', color: 'var(--violet)' }}>
                                                  {f}
                                                </span>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                        <button
                                          onClick={() => {
                                            setIsOpen(false)
                                            navigate(`/resources/${r.id}`)
                                          }}
                                          className="key key-primary"
                                          style={{ padding: '6px 12px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}
                                        >
                                          <span>View</span>
                                          <ArrowSquareOut size={13} />
                                        </button>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* 2. Booking Success Card */}
                              {card.type === 'booking_success' && card.booking && (
                                <div
                                  style={{
                                    background: 'linear-gradient(135deg, rgba(62, 230, 193, 0.1) 0%, rgba(16, 19, 42, 0.6) 100%)',
                                    border: '1px solid rgba(62, 230, 193, 0.3)',
                                    borderRadius: 'var(--radius)',
                                    padding: '14px 16px',
                                  }}
                                >
                                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--mint)', fontWeight: 700, fontSize: 13.5 }}>
                                      <CheckCircle size={18} weight="fill" />
                                      {card.title || 'Booking Reserved!'}
                                    </div>
                                    <span
                                      style={{
                                        fontSize: 10.5,
                                        fontWeight: 700,
                                        padding: '2px 8px',
                                        borderRadius: 6,
                                        background: 'rgba(62, 230, 193, 0.2)',
                                        color: 'var(--mint)',
                                      }}
                                    >
                                      {card.booking.status_label.toUpperCase()}
                                    </span>
                                  </div>

                                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>
                                    {card.booking.title}
                                  </div>
                                  <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
                                    {card.booking.resource_name} ({card.booking.building})
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '8px 10px', background: 'rgba(0,0,0,0.3)', borderRadius: 8, marginBottom: 12 }}>
                                    <div>
                                      <div style={{ fontSize: 10, color: 'var(--muted)' }}>DATE & TIME</div>
                                      <div style={{ fontSize: 12, fontWeight: 600 }}>{card.booking.date}</div>
                                      <div style={{ fontSize: 11, color: 'var(--paper-dim)' }}>{card.booking.time}</div>
                                    </div>
                                    <div>
                                      <div style={{ fontSize: 10, color: 'var(--muted)' }}>PASS REF</div>
                                      <div style={{ fontSize: 13, fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--amber)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                        {card.booking.reference}
                                        <button
                                          onClick={() => handleCopy(card.booking!.reference)}
                                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', padding: 2 }}
                                        >
                                          {copiedRef === card.booking.reference ? <Check size={12} color="var(--mint)" /> : <Copy size={12} />}
                                        </button>
                                      </div>
                                    </div>
                                  </div>

                                  <button
                                    onClick={() => {
                                      setIsOpen(false)
                                      navigate(`/bookings/${card.booking!.id}`)
                                    }}
                                    className="key key-primary"
                                    style={{ width: '100%', justifyContent: 'center', fontSize: 12.5 }}
                                  >
                                    Open Digital Boarding Pass
                                  </button>
                                </div>
                              )}

                              {/* 3. My Bookings List Card */}
                              {card.type === 'booking_list' && card.bookings && (
                                <div
                                  style={{
                                    background: 'rgba(255, 255, 255, 0.03)',
                                    border: '1px solid var(--hairline)',
                                    borderRadius: 'var(--radius)',
                                    padding: '12px',
                                  }}
                                >
                                  {card.title && (
                                    <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--amber)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                                      <CalendarCheck size={15} />
                                      {card.title}
                                    </div>
                                  )}
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    {card.bookings.map((b) => (
                                      <div
                                        key={b.id}
                                        style={{
                                          display: 'flex',
                                          alignItems: 'center',
                                          justifyContent: 'space-between',
                                          padding: '8px 10px',
                                          background: 'rgba(255, 255, 255, 0.04)',
                                          borderRadius: 8,
                                        }}
                                      >
                                        <div>
                                          <div style={{ fontSize: 13, fontWeight: 600 }}>{b.title}</div>
                                          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                                            {b.resource_name} · {b.date} ({b.time})
                                          </div>
                                        </div>
                                        <button
                                          onClick={() => {
                                            setIsOpen(false)
                                            navigate(`/bookings/${b.id}`)
                                          }}
                                          className="key key-ghost"
                                          style={{ fontSize: 11, padding: '4px 8px' }}
                                        >
                                          Pass
                                        </button>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* 4. Maintenance Ticket Card */}
                              {card.type === 'maintenance_ticket' && card.ticket && (
                                <div
                                  style={{
                                    background: 'rgba(255, 93, 143, 0.08)',
                                    border: '1px solid rgba(255, 93, 143, 0.3)',
                                    borderRadius: 'var(--radius)',
                                    padding: '12px 14px',
                                  }}
                                >
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--rose)', fontWeight: 700, fontSize: 13, marginBottom: 6 }}>
                                    <Wrench size={16} />
                                    {card.title}
                                  </div>
                                  <div style={{ fontSize: 13, fontWeight: 600 }}>{card.ticket.title}</div>
                                  <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>
                                    {card.ticket.room_name} · Dispatched to technician queue
                                  </div>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      <span style={{ fontSize: 10, color: 'var(--faint)', margin: '0 4px' }}>
                        {msg.timestamp}
                      </span>
                    </div>
                  ))
                )}

                {/* Loading indicator */}
                {isLoading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: 'rgba(255, 255, 255, 0.04)', borderRadius: 16, width: 'fit-content' }}>
                    <div className="loader-ticket" style={{ width: 16, height: 16 }} />
                    <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>
                      Querying campus database & executing ReAct tools...
                    </span>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Chat Input Bar */}
              <div
                style={{
                  padding: '16px 20px',
                  borderTop: '1px solid var(--hairline)',
                  background: 'rgba(255, 255, 255, 0.02)',
                }}
              >
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    handleSendMessage()
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    background: 'rgba(255, 255, 255, 0.06)',
                    border: '1px solid rgba(255, 255, 255, 0.12)',
                    borderRadius: 24,
                    padding: '4px 6px 4px 16px',
                  }}
                >
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask about rooms, bookings, or campus..."
                    style={{
                      flex: 1,
                      background: 'transparent',
                      border: 'none',
                      outline: 'none',
                      color: 'var(--paper)',
                      fontSize: 13.5,
                    }}
                    disabled={isLoading}
                  />
                  <button
                    type="submit"
                    disabled={!input.trim() || isLoading}
                    className="key key-primary key-icon"
                    style={{
                      width: 34,
                      height: 34,
                      borderRadius: '50%',
                      padding: 0,
                      opacity: !input.trim() || isLoading ? 0.4 : 1,
                    }}
                  >
                    <ArrowUp size={16} weight="bold" />
                  </button>
                </form>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, padding: '0 4px', fontSize: 10.5, color: 'var(--faint)' }}>
                  <span>Press Enter to send</span>
                  <span>Model: GPT-OSS-120B · Groq LPU</span>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
