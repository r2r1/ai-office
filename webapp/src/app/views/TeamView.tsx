import { memo, useEffect, useMemo, useRef, useState } from "react"
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from "motion/react"
import { useOfficeSelector, useUnread } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName, roleDesc, roleSkills } from "../../data/roles"
import { ModelPicker, type Preset } from "../components/ModelPicker"
import { AgentDetailModal } from "../components/AgentDetailModal"
import type { Worker } from "../types"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface TeamViewProps {
  onOpenChat?: (agentId: string) => void
  /** Общий инбокс переписки — «Чаты» больше не отдельный пункт NavRail, вход
   * отсюда (карта сайта, рефакторинг 2026-07-05). */
  onOpenInbox?: () => void
}

const STATUS_LABEL: Record<string, string> = {
  active: "РАБОТАЕТ", thinking: "ДУМАЕТ", done: "ГОТОВО", idle: "ЖДЁТ",
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

export function TeamView({ onOpenChat, onOpenInbox }: TeamViewProps) {
  // Селектор вместо useOffice() (весь state) — карточки перерисовывались на
  // КАЖДОЕ SSE-событие (в т.ч. не относящееся к команде — прогресс, стоимость),
  // из-за чего аватары агентов на каждый тик заново запускали пульс-анимацию.
  const agentsMap = useOfficeSelector(s => s.agents)
  const agents = Object.values(agentsMap)
  const active = agents.filter(a => a.status === "active" || a.status === "thinking").length
  const [detailId, setDetailId] = useState<string | null>(null)
  const detailEmoji = detailId ? agentsMap[detailId]?.emoji : undefined
  const unread = useUnread()

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

  // id проекта → название — для бейджа "закреплён за проектом" на карточке
  // (параллельные Work, Фаза 2/4): без имени "p1_1143" ничего не говорит.
  const [projectTitles, setProjectTitles] = useState<Record<string, string>>({})
  useEffect(() => {
    api.projects().then(d => {
      const map: Record<string, string> = {}
      for (const p of d.projects || []) map[p.id] = p.title
      setProjectTitles(map)
    })
  }, [agents.length])

  // Разные проекты держат одноролевых сотрудников (developer_p1, developer_p2, ...)
  // одновременно — бейджа на карточке недостаточно, нужна настоящая визуальная
  // группировка (та же логика группировки, что в ChatsView.tsx): "Штаб" (лидеры и
  // служебные роли без projectId) первой секцией, дальше — по секции на проект.
  const groupedByProject = useMemo(() => {
    const groups = new Map<string, Worker[]>()
    for (const a of agents) {
      const pid = a.projectId || ""
      if (!groups.has(pid)) groups.set(pid, [])
      groups.get(pid)!.push(a)
    }
    return [...groups.entries()].sort(([pa], [pb]) => (!pa ? -1 : !pb ? 1 : 0))
  }, [agents])

  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Collapsing-шапка */}
      <motion.div style={{
        paddingTop: padTop, paddingBottom: padBottom, paddingLeft: 36, paddingRight: 36, flexShrink: 0,
        position: "relative", zIndex: 3, background: "var(--surface-head)",
        display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12,
      }}>
        <div>
          <motion.div style={{ fontSize, lineHeight: 1, marginBottom: titleMargin, fontFamily: "var(--font-display)" }}>
            Команда
          </motion.div>
          <motion.div style={{ height: subHeight, opacity: subOpacity, overflow: "hidden" }}>
            <div style={{ fontSize: 13, color: "var(--muted)", whiteSpace: "nowrap" }}>
              <span style={{ color: "var(--mercury-a)" }}>{active} active</span>{" · "}{agents.length} total
            </div>
          </motion.div>
        </div>
        {onOpenInbox && <ChatsButton onClick={onOpenInbox} unread={unread.total} />}
        <motion.div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 1, background: "var(--hairline)", opacity: lineOpacity }} />
      </motion.div>

      {/* Секции по проектам (штаб + по одной на активный проект) */}
      <div ref={gridRef}
        style={{ flex: 1, overflowY: "auto", padding: "16px 28px 32px" }}>
        {agents.length === 0 ? (
          <EmptyTeam />
        ) : (
          groupedByProject.map(([pid, list], gi) => (
            <div key={pid || "hq"} style={{ marginBottom: 28 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <span className="mono" style={{ fontSize: 10, color: "var(--faint)", textTransform: "uppercase", letterSpacing: "1.2px" }}>
                  {pid ? `📁 ${projectTitles[pid] || "Проект"}` : "Штаб"}
                </span>
                <span style={{ fontSize: 10.5, color: "var(--muted)" }}>· {list.length}</span>
                <div style={{ flex: 1, height: 1, background: "var(--hairline)" }} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 12 }}>
                <AnimatePresence>
                  {list.map((agent, i) => (
                    <AgentCard key={agent.id} agent={agent} index={gi * 4 + i} onOpenChat={onOpenChat}
                      initialModel={models[agent.id] || ""} presets={presets}
                      onOpenDetail={() => setDetailId(agent.id)} />
                  ))}
                </AnimatePresence>
              </div>
            </div>
          ))
        )}
      </div>

      <AgentDetailModal agentId={detailId} emoji={detailEmoji} onClose={() => setDetailId(null)} onOpenChat={onOpenChat} />
    </div>
  )
}

// Точки волны (сверху вниз), сглаженные через квадратичные Безье с самими
// точками как контрольными — дешёвый, но убедительный способ получить живой
// изгиб без полноценного catmull-rom сплайна.
function _smoothPath(pts: { x: number; y: number }[]): string {
  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i], p1 = pts[i + 1]
    const mx = (p0.x + p1.x) / 2, my = (p0.y + p1.y) / 2
    d += ` Q ${p0.x.toFixed(1)} ${p0.y.toFixed(1)} ${mx.toFixed(1)} ${my.toFixed(1)}`
  }
  const last = pts[pts.length - 1]
  d += ` L ${last.x.toFixed(1)} ${last.y.toFixed(1)}`
  return d
}

// Форма «воды»: заливка растёт слева направо, но кромка — не прямая линия, а
// бегущая волна (амплитуда + фаза), как будто жидкость плещется об стенку.
// Возвращает ОБА пути: `fill` (замкнутый, для заливки) и `edge` (сама волна,
// без закрывающих прямых) — если использовать `fill` и для обводки-блика,
// штрих обводит ещё и верх/лево/низ прямыми линиями (не то, что нужно).
function _wavePath(progress: number, phase: number, w: number, h: number): { fill: string; edge: string } {
  const amp = Math.min(7, w * 0.05)
  const waves = 1.6
  const leadX = -amp + progress * (w + 2 * amp)
  const steps = 10
  const pts = Array.from({ length: steps + 1 }, (_, i) => {
    const y = (h * i) / steps
    const x = leadX + amp * Math.sin((y / h) * Math.PI * waves + phase)
    return { x, y }
  })
  const edge = _smoothPath(pts)
  return { edge, fill: `${edge} L -6 ${h.toFixed(1)} L -6 0 Z` }
}

// ── Кнопка «Чаты»: обычная пилюля в покое (тот же стиль, что и остальные
//    кнопки во вью), при наведении заливается mercury-градиентом с живым
//    волнистым краем (SVG-путь, пересчитывается императивно через MotionValue
//    — без React-ререндеров на каждый кадр), а не прямой вертикальной линией. ──
function ChatsButton({ onClick, unread }: { onClick: () => void; unread: number }) {
  const [hover, setHover] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const fill = useMotionValue(0)    // 0..1 — покрытие слева направо
  const phase = useMotionValue(0)   // фаза колебания волны (бесконечно бежит, пока наведено)
  const fillPath = useMotionValue("")
  const edgePath = useMotionValue("")

  const recompute = () => {
    const el = btnRef.current
    if (!el) return
    const { width: w, height: h } = el.getBoundingClientRect()
    const { fill: f, edge: e } = _wavePath(fill.get(), phase.get(), w, h)
    fillPath.set(f)
    edgePath.set(e)
  }

  useEffect(() => {
    const unsubFill = fill.on("change", recompute)
    const unsubPhase = phase.on("change", recompute)
    recompute()
    return () => { unsubFill(); unsubPhase() }
  }, []) // eslint-disable-line

  useEffect(() => {
    const controls = animate(fill, hover ? 1 : 0, { duration: hover ? 0.6 : 0.4, ease: [0.22, 1, 0.36, 1] })
    return () => controls.stop()
  }, [hover]) // eslint-disable-line

  useEffect(() => {
    if (!hover) return
    const controls = animate(phase, phase.get() + Math.PI * 2, { duration: 1.8, ease: "linear", repeat: Infinity })
    return () => controls.stop()
  }, [hover]) // eslint-disable-line

  return (
    <motion.button
      ref={btnRef}
      onClick={onClick}
      onHoverStart={() => setHover(true)}
      onHoverEnd={() => setHover(false)}
      whileTap={{ scale: 0.97 }}
      title="Все переписки с командой"
      style={{
        position: "relative", overflow: "hidden", flexShrink: 0, marginTop: 6,
        display: "flex", alignItems: "center", gap: 9,
        padding: "11px 20px", borderRadius: "var(--radius-pill)",
        border: "1px solid var(--hairline-strong)", background: "var(--surface-soft)",
        fontSize: 13.5, fontWeight: 500, cursor: "pointer", fontFamily: "var(--font-sans)",
      }}>
      {/* Жидкая заливка — волнистая кромка вместо прямого вертикального края */}
      <svg aria-hidden style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
        <defs>
          <linearGradient id="chatsLiquid" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#a0e0ab" />
            <stop offset="50%" stopColor="#ffac2e" />
            <stop offset="100%" stopColor="#a52d25" />
          </linearGradient>
        </defs>
        <motion.path style={{ d: fillPath }} fill="url(#chatsLiquid)" />
        {/* Тонкая светлая кромка вдоль ТОЛЬКО волны (не всего контура) — блик, как пена на воде */}
        <motion.path style={{ d: edgePath }} fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth={1.5} />
      </svg>
      <span style={{
        position: "relative", zIndex: 1, display: "flex", alignItems: "center", gap: 9,
        color: hover ? "#0a0a0a" : "var(--text)", transition: "color 0.25s ease",
      }}>
        💬 Чаты
        {unread > 0 && (
          <span className="mono" style={{
            fontSize: 11, fontWeight: 700, padding: "1px 6.5px", borderRadius: 8,
            background: hover ? "#0a0a0a" : "var(--mercury-a)", color: hover ? "var(--mercury-a)" : "#0a0a0a",
            transition: "background 0.25s ease, color 0.25s ease",
          }}>{unread > 9 ? "9+" : unread}</span>
        )}
      </span>
    </motion.button>
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
          width: 38, height: 38, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 18, border: `1.5px solid ${isActive ? "rgba(160,224,171,0.4)" : isThinking ? "rgba(255,172,46,0.35)" : "var(--hairline-strong)"}`,
          background: isActive ? "rgba(160,224,171,0.08)" : isThinking ? "rgba(255,172,46,0.08)" : "var(--surface-strong)",
        }}>
        {emoji}
      </motion.div>
      {/* Статус-точка */}
      <span style={{
        position: "absolute", bottom: 0, right: 0, width: 9, height: 9, borderRadius: "50%",
        background: STATUS_COLOR[status] || "var(--whisper)", border: "2px solid var(--bg)",
      }} />
    </div>
  )
})

// ── Карточка агента (компактная — принадлежность проекту показывает секция
//    выше, не сама карточка) ───────────────────────────────────────────────
function AgentCard({ agent, index, onOpenChat, initialModel, presets, onOpenDetail }: { agent: Worker; index: number; onOpenChat?: (id: string) => void; initialModel: string; presets: Preset[]; onOpenDetail?: () => void }) {
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
        borderRadius: "var(--radius-md)", padding: 14, display: "flex", flexDirection: "column", gap: 10,
        backdropFilter: "blur(26px) saturate(180%)", WebkitBackdropFilter: "blur(26px) saturate(180%)", transition: "border-color 0.3s",
        boxShadow: "var(--shadow), 0 1px 0 var(--inset-hi) inset",
      }}>

      {/* Верхняя строка: аватар + имя + статус (клик → подробности).
          role/tabIndex/onKeyDown — раньше открывалось только мышью, без
          Tab/Enter (найдено при живом аудите: Card уже почини́ли централизованно,
          эта карточка — bespoke motion.div, тот же класс бага отдельно). */}
      <div onClick={onOpenDetail} title="Подробнее об агенте"
        role={onOpenDetail ? "button" : undefined} tabIndex={onOpenDetail ? 0 : undefined}
        onKeyDown={onOpenDetail ? e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpenDetail() } } : undefined}
        style={{ display: "flex", alignItems: "center", gap: 10, cursor: onOpenDetail ? "pointer" : "default" }}>
        {/* Аватар с анимацией — вынесен в memo(), чтобы обновление lastMessage
            (родитель AgentCard всё равно перерисовывается) не перезапускало
            пульс-анимацию: React.memo пропускает ре-рендер, если status не менялся. */}
        <PulsingAvatar emoji={agent.emoji} status={agent.status} />

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{agent.name}</div>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>{roleName(agent.role)}</div>
        </div>

        {/* Статус-бейдж */}
        <div style={{
          padding: "2px 8px", borderRadius: "var(--radius-pill)", fontSize: 9, fontWeight: 600,
          letterSpacing: "0.6px", fontFamily: "var(--font-mono)",
          background: STATUS_BG[agent.status] || STATUS_BG.idle,
          color: STATUS_COLOR[agent.status] || "var(--whisper)",
          border: `1px solid ${STATUS_COLOR[agent.status] || "var(--hairline)"}22`,
          flexShrink: 0,
        }}>
          {STATUS_LABEL[agent.status] || "ЖДЁТ"}
        </div>
      </div>

      {/* Описание роли (клик → подробности) — 2 строки максимум, без "воздуха" под текстом */}
      {desc && (
        <div onClick={onOpenDetail} style={{
          fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5, cursor: onOpenDetail ? "pointer" : "default",
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
        }}>{desc}</div>
      )}

      {/* Скиллы — максимум 3, остальное схлопнуто в "+N" (не раздувает карточку) */}
      {skills.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          {skills.slice(0, 3).map(s => (
            <span key={s} style={{
              fontSize: 10, padding: "2px 8px", borderRadius: "var(--radius-pill)",
              border: "1px solid var(--hairline)", color: "var(--text-dim)",
              background: "var(--surface-soft)",
            }}>{s}</span>
          ))}
          {skills.length > 3 && (
            <span style={{ fontSize: 10, padding: "2px 8px", color: "var(--faint)" }}>+{skills.length - 3}</span>
          )}
        </div>
      )}

      {/* Текущая активность */}
      <AnimatePresence mode="wait">
        {agent.lastMessage && (
          <motion.div key={agent.lastMessage}
            initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.25 }}
            style={{
              fontSize: 11, color: isActive ? "#a0e0ab" : isThinking ? "var(--mercury-a)" : "var(--muted)",
              lineHeight: 1.45, padding: "7px 10px",
              borderLeft: `3px solid ${isActive ? "#a0e0ab" : isThinking ? "var(--mercury-a)" : "var(--hairline-strong)"}`,
              background: "var(--surface-soft)", borderRadius: "0 var(--radius-sm) var(--radius-sm) 0",
              display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
            }}>
            {agent.lastMessage.slice(0, 140)}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Выбор модели (список пресетов + своя) */}
      {editModel ? (
        <div style={{ marginTop: "auto", paddingTop: 2 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 10, color: "var(--faint)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Модель агента</span>
            <button onClick={() => setEditModel(false)}
              style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 11 }}>свернуть ✕</button>
          </div>
          <ModelPicker value={model} presets={presets} onSave={saveModel} allowDefault saving={saving} compact />
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: "auto", paddingTop: 2 }}>
          <button onClick={() => setEditModel(true)} title="Сменить модель агента"
            style={{
              flex: 1, display: "flex", alignItems: "center", gap: 6,
              background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-pill)", padding: "6px 11px", cursor: "pointer",
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

          <button onClick={() => onOpenChat?.(agent.id)}
            style={{
              border: "none", borderRadius: "var(--radius-pill)", padding: "6px 14px",
              background: "var(--text)", color: "var(--bg)", cursor: "pointer",
              fontSize: 12, fontWeight: 500, whiteSpace: "nowrap",
              fontFamily: "var(--font-sans)", transition: "opacity 0.15s", flexShrink: 0,
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = "0.85")}
            onMouseLeave={e => (e.currentTarget.style.opacity = "1")}>
            Написать →
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
