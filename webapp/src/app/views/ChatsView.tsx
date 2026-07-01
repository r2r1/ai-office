import { useEffect, useMemo, useRef, useState } from "react"
import { useOfficeSelector, useUnread, markThreadSeen } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, STATUS_COLOR } from "./ui"
import { useThrottled } from "../hooks"
import { motion } from "motion/react"
import { roleName } from "../../data/roles"

// анимированные точки «печатает…»
function TypingDots() {
  return (
    <span style={{ display: "inline-flex", gap: 3, flexShrink: 0 }}>
      {[0, 1, 2].map(i => (
        <motion.span key={i}
          animate={{ opacity: [0.25, 1, 0.25], y: [0, -2, 0] }}
          transition={{ repeat: Infinity, duration: 1, delay: i * 0.18, ease: "easeInOut" }}
          style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--mercury-a)", display: "inline-block" }} />
      ))}
    </span>
  )
}

// дружелюбное имя отправителя (CEO вместо orchestrator_1, имя агента в личном чате)
function senderName(m: any, fallback?: string): string {
  if (m.role && m.role !== "user") return roleName(m.role)
  if (typeof m.from === "string" && !["user", "agent"].includes(m.from)) {
    return roleName(m.from.replace(/_\d+$/, ""))
  }
  return fallback || m.from || ""
}

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface ChatsViewProps { initialAgent?: string }

export function ChatsView({ initialAgent }: ChatsViewProps) {
  // Селекторы вместо useOffice() (весь state) — раньше чат перерисовывался на
  // события, никак не связанные с агентами/тредами (прогресс, стоимость и т.д.).
  const agentsMap = useOfficeSelector(s => s.agents)
  const threads = useOfficeSelector(s => s.threads)
  const feedLength = useOfficeSelector(s => s.feed.length)
  const unread = useUnread()
  const agents = Object.values(agentsMap)
  const [active, setActive] = useState<string>(initialAgent || "office")
  const [messages, setMessages] = useState<any[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const feedRef = useRef<HTMLDivElement>(null)

  // pending — оптимистично отправленные сообщения, ещё не подтверждённые сервером.
  // Держим их отдельно, чтобы фоновый reload (по событиям офиса) не стирал их.
  const [pending, setPending] = useState<any[]>([])

  useEffect(() => { if (initialAgent) setActive(initialAgent) }, [initialAgent])

  async function load() {
    const data = active === "office" ? await api.chatGet() : await api.thread(active)
    const server = data.messages || []
    setMessages(server)
    // убираем из pending те, что сервер уже сохранил
    setPending(p => p.filter(pm => !server.some((sm: any) => sm.from === "user" && sm.text === pm.text)))
    // отмечаем личный чат прочитанным по последнему сообщению, которое сейчас видно
    if (active !== "office" && server.length) {
      const lastTs = server[server.length - 1].ts || 0
      markThreadSeen(active, lastTs)
    }
  }
  const tick = useThrottled(feedLength, 2000)
  useEffect(() => { setPending([]); load() }, [active]) // eslint-disable-line — смена собеседника
  useEffect(() => { load() }, [tick])                   // eslint-disable-line — живой апдейт
  useEffect(() => { feedRef.current?.scrollTo(0, feedRef.current.scrollHeight) },
    [messages, pending, sending]) // eslint-disable-line

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    setPending(p => [...p, { from: "user", text, ts: Date.now() / 1000 }])
    setInput("")
    try {
      if (active === "office") await api.chatPost(text)
      else await api.ask(active, text)
    } finally {
      setSending(false)
      setTimeout(load, 500)
    }
  }

  const allMessages = [...messages, ...pending]

  const activeAgent = active !== "office" ? agentsMap[active] : null
  const activeUnanswered = activeAgent ? (threads[active]?.unanswered || 0) : 0
  const headerName = active === "office" ? "Общий чат" : (activeAgent?.name ?? "Агент")
  // Подзаголовок — стабильный (роль / ожидание ответа). НИКАКОЙ внутренней активности
  // агента: «кто что делает» живёт в журнале и на сцене офиса, а не в личной переписке.
  const headerSub = active === "office"
    ? `Сообщение получат все ${agents.length} агентов`
    : activeUnanswered > 0 ? "Ждёт вашего ответа" : (roleName(activeAgent?.role || "") || "Личный диалог")

  // Список агентов как в мессенджере: непрочитанные сверху, затем по свежести переписки.
  const agentsSorted = useMemo(() => {
    return [...agents].sort((a, b) => {
      const ua = unread.byAgent[a.id] ? 1 : 0
      const ub = unread.byAgent[b.id] ? 1 : 0
      if (ua !== ub) return ub - ua
      const ta = threads[a.id]?.last_ts || 0
      const tb = threads[b.id]?.last_ts || 0
      return tb - ta
    })
  }, [agents, unread.byAgent, threads])

  // Превью последнего сообщения треда (а не служебной активности агента).
  function rowSub(a: any): { text: string; accent: boolean } {
    const t = threads[a.id]
    if (t?.unanswered) return { text: "Ждёт вашего ответа", accent: true }
    if (t?.last_text) return { text: (t.last_from === "user" ? "Вы: " : "") + t.last_text, accent: false }
    return { text: roleName(a.role), accent: false }
  }

  // Печатает — только пока обрабатывается ВАШЕ сообщение в этом чате. Без текста активности.
  const showTyping = active !== "office" && sending

  return (
    <ViewShell>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* sidebar */}
        {sidebarOpen && (
          <div style={{ width: 260, flexShrink: 0, borderRight: "1px solid var(--hairline)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {/* заголовок sidebar */}
            <div style={{ padding: "18px 16px 12px", borderBottom: "1px solid var(--hairline-soft)", flexShrink: 0 }}>
              <div className="display" style={{ fontSize: 22, color: "var(--text)" }}>Чаты</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                {agents.length} агентов{unread.total > 0 ? ` · ${unread.total} непрочитано` : ""}
              </div>
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

              {agentsSorted.map(a => {
                const sub = rowSub(a)
                return (
                  <Row key={a.id} active={active === a.id} onClick={() => setActive(a.id)}
                    emoji={a.emoji} name={a.name} sub={sub.text} subAccent={sub.accent}
                    dot={STATUS_COLOR[a.status]} unread={unread.byAgent[a.id] ?? 0} />
                )
              })}
            </div>
          </div>
        )}

        {/* панель чата */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* шапка чата */}
          <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid var(--hairline)", flexShrink: 0,
            display: "flex", alignItems: "center", gap: 12 }}>
            <button onClick={() => setSidebarOpen(s => !s)}
              aria-label={sidebarOpen ? "Скрыть список чатов" : "Показать список чатов"}
              style={{ width: 28, height: 28, border: "1px solid var(--hairline)", borderRadius: "var(--radius-xs)",
                background: "transparent", cursor: "pointer", color: "var(--muted)", fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center" }}>
              {sidebarOpen ? "◁" : "▷"}
            </button>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)" }}>{headerName}</div>
              <div style={{ fontSize: 11, color: activeUnanswered > 0 ? "var(--mercury-a)" : "var(--muted)",
                marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{headerSub}</div>
            </div>
            {activeAgent && (
              <span aria-hidden style={{ marginLeft: "auto", width: 8, height: 8, borderRadius: "50%", background: STATUS_COLOR[activeAgent.status], flexShrink: 0 }} />
            )}
          </div>

          {/* сообщения */}
          <div ref={feedRef} role="log" aria-label="Сообщения чата"
            style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
            {allMessages.length === 0 && (
              <div style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", paddingTop: 60 }}>
                {active === "office" ? "Напишите что-нибудь — вся команда услышит" : "Начните разговор с агентом"}
              </div>
            )}
            {allMessages.map((m, i) => {
              const mine = m.from === "user"
              const isQuestion = m.kind === "question"
              return (
                <div key={i} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "78%" }}>
                  {!mine && (
                    <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>
                      {senderName(m, activeAgent?.name)}{isQuestion && " · вопрос"}
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

            {/* «печатает…» — только пока обрабатывается ваше сообщение, без утечки активности */}
            {showTyping && (
              <div style={{ alignSelf: "flex-start", maxWidth: "82%" }}>
                <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>{activeAgent?.name}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "10px 14px",
                  borderRadius: "var(--radius-md) var(--radius-md) var(--radius-md) 4px",
                  background: "var(--surface-strong)", border: "1px solid rgba(255,172,46,0.25)" }}>
                  <TypingDots />
                  <span style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.45 }}>печатает…</span>
                </div>
              </div>
            )}
          </div>

          {/* ввод */}
          <div style={{ display: "flex", gap: 8, padding: "12px 16px", borderTop: "1px solid var(--hairline)", flexShrink: 0 }}>
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
              aria-label={active === "office" ? "Сообщение команде" : `Сообщение агенту ${activeAgent?.name ?? ""}`}
              placeholder={active === "office" ? "Сообщение команде…" : `Написать ${activeAgent?.name ?? "агенту"}…`}
              style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
                borderRadius: "var(--radius-pill)", padding: "10px 18px", color: "var(--text)",
                fontSize: 13, outline: "none", transition: "border-color 0.15s", fontFamily: "var(--font-sans)" }}
              onFocus={e => (e.currentTarget.style.borderColor = "rgba(255,172,46,0.4)")}
              onBlur={e => (e.currentTarget.style.borderColor = "")} />
            <button onClick={send} disabled={sending || !input.trim()} aria-label="Отправить сообщение"
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

function Row({ active, onClick, emoji, name, sub, subAccent, dot, unread = 0 }: {
  active: boolean; onClick: () => void; emoji: string; name: string
  sub?: string; subAccent?: boolean; dot?: string; unread?: number
}) {
  const hasUnread = unread > 0
  return (
    <div onClick={onClick} role="button" tabIndex={0}
      onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick() } }}
      aria-label={hasUnread ? `${name}, непрочитанных: ${unread}` : name}
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
        <div style={{ fontSize: 12.5, color: active || hasUnread ? "var(--text)" : "var(--text-dim)",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: active || hasUnread ? 600 : 400 }}>
          {name}
        </div>
        {sub && (
          <div style={{ fontSize: 10.5, color: subAccent ? "var(--mercury-a)" : (hasUnread ? "var(--text-dim)" : "var(--muted)"),
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 1,
            fontWeight: hasUnread && !subAccent ? 500 : 400 }}>
            {sub}
          </div>
        )}
      </div>
      {hasUnread && (
        <span aria-hidden style={{ flexShrink: 0, minWidth: 18, height: 18, padding: "0 5px",
          borderRadius: 9, background: "var(--mercury-a)", color: "#0a0a0a",
          fontSize: 10, fontWeight: 700, lineHeight: "18px", textAlign: "center" }}>
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </div>
  )
}
