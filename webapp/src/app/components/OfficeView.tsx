import { useEffect, useMemo, useRef, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { useOffice } from "../../data/OfficeProvider"
import type { Worker } from "../types"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

// Комнаты (x,y,w,h в % контейнера) — из Figma-плана офиса.
// Раньше подписи были на английском (RESEARCH LAB/STRATEGY/...) — единственное
// место интерфейса, нарушавшее правило проекта "язык продукта — русский"
// (найдено при живом дизайн-аудите: смешение RU/EN резало глаз именно здесь,
// на самом заметном экране продукта).
const ROOMS = [
  { id: "research", label: "ИССЛЕДОВАНИЯ", x: 4, y: 7, w: 30, h: 44 },
  { id: "strategy", label: "СТРАТЕГИЯ", x: 37, y: 7, w: 22, h: 44 },
  { id: "hr", label: "HR", x: 62, y: 7, w: 17, h: 44 },
  { id: "mgmt", label: "УПРАВЛЕНИЕ", x: 82, y: 7, w: 14, h: 44 },
  { id: "sales", label: "ПРОДАЖИ", x: 4, y: 58, w: 22, h: 36 },
  { id: "dev", label: "РАЗРАБОТКА", x: 29, y: 58, w: 32, h: 36 },
  { id: "meeting", label: "ПЕРЕГОВОРНАЯ", x: 64, y: 58, w: 32, h: 36 },
]

const DESKS: Array<[number, number]> = [
  [9, 17], [17, 17], [25, 17], [9, 31], [17, 31], [25, 31],
  [42, 17], [50, 17], [42, 31], [50, 31],
  [68, 17], [68, 31], [88, 17], [88, 31],
  [9, 68], [16, 68], [9, 78], [16, 78],
  [35, 68], [42, 68], [49, 68], [35, 78], [42, 78], [49, 78],
  [70, 68], [78, 68], [86, 68],
]

// Роль → домашняя позиция (x,y %). Дубликаты роли разводим оффсетом.
const ROLE_HOME: Record<string, [number, number]> = {
  orchestrator: [88, 17], cto: [88, 31], cmo: [88, 24], sales_lead: [88, 38],
  researcher: [17, 31], analyst: [9, 31],
  strategist: [50, 31], architect: [42, 31],
  hr: [68, 31],
  salesman: [13, 73], marketer: [13, 84],
  developer: [42, 73], designer: [49, 73], integrator: [35, 73],
}
const MEETING: [number, number] = [80, 75]

function homeFor(agent: Worker, idx: number): [number, number] {
  const base = ROLE_HOME[agent.role]
  if (base) return base
  // неизвестная роль — раскидываем по свободным столам
  return DESKS[idx % DESKS.length]
}

interface OfficeViewProps { onOpenAgent?: (id: string) => void }

export function OfficeView({ onOpenAgent }: OfficeViewProps) {
  const { state } = useOffice()
  const agents = useMemo(() => Object.values(state.agents), [state.agents])
  const [meeting, setMeeting] = useState<Record<string, boolean>>({})

  // Держим актуальный список агентов в ref, чтобы интервал ниже НЕ пересоздавался
  // на каждый SSE-апдейт (иначе таймер 6с постоянно сбрасывался и почти не срабатывал).
  const agentsRef = useRef(agents)
  agentsRef.current = agents

  // Изредка отправляем случайного агента в переговорку и обратно (живость).
  useEffect(() => {
    if (agents.length === 0) return
    const t = setInterval(() => {
      const list = agentsRef.current
      if (list.length === 0) return
      const a = list[Math.floor(Math.random() * list.length)]
      setMeeting(prev => ({ ...prev, [a.id]: !prev[a.id] }))
    }, 6000)
    return () => clearInterval(t)
  }, [agents.length])

  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      {/* перспективный пол-сетка для глубины (изо-намёк) */}
      <div style={{
        position: "absolute", inset: 0, pointerEvents: "none", opacity: 0.5,
        backgroundImage: "linear-gradient(var(--hairline) 1px, transparent 1px), linear-gradient(90deg, var(--hairline) 1px, transparent 1px)",
        backgroundSize: "5% 6.5%",
        maskImage: "radial-gradient(120% 90% at 50% 40%, #000 50%, transparent 90%)",
        WebkitMaskImage: "radial-gradient(120% 90% at 50% 40%, #000 50%, transparent 90%)",
      }} />

      {/* комнаты */}
      {ROOMS.map(r => (
        <div key={r.id} style={{
          position: "absolute", left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%`,
          border: "1px solid var(--hairline)", borderRadius: "var(--radius-md)",
          background: "var(--surface-soft)",
        }}>
          <div className="mono" style={{ position: "absolute", top: 8, left: 11, fontSize: 9, letterSpacing: "1.5px",
            color: "var(--faint)", userSelect: "none" }}>{r.label}</div>
        </div>
      ))}

      {/* столы */}
      {DESKS.map((d, i) => (
        <div key={i} style={{ position: "absolute", left: `${d[0]}%`, top: `${d[1]}%`,
          width: 26, height: 16, transform: "translate(-50%,-50%)",
          border: "1px solid var(--hairline)", borderRadius: 4, background: "var(--surface-soft)" }} />
      ))}

      {/* агенты (живые данные + Motion) */}
      {agents.map((a, i) => {
        const [hx, hy] = homeFor(a, i)
        const [x, y] = meeting[a.id] ? MEETING : [hx, hy]
        const active = a.status === "active"
        const thinking = a.status === "thinking"
        return (
          <motion.div key={a.id}
            initial={{ left: `${x}%`, top: `${y}%`, opacity: 0, scale: 0.6 }}
            animate={{ left: `${x}%`, top: `${y}%`, opacity: 1, scale: 1 }}
            transition={{ left: { type: "spring", stiffness: 45, damping: 16 }, top: { type: "spring", stiffness: 45, damping: 16 }, opacity: { duration: 0.4 }, scale: { type: "spring", stiffness: 300, damping: 20 } }}
            onClick={() => onOpenAgent?.(a.id)}
            style={{ position: "absolute", transform: "translate(-50%,-50%)", cursor: "pointer", zIndex: 10 }}>
            {/* glow для активных */}
            {active && (
              <motion.div animate={{ opacity: [0.6, 0.2, 0.6], scale: [1, 1.25, 1] }}
                transition={{ repeat: Infinity, duration: 2.4, ease: "easeInOut" }}
                style={{ position: "absolute", inset: -8, borderRadius: "50%",
                  background: "radial-gradient(circle, rgba(255,172,46,0.22) 0%, transparent 70%)", pointerEvents: "none" }} />
            )}
            {/* аватар */}
            <motion.div animate={active || thinking ? { scale: [1, 1.1, 1] } : { scale: 1 }}
              transition={{ repeat: Infinity, duration: active ? 2.4 : 4, ease: "easeInOut" }}
              style={{ position: "relative", width: 36, height: 36, borderRadius: "50%",
                background: active ? "var(--avatar-active)" : "var(--avatar-idle)",
                border: `1px solid ${active ? "var(--avatar-active)" : "var(--hairline-strong)"}`,
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 17 }}>
              {a.emoji}
              {/* статус-точка */}
              <span style={{ position: "absolute", top: 0, right: 0, width: 9, height: 9, borderRadius: "50%",
                border: "1.5px solid var(--bg)", background: active ? "#a0e0ab" : thinking ? "#ffac2e" : "var(--whisper)" }} />
            </motion.div>
            {/* имя */}
            <div style={{ position: "absolute", bottom: -19, left: "50%", transform: "translateX(-50%)",
              fontSize: 9, letterSpacing: "0.5px", textTransform: "uppercase", whiteSpace: "nowrap", userSelect: "none",
              color: active ? "var(--text-dim)" : "var(--faint)" }}>{a.name}</div>
            {/* бабл активности */}
            <AnimatePresence>
              {(active || thinking) && a.lastMessage && (
                <motion.div key={a.lastMessage}
                  initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.35 }}
                  style={{ position: "absolute", bottom: "calc(100% + 9px)", left: "50%", transform: "translateX(-50%)",
                    background: "var(--surface-card)",
                    border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-sm)",
                    boxShadow: "var(--shadow)", padding: "6px 11px", fontSize: 10, color: "var(--text-dim)",
                    whiteSpace: "nowrap", maxWidth: 230, overflow: "hidden", textOverflow: "ellipsis",
                    pointerEvents: "none", zIndex: 20 }}>
                  {a.lastMessage.slice(0, 64)}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )
      })}

      {/* подсказка / индикатор «офис ожидает» */}
      {agents.length === 0 && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 10 }}>
          <div className="display" style={{ fontSize: 40, color: "var(--text)" }}>Офис</div>
          <div style={{ fontSize: 13, color: "var(--muted)" }}>Агенты появятся после старта работы</div>
        </div>
      )}

      {/* нижняя Mercury-полоса этапа */}
      <div style={{ position: "absolute", left: 24, right: 24, bottom: 16, height: 2, borderRadius: 999,
        background: "var(--hairline-strong)", overflow: "hidden" }}>
        <motion.div animate={{ width: `${state.progress.percent}%` }} transition={{ duration: 0.6 }}
          style={{ height: "100%", background: MERCURY, borderRadius: 999 }} />
      </div>
    </div>
  )
}
