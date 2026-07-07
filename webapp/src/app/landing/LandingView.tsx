import { motion, useMotionValue, useSpring, useScroll, useTransform, useReducedMotion } from "motion/react"
import { useRef } from "react"
import type { ReactNode } from "react"
import { ROLE_NAMES, ROLE_DESC } from "../../data/roles"

// Скилл vite_react_site: палитра ДОСЛОВНО из уже установленного бренда платформы
// (design.css — Mercury Flow, единственный цветной акцент поверх ахроматики) —
// не изобретаем новую, это и есть «Стиль: …» этого продукта.
const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface LandingProps {
  onLogin: () => void
  onDemo?: () => void
}

const container = { hidden: {}, show: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } } }
const item = {
  hidden: { opacity: 0, y: 20 },
  show:   { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 90, damping: 18 } },
}

export function LandingView({ onLogin, onDemo }: LandingProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const reduceMotion = useReducedMotion()
  // Параллакс амбиента (скилл, приём 2): фоновые пятна двигаются МЕДЛЕННЕЕ
  // контента при скролле — глубина без единого лишнего элемента в DOM.
  const { scrollYProgress } = useScroll({ container: scrollRef })
  const blobY1 = useTransform(scrollYProgress, [0, 1], [0, reduceMotion ? 0 : -120])
  const blobY2 = useTransform(scrollYProgress, [0, 1], [0, reduceMotion ? 0 : 90])

  return (
    <div ref={scrollRef} style={{ position: "absolute", inset: 0, overflowY: "auto", overflowX: "hidden", background: "var(--bg)", color: "var(--text)" }}>
      {/* амбиент — параллакс по скроллу */}
      <motion.div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, y: blobY1,
        background:
          "radial-gradient(45vw 45vw at 15% 0%, rgba(160,224,171,0.10), transparent 60%)," +
          "radial-gradient(50vw 50vw at 40% 100%, rgba(165,45,37,0.06), transparent 60%)" }} />
      <motion.div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, y: blobY2,
        background: "radial-gradient(55vw 55vw at 90% 25%, rgba(255,172,46,0.09), transparent 60%)" }} />

      <div style={{ position: "relative", zIndex: 1, maxWidth: 1080, margin: "0 auto", padding: "0 24px" }}>
        <Nav onLogin={onLogin} />
        <Hero onLogin={onLogin} onDemo={onDemo} />
        <InsightStrip />
        <HowItWorks />
        <TeamHierarchy />
        <Capabilities />
        <FinalCTA onLogin={onLogin} />
        <Footer />
      </div>
    </div>
  )
}

// ── навбар ────────────────────────────────────────────────────────────────────
function Nav({ onLogin }: { onLogin: () => void }) {
  return (
    <motion.nav initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 72 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: MERCURY, boxShadow: "0 0 12px rgba(255,172,46,0.6)" }} />
        <span style={{ fontSize: 15, letterSpacing: "0.5px" }}>AI <em style={{ fontFamily: "var(--font-display)", color: "var(--muted)" }}>office</em></span>
      </div>
      <button onClick={onLogin}
        style={{ padding: "8px 18px", borderRadius: "var(--radius-pill)", border: "1px solid var(--hairline-strong)",
          background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13, fontWeight: 500 }}
        onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--mercury-a)")}
        onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--hairline-strong)")}>
        Войти
      </button>
    </motion.nav>
  )
}

// ── HERO: кинетический заголовок по словам + магнитный CTA + рой агентов ──────
function Hero({ onLogin, onDemo }: { onLogin: () => void; onDemo?: () => void }) {
  const words = ["Ваш", "бизнес", "растит", "целый", "офис", "из", "AI"]
  return (
    <motion.section variants={container} initial="hidden" animate="show"
      style={{ paddingTop: "11vh", paddingBottom: "9vh", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center" }}>
      <motion.div variants={item}
        style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "5px 14px", borderRadius: "var(--radius-pill)",
          border: "1px solid var(--hairline)", background: "var(--surface-soft)", fontSize: 11.5, color: "var(--text-dim)", marginBottom: 28 }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#a0e0ab" }} />
        Автономная команда AI-агентов · SaaS
      </motion.div>

      <h1 className="display" aria-label="Ваш бизнес растит целый офис из AI"
        style={{ fontSize: "clamp(40px, 7vw, 88px)", lineHeight: 1.02, fontWeight: 300, letterSpacing: "-0.02em", margin: 0, maxWidth: 900 }}>
        {words.map((w, i) => (
          <motion.span key={i} variants={item} style={{ display: "inline-block",
            ...(w === "целый" || w === "офис" ? { fontStyle: "italic", background: MERCURY, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" } : {}) }}>
            {w}{i < words.length - 1 ? " " : ""}
          </motion.span>
        ))}
      </h1>

      <motion.p variants={item}
        style={{ fontSize: "clamp(14px, 1.6vw, 17px)", color: "var(--muted)", lineHeight: 1.6, maxWidth: 560, marginTop: 24 }}>
        Директор, стратег, разработчики и маркетологи на базе AI сами исследуют рынок,
        строят стратегию, пишут код и приводят клиентов. Вы — ставите цель.
      </motion.p>

      <motion.div variants={item} style={{ display: "flex", gap: 12, marginTop: 36, flexWrap: "wrap", justifyContent: "center" }}>
        <CTA primary magnetic onClick={onLogin}>Запустить офис →</CTA>
        {onDemo && <CTA onClick={onDemo}>Посмотреть демо</CTA>}
      </motion.div>

      <motion.div variants={item} style={{ marginTop: 64, width: "100%" }}>
        <AgentSwarm />
      </motion.div>
    </motion.section>
  )
}

// Рой агентов вокруг центра — orbit-приём сохранён (уже был сигнатурным для
// продукта), но добавлена лёгкая mousemove-параллакс-реакция всей сцены —
// скилл, приём 2/3: элемент реагирует на действие пользователя, не просто крутится.
function AgentSwarm() {
  const reduceMotion = useReducedMotion()
  const mx = useMotionValue(0)
  const my = useMotionValue(0)
  const rx = useSpring(mx, { stiffness: 60, damping: 20 })
  const ry = useSpring(my, { stiffness: 60, damping: 20 })

  function onMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (reduceMotion) return
    const r = e.currentTarget.getBoundingClientRect()
    mx.set(((e.clientY - (r.top + r.height / 2)) / r.height) * -10)
    my.set(((e.clientX - (r.left + r.width / 2)) / r.width) * 10)
  }
  function onMouseLeave() { mx.set(0); my.set(0) }

  const ring = (size: number, dur: number, dir: 1 | -1, roles: string[]) => (
    <motion.div
      animate={reduceMotion ? {} : { rotate: dir * 360 }} transition={{ repeat: Infinity, duration: dur, ease: "linear" }}
      style={{ position: "absolute", top: "50%", left: "50%", width: size, height: size, marginTop: -size / 2, marginLeft: -size / 2,
        borderRadius: "50%", border: "1px solid var(--hairline)" }}>
      {roles.map((role, i) => {
        const a = (i / roles.length) * Math.PI * 2
        return (
          <motion.div key={role}
            animate={reduceMotion ? {} : { rotate: dir * -360 }} transition={{ repeat: Infinity, duration: dur, ease: "linear" }}
            style={{ position: "absolute", top: `calc(50% + ${Math.sin(a) * 50}% - 15px)`, left: `calc(50% + ${Math.cos(a) * 50}% - 15px)`,
              width: 30, height: 30, borderRadius: "50%", background: "var(--surface-card)", border: "1px solid var(--hairline-strong)",
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 600, color: "var(--text-dim)" }}
            title={ROLE_NAMES[role] || role}>
            {(ROLE_NAMES[role] || role).slice(0, 2)}
          </motion.div>
        )
      })}
    </motion.div>
  )

  return (
    <div onMouseMove={onMouseMove} onMouseLeave={onMouseLeave} style={{ position: "relative", height: 300, perspective: 1000 }}>
      <motion.div style={{ position: "absolute", inset: 0, rotateX: rx, rotateY: ry, transformStyle: "preserve-3d" }}>
        {ring(300, 50, 1, ["cto", "cmo", "sales_lead", "hr"])}
        {ring(210, 36, -1, ["developer", "marketer", "salesman", "researcher"])}
        {ring(130, 26, 1, ["architect", "analyst"])}
        <motion.div
          animate={reduceMotion ? {} : { scale: [1, 1.08, 1] }} transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
          style={{ position: "absolute", top: "50%", left: "50%", width: 64, height: 64, marginTop: -32, marginLeft: -32,
            borderRadius: "50%", background: MERCURY, boxShadow: "0 0 50px rgba(255,172,46,0.35)",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, color: "#0a0a0a", fontWeight: 700 }}
          title="CEO">
          🧭
        </motion.div>
      </motion.div>
    </div>
  )
}

// ── ИНСАЙТ-СТРАЙП: три строки последовательно проявляются при скролле ─────────
// Scrollytelling (скилл, приём 1) — не карточка, а МЫСЛЬ, разворачивающаяся по
// мере прокрутки: обычный SaaS ждёт настройки, AI Office сам ведёт бизнес.
const INSIGHT_LINES = [
  "Обычный SaaS ждёт, что вы настроите каждый шаг.",
  "AI Office сам исследует рынок, строит стратегию и нанимает нужных агентов.",
  "Вы формулируете цель — офис доводит её до результата.",
]
function InsightStrip() {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.8", "end 0.3"] })
  return (
    <div ref={ref} style={{ marginTop: "16vh", padding: "8vh 0", maxWidth: 760, marginLeft: "auto", marginRight: "auto" }}>
      {INSIGHT_LINES.map((line, i) => (
        <InsightLine key={i} line={line} index={i} total={INSIGHT_LINES.length} scrollYProgress={scrollYProgress} />
      ))}
    </div>
  )
}
// Хук useTransform ОБЯЗАН жить в теле компонента, вызываемого 1 раз на строку —
// не внутри .map() родителя (нарушение Rules of Hooks: число вызовов хука
// должно быть стабильно между рендерами, а не зависеть от длины массива в цикле).
function InsightLine({ line, index, total, scrollYProgress }: { line: string; index: number; total: number; scrollYProgress: ReturnType<typeof useScroll>["scrollYProgress"] }) {
  const start = index / total
  const end = (index + 1) / total
  const opacity = useTransform(scrollYProgress, [start, start + 0.08, end - 0.08, end], [0.15, 1, 1, 0.15])
  const x = useTransform(scrollYProgress, [start, start + 0.08], [index % 2 === 0 ? -16 : 16, 0])
  return (
    <motion.p style={{ opacity, x,
      fontFamily: "var(--font-display)", fontWeight: 300, fontSize: "clamp(22px, 3.4vw, 36px)",
      lineHeight: 1.35, textAlign: "center", color: index === 1 ? "var(--text)" : "var(--text-dim)", margin: "0 0 18px" }}>
      {line}
    </motion.p>
  )
}

// ── КАК ЭТО РАБОТАЕТ: шаги с прогресс-рейкой, привязанной к скроллу ───────────
function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.75", "end 0.6"] })
  const railHeight = useTransform(scrollYProgress, [0, 1], ["0%", "100%"])
  return (
    <Reveal>
      <SectionLabel>Как это работает</SectionLabel>
      <div ref={ref} style={{ position: "relative", display: "flex", flexDirection: "column", gap: 28, marginTop: 8, paddingLeft: 28 }}>
        <div style={{ position: "absolute", left: 5, top: 6, bottom: 6, width: 2, background: "var(--hairline)" }} />
        <motion.div style={{ position: "absolute", left: 5, top: 6, width: 2, height: railHeight, background: MERCURY, transformOrigin: "top" }} />
        {STEPS.map((s, i) => (
          <motion.div key={i} initial={{ opacity: 0, x: -12 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.4 }} style={{ position: "relative" }}>
            <div style={{ position: "absolute", left: -28, top: 2, width: 12, height: 12, borderRadius: "50%",
              background: "var(--surface-card)", border: "2px solid var(--mercury-a)" }} />
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>{s.title}</div>
            <div style={{ fontSize: 13.5, color: "var(--muted)", lineHeight: 1.6, maxWidth: 520 }}>{s.body}</div>
          </motion.div>
        ))}
      </div>
    </Reveal>
  )
}

// ── КОМАНДА: bento-иерархия (CEO → лидеры отделов → воркеры → штаб) ───────────
// Не декоративная сетка — реальная орг-структура платформы (BOS §3.2): один
// CEO управляет ОТДЕЛАМИ, у каждого отдела свой лидер и подчинённые, штаб
// (ресёрчер/стратег/архитектор/HR) подчиняется CEO напрямую.
const DEPARTMENTS: { lead: string; workers: string[] }[] = [
  { lead: "cto", workers: ["developer", "designer"] },
  { lead: "cmo", workers: ["marketer", "analyst"] },
  { lead: "sales_lead", workers: ["salesman"] },
]
const STAFF = ["researcher", "strategist", "architect", "hr"]

function TeamHierarchy() {
  return (
    <Reveal>
      <SectionLabel>Реальная оргструктура, не набор промптов</SectionLabel>
      <div className="bento-grid" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gridAutoRows: 120, gridAutoFlow: "dense", gap: 14, marginTop: 8 }}>
        <RoleCard role="orchestrator" span={{ col: 4, row: 1 }} lead />
        {DEPARTMENTS.map(d => (
          <RoleCard key={d.lead} role={d.lead} span={{ col: 2, row: 1 }} lead />
        ))}
        {DEPARTMENTS.flatMap(d => d.workers).map(r => (
          <RoleCard key={r} role={r} span={{ col: 1, row: 1 }} />
        ))}
        {STAFF.map(r => (
          <RoleCard key={r} role={r} span={{ col: 1, row: 1 }} muted />
        ))}
      </div>
    </Reveal>
  )
}
function RoleCard({ role, span, lead, muted }: { role: string; span: { col: number; row: number }; lead?: boolean; muted?: boolean }) {
  return (
    <motion.div whileHover={{ y: -3 }} transition={{ type: "spring", stiffness: 300, damping: 22 }}
      className="card" style={{ borderRadius: "var(--radius-md)", padding: lead ? "20px 24px" : 16,
        gridColumn: `span ${span.col}`, gridRow: `span ${span.row}`,
        display: "flex", flexDirection: lead ? "row" : "column", alignItems: lead ? "center" : "flex-start",
        justifyContent: lead ? "space-between" : "center", gap: 6,
        opacity: muted ? 0.75 : 1, borderColor: lead ? "var(--hairline-strong)" : undefined }}>
      <div>
        <div style={{ fontSize: lead ? 16 : 13, fontWeight: 600, marginBottom: lead ? 4 : 2 }}>{ROLE_NAMES[role] || role}</div>
        {(lead || span.col > 1) && (
          <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5, maxWidth: lead ? 640 : undefined }}>
            {ROLE_DESC[role] || ""}
          </div>
        )}
      </div>
      {lead && <span className="mono" style={{ fontSize: 10, color: "var(--mercury-a)", letterSpacing: "1px", flexShrink: 0 }}>
        {role === "orchestrator" ? "CEO" : "ЛИДЕР ОТДЕЛА"}
      </span>}
    </motion.div>
  )
}

// ── ВОЗМОЖНОСТИ ─────────────────────────────────────────────────────────────
function Capabilities() {
  return (
    <Reveal>
      <SectionLabel>Реальный результат, не пересказ</SectionLabel>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, marginTop: 8 }}>
        {FEATURES.map((f, i) => (
          <motion.div key={i} whileHover={{ y: -3 }} transition={{ type: "spring", stiffness: 300, damping: 22 }}
            className="card" style={{ borderRadius: "var(--radius-md)", padding: 22 }}>
            <div style={{ fontSize: 22, marginBottom: 12 }}>{f.icon}</div>
            <div style={{ fontSize: 14.5, fontWeight: 600, marginBottom: 6 }}>{f.title}</div>
            <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.55 }}>{f.body}</div>
          </motion.div>
        ))}
      </div>
    </Reveal>
  )
}

// ── ФИНАЛЬНЫЙ CTA ─────────────────────────────────────────────────────────────
function FinalCTA({ onLogin }: { onLogin: () => void }) {
  return (
    <Reveal>
      <div className="card" style={{ borderRadius: "var(--radius-xl)", padding: "56px 32px", textAlign: "center", marginTop: 24, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(60% 100% at 50% 0%, rgba(255,172,46,0.08), transparent 70%)", pointerEvents: "none" }} />
        <div className="display" style={{ fontSize: "clamp(28px, 4vw, 44px)", fontWeight: 300, position: "relative" }}>
          Откройте офис за минуту
        </div>
        <p style={{ fontSize: 14, color: "var(--muted)", marginTop: 14, marginBottom: 28, position: "relative" }}>
          Вход через GitHub или email. Дальше — только ваша цель.
        </p>
        <div style={{ position: "relative", display: "flex", justifyContent: "center" }}>
          <CTA primary onClick={onLogin}>Начать бесплатно →</CTA>
        </div>
      </div>
    </Reveal>
  )
}

function Footer() {
  return (
    <footer style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "40px 0 32px", marginTop: 48,
      borderTop: "1px solid var(--hairline)", fontSize: 12, color: "var(--faint)", flexWrap: "wrap", gap: 12 }}>
      <span>© {new Date().getFullYear()} AI Office</span>
      <span style={{ display: "flex", gap: 18 }}>
        <a href="#" style={{ color: "var(--faint)", textDecoration: "none" }}>Условия</a>
        <a href="#" style={{ color: "var(--faint)", textDecoration: "none" }}>Конфиденциальность</a>
      </span>
    </footer>
  )
}

// ── контент ───────────────────────────────────────────────────────────────────
const STEPS = [
  { title: "Поставьте цель", body: "Опишите бизнес и задачу в брифе. Директор разбивает путь на этапы." },
  { title: "Офис исследует и планирует", body: "Ресёрчер собирает данные рынка, стратег строит план, архитектор проектирует решение." },
  { title: "Отделы работают автономно", body: "CTO/CMO/Head of Sales нанимают нужных специалистов и распределяют задачи между ними." },
  { title: "Вы получаете результат", body: "Лиды, лендинги, реальный код в GitHub и отчёты. Вмешивайтесь и направляйте в любой момент." },
]
const FEATURES = [
  { icon: "🔍", title: "Реальный веб-поиск", body: "Агенты исследуют рынок и конкурентов через живой поиск, а не выдумывают данные." },
  { icon: "💻", title: "Настоящий код", body: "Разработчики пишут код в рабочую папку и пушат в GitHub после вашего одобрения." },
  { icon: "🌐", title: "Лендинги и лиды", body: "Маркетолог публикует сайты, а формы собирают живые заявки в разделе «Лиды»." },
  { icon: "🔌", title: "Интеграции", body: "Telegram, GitHub и другие сервисы подключаются автоматически через способности." },
  { icon: "💸", title: "Прозрачный расход", body: "Свой LLM-ключ, любой OpenAI-совместимый провайдер, учёт токенов в реальном времени." },
  { icon: "🛡️", title: "Приёмка, не пересказ", body: "Задача закрывается только после проверки результата — сборка, форма, реальный критерий." },
]

// ── мелкие части ──────────────────────────────────────────────────────────────
// Магнитная кнопка (скилл vite_react_site, п.4): кнопка слегка «тянется» к
// курсору при наведении — onMouseMove считает смещение курсора относительно
// центра, useMotionValue+useSpring даёт живую инерцию (не дёрганье). Только
// на ГЛАВНОЙ кнопке (magnetic=true) — «1 главная кнопка на экран», не на
// каждый CTA, иначе это уже не сигнатурный приём, а шум.
function CTA({ children, onClick, primary, magnetic }: { children: ReactNode; onClick?: () => void; primary?: boolean; magnetic?: boolean }) {
  const ref = useRef<HTMLButtonElement>(null)
  const reduceMotion = useReducedMotion()
  const mx = useMotionValue(0)
  const my = useMotionValue(0)
  const x = useSpring(mx, { stiffness: 150, damping: 15, mass: 0.1 })
  const y = useSpring(my, { stiffness: 150, damping: 15, mass: 0.1 })

  function onMouseMove(e: React.MouseEvent<HTMLButtonElement>) {
    if (!magnetic || reduceMotion || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    mx.set((e.clientX - (r.left + r.width / 2)) * 0.35)
    my.set((e.clientY - (r.top + r.height / 2)) * 0.35)
  }
  function onMouseLeave() { mx.set(0); my.set(0) }

  return (
    <motion.button ref={ref} onClick={onClick} onMouseMove={onMouseMove} onMouseLeave={onMouseLeave}
      whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
      style={{ x: magnetic ? x : 0, y: magnetic ? y : 0,
        padding: "13px 26px", borderRadius: "var(--radius-pill)", cursor: "pointer", fontSize: 14, fontWeight: 500,
        border: primary ? "none" : "1px solid var(--hairline-strong)",
        background: primary ? MERCURY : "transparent", color: primary ? "#0a0a0a" : "var(--text)",
        boxShadow: primary ? "0 8px 30px rgba(255,172,46,0.25)" : "none", fontFamily: "var(--font-sans)" }}>
      {children}
    </motion.button>
  )
}
function Reveal({ children }: { children: ReactNode }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 28 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      style={{ marginTop: "12vh" }}>
      {children}
    </motion.section>
  )
}
function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="mono" style={{ fontSize: 10.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "2px", marginBottom: 22 }}>{children}</div>
}
