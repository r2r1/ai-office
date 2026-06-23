import { useEffect, useRef, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

const KIND_COLOR: Record<string, string> = {
  error:    "#cf6679",
  done:     "#a0e0ab",
  thinking: "#ffac2e",
  hired:    "#a0c0ff",
  speech:   "var(--text-dim)",
  system:   "var(--muted)",
}

interface RightPanelProps {
  collapsed: boolean
  onToggle: () => void
}

export function RightPanel({ collapsed, onToggle }: RightPanelProps) {
  const [tab, setTab] = useState<"feed" | "chat">("chat")
  const { state } = useOffice()

  return (
    <motion.div
      initial={false}
      animate={{ width: collapsed ? 36 : 300 }}
      transition={{ type: "spring", stiffness: 280, damping: 30 }}
      style={{
        flexShrink: 0, height: "100%", display: "flex", flexDirection: "column",
        borderRadius: "var(--radius-xl)",
        background: "var(--surface)",
        backdropFilter: "blur(28px) saturate(160%)", WebkitBackdropFilter: "blur(28px) saturate(160%)",
        border: "1px solid var(--hairline)",
        boxShadow: "var(--shadow-lg), 0 1px 0 var(--inset-hi) inset",
        overflow: "hidden", position: "relative",
      }}>

      {/* Кнопка-тоггл (всегда видна) */}
      <button onClick={onToggle}
        style={{
          position: "absolute", top: 12, left: collapsed ? "50%" : 12,
          transform: collapsed ? "translateX(-50%)" : "none",
          zIndex: 10, width: 28, height: 28, border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-xs)", background: "var(--surface-strong)",
          cursor: "pointer", color: "var(--muted)", fontSize: 12,
          display: "flex", alignItems: "center", justifyContent: "center",
          transition: "left 0.3s, transform 0.3s",
        }}>
        {collapsed ? "◁" : "▷"}
      </button>

      {/* Контент (скрыт при collapse) */}
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

            {/* Вкладки */}
            <div style={{
              display: "flex", borderBottom: "1px solid var(--hairline)",
              paddingLeft: 48, paddingRight: 12, paddingTop: 8, flexShrink: 0,
            }}>
              {(["chat", "feed"] as const).map(t => {
                const label = t === "chat" ? "Чат" : "Журнал"
                const isActive = tab === t
                return (
                  <button key={t} onClick={() => setTab(t)}
                    style={{
                      padding: "8px 14px", fontSize: 12.5, fontWeight: isActive ? 500 : 400,
                      color: isActive ? "var(--text)" : "var(--muted)",
                      background: "none", border: "none",
                      borderBottom: isActive ? "2px solid var(--mercury-a)" : "2px solid transparent",
                      marginBottom: -1, cursor: "pointer", whiteSpace: "nowrap",
                      fontFamily: "var(--font-sans)", transition: "color 0.15s",
                    }}>
                    {label}
                    {t === "feed" && state.feed.length > 0 && (
                      <span style={{
                        marginLeft: 6, fontSize: 9, padding: "1px 5px", borderRadius: 99,
                        background: isActive ? "rgba(255,172,46,0.15)" : "var(--hairline-soft)",
                        color: isActive ? "var(--mercury-a)" : "var(--muted)",
                        border: `1px solid ${isActive ? "rgba(255,172,46,0.3)" : "var(--hairline)"}`,
                      }}>{state.feed.length}</span>
                    )}
                  </button>
                )
              })}
            </div>

            {tab === "chat" && <ChatTab />}
            {tab === "feed" && <FeedTab />}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ── Чат офиса ────────────────────────────────────────────────────────────────
function ChatTab() {
  const { state } = useOffice()
  const [messages, setMessages] = useState<any[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  async function load() { setMessages((await api.chatGet()).messages || []) }
  useEffect(() => { load() }, [state.feed.length])   // eslint-disable-line
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages])

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    setMessages(m => [...m, { from: "user", text, ts: Date.now() / 1000 }])
    setInput("")
    await api.chatPost(text)
    setSending(false)
    setTimeout(load, 600)
  }

  return (
    <>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.length === 0 && (
          <div style={{ color: "var(--faint)", fontSize: 12, textAlign: "center", paddingTop: 40, lineHeight: 1.6 }}>
            Напишите что-нибудь —<br />вся команда услышит
          </div>
        )}
        {messages.map((m, i) => {
          const mine = m.from === "user"
          const isQ  = m.kind === "question"
          return (
            <div key={i} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "88%" }}>
              {!mine && (
                <div style={{ fontSize: 9.5, color: "var(--muted)", marginBottom: 3, paddingLeft: 2 }}>{m.from}</div>
              )}
              <div style={{
                fontSize: 12, lineHeight: 1.5, padding: "8px 11px", wordBreak: "break-word",
                borderRadius: mine
                  ? "var(--radius-md) var(--radius-md) 4px var(--radius-md)"
                  : "var(--radius-md) var(--radius-md) var(--radius-md) 4px",
                background: mine ? "var(--text)" : "var(--surface-strong)",
                color: mine ? "var(--bg)" : "var(--text-dim)",
                border: mine ? "none" : `1px solid ${isQ ? "rgba(255,172,46,0.3)" : "var(--hairline)"}`,
                borderLeft: isQ ? "3px solid var(--mercury-a)" : undefined,
              }}>
                {m.text}
              </div>
              {m.ts && (
                <div style={{ fontSize: 9, color: "var(--faint)", marginTop: 3, textAlign: mine ? "right" : "left", paddingLeft: 2 }}>
                  {new Date(m.ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}
                </div>
              )}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      <div style={{ display: "flex", gap: 6, padding: "10px 12px", borderTop: "1px solid var(--hairline)", flexShrink: 0 }}>
        <input value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
          placeholder="Сообщение офису…"
          style={{
            flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
            borderRadius: "var(--radius-pill)", padding: "8px 14px", color: "var(--text)",
            fontSize: 12, outline: "none", fontFamily: "var(--font-sans)",
            transition: "border-color 0.15s",
          }}
          onFocus={e => (e.currentTarget.style.borderColor = "rgba(255,172,46,0.4)")}
          onBlur={e => (e.currentTarget.style.borderColor = "")} />
        <button onClick={send} disabled={sending || !input.trim()}
          style={{
            border: "none", borderRadius: "var(--radius-pill)", padding: "0 14px",
            background: input.trim() && !sending ? MERCURY : "var(--ghost)",
            color: input.trim() && !sending ? "#0a0a0a" : "var(--faint)",
            cursor: input.trim() ? "pointer" : "default", fontSize: 13, transition: "all 0.15s",
            fontFamily: "var(--font-sans)",
          }}>
          {sending ? "…" : "▶"}
        </button>
      </div>
    </>
  )
}

// ── Журнал событий ───────────────────────────────────────────────────────────
function FeedTab() {
  const { state } = useOffice()
  const feed = [...state.feed].reverse()
  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }) }, [state.feed.length])

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
      {feed.length === 0 && (
        <div style={{ color: "var(--faint)", fontSize: 12, textAlign: "center", paddingTop: 40 }}>
          События появятся после старта
        </div>
      )}
      {feed.map(f => (
        <div key={f.id} style={{
          display: "flex", gap: 8, padding: "7px 14px",
          borderBottom: "1px solid var(--hairline-soft)",
          animation: "fade-in 0.2s ease",
        }}>
          <span style={{ fontSize: 13, flexShrink: 0, paddingTop: 1 }}>{f.icon}</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            {f.who && <div className="mono" style={{ fontSize: 9, color: "var(--faint)", marginBottom: 2 }}>{f.who}</div>}
            <div style={{
              fontSize: 11.5, lineHeight: 1.45,
              color: KIND_COLOR[f.kind] ?? "var(--text-dim)",
              wordBreak: "break-word",
            }}>
              {f.text}
            </div>
          </div>
          {f.ts && (
            <span className="mono" style={{ fontSize: 8.5, color: "var(--faint)", flexShrink: 0, paddingTop: 2 }}>
              {new Date(f.ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
