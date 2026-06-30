/**
 * NavRail — вертикальная навигация.
 * Исправлено: выпуклость теперь корректно доходит до краевых элементов.
 */

import { useRef, useEffect } from "react"
import { motion, useMotionValue, useSpring, useTransform } from "motion/react"
import type { Section } from "../types"
import { Icon } from "./icons"

const AMBER     = "#ffac2e"
const AMBER_RGB = "255,172,46"

/* Геометрия */
const W_VIS = 88     
const W_EL  = 102   
const R     = 24     

// Увеличиваем глубину и высоту зоны, чтобы эффект был заметнее
const INDENT_DEPTH = 14 
const INDENT_HEIGHT = 48 

/** 
 * SVG-путь для формы сайдбара.
 * by = Y-центр активной иконки.
 */
function buildPath(H: number, by: number): string {
  if (H < 1) return ""
  
  // Ограничиваем центр, чтобы не вылезать за пределы контейнера
  // Добавляем небольшой отступ (padding), чтобы кривая не ломалась о скругления углов
  const safeTop = -10
  const safeBot = H - R 
  
  const by_c = Math.max(safeTop, Math.min(safeBot, by))
  
  // Проверяем, насколько близко активный элемент к краям
  const distToTop = by_c - safeTop
  const distToBot = safeBot - by_c
  
  // Если элемент очень близко к краю (< INDENT_HEIGHT), используем упрощенную геометрию
  // чтобы "вытянуть" выпуклость до самого края без артефактов
  const isNearEdge = distToTop < INDENT_HEIGHT || distToBot < INDENT_HEIGHT
  
  function buildPath(H: number, by: number): string {
  if (H < 1) return ""

  const pad = R + 4
  const safeTop = pad
  const safeBot = H - pad
  const by_c = Math.max(safeTop, Math.min(safeBot, by))

  const halfH = INDENT_HEIGHT
  const topY = Math.max(safeTop, by_c - halfH)
  const botY = Math.min(safeBot, by_c + halfH)
  const cpFactor = (botY - topY) * 0.55

  return [
    `M ${R} 0 L ${W_VIS - R} 0 Q ${W_VIS} 0 ${W_VIS} ${R}`,
    `L ${W_VIS} ${topY}`,
    `C ${W_VIS} ${topY + cpFactor} ${W_VIS - INDENT_DEPTH} ${by_c - cpFactor * 0.6} ${W_VIS - INDENT_DEPTH} ${by_c}`,
    `C ${W_VIS - INDENT_DEPTH} ${by_c + cpFactor * 0.6} ${W_VIS} ${botY - cpFactor} ${W_VIS} ${botY}`,
    `L ${W_VIS} ${H - R} Q ${W_VIS} ${H} ${W_VIS - R} ${H}`,
    `L ${R} ${H} Q 0 ${H} 0 ${H - R} L 0 ${R} Q 0 0 ${R} 0 Z`,
  ].join(" ")
}

  // СТАНДАРТНАЯ ГЕОМЕТРИЯ (для средних элементов)
  // Плавные кубические кривые Безье
  const topY = by_c - INDENT_HEIGHT
  const botY = by_c + INDENT_HEIGHT
  const cpFactor = INDENT_HEIGHT * 0.55 

  return [
    `M ${R} 0 L ${W_VIS - R} 0 Q ${W_VIS} 0 ${W_VIS} ${R}`,
    `L ${W_VIS} ${topY}`,
    
    // Вход во вдавливание
    `C ${W_VIS} ${topY + cpFactor} ${W_VIS - INDENT_DEPTH} ${by_c - cpFactor * 0.6} ${W_VIS - INDENT_DEPTH} ${by_c}`,
    
    // Выход из вдавливания
    `C ${W_VIS - INDENT_DEPTH} ${by_c + cpFactor * 0.6} ${W_VIS} ${botY - cpFactor} ${W_VIS} ${botY}`,
    
    `L ${W_VIS} ${H - R} Q ${W_VIS} ${H} ${W_VIS - R} ${H}`,
    `L ${R} ${H} Q 0 ${H} 0 ${H - R} L 0 ${R} Q 0 0 ${R} 0 Z`,
  ].join(" ")
}

const NAV: Array<{ id: Section; label: string; group: "top" | "bottom" }> = [
  { id: "office",      label: "Офис",    group: "top" },
  { id: "dashboard",   label: "Сводка",  group: "top" },
  { id: "project",     label: "Проект",  group: "top" },
  { id: "team",        label: "Команда", group: "top" },
  { id: "results",     label: "Итоги",   group: "top" },
  { id: "chats",       label: "Чаты",    group: "top" },
  { id: "connections", label: "Доступы", group: "bottom" },
  { id: "company",     label: "Компания", group: "bottom" },
  { id: "account",     label: "Аккаунт", group: "bottom" },
]

interface NavRailProps {
  active: Section
  onChange: (s: Section) => void
  orientation?: "vertical" | "horizontal"
}

export function NavRail({ active, onChange, orientation = "vertical" }: NavRailProps) {
  if (orientation === "horizontal") {
    return (
      <div className="glass" style={{
        display: "flex", gap: 2, borderRadius: "var(--radius-pill)",
        padding: "5px 7px", overflowX: "auto",
      }}>
        {NAV.map(item => {
          const isActive = item.id === active
          return (
            <button key={item.id} onClick={() => onChange(item.id)} style={{
              display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
              padding: "6px 12px", borderRadius: "var(--radius-pill)", border: "none",
              cursor: "pointer", background: "transparent",
              color: isActive ? AMBER : "var(--muted)",
              transition: "color 0.2s", fontFamily: "var(--font-sans)", minWidth: 52,
            }}>
              <Icon name={item.id} size={17} />
              <span style={{
                fontSize: 8.5, letterSpacing: "0.4px", textTransform: "uppercase",
                fontWeight: isActive ? 500 : 400, color: isActive ? "var(--text)" : "inherit",
              }}>{item.label}</span>
            </button>
          )
        })}
      </div>
    )
  }

  return <NavRailVertical active={active} onChange={onChange} />
}

function NavRailVertical({ active, onChange }: { active: Section; onChange: (s: Section) => void }) {
  const containerRef = useRef<HTMLDivElement>(null)

  /* Motion values */
  const rawY   = useMotionValue(200)
  const springY = useSpring(rawY, { stiffness: 320, damping: 28, mass: 0.8 })
  const navHMV  = useMotionValue(0)

  const clipPath = useTransform(
    [springY, navHMV] as const,
    ([y, h]: number[]) => `path('${buildPath(h, y)}')`
  )
  
  const svgD = useTransform(
    [springY, navHMV] as const,
    ([y, h]: number[]) => buildPath(h, y)
  )

  // Для блика используем тот же Y
  const glowY = useTransform(springY, y => {
    const h = navHMV.get()
    // Используем те же ограничения, что и в buildPath
    const safeTop = R + 10
    const safeBot = h - R - 10
    return Math.max(safeTop, Math.min(safeBot, y))
  })

  useEffect(() => {
    const measure = () => {
      const nav = containerRef.current
      const btn = nav?.querySelector('[data-bridge-active="true"]') as HTMLElement | null
      if (!nav || !btn) return
      const nr = nav.getBoundingClientRect()
      const br = btn.getBoundingClientRect()
      navHMV.set(nr.height)
      rawY.set(br.top - nr.top + br.height / 2)
    }
    measure()
    const ro = new ResizeObserver(measure)
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [active])

  const top    = NAV.filter(n => n.group === "top")
  const bottom = NAV.filter(n => n.group === "bottom")

  return (
    <div
      ref={containerRef}
      style={{
        width: W_EL, flexShrink: 0, position: "relative",
      }}
    >
      {/* 1. Glass-слой */}
      <motion.div
        className="glass"
        style={{
          position: "absolute", top: 0, left: 0,
          width: W_EL, height: "100%",
          borderRadius: 0,
          border: "none",
          clipPath,
        }}
      />

      {/* 2. SVG-контур и эффекты */}
      <svg
        style={{
          position: "absolute", top: 0, left: 0,
          width: W_EL, height: "100%",
          overflow: "visible",
          pointerEvents: "none",
          zIndex: 2,
        }}
      >
        {/* Основная граница */}
        <motion.path
          d={svgD}
          fill="none"
          stroke="var(--hairline-strong)"
          strokeWidth={1}
        />

   

        {/* Глянцевый блик по контуру */}
        <motion.path
          d={svgD}
          fill="none"
          stroke="rgba(255,255,255,0.15)"
          strokeWidth={1}
          style={{ filter: "blur(0.5px)" }}
        />
      </svg>

      {/* 3. Кнопки навигации */}
      <div style={{
        position: "relative", zIndex: 3,
        width: W_VIS,
        height: "100%",
        display: "flex", flexDirection: "column",
        justifyContent: "space-between",
        paddingTop: 40,
        paddingBottom: 40,
        paddingLeft: 8,
        paddingRight: 8,
      }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {top.map(item => <NavItem key={item.id} item={item} active={active} onChange={onChange} />)}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {bottom.map(item => <NavItem key={item.id} item={item} active={active} onChange={onChange} />)}
        </div>
      </div>
    </div>
  )
}

function NavItem({ item, active, onChange }: {
  item: typeof NAV[0]; active: Section; onChange: (s: Section) => void
}) {
  const isActive = item.id === active

  return (
    <button
      onClick={() => onChange(item.id)}
      data-bridge-active={isActive ? "true" : undefined}
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", gap: 5,
        padding: "11px 4px",
        border: "none", cursor: "pointer",
        background: "transparent",
        fontFamily: "var(--font-sans)", width: "100%",
        WebkitTapHighlightColor: "transparent",
        outline: "none",
        borderRadius: "var(--radius-md)",
        transition: "color 0.2s var(--ease-out)",
        color: isActive ? AMBER : "var(--muted)",
      }}
      onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.color = "var(--text-dim)" }}
      onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.color = "var(--muted)" }}
    >
      {/* Анимированная иконка */}
      <motion.span
        style={{ display: "flex", lineHeight: 0 }}
       animate={isActive
          ? { scale: 1.08 }
          : { scale: 1 }
}
        transition={{ type: "spring", stiffness: 400, damping: 20 }}
      >
        <Icon
          name={item.id}
          size={22}
          strokeWidth={isActive ? 2.2 : 1.8}
          color={isActive ? AMBER : undefined}
        />
      </motion.span>

      <span style={{
        fontSize: 8.5, letterSpacing: "0.45px", textTransform: "uppercase",
        lineHeight: 1, fontWeight: isActive ? 600 : 400,
        color: isActive ? "var(--text)" : undefined,
        transition: "color 0.2s, font-weight 0.2s",
      }}>
        {item.label}
      </span>
      
      
    </button>
  )
}