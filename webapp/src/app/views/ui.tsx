import { useState, useEffect, useRef, createContext, useContext } from "react"
import type { ReactNode, CSSProperties } from "react"
import { motion, useMotionValue, useTransform, type MotionValue } from "motion/react"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

/* ─────────────────────────────────────────────────────────────────────────────
   Collapsing-header механика.
   ViewShell держит общий MotionValue прокрутки; ViewBody пишет в него свой
   scrollTop (без ре-рендера React); ViewHead читает его через useTransform и
   плавно ужимается. Всё считается на компоновочном слое → 0 ре-рендеров на скролл.
   ───────────────────────────────────────────────────────────────────────────── */
const ScrollCtx = createContext<MotionValue<number> | null>(null)

export function ViewShell({ children }: { children: ReactNode }) {
  const scrollY = useMotionValue(0)
  return (
    <ScrollCtx.Provider value={scrollY}>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {children}
      </div>
    </ScrollCtx.Provider>
  )
}

export function ViewHead({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  const scrollY = useContext(ScrollCtx)
  // Фоллбэк, если ViewHead используется вне ViewShell
  const fallback = useMotionValue(0)
  const sy = scrollY ?? fallback

  const fontSize   = useTransform(sy, [0, 64], [30, 19])
  const padTop     = useTransform(sy, [0, 64], [24, 13])
  const padBottom  = useTransform(sy, [0, 64], [16, 13])
  const subHeight  = useTransform(sy, [0, 34], [20, 0])
  const subOpacity = useTransform(sy, [0, 28], [1, 0])
  const subMargin  = useTransform(sy, [0, 34], [7, 0])
  const lineOpacity = useTransform(sy, [40, 64], [0, 1])

  return (
    <motion.div style={{
      paddingTop: padTop, paddingBottom: padBottom, paddingLeft: 28, paddingRight: 28,
      flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
      position: "relative", zIndex: 3, background: "var(--surface-head)",
    }}>
      <div style={{ minWidth: 0 }}>
        <motion.div className="display" style={{ fontSize, color: "var(--text)", lineHeight: 1.05 }}>{title}</motion.div>
        {sub != null && (
          <motion.div style={{ height: subHeight, opacity: subOpacity, marginTop: subMargin, overflow: "hidden" }}>
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.4, whiteSpace: "nowrap" }}>{sub}</div>
          </motion.div>
        )}
      </div>
      {right}
      {/* хайрлайн снизу — появляется при компактном состоянии */}
      <motion.div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 1, background: "var(--hairline)", opacity: lineOpacity }} />
    </motion.div>
  )
}

export function ViewBody({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  const scrollY = useContext(ScrollCtx)
  const ref = useRef<HTMLDivElement>(null)

  // нативный scroll-листенер (надёжнее React onScroll) + сброс при монтировании/смене таба
  useEffect(() => {
    const el = ref.current
    if (!el || !scrollY) return
    scrollY.set(0); el.scrollTop = 0
    const onScroll = () => scrollY.set(el.scrollTop)
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [scrollY])

  return (
    <div ref={ref} style={{ flex: 1, overflowY: "auto", padding: "18px 28px 28px", ...style }}>
      {children}
    </div>
  )
}

/* ── Sub-tab bar ─────────────────────────────────────────────────────────────── */
export interface TabDef { id: string; label: string; badge?: number }

export function SubTabs({ tabs, active, onChange }: { tabs: TabDef[]; active: string; onChange: (id: string) => void }) {
  // Ряд табов горизонтально скроллится (overflowX: auto) без визуальной
  // подсказки — на узких экранах (напр. 8 под-вкладок «Компании» на 375px)
  // хвост списка обрезается краем экрана без намёка, что там ещё есть табы
  // (найдено при мобильном аудите после карты сайта). Затухание справа
  // показывается, только если реально есть что докрутить — не декорация.
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canScrollRight, setCanScrollRight] = useState(false)
  const [canScrollLeft, setCanScrollLeft] = useState(false)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const check = () => {
      setCanScrollRight(el.scrollWidth - el.scrollLeft - el.clientWidth > 4)
      setCanScrollLeft(el.scrollLeft > 4)
    }
    check()
    el.addEventListener("scroll", check, { passive: true })
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => { el.removeEventListener("scroll", check); ro.disconnect() }
  }, [tabs.length])

  return (
    <div style={{ position: "relative", flexShrink: 0 }}>
      <div ref={scrollRef} style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--hairline)",
        paddingLeft: 28, paddingRight: 28, overflowX: "auto", position: "relative", zIndex: 3 }}>
        {tabs.map(t => {
          const isActive = t.id === active
          return (
            <button key={t.id} onClick={() => onChange(t.id)}
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "11px 16px", fontSize: 12.5,
                fontWeight: isActive ? 500 : 400, color: isActive ? "var(--text)" : "var(--muted)",
                background: "none", border: "none", borderBottom: isActive ? "2px solid var(--mercury-a)" : "2px solid transparent",
                marginBottom: -1, cursor: "pointer", whiteSpace: "nowrap", transition: "color 0.15s, border-color 0.15s",
                fontFamily: "var(--font-sans)", flexShrink: 0 }}
              onMouseEnter={e => { if (!isActive) e.currentTarget.style.color = "var(--text-dim)" }}
              onMouseLeave={e => { if (!isActive) e.currentTarget.style.color = "var(--muted)" }}>
              {t.label}
              {t.badge != null && t.badge > 0 && (
                <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 99,
                  background: isActive ? "rgba(255,172,46,0.15)" : "var(--hairline-soft)",
                  color: isActive ? "var(--mercury-a)" : "var(--muted)",
                  border: `1px solid ${isActive ? "rgba(255,172,46,0.3)" : "var(--hairline)"}` }}>
                  {t.badge}
                </span>
              )}
            </button>
          )
        })}
      </div>
      {canScrollLeft && (
        <div style={{
          position: "absolute", top: 0, left: 0, bottom: 1, width: 28, pointerEvents: "none", zIndex: 4,
          background: "linear-gradient(to left, transparent, var(--surface))",
        }} />
      )}
      {canScrollRight && (
        <div style={{
          position: "absolute", top: 0, right: 0, bottom: 1, width: 32, pointerEvents: "none", zIndex: 4,
          background: "linear-gradient(to right, transparent, var(--surface))",
        }} />
      )}
    </div>
  )
}

export function useSubTab(tabs: TabDef[], initial?: string) {
  const [active, setActive] = useState(initial || tabs[0]?.id || "")
  return { active, setActive, tabs }
}

export function SectionLabel({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase",
    letterSpacing: "1.5px", margin: "0 0 12px", ...style }}>{children}</div>
}

export function Card({ children, style, onClick }: { children: ReactNode; style?: CSSProperties; onClick?: () => void }) {
  const hover = !!onClick
  return (
    <div className="card" onClick={onClick}
      style={{ borderRadius: "var(--radius-md)", padding: 16, cursor: hover ? "pointer" : "default",
        transition: "border-color 0.18s, transform 0.18s, box-shadow 0.18s", ...style }}
      onMouseEnter={hover ? e => { const el = e.currentTarget as HTMLElement; el.style.transform = "translateY(-1px)"; el.style.borderColor = "var(--hairline-strong)" } : undefined}
      onMouseLeave={hover ? e => { const el = e.currentTarget as HTMLElement; el.style.transform = ""; el.style.borderColor = "" } : undefined}>
      {children}
    </div>
  )
}

export function Empty({ icon, text, hint }: { icon?: string; text: string; hint?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: "56px 24px", gap: 11, textAlign: "center" }}>
      {icon && <div style={{ fontSize: 34, opacity: 0.25, lineHeight: 1 }}>{icon}</div>}
      <div style={{ fontSize: 13, color: "var(--muted)" }}>{text}</div>
      {hint && <div style={{ fontSize: 11.5, color: "var(--faint)", maxWidth: 300, lineHeight: 1.55 }}>{hint}</div>}
    </div>
  )
}

export function Pill({ children, accent, color }: { children: ReactNode; accent?: boolean; color?: string }) {
  const c = color ?? (accent ? "rgba(255,172,46,0.4)" : "var(--hairline)")
  const tc = color ? "#fff" : accent ? "var(--mercury-a)" : "var(--text-dim)"
  return (
    <span style={{ fontSize: 10, padding: "2px 10px", borderRadius: "var(--radius-pill)", border: `1px solid ${c}`,
      color: tc, whiteSpace: "nowrap", background: color ? color + "22" : undefined }}>
      {children}
    </span>
  )
}

export function MercuryBar({ percent, style }: { percent: number; style?: CSSProperties }) {
  return (
    <div style={{ height: 3, borderRadius: 99, background: "var(--hairline-strong)", overflow: "hidden", ...style }}>
      <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, percent))}%`, background: MERCURY,
        borderRadius: 99, transition: "width 0.6s var(--ease-out)" }} />
    </div>
  )
}

export const STATUS_COLOR: Record<string, string> = {
  active: "#a0e0ab", thinking: "#ffac2e", done: "var(--text-dim)", idle: "var(--whisper)",
}
