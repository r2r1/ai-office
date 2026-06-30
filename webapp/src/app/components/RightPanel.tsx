import { useEffect, useRef, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { useThrottled } from "../hooks"
import { roleName } from "../../data/roles"

// дружелюбное имя отправителя в общем чате (CEO вместо orchestrator_1 и т.п.)
function senderName(m: any): string {
  if (m.role && m.role !== "user") return roleName(m.role)
  if (typeof m.from === "string" && m.from !== "user") {
    const base = m.from.replace(/_\d+$/, "")
    return roleName(base)
  }
  return m.from || ""
}

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
        backdropFilter: "blur(30px) saturate(180%)", WebkitBackdropFilter: "blur(30px) saturate(180%)",
        border: "1px solid var(--hairline-strong)",
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
  const [pending, setPending] = useState<any[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const tick = useThrottled(state.feed.length, 2000)
  async function load() {
    const server = (await api.chatGet()).messages || []
    setMessages(server)
    setPending(p => p.filter(pm => !server.some((sm: any) => sm.from === "user" && sm.text === pm.text)))
  }
  useEffect(() => { load() }, [tick])   // eslint-disable-line
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages, pending])

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    setPending(p => [...p, { from: "user", text, ts: Date.now() / 1000 }])
    setInput("")
    try {
      await api.chatPost(text)
    } finally {
      setSending(false)
      setTimeout(load, 600)
    }
  }

  const allMessages = [...messages, ...pending]

  return (
    <>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
        {allMessages.length === 0 && (
          <div style={{ color: "var(--faint)", fontSize: 12, textAlign: "center", paddingTop: 40, lineHeight: 1.6 }}>
            Напишите что-нибудь —<br />вся команда услышит
          </div>
        )}
        {allMessages.map((m, i) => {
          const mine = m.from === "user"
          const isQ  = m.kind === "question"
          return (
            <div key={i} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "88%" }}>
              {!mine && (
                <div style={{ fontSize: 9.5, color: "var(--muted)", marginBottom: 3, paddingLeft: 2 }}>{senderName(m)}</div>
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

  // Блок 3: подгружаем последние решения CEO для UI «Почему?»
  const [decisions, setDecisions] = useState<any[]>([])
  const [expandedDid, setExpandedDid] = useState<string | null>(null)
  useEffect(() => {
    const load = () => { api.get("/api/decisions").then(d => setDecisions(d?.decisions || [])).catch(() => {}) }
    load(); const t = setInterval(load, 8000); return () => clearInterval(t)
  }, [])
  // Сопоставляем CEO-feed-итемы с решениями по времени и совпадению мысли
  const decisionForFeed = (f: any) => {
    if (f.who !== "orchestrator" && !(f.text || "").startsWith("🧭")) return null
    const txt = (f.text || "").replace(/^🧭\s*/, "").slice(0, 30).toLowerCase()
    return decisions.find(d => (d.thought || "").slice(0, 30).toLowerCase() === txt) || null
  }

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
            {(() => {
              const dec = decisionForFeed(f)
              if (!dec) return null
              const open = expandedDid === dec.id
              return (
                <div style={{ marginTop: 4 }}>
                  <button onClick={() => setExpandedDid(open ? null : dec.id)}
                    style={{ fontSize: 10, color: "var(--mercury-a)", background: "transparent",
                      border: "none", cursor: "pointer", padding: 0, textDecoration: "underline" }}>
                    🔍 Почему? {open ? "↑" : "↓"}
                  </button>
                  {open && (
                    <div style={{ marginTop: 6, padding: "8px 10px", background: "var(--surface-soft)",
                      borderLeft: "2px solid var(--mercury-a)", borderRadius: 4, fontSize: 11 }}>
                      <div style={{ color: "var(--text-dim)" }}>Уверенность: <b>{dec.confidence}/100</b></div>
                      {dec.expected_effect && <div style={{ color: "var(--text-dim)", marginTop: 4 }}>
                        Ожидаемый эффект: {dec.expected_effect}</div>}
                      {dec.alternatives?.length > 0 && (
                        <div style={{ marginTop: 6 }}>
                          <div style={{ color: "var(--muted)", marginBottom: 3 }}>Рассматривал:</div>
                          {dec.alternatives.map((a: any, i: number) => (
                            <div key={i} style={{ color: "var(--text-dim)", fontSize: 10.5, marginLeft: 6 }}>
                              • <b>{a.action}</b> — {a.reason}
                            </div>
                          ))}
                        </div>
                      )}
                      {dec.risks?.length > 0 && (
                        <div style={{ marginTop: 6, color: "#ffac2e", fontSize: 10.5 }}>
                          ⚠ {dec.risks.join(" · ")}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })()}
          </div>
          {(f as any).ts && (
            <span className="mono" style={{ fontSize: 8.5, color: "var(--faint)", flexShrink: 0, paddingTop: 2 }}>
              {new Date((f as any).ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
