import { memo, useEffect, useRef, useState } from "react"
import { motion, AnimatePresence, useMotionValue, useTransform } from "motion/react"
import { useOfficeSelector } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName, roleDesc, roleSkills } from "../../data/roles"
import { ModelPicker, type Preset } from "../components/ModelPicker"
import { AgentDetailModal } from "../components/AgentDetailModal"
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
  // Селектор вместо useOffice() (весь state) — карточки перерисовывались на
  // КАЖДОЕ SSE-событие (в т.ч. не относящееся к команде — прогресс, стоимость),
  // из-за чего аватары агентов на каждый тик заново запускали пульс-анимацию.
  const agentsMap = useOfficeSelector(s => s.agents)
  const agents = Object.values(agentsMap)
  const active = agents.filter(a => a.status === "active" || a.status === "thinking").length
  const [detailId, setDetailId] = useState<string | null>(null)
  const detailEmoji = detailId ? agentsMap[detailId]?.emoji : undefined

  // collapsing header (через MotionValue — без ре-рендеров на скролл)
  const scrollY     = useMotionValue(0)
  const fontSize    = useTransform(scrollY, [0, 70], [52, 26])
  const padTop      = useTransform(scrollY, [0, 70], [32, 16])
  const padBottom   = useTransform(scrollY, [0, 70], [22, 14])
  const subHeight   = useTransform(scrollY, [0, 40], [22, 0])
  const subOpacity  = useTransform(scrollY, [0, 30], [1, 0])
  const titleMargin = useTransform(scrollY, [0, 70], [10, 0])
  const lineOpacity = useTransform(scrollY, [44, 70], [0, 1])

  const gridRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = gridRef.current
    if (!el) return
    const onScroll = () => scrollY.set(el.scrollTop)
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [scrollY])

  // Один запрос на все модели агентов вместо N запросов agentDetail.
  const [models, setModels] = useState<Record<string, string>>({})
  const [presets, setPresets] = useState<Preset[]>([])
  useEffect(() => {
    api.models().then(m => { setModels(m?.per_agent || {}); setPresets(m?.presets || []) })
  }, [agents.length])

  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Collapsing-шапка */}
      <motion.div style={{
        paddingTop: padTop, paddingBottom: padBottom, paddingLeft: 36, paddingRight: 36, flexShrink: 0,
        position: "relative", zIndex: 3, background: "var(--surface-head)",
      }}>
        <motion.div style={{ fontSize, lineHeight: 1, marginBottom: titleMargin, fontFamily: "var(--font-display)" }}>
          Команда 
        </motion.div>
        <motion.div style={{ height: subHeight, opacity: subOpacity, overflow: "hidden" }}>
          <div style={{ fontSize: 13, color: "var(--muted)", whiteSpace: "nowrap" }}>
            <span style={{ color: "var(--mercury-a)" }}>{active} active</span>{" · "}{agents.length} total
          </div>
        </motion.div>
        <motion.div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 1, background: "var(--hairline)", opacity: lineOpacity }} />
      </motion.div>

      {/* Сетка карточек */}
      <div ref={gridRef}
        style={{ flex: 1, overflowY: "auto", padding: "16px 28px 32px" }}>
        {agents.length === 0 ? (
          <EmptyTeam />
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
            <AnimatePresence>
              {agents.map((agent, i) => (
                <AgentCard key={agent.id} agent={agent} index={i} onOpenChat={onOpenChat}
                  initialModel={models[agent.id] || ""} presets={presets}
                  onOpenDetail={() => setDetailId(agent.id)} />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      <AgentDetailModal agentId={detailId} emoji={detailEmoji} onClose={() => setDetailId(null)} onOpenChat={onOpenChat} />
    </div>
  )
}

// ── Пульсирующий аватар (memo — не перерисовывается при неизменном статусе) ──
const PulsingAvatar = memo(function PulsingAvatar({ emoji, status }: { emoji: string; status: string }) {
  const isActive = status === "active"
  const isThinking = status === "thinking"
  return (
    <div style={{ position: "relative", flexShrink: 0 }}>
      <motion.div
        animate={(isActive || isThinking) ? { scale: [1, 1.08, 1] } : { scale: 1 }}
        transition={{ repeat: Infinity, duration: isActive ? 2.4 : 3.5, ease: "easeInOut" }}
        style={{
          width: 54, height: 54, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 26, border: `1.5px solid ${isActive ? "rgba(160,224,171,0.4)" : isThinking ? "rgba(255,172,46,0.35)" : "var(--hairline-strong)"}`,
          background: isActive ? "rgba(160,224,171,0.08)" : isThinking ? "rgba(255,172,46,0.08)" : "var(--surface-strong)",
        }}>
        {emoji}
      </motion.div>
      {/* Статус-точка */}
      <span style={{
        position: "absolute", bottom: 1, right: 1, width: 11, height: 11, borderRadius: "50%",
        background: STATUS_COLOR[status] || "var(--whisper)", border: "2px solid var(--bg)",
      }} />
    </div>
  )
})

// ── Карточка агента ──────────────────────────────────────────────────────────
function AgentCard({ agent, index, onOpenChat, initialModel, presets, onOpenDetail }: { agent: Agent; index: number; onOpenChat?: (id: string) => void; initialModel: string; presets: Preset[]; onOpenDetail?: () => void }) {
  const [model, setModel]       = useState(initialModel)
  const [editModel, setEditModel] = useState(false)
  const [saving, setSaving]     = useState(false)

  // подхватываем модель из общего запроса (без отдельного fetch на карточку)
  useEffect(() => { setModel(initialModel) }, [initialModel])

  async function saveModel(next: string) {
    setSaving(true)
    await api.setAgentModel(agent.id, next.trim())  // "" = вернуть к модели офиса
    setModel(next.trim())
    setSaving(false)
    setEditModel(false)
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
        background: "var(--surface)",
        border: `1px solid ${isActive ? "rgba(160,224,171,0.3)" : isThinking ? "rgba(255,172,46,0.25)" : "var(--hairline-strong)"}`,
        borderRadius: "var(--radius-lg)", padding: 24, display: "flex", flexDirection: "column", gap: 16,
        backdropFilter: "blur(26px) saturate(180%)", WebkitBackdropFilter: "blur(26px) saturate(180%)", transition: "border-color 0.3s",
        boxShadow: "var(--shadow), 0 1px 0 var(--inset-hi) inset",
      }}>

      {/* Верхняя строка: аватар + имя + статус (клик → подробности) */}
      <div onClick={onOpenDetail} title="Подробнее об агенте"
        style={{ display: "flex", alignItems: "flex-start", gap: 14, cursor: onOpenDetail ? "pointer" : "default" }}>
        {/* Аватар с анимацией — вынесен в memo(), чтобы обновление lastMessage
            (родитель AgentCard всё равно перерисовывается) не перезапускало
            пульс-анимацию: React.memo пропускает ре-рендер, если status не менялся. */}
        <PulsingAvatar emoji={agent.emoji} status={agent.status} />

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

      {/* Описание роли (клик → подробности) */}
      {desc && (
        <div onClick={onOpenDetail} style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.6, cursor: onOpenDetail ? "pointer" : "default" }}>{desc}</div>
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

      {/* Выбор модели (список пресетов + своя) */}
      {editModel ? (
        <div style={{ marginTop: "auto", paddingTop: 4 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 10, color: "var(--faint)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Модель агента</span>
            <button onClick={() => setEditModel(false)}
              style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 11 }}>свернуть ✕</button>
          </div>
          <ModelPicker value={model} presets={presets} onSave={saveModel} allowDefault saving={saving} compact />
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: "auto", paddingTop: 4 }}>
          <button onClick={() => setEditModel(true)} title="Сменить модель агента"
            style={{
              flex: 1, display: "flex", alignItems: "center", gap: 7,
              background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-pill)", padding: "7px 14px", cursor: "pointer",
              color: "var(--text-dim)", transition: "border-color 0.15s", minWidth: 0,
            }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--hairline-strong)")}
            onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--hairline)")}>
            <span style={{ fontSize: 11 }}>🧠</span>
            <span className="mono" style={{ fontSize: 11, flex: 1, textAlign: "left", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {model || "модель офиса"}
            </span>
            <span style={{ fontSize: 10, color: "var(--faint)" }}>✎</span>
          </button>

          {/* Chat → */}
          <button onClick={() => onOpenChat?.(agent.id)}
            style={{
              border: "none", borderRadius: "var(--radius-pill)", padding: "8px 18px",
              background: "var(--text)", color: "var(--bg)", cursor: "pointer",
              fontSize: 13, fontWeight: 500, whiteSpace: "nowrap",
              fontFamily: "var(--font-sans)", transition: "opacity 0.15s", flexShrink: 0,
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = "0.85")}
            onMouseLeave={e => (e.currentTarget.style.opacity = "1")}>
            Chat →
          </button>
        </div>
      )}
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
