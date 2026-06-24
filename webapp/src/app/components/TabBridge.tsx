import { useEffect, useRef, useState, type RefObject } from "react"
import { motion, useMotionValue, useSpring, useVelocity, useTransform } from "motion/react"

/**
 * Liquid-glass мост-метабол (Apple visionOS / Telegram metaball).
 * Активная вкладка НЕ имеет плашки — индикатор это ФИЗИЧЕСКАЯ связь: из тела сайдбара
 * вытекает капля и сливается с панелью одной непрерывной геометрией (две эллипс-капли +
 * вогнутая «шейка» поверхностного натяжения). Рисуется ЗА контентом, цвет = поверхность.
 * Физика: пружина (растяжение по скорости → перетекание → упругое оседание ~600мс).
 */
const THETA = 0.95          // угол схода «шейки» с капли
const R = 18                // базовый радиус капли

function buildNeck(ax: number, bx: number, cy: number, stretch: number): string {
  const rx = R, ry = R + stretch
  const ct = Math.cos(THETA), st = Math.sin(THETA)
  const aTopX = ax + rx * ct
  const bTopX = bx - rx * ct
  const topY = cy - ry * st
  const botY = cy + ry * st
  const k = (bTopX - aTopX) * 0.42
  const pinch = ry * st * 0.5          // < высоты схода → вогнутая шейка (натяжение)
  return (
    `M ${aTopX} ${topY} ` +
    `C ${aTopX + k} ${cy - pinch}, ${bTopX - k} ${cy - pinch}, ${bTopX} ${topY} ` +
    `L ${bTopX} ${botY} ` +
    `C ${bTopX - k} ${cy + pinch}, ${aTopX + k} ${cy + pinch}, ${aTopX} ${botY} Z`
  )
}

export function TabBridge({ active, enabled, containerRef }: {
  active: string; enabled: boolean; containerRef: RefObject<HTMLElement | null>
}) {
  const [geo, setGeo] = useState<{ ax: number; bx: number } | null>(null)
  const yMV = useMotionValue(0)
  // упругая пружина — лёгкий перелёт и оседание (~600мс)
  const y = useSpring(yMV, { stiffness: 170, damping: 16, mass: 1 })
  const vel = useVelocity(y)
  // растяжение капли по вертикали пропорционально скорости (жидкость тянется при движении)
  const stretchRaw = useTransform(vel, v => Math.min(18, Math.abs(v) * 0.015))
  const stretch = useSpring(stretchRaw, { stiffness: 320, damping: 26 })
  const first = useRef(true)

  const ax = geo?.ax ?? 0
  const bx = geo?.bx ?? 0
  // мотион-значения геометрии (пересобираются при смене раскладки/вкладки)
  const ry = useTransform(stretch, s => R + s)
  const neckD = useTransform([y, stretch], ([yy, s]) => buildNeck(ax, bx, yy as number, s as number))
  const hiCy = useTransform([y, stretch], ([yy, s]) => (yy as number) - (R + (s as number)) * 0.42)

  useEffect(() => {
    if (!enabled) { setGeo(null); first.current = true; return }
    let raf = 0
    const measure = () => {
      const root = containerRef.current
      const btn = document.querySelector('nav [data-bridge-active="true"]') as HTMLElement | null
      const panel = document.getElementById("main-panel")
      if (!root || !btn || !panel) { setGeo(null); return }
      const r = root.getBoundingClientRect()
      const b = btn.getBoundingClientRect()
      const p = panel.getBoundingClientRect()
      // капли заходят ВНУТРЬ тел сайдбара и панели → «вытекают» из них
      setGeo({ ax: b.right - r.left - 7, bx: p.left - r.left + 7 })
      const cy = b.top - r.top + b.height / 2
      if (first.current) { yMV.jump(cy); y.jump(cy); first.current = false }
      else yMV.set(cy)
    }
    const run = () => { raf = requestAnimationFrame(measure) }
    run()
    const t = setTimeout(measure, 70)
    const panel = document.getElementById("main-panel")
    const ro = new ResizeObserver(run)
    if (panel) ro.observe(panel)
    if (containerRef.current) ro.observe(containerRef.current)
    window.addEventListener("resize", run)
    return () => { cancelAnimationFrame(raf); clearTimeout(t); ro.disconnect(); window.removeEventListener("resize", run) }
  }, [active, enabled]) // eslint-disable-line

  if (!enabled || !geo) return null

  return (
    <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%",
      pointerEvents: "none", zIndex: 0, overflow: "visible" }} aria-hidden>
      <defs>
        {/* очень тонкий стеклянный блик сверху — БЕЗ теней (тени мешают) */}
        <radialGradient id="bridge-spec" cx="0.5" cy="0.25" r="0.7">
          <stop offset="0%" stopColor="var(--inset-hi)" stopOpacity="0.6" />
          <stop offset="100%" stopColor="var(--inset-hi)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* непрерывное стеклянное тело: две капли + вогнутая шейка. ТОЧНО цвет панелей, без теней/швов */}
      <g fill="var(--surface-card)">
        <motion.ellipse cx={ax} cy={y} rx={R} ry={ry} />
        <motion.ellipse cx={bx} cy={y} rx={R} ry={ry} />
        <motion.path d={neckD} />
      </g>
      {/* лёгкий стеклянный блик сверху (только свет, не тень) */}
      <motion.ellipse cx={(ax + bx) / 2} cy={hiCy} rx={(bx - ax) / 2 + R * 0.5} ry={4}
        fill="url(#bridge-spec)" opacity={0.45} />
    </svg>
  )
}
