import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName, roleDesc, roleSkills } from "../../data/roles"
import type { Agent } from "../types"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface TeamViewProps {
  onOpenChat?: (agentId: string) => void
}

const STATUS_LABEL: Record<string, string> = {
  active: "ACTIVE", thinking: "THINKING", done: "DONE", idle: "IDLE",
}
const STATUS_COLOR: Record<string, string> = {
  active: "#a0e0ab", thinking: "#ffac2e", done: "var(--text-dim)", idle: "var(--whisper)",
}
const STATUS_BG: Record<string, string> = {
  active:   "rgba(160,224,171,0.12)",
  thinking: "rgba(255,172,46,0.12)",
  done:     "rgba(255,255,255,0.04)",
  idle:     "rgba(255,255,255,0.03)",
}

export function TeamView({ onOpenChat }: TeamViewProps) {
  const { state } = useOffice()
  const agents = Object.values(state.agents)
  const active = agents.filter(a => a.status === "active" || a.status === "thinking").length

  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Шапка в стиле скриншота */}
      <div style={{ padding: "32px 36px 24px", flexShrink: 0 }}>
        <div style={{ fontSize: 52, lineHeight: 1, marginBottom: 10, fontFamily: "var(--font-display)" }}>
          The <em style={{ color: "var(--muted)", fontStyle: "italic" }}>team</em>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
          <div style={{ fontSize: 13, color: "var(--muted)" }}>
            <span style={{ color: "var(--mercury-a)" }}>{active} active</span>
            {" · "}
            {agents.length} total
          </div>
        </div>
      </div>

      {/* Сетка карточек */}
      <div style={{ flex: 1, overflowY: "auto", padding: "4px 28px 32px" }}>
        {agents.length === 0 ? (
          <EmptyTeam />
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
            <AnimatePresence>
              {agents.map((agent, i) => (
                <AgentCard key={agent.id} agent={agent} index={i} onOpenChat={onOpenChat} />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Карточка агента ──────────────────────────────────────────────────────────
function AgentCard({ agent, index, onOpenChat }: { agent: Agent; index: number; onOpenChat?: (id: string) => void }) {
  const [model, setModel]       = useState("")
  const [editModel, setEditModel] = useState(false)
  const [modelInput, setModelInput] = useState("")
  const [saving, setSaving]     = useState(false)
  const [detail, setDetail]     = useState<any>(null)

  useEffect(() => {
    api.agentDetail(agent.id).then(d => {
      setDetail(d)
      setModel(d.model || "")
      setModelInput(d.model || "")
    })
  }, [agent.id, agent.status])

  async function saveModel() {
    if (!modelInput.trim()) return
    setSaving(true)
    await api.setAgentModel(agent.id, modelInput.trim())
    setModel(modelInput.trim())
    setEditModel(false)
    setSaving(false)
  }

  const isActive   = agent.status === "active"
  const isThinking = agent.status === "thinking"
  const skills     = roleSkills(agent.role)
  const desc       = roleDesc(agent.role)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.3, delay: index * 0.04 }}
      style={{
        background: "var(--surface)", border: `1px solid ${isActive ? "rgba(160,224,171,0.2)" : isThinking ? "rgba(255,172,46,0.15)" : "var(--hairline)"}`,
        borderRadius: "var(--radius-lg)", padding: 24, display: "flex", flexDirection: "column", gap: 16,
        backdropFilter: "blur(28px) saturate(160%)", transition: "border-color 0.3s",
        boxShadow: isActive ? "0 0 0 1px rgba(160,224,171,0.08), 0 16px 48px rgba(0,0,0,0.25)" : "var(--shadow)",
      }}>

      {/* Верхняя строка: аватар + имя + статус */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
        {/* Аватар с анимацией */}
        <div style={{ position: "relative", flexShrink: 0 }}>
          <motion.div
            animate={(isActive || isThinking) ? { scale: [1, 1.08, 1] } : { scale: 1 }}
            transition={{ repeat: Infinity, duration: isActive ? 2.4 : 3.5, ease: "easeInOut" }}
            style={{
              width: 54, height: 54, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 26, border: `1.5px solid ${isActive ? "rgba(160,224,171,0.4)" : isThinking ? "rgba(255,172,46,0.35)" : "var(--hairline-strong)"}`,
              background: isActive ? "rgba(160,224,171,0.08)" : isThinking ? "rgba(255,172,46,0.08)" : "var(--surface-strong)",
            }}>
            {agent.emoji}
          </motion.div>
          {/* Статус-точка */}
          <span style={{
            position: "absolute", bottom: 1, right: 1, width: 11, height: 11, borderRadius: "50%",
            background: STATUS_COLOR[agent.status] || "var(--whisper)", border: "2px solid var(--bg)",
          }} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 17, fontWeight: 600, color: "var(--text)", marginBottom: 2 }}>{agent.name}</div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>{roleName(agent.role)}</div>
        </div>

        {/* Статус-бейдж */}
        <div style={{
          padding: "3px 10px", borderRadius: "var(--radius-pill)", fontSize: 10, fontWeight: 600,
          letterSpacing: "0.8px", fontFamily: "var(--font-mono)",
          background: STATUS_BG[agent.status] || STATUS_BG.idle,
          color: STATUS_COLOR[agent.status] || "var(--whisper)",
          border: `1px solid ${STATUS_COLOR[agent.status] || "var(--hairline)"}22`,
          flexShrink: 0,
        }}>
          {STATUS_LABEL[agent.status] || "IDLE"}
        </div>
      </div>

      {/* Описание роли */}
      {desc && (
        <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.6 }}>{desc}</div>
      )}

      {/* Скиллы */}
      {skills.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {skills.map(s => (
            <span key={s} style={{
              fontSize: 11, padding: "3px 10px", borderRadius: "var(--radius-pill)",
              border: "1px solid var(--hairline)", color: "var(--text-dim)",
              background: "var(--surface-soft)",
            }}>{s}</span>
          ))}
        </div>
      )}

      {/* Текущая активность */}
      <AnimatePresence mode="wait">
        {agent.lastMessage && (
          <motion.div key={agent.lastMessage}
            initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.25 }}
            style={{
              fontSize: 12, color: isActive ? "#a0e0ab" : isThinking ? "var(--mercury-a)" : "var(--muted)",
              lineHeight: 1.5, padding: "10px 14px",
              borderLeft: `3px solid ${isActive ? "#a0e0ab" : isThinking ? "var(--mercury-a)" : "var(--hairline-strong)"}`,
              background: "var(--surface-soft)", borderRadius: "0 var(--radius-sm) var(--radius-sm) 0",
            }}>
            {agent.lastMessage.slice(0, 120)}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Модель + кнопки */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: "auto", paddingTop: 4 }}>
        {/* Выбор модели */}
        {editModel ? (
          <div style={{ flex: 1, display: "flex", gap: 6 }}>
            <input value={modelInput} onChange={e => setModelInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") saveModel(); if (e.key === "Escape") setEditModel(false) }}
              autoFocus placeholder="glm-4.5-flash"
              style={{
                flex: 1, background: "var(--surface-soft)", border: "1px solid rgba(255,172,46,0.4)",
                borderRadius: "var(--radius-pill)", padding: "7px 14px", color: "var(--text)",
                fontSize: 12, outline: "none", fontFamily: "var(--font-mono)",
              }} />
            <button onClick={saveModel} disabled={saving}
              style={{ border: "none", borderRadius: "var(--radius-pill)", padding: "0 14px",
                background: MERCURY, color: "#0a0a0a", cursor: "pointer", fontSize: 12, fontWeight: 500,
                fontFamily: "var(--font-sans)" }}>
              {saving ? "…" : "✓"}
            </button>
            <button onClick={() => setEditModel(false)}
              style={{ border: "1px solid var(--hairline)", borderRadius: "var(--radius-pill)", padding: "0 12px",
                background: "transparent", color: "var(--muted)", cursor: "pointer", fontSize: 12,
                fontFamily: "var(--font-sans)" }}>✕</button>
          </div>
        ) : (
          <button onClick={() => setEditModel(true)}
            title="Сменить модель"
            style={{
              flex: 1, display: "flex", alignItems: "center", gap: 7,
              background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-pill)", padding: "7px 14px", cursor: "pointer",
              color: "var(--text-dim)", transition: "border-color 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--hairline-strong)")}
            onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--hairline)")}>
            <span style={{ fontSize: 10, color: "var(--faint)" }}>◈</span>
            <span className="mono" style={{ fontSize: 11, flex: 1, textAlign: "left", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {model || "по умолчанию"}
            </span>
            <span style={{ fontSize: 10, color: "var(--faint)" }}>✎</span>
          </button>
        )}

        {/* Chat → */}
        <button onClick={() => onOpenChat?.(agent.id)}
          style={{
            border: "none", borderRadius: "var(--radius-pill)", padding: "8px 18px",
            background: "var(--text)", color: "var(--bg)", cursor: "pointer",
            fontSize: 13, fontWeight: 500, whiteSpace: "nowrap",
            fontFamily: "var(--font-sans)", transition: "opacity 0.15s",
            flexShrink: 0,
          }}
          onMouseEnter={e => (e.currentTarget.style.opacity = "0.85")}
          onMouseLeave={e => (e.currentTarget.style.opacity = "1")}>
          Chat →
        </button>
      </div>
    </motion.div>
  )
}

function EmptyTeam() {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      height: 320, gap: 14, textAlign: "center" }}>
      <div style={{ fontSize: 48, opacity: 0.2 }}>👥</div>
      <div style={{ fontSize: 14, color: "var(--muted)" }}>Команда пока не набрана</div>
      <div style={{ fontSize: 12, color: "var(--faint)", maxWidth: 280, lineHeight: 1.6 }}>
        Агенты появятся после старта офиса. Директор наймёт нужных специалистов автоматически.
      </div>
    </div>
  )
}
