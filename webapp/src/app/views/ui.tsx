import { useState, useEffect, useRef, createContext, useContext } from "react"
import type { ReactNode, CSSProperties, ButtonHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from "react"
import { motion, useMotionValue, useTransform, type MotionValue } from "motion/react"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"
// Только для MercuryBar (% выполнения задач) — НЕ общий бренд-акцент (MERCURY
// на кнопках/аватарах не трогаем). Полный зелёно-жёлто-красный MERCURY на
// прогресс-баре при 100% всегда показывает красный край — а во всём
// остальном интерфейсе (Здоровье/Доверие в топбаре) зелёный=хорошо/высоко,
// красный=плохо/низко. Прогресс к завершению — это всегда "хорошо, когда
// растёт", а не риск, поэтому красный на 100% читается как "что-то не так",
// хотя всё сделано (реальная путаница на скриншоте пользователя).
const PROGRESS_GRADIENT = "linear-gradient(90deg, #6fb87a, #a0e0ab)"

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
    // clamp() вместо фиксированных 28px — раньше отступы не менялись НИ ПРИ
    // каком viewport (ни одного isMobile/matchMedia не было ни в одной из
    // крупных вкладок, production-readiness worklist п.22); на узком экране
    // 28px с каждой стороны съедали заметную долю и без того тесной ширины.
    // Один общий фикс здесь закрывает все вкладки, использующие ViewBody,
    // не только 4 названных в аудите — правка каждой по отдельности была бы
    // дублированием одного и того же решения.
    <div ref={ref} style={{ flex: 1, overflowY: "auto",
      padding: "clamp(10px, 3vw, 18px) clamp(12px, 4vw, 28px) clamp(14px, 4vw, 28px)", ...style }}>
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
      {/* Живой аудит показал: одно затухание слишком тонкое, чтобы его заметить
          (пропущено при собственном тестировании) — явный шеврон поверх делает
          «тут ещё есть табы» однозначным, не полагаясь на тонкий градиент. */}
      {canScrollLeft && (
        <div style={{
          position: "absolute", top: 0, left: 0, bottom: 1, width: 28, pointerEvents: "none", zIndex: 4,
          background: "linear-gradient(to left, transparent, var(--surface-card))",
          display: "flex", alignItems: "center",
        }}>
          <span style={{ fontSize: 11, color: "var(--muted)" }}>‹</span>
        </div>
      )}
      {canScrollRight && (
        <div style={{
          position: "absolute", top: 0, right: 0, bottom: 1, width: 32, pointerEvents: "none", zIndex: 4,
          background: "linear-gradient(to right, transparent, var(--surface-card))",
          display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 4,
        }}>
          <span style={{ fontSize: 11, color: "var(--muted)" }}>›</span>
        </div>
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
  // Раньше клик обрабатывался на <div> — карточка была активируема только
  // мышью, без Tab/Enter/Space и видимого фокус-кольца (найдено при живом
  // дизайн-аудите; Card используется как кликабельная почти везде — MCP-
  // серверы, Приложения, инициативы). role="button" + tabIndex + onKeyDown
  // делают её доступной централизованно, в одном месте на всё приложение.
  return (
    <div className="card" onClick={onClick}
      role={hover ? "button" : undefined} tabIndex={hover ? 0 : undefined}
      onKeyDown={hover ? e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick!() } } : undefined}
      style={{ borderRadius: "var(--radius-md)", padding: 16, cursor: hover ? "pointer" : "default",
        transition: "border-color 0.18s, transform 0.18s, box-shadow 0.18s",
        outlineOffset: 2, ...style }}
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

/* ── Button / TextInput / TextArea — единый словарь поверх .btn/.input из
   design.css (аудит дизайн-системы: платформа уже объявляла CSS-классы
   .btn-primary/.btn-secondary/.btn-ghost/.btn-danger/.btn-toggle, но ни один
   React-компонент их не использовал — каждый файл заново писал inline-стиль
   кнопки/поля, отсюда мелкий разъезд padding/radius/цвета между вкладками.
   Новый код — через эти компоненты, не через свой style={{...}}. */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "toggle"
export type ButtonSize = "md" | "sm" | "icon" | "icon-sm" | "pill"

export function Button({ variant = "secondary", size = "md", active, className = "", style, children, ...rest }:
  { variant?: ButtonVariant; size?: ButtonSize; active?: boolean; className?: string; style?: CSSProperties; children?: ReactNode }
  & ButtonHTMLAttributes<HTMLButtonElement>) {
  const sizeClass = size === "pill" ? "btn-md btn-pill" : `btn-${size}`
  const cls = `btn btn-${variant} ${sizeClass}${active ? " is-on" : ""} ${className}`.trim()
  return <button className={cls} style={style} {...rest}>{children}</button>
}

type InputExtra = { mono?: boolean; compact?: boolean; className?: string }

export function TextInput({ mono, compact, className = "", style, ...rest }:
  InputExtra & { style?: CSSProperties } & InputHTMLAttributes<HTMLInputElement>) {
  const cls = `input${compact ? " input-sm" : ""}${mono ? " input-mono" : ""} ${className}`.trim()
  return <input className={cls} style={style} {...rest} />
}

export function TextArea({ mono, compact, className = "", style, ...rest }:
  InputExtra & { style?: CSSProperties } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const cls = `input${compact ? " input-sm" : ""}${mono ? " input-mono" : ""} ${className}`.trim()
  return <textarea className={cls} style={style} {...rest} />
}

export function MercuryBar({ percent, style }: { percent: number; style?: CSSProperties }) {
  return (
    <div style={{ height: 3, borderRadius: 99, background: "var(--hairline-strong)", overflow: "hidden", ...style }}>
      <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, percent))}%`, background: PROGRESS_GRADIENT,
        borderRadius: 99, transition: "width 0.6s var(--ease-out)" }} />
    </div>
  )
}

export const STATUS_COLOR: Record<string, string> = {
  active: "#a0e0ab", thinking: "#ffac2e", done: "var(--text-dim)", idle: "var(--whisper)",
}

/* ── Disclosure: свёрнутая по умолчанию секция «заголовок + краткая сводка →
   клик разворачивает подробности». Раньше в проекте не было ни одного
   переиспользуемого примитива для этого — каждый экран («Проект», «Компания»,
   «Сводка») показывал ВСЁ содержимое плоско одновременно (этапы, граф задач,
   команда, объективы — 6+ секций на одном экране без иерархии), поэтому
   первый экран тонул в деталях вместо того, чтобы показать главное и дать
   углубиться по запросу. summary — то, что видно всегда (даже свёрнуто). */
export function Disclosure({ summary, children, defaultOpen = false, count }:
  { summary: ReactNode; children: ReactNode; defaultOpen?: boolean; count?: number }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div>
      <button onClick={() => setOpen(o => !o)}
        style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left",
          background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit",
          fontFamily: "var(--font-sans)" }}>
        <span style={{ fontSize: 10, color: "var(--faint)", transition: "transform 0.15s",
          transform: open ? "rotate(90deg)" : "rotate(0deg)", flexShrink: 0 }}>▶</span>
        <span style={{ flex: 1, minWidth: 0 }}>{summary}</span>
        {count != null && (
          <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)", flexShrink: 0 }}>{count}</span>
        )}
      </button>
      {open && <div style={{ marginTop: 10, paddingLeft: 18 }}>{children}</div>}
    </div>
  )
}

/** Список с "показать ещё N" вместо рендера всех элементов сразу — раньше
 * gap-карточки/цели/пилюли ролей рендерились ЦЕЛИКОМ независимо от количества. */
export function ShowMore<T>({ items, initial, render, moreLabel }:
  { items: T[]; initial: number; render: (item: T, i: number) => ReactNode; moreLabel?: (n: number) => string }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? items : items.slice(0, initial)
  const hidden = items.length - initial
  return (
    <>
      {visible.map(render)}
      {!expanded && hidden > 0 && (
        <button onClick={() => setExpanded(true)}
          style={{ fontSize: 11, color: "var(--mercury-a)", background: "none", border: "none",
            cursor: "pointer", padding: "4px 0", textAlign: "left", fontFamily: "var(--font-sans)" }}>
          {moreLabel ? moreLabel(hidden) : `Показать ещё ${hidden}`}
        </button>
      )}
    </>
  )
}
