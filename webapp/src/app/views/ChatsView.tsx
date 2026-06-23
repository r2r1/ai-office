import { useEffect, useRef, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, STATUS_COLOR } from "./ui"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface ChatsViewProps { initialAgent?: string }

export function ChatsView({ initialAgent }: ChatsViewProps) {
  const { state } = useOffice()
  const agents = Object.values(state.agents)
  const [active, setActive] = useState<string>(initialAgent || "office")
  const [messages, setMessages] = useState<any[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => { if (initialAgent) setActive(initialAgent) }, [initialAgent])

  async function load() {
    if (active === "office") setMessages((await api.chatGet()).messages || [])
    else setMessages((await api.thread(active)).messages || [])
  }
  useEffect(() => { load() }, [active, state.feed.length]) // eslint-disable-line
  useEffect(() => { feedRef.current?.scrollTo(0, feedRef.current.scrollHeight) }, [messages])

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    setMessages(m => [...m, { from: "user", text, ts: Date.now() / 1000 }])
    setInput("")
    if (active === "office") await api.chatPost(text)
    else await api.ask(active, text)
    setSending(false)
    setTimeout(load, 500)
  }

  const activeAgent = active !== "office" ? state.agents[active] : null
  const headerName = active === "office" ? "Общий чат" : (activeAgent?.name ?? "Агент")
  const headerSub  = active === "office"
    ? `Сообщение получат все ${agents.length} агентов`
    : (activeAgent?.lastMessage ?? "Личный диалог")

  return (
    <ViewShell>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* sidebar */}
        {sidebarOpen && (
          <div style={{ width: 260, flexShrink: 0, borderRight: "1px solid var(--hairline)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {/* заголовок sidebar */}
            <div style={{ padding: "18px 16px 12px", borderBottom: "1px solid var(--hairline-soft)", flexShrink: 0 }}>
              <div className="display" style={{ fontSize: 22, color: "var(--text)" }}>Команда</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>{agents.length} агентов</div>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
              {/* офис-канал */}
              <Row active={active === "office"} onClick={() => setActive("office")}
                emoji="🏢" name="Общий чат" sub="Написать всей команде" />

              {/* разделитель */}
              {agents.length > 0 && (
                <div className="mono" style={{ fontSize: 9, color: "var(--faint)", textTransform: "uppercase", letterSpacing: "1.5px", padding: "12px 8px 6px" }}>
                  Агенты
                </div>
              )}

              {agents.map(a => (
                <Row key={a.id} active={active === a.id} onClick={() => setActive(a.id)}
                  emoji={a.emoji} name={a.name} sub={a.lastMessage} dot={STATUS_COLOR[a.status]} />
              ))}
            </div>
          </div>
        )}

        {/* панель чата */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* шапка чата */}
          <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid var(--hairline)", flexShrink: 0,
            display: "flex", alignItems: "center", gap: 12 }}>
            <button onClick={() => setSidebarOpen(s => !s)}
              style={{ width: 28, height: 28, border: "1px solid var(--hairline)", borderRadius: "var(--radius-xs)",
                background: "transparent", cursor: "pointer", color: "var(--muted)", fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center" }}>
              {sidebarOpen ? "◁" : "▷"}
            </button>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)" }}>{headerName}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{headerSub}</div>
            </div>
            {activeAgent && (
              <span style={{ marginLeft: "auto", width: 8, height: 8, borderRadius: "50%", background: STATUS_COLOR[activeAgent.status], flexShrink: 0 }} />
            )}
          </div>

          {/* сообщения */}
          <div ref={feedRef} style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
            {messages.length === 0 && (
              <div style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", paddingTop: 60 }}>
                {active === "office" ? "Напишите что-нибудь — вся команда услышит" : "Начните разговор с агентом"}
              </div>
            )}
            {messages.map((m, i) => {
              const mine = m.from === "user"
              const isQuestion = m.kind === "question"
              return (
                <div key={i} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "78%" }}>
                  {!mine && (
                    <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>
                      {m.from}{isQuestion && " · вопрос"}
                    </div>
                  )}
                  <div style={{
                    fontSize: 13, lineHeight: 1.55, padding: "10px 14px",
                    borderRadius: mine ? "var(--radius-md) var(--radius-md) 4px var(--radius-md)" : "var(--radius-md) var(--radius-md) var(--radius-md) 4px",
                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                    background: mine ? "var(--text)" : "var(--surface-strong)",
                    color: mine ? "var(--bg)" : "var(--text-dim)",
                    border: mine ? "none" : `1px solid ${isQuestion ? "rgba(255,172,46,0.35)" : "var(--hairline)"}`,
                    borderLeft: isQuestion ? "3px solid var(--mercury-a)" : undefined,
                  }}>
                    {m.text}
                  </div>
                  {m.ts && (
                    <div style={{ fontSize: 9.5, color: "var(--faint)", marginTop: 4, textAlign: mine ? "right" : "left" }}>
                      {new Date(m.ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* ввод */}
          <div style={{ display: "flex", gap: 8, padding: "12px 16px", borderTop: "1px solid var(--hairline)", flexShrink: 0 }}>
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
              placeholder={active === "office" ? "Сообщение команде…" : `Написать ${activeAgent?.name ?? "агенту"}…`}
              style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
                borderRadius: "var(--radius-pill)", padding: "10px 18px", color: "var(--text)",
                fontSize: 13, outline: "none", transition: "border-color 0.15s", fontFamily: "var(--font-sans)" }}
              onFocus={e => (e.currentTarget.style.borderColor = "rgba(255,172,46,0.4)")}
              onBlur={e => (e.currentTarget.style.borderColor = "")} />
            <button onClick={send} disabled={sending || !input.trim()}
              style={{ border: "none", borderRadius: "var(--radius-pill)", padding: "0 22px",
                background: input.trim() && !sending ? MERCURY : "var(--ghost)",
                color: input.trim() && !sending ? "#0a0a0a" : "var(--faint)",
                cursor: input.trim() ? "pointer" : "default", fontSize: 14,
                transition: "all 0.15s", fontFamily: "var(--font-sans)" }}>
              {sending ? "…" : "▶"}
            </button>
          </div>
        </div>
      </div>
    </ViewShell>
  )
}

function Row({ active, onClick, emoji, name, sub, dot }: {
  active: boolean; onClick: () => void; emoji: string; name: string; sub?: string; dot?: string
}) {
  return (
    <div onClick={onClick}
      style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px",
        borderRadius: "var(--radius-sm)", cursor: "pointer",
        background: active ? "var(--hairline-soft)" : "transparent",
        borderLeft: `2px solid ${active ? "var(--mercury-a)" : "transparent"}`,
        marginBottom: 2, transition: "all 0.12s" }}
      onMouseEnter={e => { if (!active) (e.currentTarget as HTMLElement).style.background = "var(--surface-soft)" }}
      onMouseLeave={e => { if (!active) (e.currentTarget as HTMLElement).style.background = "transparent" }}>
      <div style={{ position: "relative", width: 34, height: 34, borderRadius: "50%", flexShrink: 0,
        background: active ? "var(--hairline-strong)" : "var(--avatar-idle)",
        border: "1px solid var(--hairline)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>
        {emoji}
        {dot && <span style={{ position: "absolute", top: 0, right: 0, width: 9, height: 9,
          borderRadius: "50%", background: dot, border: "2px solid var(--bg)" }} />}
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 12.5, color: active ? "var(--text)" : "var(--text-dim)",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: active ? 500 : 400 }}>
          {name}
        </div>
        {sub && (
          <div style={{ fontSize: 10.5, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 1 }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  )
}
