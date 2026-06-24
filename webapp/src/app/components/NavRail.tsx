/**
 * NavRail — вертикальная навигация.
 * Активная вкладка не помечается наложением — сам сайдбар деформирует свою правую грань:
 * выпуклость (bulge) «вытекает» из стекла к основной панели (spring-физика).
 * Реализация: clip-path: path(...) на glass-элементе + SVG-контур сверху.
 */

import { useRef, useEffect } from "react"
import { motion, useMotionValue, useSpring, useTransform } from "motion/react"
import type { Section } from "../types"
import { Icon } from "./icons"

const AMBER     = "#ffac2e"
const AMBER_RGB = "255,172,46"

/* Геометрия */
const W_VIS = 88     // визуальная ширина сайдбара
const W_EL  = 102    // ширина элемента (с запасом под выпуклость)
const R     = 24     // радиус скруглений
const BE    = 12     // насколько выпуклость выступает вправо
const BH    = 44     // полу-высота зоны выпуклости

/** SVG-путь для формы сайдбара. by = Y-центр выпуклости. */
function buildPath(H: number, by: number): string {
  if (H < 1) return ""
  const c  = BH * 0.44                                          // control offset
  const by_c = Math.max(R + BH + 2, Math.min(H - R - BH - 2, by))
  const b1 = by_c - BH
  const b2 = by_c + BH

  return [
    // верх + правый верхний угол
    `M ${R} 0 L ${W_VIS - R} 0 Q ${W_VIS} 0 ${W_VIS} ${R}`,
    // правая грань сверху до начала выпуклости
    `L ${W_VIS} ${b1}`,
    // вход в выпуклость (bezier)
    `C ${W_VIS} ${b1 + c} ${W_VIS + BE} ${by_c - c * 0.25} ${W_VIS + BE} ${by_c}`,
    // выход из выпуклости (bezier)
    `C ${W_VIS + BE} ${by_c + c * 0.25} ${W_VIS} ${b2 - c} ${W_VIS} ${b2}`,
    // правая грань вниз + правый нижний угол
    `L ${W_VIS} ${H - R} Q ${W_VIS} ${H} ${W_VIS - R} ${H}`,
    // низ + левый нижний угол + левая грань + левый верхний угол
    `L ${R} ${H} Q 0 ${H} 0 ${H - R} L 0 ${R} Q 0 0 ${R} 0 Z`,
  ].join(" ")
}

/* ─── Типы ─── */
const NAV: Array<{ id: Section; label: string; group: "top" | "bottom" }> = [
  { id: "office",      label: "Офис",    group: "top" },
  { id: "project",     label: "Проект",  group: "top" },
  { id: "team",        label: "Команда", group: "top" },
  { id: "chats",       label: "Чаты",    group: "top" },
  { id: "results",     label: "Итоги",   group: "top" },
  { id: "connections", label: "Доступы", group: "bottom" },
  { id: "account",     label: "Аккаунт", group: "bottom" },
]

interface NavRailProps {
  active: Section
  onChange: (s: Section) => void
  orientation?: "vertical" | "horizontal"
}

/* ─── Горизонтальный вариант (мобайл) ─── */
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

/* ─── Вертикальный вариант — деформируемый сайдбар ─── */
function NavRailVertical({ active, onChange }: { active: Section; onChange: (s: Section) => void }) {
  const containerRef = useRef<HTMLDivElement>(null)

  /* Motion values для пружины */
  const rawY   = useMotionValue(200)
  const springY = useSpring(rawY, { stiffness: 280, damping: 26, mass: 0.9 })
  const navHMV  = useMotionValue(0)

  /* clip-path path() для glass-слоя */
  const clipPath = useTransform(
    [springY, navHMV] as const,
    ([y, h]: number[]) => `path('${buildPath(h, y)}')`
  )
  /* Та же форма — для SVG-контура (без обёртки path('...')) */
  const svgD = useTransform(
    [springY, navHMV] as const,
    ([y, h]: number[]) => buildPath(h, y)
  )
  /* Y-центр кончика выпуклости для янтарного акцента */
  const glowY = useTransform(springY, y => {
    const h = navHMV.get()
    return Math.max(R + BH + 2, Math.min(h - R - BH - 2, y))
  })

  /* Замеры при смене активного пункта или ресайзе */
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
  }, [active]) // eslint-disable-line

  const top    = NAV.filter(n => n.group === "top")
  const bottom = NAV.filter(n => n.group === "bottom")

  return (
    /* Внешний контейнер — резервирует место (W_EL) но не имеет фона */
    <div
      ref={containerRef}
      style={{
        width: W_EL, flexShrink: 0, position: "relative",
        /* overflow: visible чтобы SVG-контур не обрезался по границе */
      }}
    >
      {/* ── 1. Glass-слой, обрезанный по форме с выпуклостью ─────────────── */}
      <motion.div
        className="glass"
        style={{
          position: "absolute", top: 0, left: 0,
          width: W_EL, height: "100%",
          borderRadius: 0,          /* скругления теперь в clip-path */
          border: "none",           /* граница рисуется SVG-контуром */
          clipPath,
        }}
      />

      {/* ── 2. SVG-контур (тонкая линия, следует за формой) ─────────────── */}
      <svg
        style={{
          position: "absolute", top: 0, left: 0,
          width: W_EL, height: "100%",
          overflow: "visible",
          pointerEvents: "none",
          zIndex: 2,
        }}
      >
        {/* Основная граница сайдбара */}
        <motion.path
          d={svgD}
          fill="none"
          stroke="var(--hairline-strong)"
          strokeWidth={1}
        />

        {/* Янтарный блик на кончике выпуклости */}
        <motion.ellipse
          cx={W_VIS + BE}
          cy={glowY}
          rx={5} ry={16}
          fill={`rgba(${AMBER_RGB}, 0.18)`}
          style={{ filter: "blur(4px)" }}
        />
        <motion.circle
          cx={W_VIS + BE}
          cy={glowY}
          r={2.5}
          fill={`rgba(${AMBER_RGB}, 0.65)`}
        />

        {/* Верхний глянцевый блик внутри сайдбара */}
        <motion.path
          d={svgD}
          fill="none"
          stroke="rgba(255,255,255,0.12)"
          strokeWidth={1}
          style={{ filter: "blur(0.5px)" }}
        />
      </svg>

      {/* ── 3. Кнопки навигации (поверх glass-слоя) ─────────────────────── */}
      <div style={{
        position: "relative", zIndex: 3,
        width: W_VIS,            /* кнопки занимают только визуальную ширину */
        height: "100%",
        display: "flex", flexDirection: "column",
        justifyContent: "space-between",
        padding: "14px 8px",
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

/* ─── Кнопка навигации — без наложений, только иконка + текст ─── */
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
      <motion.span
        style={{ display: "flex", lineHeight: 0 }}
        animate={isActive
          ? { scale: 1.1, filter: `drop-shadow(0 0 5px rgba(${AMBER_RGB},0.5))` }
          : { scale: 1,   filter: "none" }
        }
        transition={{ type: "spring", stiffness: 380, damping: 22 }}
      >
        <Icon
          name={item.id}
          size={20}
          strokeWidth={isActive ? 2.1 : 1.7}
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
