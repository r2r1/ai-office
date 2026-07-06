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

// Карта сайта (рефакторинг сессии 2026-07-05): "Чаты" убраны как отдельный
// пункт — открываются из «Команды» (кнопка «написать агенту» на карточке или
// общий вход в инбокс) и по клику на агента где угодно (Офис/модалка агента);
// "Сценарии" тоже убраны — стали переключателем вида ВНУТРИ «Офис» (App.tsx,
// officeMode), а не отдельным пунктом: изо-сцена и органиграмма — один и тот
// же слепок компании под разными углами; "Лиды" подняты из под-вкладки «Итоги»
// на верхний уровень — мини-CRM это корневая зависимость продукта, не файл
// наравне с прочими результатами; "Итоги" убраны полностью — материалы и
// сайты теперь артефакты КОНКРЕТНОГО проекта (см. «Работа» → карточка
// проекта → «Артефакты»), а не общий котёл на всю компанию (Work — BOS §5).
const NAV: Array<{ id: Section; label: string; group: "top" | "bottom" }> = [
  { id: "office",      label: "Офис",    group: "top" },
  { id: "dashboard",   label: "Сводка",  group: "top" },
  { id: "project",     label: "Работа",  group: "top" },
  { id: "team",        label: "Команда", group: "top" },
  { id: "leads",       label: "Лиды",    group: "top" },
  { id: "company",     label: "Компания", group: "bottom" },
  { id: "account",     label: "Аккаунт", group: "bottom" },
]

interface NavRailProps {
  active: Section
  onChange: (s: Section) => void
  orientation?: "vertical" | "horizontal"
  badges?: Partial<Record<Section, number>>
}

/** Бейдж-счётчик непрочитанного поверх иконки навигации. */
function NavBadge({ count, compact }: { count: number; compact?: boolean }) {
  if (count <= 0) return null
  const label = count > 9 ? "9+" : String(count)
  return (
    <motion.span
      initial={{ scale: 0 }} animate={{ scale: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 24 }}
      aria-hidden
      style={{
        position: "absolute", top: compact ? 0 : 4, right: compact ? 4 : 18,
        minWidth: 16, height: 16, padding: "0 4px", borderRadius: 9,
        background: AMBER, color: "#0a0a0a",
        fontSize: 9.5, fontWeight: 700, lineHeight: "16px", textAlign: "center",
        boxShadow: `0 0 0 2px var(--bg), 0 1px 3px rgba(${AMBER_RGB},0.5)`,
        fontFamily: "var(--font-sans)", pointerEvents: "none",
      }}>{label}</motion.span>
  )
}

export function NavRail({ active, onChange, orientation = "vertical", badges }: NavRailProps) {
  if (orientation === "horizontal") {
    return (
      <div style={{ position: "relative", width: "100%", maxWidth: "100%", minWidth: 0 }}>
        <div className="glass" style={{
          display: "flex", alignItems: "center", gap: 2, borderRadius: "var(--radius-pill)",
          padding: "6px 8px", overflowX: "auto", maxWidth: "100%",
          WebkitOverflowScrolling: "touch", scrollbarWidth: "none",
          // Растягиваем маску прозрачности по краям — визуальный намёк, что
          // список скроллится (найдено в аудите: обрезанные вкладки без
          // подсказки о скролле).
          maskImage: "linear-gradient(to right, transparent 0, black 14px, black calc(100% - 14px), transparent 100%)",
          WebkitMaskImage: "linear-gradient(to right, transparent 0, black 14px, black calc(100% - 14px), transparent 100%)",
        }}>
          {NAV.map(item => {
            const isActive = item.id === active
            const badge = badges?.[item.id] ?? 0
            return (
              <button key={item.id} onClick={() => onChange(item.id)}
                aria-label={badge > 0 ? `${item.label}, непрочитанных: ${badge}` : item.label}
                style={{
                  position: "relative", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  height: 40, border: "none", cursor: "pointer", background: "transparent",
                  fontFamily: "var(--font-sans)", WebkitTapHighlightColor: "transparent",
                }}>
                {/* Индикатор активной вкладки — узнаваемый паттерн (Material 3
                    NavigationBar): растущая амбер-пилюля позади иконки, а не
                    просто смена цвета текста. Общий layoutId даёт пилюле
                    плавно "переезжать" между вкладками вместо перескока. */}
                {isActive && (
                  <motion.span layoutId="mobile-nav-pill"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                    style={{
                      position: "absolute", inset: 0, borderRadius: "var(--radius-pill)",
                      background: `rgba(${AMBER_RGB},0.16)`,
                      border: `1px solid rgba(${AMBER_RGB},0.3)`,
                    }} />
                )}
                <span style={{
                  position: "relative", zIndex: 1,
                  display: "flex", alignItems: "center", gap: 6,
                  padding: isActive ? "0 14px" : "0 11px",
                  color: isActive ? AMBER : "var(--muted)",
                  transition: "color 0.2s",
                }}>
                  <span style={{ position: "relative", display: "flex" }}>
                    <Icon name={item.id} size={17} strokeWidth={isActive ? 2.2 : 1.8} />
                    <NavBadge count={badge} compact />
                  </span>
                  {isActive && (
                    <motion.span
                      initial={{ opacity: 0, width: 0 }} animate={{ opacity: 1, width: "auto" }}
                      exit={{ opacity: 0, width: 0 }} transition={{ duration: 0.16 }}
                      style={{
                        fontSize: 11, letterSpacing: "0.2px", fontWeight: 600,
                        color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden",
                      }}>{item.label}</motion.span>
                  )}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    )
  }

  return <NavRailVertical active={active} onChange={onChange} badges={badges} />
}

function NavRailVertical({ active, onChange, badges }: { active: Section; onChange: (s: Section) => void; badges?: Partial<Record<Section, number>> }) {
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
          {top.map(item => <NavItem key={item.id} item={item} active={active} onChange={onChange} badge={badges?.[item.id] ?? 0} />)}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {bottom.map(item => <NavItem key={item.id} item={item} active={active} onChange={onChange} badge={badges?.[item.id] ?? 0} />)}
        </div>
      </div>
    </div>
  )
}

function NavItem({ item, active, onChange, badge = 0 }: {
  item: typeof NAV[0]; active: Section; onChange: (s: Section) => void; badge?: number
}) {
  const isActive = item.id === active

  return (
    <button
      onClick={() => onChange(item.id)}
      data-bridge-active={isActive ? "true" : undefined}
      aria-label={badge > 0 ? `${item.label}, непрочитанных: ${badge}` : item.label}
      style={{
        position: "relative",
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
        style={{ display: "flex", lineHeight: 0, position: "relative" }}
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
        <NavBadge count={badge} compact />
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