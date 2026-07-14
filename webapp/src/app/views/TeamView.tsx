import { memo, useEffect, useMemo, useRef, useState } from "react"
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from "motion/react"
import { useOfficeSelector, useUnread } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName, roleDesc, roleSkills } from "../../data/roles"
import { ModelPicker, type Preset } from "../components/ModelPicker"
import { AgentDetailModal } from "../components/AgentDetailModal"
import { SubTabs, useSubTab, Card, SectionLabel, Empty, Pill, ViewBody } from "./ui"
import type { Worker } from "../types"

// IA-пересборка (вариант C, живой дизайн-аудит): Роли и Скиллы раньше жили в
// «Компании», отдельно от живых карточек агентов той же роли — дублирование
// "кто работает" в двух не связанных местах меню. Теперь рядом, под-вкладками.
const TEAM_TABS = [
  { id: "agents", label: "Агенты" },
  { id: "roles", label: "Роли" },
  { id: "skills", label: "Скиллы" },
]

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
  const { active: teamTab, setActive: setTeamTab } = useSubTab(TEAM_TABS)

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

      <div style={{ flexShrink: 0, padding: "0 28px", background: "var(--surface-head)" }}>
        <SubTabs tabs={TEAM_TABS} active={teamTab} onChange={setTeamTab} />
      </div>

      {teamTab === "agents" && (
        /* Секции по проектам (штаб + по одной на активный проект) */
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
      )}
      {teamTab === "roles" && <RolesTab />}
      {teamTab === "skills" && <SkillsTab />}

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

// ── Роли: Role Definition (read-only) — перенесено из «Компании» (IA-пересборка,
// вариант C): раньше жило отдельно от живых карточек агентов той же роли. ─────
const DEPT_RU: Record<string, string> = { tech: "Технический", marketing: "Маркетинг", sales: "Продажи" }

function RolesTab() {
  const [roles, setRoles] = useState<any[]>([])
  useEffect(() => { api.get("/api/roles").then(r => r?.roles && setRoles(r.roles)) }, [])
  return (
    <ViewBody style={{ maxWidth: 680 }}>
      <SectionLabel>Роли компании — описание, а не зашитый промпт</SectionLabel>
      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 16 }}>
        У каждой роли есть миссия, зона ответственности, инструменты и ограничения.
        Итоговый промпт собирается под задачу автоматически.
      </div>
      {roles.length === 0 ? <Empty text="Загрузка…" /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {roles.map((r: any) => (
            <Card key={r.role}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 14, color: "var(--text)" }}>{r.title || r.role}</span>
                {r.department && <span style={{ fontSize: 10.5, color: "var(--muted)" }}>{DEPT_RU[r.department] || r.department}</span>}
              </div>
              {r.mission && <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45, marginBottom: 8 }}>{r.mission}</div>}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {(r.responsibilities || []).map((x: string, i: number) => (
                  <span key={i} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99,
                    background: "var(--surface-soft)", border: "1px solid var(--hairline)", color: "var(--text-dim)" }}>{x}</span>
                ))}
              </div>
              {(r.constraints || []).length > 0 && (
                <div style={{ fontSize: 10.5, color: "var(--mercury-a)", marginTop: 8 }}>🚫 {(r.constraints || []).join(" · ")}</div>
              )}
            </Card>
          ))}
        </div>
      )}
    </ViewBody>
  )
}

// ── Скиллы: каталог + установка из любого источника (как npx skills) ──────────
const ROLE_RU: Record<string, string> = {
  cto: "CTO", cmo: "CMO", sales_lead: "Head of Sales", developer: "Разработчик",
  // designer вернулась как отдельная нанимаемая роль (roles.py, 2026-07-14) —
  // готовит бренд-бук ДО кода, developer строит сайт. Раньше была слита с
  // developer (один артефакт site/, дублирующая работа) — теперь разные
  // артефакты (docs/brand_book.md vs site/), конфликт не повторяется.
  designer: "Дизайнер",
  integrator: "Интегратор", marketer: "Маркетолог",
  analyst: "Аналитик", salesman: "Продажник", researcher: "Ресёрчер",
  strategist: "Стратег", architect: "Архитектор", hr: "HR",
}
const SKILL_FIELD: React.CSSProperties = {
  background: "var(--surface-soft)", border: "1px solid var(--hairline)",
  borderRadius: "var(--radius-md)", padding: "8px 11px", color: "var(--text)",
  fontSize: 12, outline: "none",
}

// Разбор вставленного SKILL.md: если есть frontmatter (--- … ---) — вытащить поля,
// вернуть тело без него. Позволяет вставить готовый скилл и заполнить поля сами.
function splitFrontmatter(text: string): { fm: Record<string, string> | null; body: string } {
  const m = text.match(/^﻿?\s*---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n?([\s\S]*)$/)
  if (!m) return { fm: null, body: text }
  const fm: Record<string, string> = {}
  for (const line of m[1].split("\n")) {
    const i = line.indexOf(":")
    if (i > 0) fm[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim()
  }
  return { fm, body: m[2].replace(/^\s+/, "") }
}

function SkillsTab() {
  const [skills, setSkills] = useState<any[]>([])
  const [mode, setMode] = useState<"markdown" | "url" | "github">("markdown")
  // Поля скилла — тело первично, параметры заполняются сами при вставке готового SKILL.md.
  const [body, setBody] = useState("")
  const [title, setTitle] = useState("")
  const [desc, setDesc] = useState("")
  const [keywords, setKeywords] = useState("")
  const [roles, setRoles] = useState("")
  const [ref, setRef] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const load = () => api.get("/api/skills").then(d => d?.skills && setSkills(d.skills))
  useEffect(() => { load() }, [])

  // Вставили тело — если это готовый SKILL.md с frontmatter, разложим по полям.
  function onBodyChange(v: string) {
    const { fm, body: b } = splitFrontmatter(v)
    if (fm) {
      if (fm.title || fm.name) setTitle(fm.title || fm.name)
      if (fm.description) setDesc(fm.description)
      if (fm.keywords) setKeywords(fm.keywords)
      if (fm.roles) setRoles(fm.roles)
      setBody(b)
    } else {
      setBody(v)
    }
  }

  function assembleMarkdown(): string {
    const fm = ["---"]
    fm.push(`title: ${title.trim() || "Новый скилл"}`)
    if (desc.trim()) fm.push(`description: ${desc.trim()}`)
    if (keywords.trim()) fm.push(`keywords: ${keywords.trim()}`)
    if (roles.trim()) fm.push(`roles: ${roles.trim()}`)
    fm.push("---")
    return `${fm.join("\n")}\n${body.trim()}`
  }

  async function install() {
    setBusy(true); setMsg(null)
    const payload: any = { source: mode }
    if (mode === "markdown") payload.content = assembleMarkdown()
    else if (mode === "url") payload.url = ref
    else payload.ref = ref
    // Прямой fetch: install отдаёт 400 с {message} при ошибке, а api.post глотает
    // тело на non-2xx — нам нужно показать пользователю причину.
    let res: any = null
    try {
      const r = await fetch("/api/skills/install", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      })
      res = await r.json().catch(() => ({ ok: false }))
    } catch { res = { ok: false, message: "Сеть недоступна" } }
    setBusy(false)
    if (res?.ok) {
      setMsg({ ok: true, text: `Установлен: ${res.title || res.id}` })
      setBody(""); setTitle(""); setDesc(""); setKeywords(""); setRoles(""); setRef(""); load()
    } else {
      setMsg({ ok: false, text: res?.message || "Не удалось установить" })
    }
  }

  async function removeSkill(id: string) {
    const res = await api.del(`/api/skills/${encodeURIComponent(id)}`)
    if (res?.ok) load()
    else setMsg({ ok: false, text: res?.message || "Не удалось удалить" })
  }

  const installed = skills.filter(s => s.source === "installed")
  const builtin = skills.filter(s => s.source !== "installed")

  return (
    <ViewBody style={{ maxWidth: 720 }}>
      <SectionLabel>Установить скилл (из любого источника)</SectionLabel>
      <Card style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 12 }}>
          Скилл — это готовый «как делать» для агентов: заголовок с описанием
          + текст инструкции. Скилл — <b style={{ color: "var(--text-dim)" }}>инструкция,
          которой агенты будут следовать</b>: ставьте из доверенных источников.
        </div>
        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          {([["markdown", "Вставить"], ["url", "По ссылке"], ["github", "GitHub"]] as const).map(([m, label]) => (
            <button key={m} onClick={() => setMode(m)}
              style={{ padding: "5px 12px", borderRadius: "var(--radius-pill)", fontSize: 12, cursor: "pointer",
                border: `1px solid ${mode === m ? "var(--mercury-a)" : "var(--hairline)"}`,
                background: mode === m ? "rgba(255,172,46,0.08)" : "transparent",
                color: mode === m ? "var(--mercury-a)" : "var(--text-dim)" }}>{label}</button>
          ))}
        </div>
        {mode === "markdown" ? (
          <>
            {/* Тело — первично: вставь сюда готовый скилл ИЛИ опиши, как делать. */}
            <textarea value={body} onChange={e => onBodyChange(e.target.value)}
              placeholder={"Вставьте готовый скилл (SKILL.md) — параметры ниже заполнятся сами.\nИли просто опишите, как делать: пошагово, приёмы, чеклист."}
              rows={8}
              style={{ width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
                borderRadius: "var(--radius-md)", padding: "10px 12px", color: "var(--text)", fontSize: 12,
                outline: "none", fontFamily: "var(--font-mono)", resize: "vertical", lineHeight: 1.5 }} />
            <div style={{ fontSize: 11, color: "var(--muted)", margin: "8px 0 4px" }}>
              Параметры (заполнятся сами, если вставили готовый SKILL.md):
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Название *"
                style={SKILL_FIELD} />
              <input value={roles} onChange={e => setRoles(e.target.value)} placeholder="Роли: developer, marketer"
                style={SKILL_FIELD} />
              <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Описание — что делает"
                style={{ ...SKILL_FIELD, gridColumn: "1 / -1" }} />
              <input value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="Ключевые слова (через запятую)"
                style={{ ...SKILL_FIELD, gridColumn: "1 / -1" }} />
            </div>
          </>
        ) : (
          <input value={ref} onChange={e => setRef(e.target.value)}
            placeholder={mode === "url" ? "https://…/SKILL.md (сырой markdown)" : "owner/repo@skill"}
            style={{ width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "10px 12px", color: "var(--text)", fontSize: 13, outline: "none" }} />
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
          <button onClick={install} disabled={busy || (mode === "markdown" ? !(body.trim() && title.trim()) : !ref.trim())}
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-pill)", padding: "9px 20px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13,
              opacity: busy ? 0.5 : 1 }}>{busy ? "Устанавливаю…" : "Установить"}</button>
          {msg && <span style={{ fontSize: 12, color: msg.ok ? "var(--success)" : "var(--danger)" }}>{msg.text}</span>}
        </div>
      </Card>

      {installed.length > 0 && (
        <>
          <SectionLabel>Установленные · {installed.length}</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
            {installed.map(s => <SkillCard key={s.id} s={s} onRemove={() => removeSkill(s.id)} />)}
          </div>
        </>
      )}

      <SectionLabel>Встроенные · {builtin.length}</SectionLabel>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {builtin.map(s => <SkillCard key={s.id} s={s} />)}
      </div>
    </ViewBody>
  )
}

function SkillCard({ s, onRemove }: { s: any; onRemove?: () => void }) {
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 13.5, color: "var(--text)", fontWeight: 500 }}>{s.title}</span>
            <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 99,
              background: onRemove ? "rgba(255,172,46,0.12)" : "var(--surface-soft)",
              color: onRemove ? "var(--mercury-a)" : "var(--faint)", border: "1px solid var(--hairline)" }}>
              {onRemove ? "установлен" : "встроенный"}
            </span>
          </div>
          {s.description && <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.45 }}>{s.description}</div>}
          {(s.roles || []).length > 0 && (
            <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 6 }}>
              роли: {Array.from(new Set((s.roles || []).map((r: string) => ROLE_RU[r] || r))).join(", ")}
            </div>
          )}
        </div>
        {onRemove && (
          <button onClick={onRemove} title="Удалить скилл"
            style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer", fontSize: 16, flexShrink: 0 }}>×</button>
        )}
      </div>
    </Card>
  )
}
