import { useEffect, useMemo, useRef, useState } from "react"
import { motion, useMotionValue } from "motion/react"
import { api } from "../../data/api"
import { ViewBody, Card, Empty, SectionLabel } from "./ui"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"
const GAP = 10
const GRID = 10          // шаг сетки — позиция/размер всегда кратны ей, не "куда угодно"
const MIN_W = 180
const MIN_H = 110

type Rect = { x: number; y: number; w: number; h: number }

function snap(v: number): number {
  return Math.round(v / GRID) * GRID
}

function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

function defaultSize(kind: string): { w: number; h: number } {
  return kind === "chart" ? { w: 380, h: 240 } : { w: 220, h: 130 }
}

// Раскладка по умолчанию для виджетов без сохранённой позиции (первый визит/
// новый виджет) — простая упаковка полками слева направо, сверху вниз, уже по
// сетке (кратно GRID), поэтому никогда не конфликтует с ручной расстановкой.
// Сохранённые вручную позиции (widget.layout) НЕ трогает.
function packDefaults(widgets: any[], containerWidth: number): Record<string, Rect> {
  const out: Record<string, Rect> = {}
  let x = 0, y = 0, rowH = 0
  for (const w of widgets) {
    if (w.layout) continue
    const { w: dw, h: dh } = defaultSize(w.kind)
    if (x > 0 && x + dw > containerWidth) { x = 0; y += rowH + GAP; rowH = 0 }
    out[w.id] = { x: snap(x), y: snap(y), w: dw, h: dh }
    x += dw + GAP
    rowH = Math.max(rowH, dh)
  }
  return out
}

// Вкладка "Бизнес" (в отличие от "Офис" — не ход работы агентов, а цифры о
// самом бизнесе клиента). Без интеграций CRM/ERP реальных источников мало —
// см. src/office/dashboard.py: показываем только то, что РЕАЛЬНО измеримо
// (никаких KPI-заглушек), а недостающее клиент может попросить словами внизу.
//
// Свободный холст: каждый виджет — свои x/y/ширина/высота (не список с одним
// порядком), перетаскивание и ресайз в любом направлении, "как иконки на
// рабочем столе".
export function BusinessDashboard() {
  const [widgets, setWidgets] = useState<any[]>([])
  const [loaded, setLoaded] = useState(false)
  const [layout, setLayout] = useState<Record<string, Rect>>({})
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(900)

  const load = () => api.dashboard().then(d => { setWidgets(d.widgets || []); setLoaded(true) })
  useEffect(() => { load() }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => setContainerWidth(entries[0].contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Собранная раскладка: сохранённая позиция виджета (с сервера) побеждает,
  // иначе — вычисленная упаковка по умолчанию.
  const resolvedLayout = useMemo(() => {
    const defaults = packDefaults(widgets, Math.max(containerWidth, MIN_W))
    const merged: Record<string, Rect> = {}
    for (const w of widgets) {
      merged[w.id] = layout[w.id] || w.layout || defaults[w.id] || { x: 0, y: 0, ...defaultSize(w.kind) }
    }
    return merged
  }, [widgets, layout, containerWidth])

  const canvasHeight = useMemo(() => {
    let maxY = 0
    for (const r of Object.values(resolvedLayout)) maxY = Math.max(maxY, r.y + r.h)
    return maxY + GAP
  }, [resolvedLayout])

  function persistLayout(id: string, rect: Rect) {
    setLayout(prev => ({ ...prev, [id]: rect }))
    api.dashboardSetLayout(id, rect.x, rect.y, rect.w, rect.h)
  }

  async function onRemove(id: string) {
    setWidgets(prev => prev.filter(w => w.id !== id))
    await api.dashboardRemove(id)
  }

  if (!loaded) return <ViewBody><Empty icon="📊" text="Загрузка…" /></ViewBody>

  return (
    <ViewBody>
      <SectionLabel>Показатели бизнеса</SectionLabel>
      {widgets.length === 0 ? (
        <Empty icon="📊" text="Пока нет ни одной измеримой цифры"
          hint="Появятся сами, как только придут первые заявки или начнётся расход на ИИ — либо попроси конкретный график ниже" />
      ) : (
        <div ref={containerRef} style={{ position: "relative", width: "100%", height: canvasHeight, marginBottom: 24 }}>
          {widgets.map(w => (
            <FreeWidget key={w.id} widget={w} rect={resolvedLayout[w.id]}
              others={widgets.filter(o => o.id !== w.id).map(o => resolvedLayout[o.id])}
              onSettle={rect => persistLayout(w.id, rect)} onRemove={onRemove} />
          ))}
        </div>
      )}

      <RequestBox onAdded={load} />
    </ViewBody>
  )
}

// Один виджет на свободном холсте: перетаскивание в любом направлении
// (framer-motion drag) + ручка ресайза в углу (обычные pointer-события —
// resize не входит в API framer-motion drag). Позиция/размер всегда кратны
// GRID, и итог отклоняется (откатывается назад), если пересекается с другим
// виджетом — сетка не даёт положить "куда угодно" и наложить друг на друга.
function FreeWidget({ widget: w, rect, others, onSettle, onRemove }: {
  widget: any; rect: Rect; others: Rect[]; onSettle: (r: Rect) => void; onRemove: (id: string) => void
}) {
  // x/y — motion values (не React state): drag сам их двигает в реальном
  // времени, а .set() снаружи мгновенно "телепортирует" обратно при откате —
  // в отличие от прежнего animate={{x,y}}, это не зависит от того, считает ли
  // framer текущее значение уже равным целевому.
  const x = useMotionValue(rect.x)
  const y = useMotionValue(rect.y)
  const [size, setSize] = useState({ w: rect.w, h: rect.h })
  // Пока идёт ресайз, drag на виджете ВЫКЛЮЧЕН (передаётся как проп в
  // motion.div, а не просто stopPropagation внутри ручки) — иначе виджет
  // ресайзится и одновременно едет за курсором вслед за перемещением мыши.
  const [isResizing, setIsResizing] = useState(false)

  useEffect(() => {
    if (isResizing) return
    x.set(rect.x); y.set(rect.y)
    setSize({ w: rect.w, h: rect.h })
  }, [rect.x, rect.y, rect.w, rect.h]) // eslint-disable-line

  function overlapsOthers(cand: Rect): boolean {
    return others.some(o => o && rectsOverlap(cand, o))
  }

  function onDragEnd() {
    const cand: Rect = { x: Math.max(0, snap(x.get())), y: Math.max(0, snap(y.get())), w: size.w, h: size.h }
    if (overlapsOthers(cand)) {
      x.set(rect.x); y.set(rect.y)  // место занято — откатываем на прежнюю позицию
      return
    }
    x.set(cand.x); y.set(cand.y)
    onSettle(cand)
  }

  function startResize(e: React.PointerEvent) {
    e.stopPropagation()
    e.preventDefault()
    setIsResizing(true)
    const startX = e.clientX, startY = e.clientY
    const startW = size.w, startH = size.h
    const target = e.currentTarget
    try { target.setPointerCapture(e.pointerId) } catch { /* некоторые браузеры/устройства не поддерживают — не критично, слушаем на window */ }

    function candidateSize(ev: PointerEvent) {
      return {
        w: Math.max(MIN_W, snap(startW + (ev.clientX - startX))),
        h: Math.max(MIN_H, snap(startH + (ev.clientY - startY))),
      }
    }
    function onMove(ev: PointerEvent) { setSize(candidateSize(ev)) }
    function onUp(ev: PointerEvent) {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
      setIsResizing(false)
      const { w: cw, h: ch } = candidateSize(ev)
      const cand: Rect = { x: x.get(), y: y.get(), w: cw, h: ch }
      if (overlapsOthers(cand)) {
        setSize({ w: startW, h: startH })  // новый размер налез на соседа — откат
        return
      }
      setSize({ w: cw, h: ch })
      onSettle(cand)
    }
    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
  }

  return (
    <motion.div
      drag={!isResizing}
      dragMomentum={false}
      dragElastic={0}
      onDragEnd={onDragEnd}
      whileDrag={{ zIndex: 20, boxShadow: "0 14px 36px rgba(0,0,0,0.4)", cursor: "grabbing" }}
      style={{ position: "absolute", top: 0, left: 0, width: size.w, height: size.h, x, y, cursor: "grab" }}>
      <div style={{ position: "relative", width: "100%", height: "100%" }}>
        {w.kind === "chart" ? <ChartWidget widget={w} onRemove={onRemove} /> : <MetricWidget widget={w} />}
        {/* Ручка ресайза — любой размер (кратный сетке), не только предустановленный */}
        <div onPointerDown={startResize} title="Изменить размер"
          style={{
            position: "absolute", right: 2, bottom: 2, width: 16, height: 16, cursor: "nwse-resize",
            background: "linear-gradient(135deg, transparent 50%, var(--hairline-strong) 50%)",
            borderRadius: "0 0 var(--radius-md) 0",
          }} />
      </div>
    </motion.div>
  )
}

function MetricWidget({ widget: w }: { widget: any }) {
  return (
    <Card style={{ height: "100%", userSelect: "none" }}>
      <div className="display" style={{ fontSize: 26, color: "var(--text)", lineHeight: 1 }}>
        {typeof w.value === "number" && w.unit === "$" ? `$${w.value}` : `${w.value} ${w.unit === "деньги" ? "" : w.unit}`.trim()}
      </div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 7 }}>{w.title}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8 }}>
        <span style={{
          fontSize: 9.5, padding: "1px 7px", borderRadius: "var(--radius-pill)",
          border: "1px solid var(--hairline)", color: w.source === "факт" ? "var(--success)" : "var(--mercury-a)",
        }}>{w.source}</span>
        {w.note && <span style={{ fontSize: 10, color: "var(--faint)" }}>{w.note}</span>}
      </div>
    </Card>
  )
}

function ChartWidget({ widget: w, onRemove }: { widget: any; onRemove: (id: string) => void }) {
  const series: { label: string; value: number }[] = w.series || []
  return (
    <Card style={{ height: "100%", userSelect: "none", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, marginBottom: 10 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}>{w.title}</div>
        <button onClick={() => onRemove(w.id)} title="Убрать график" onPointerDown={e => e.stopPropagation()}
          style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer", fontSize: 13, lineHeight: 1, flexShrink: 0 }}>×</button>
      </div>
      {series.length === 0 ? (
        <div style={{ fontSize: 11.5, color: "var(--faint)", padding: "16px 0", textAlign: "center", flex: 1 }}>Пока нет данных за выбранный период</div>
      ) : (
        <div style={{ flex: 1, minHeight: 0 }}><MiniChart series={series} type={w.chart_type === "bar" ? "bar" : "line"} /></div>
      )}
      <div style={{ fontSize: 10, color: "var(--faint)", marginTop: 8, flexShrink: 0 }}>
        {series.length} {series.length === 1 ? "точка" : "точек"} · {w.group_by === "month" ? "по месяцам" : w.group_by === "week" ? "по неделям" : "по дням"}
      </div>
    </Card>
  )
}

// Лёгкий инлайн-график без сторонних зависимостей (line/bar), в духе TaskGraph
// из ProjectView — согласуется с остальным продуктом, не тянет charting-либу
// ради 1-2 линий на дашборде раннего этапа. viewBox фиксирован, но растягивается
// на весь размер виджета (widget теперь любого размера — см. FreeWidget).
function MiniChart({ series, type }: { series: { label: string; value: number }[]; type: "line" | "bar" }) {
  const w = 400, h = 120, padX = 8, padY = 10
  const values = series.map(s => s.value)
  const max = Math.max(1, ...values)
  const min = Math.min(0, ...values)
  const range = max - min || 1
  const stepX = series.length > 1 ? (w - padX * 2) / (series.length - 1) : 0
  const yFor = (v: number) => h - padY - ((v - min) / range) * (h - padY * 2)
  const xFor = (i: number) => padX + i * stepX

  const points = series.map((s, i) => ({ x: xFor(i), y: yFor(s.value) }))
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ")
  const barWidth = series.length > 0 ? Math.max(4, (w - padX * 2) / series.length - 4) : 0

  // Показываем не больше 6 подписей по оси X, иначе они налезают друг на друга.
  const labelEvery = Math.max(1, Math.ceil(series.length / 6))

  return (
    <svg viewBox={`0 0 ${w} ${h + 16}`} preserveAspectRatio="none" style={{ width: "100%", height: "100%", display: "block" }}>
      <defs>
        <linearGradient id={`biz-grad-${type}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#a0e0ab" />
          <stop offset="50%" stopColor="#ffac2e" />
          <stop offset="100%" stopColor="#a52d25" />
        </linearGradient>
      </defs>
      {type === "bar" ? (
        points.map((p, i) => (
          <rect key={i} x={p.x - barWidth / 2} y={p.y} width={barWidth} height={Math.max(1, h - padY - p.y)}
            rx={2} fill={`url(#biz-grad-${type})`} opacity={0.85} />
        ))
      ) : (
        <>
          <path d={`${linePath} L ${points[points.length - 1]?.x ?? 0} ${h - padY} L ${points[0]?.x ?? 0} ${h - padY} Z`}
            fill={`url(#biz-grad-${type})`} opacity={0.12} />
          <path d={linePath} fill="none" stroke={`url(#biz-grad-${type})`} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {points.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={2.2} fill="#ffac2e" />)}
        </>
      )}
      {series.map((s, i) => (
        i % labelEvery === 0 && (
          <text key={i} x={xFor(i)} y={h + 12} fontSize={8.5} textAnchor="middle" fill="var(--faint)">{s.label.slice(-5)}</text>
        )
      ))}
    </svg>
  )
}

function RequestBox({ onAdded }: { onAdded: () => void }) {
  const [text, setText] = useState("")
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(null)

  async function submit() {
    if (!text.trim() || busy) return
    setBusy(true)
    setFeedback(null)
    const r = await api.dashboardRequest(text.trim())
    setBusy(false)
    if (r.ok) {
      setText("")
      setFeedback({ ok: true, text: "Добавлено на дашборд" })
      onAdded()
    } else {
      setFeedback({
        ok: false,
        text: r.initiative_id
          ? `${r.reason} Добавил в инициативы (со скриптом и автообновлением) — можно принять на вкладке «Работа».`
          : r.reason || "Не получилось — попробуй переформулировать.",
      })
    }
  }

  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <SectionLabel style={{ marginBottom: 0 }}>Попросить ИИ добавить график или метрику</SectionLabel>
      <div style={{ display: "flex", gap: 8 }}>
        <input value={text} onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === "Enter" && submit()}
          placeholder="Например: построй график выручки по месяцам за 12 месяцев"
          style={{
            flex: 1, padding: "9px 14px", borderRadius: "var(--radius-md)",
            border: "1px solid var(--hairline-strong)", background: "var(--surface)",
            color: "var(--text)", fontSize: 12.5, fontFamily: "var(--font-sans)",
          }} />
        <button onClick={submit} disabled={busy || !text.trim()}
          style={{
            padding: "9px 18px", borderRadius: "var(--radius-pill)", fontSize: 12.5, fontWeight: 600,
            border: "none", background: MERCURY, color: "#0a0a0a", cursor: "pointer",
            opacity: busy || !text.trim() ? 0.6 : 1, flexShrink: 0,
          }}>{busy ? "Думаю…" : "Добавить"}</button>
      </div>
      {feedback && (
        <div style={{ fontSize: 11.5, color: feedback.ok ? "var(--success)" : "var(--mercury-a)", lineHeight: 1.5 }}>
          {feedback.ok ? "✅ " : "ℹ️ "}{feedback.text}
        </div>
      )}
    </Card>
  )
}
