import { motion } from "motion/react"
import type { ReactNode } from "react"
import { ROLE_NAMES, ROLE_DESC } from "../../data/roles"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface LandingProps {
  onLogin: () => void
  onDemo?: () => void
}

// варианты для каскадного появления
const container = { hidden: {}, show: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } } }
const item = {
  hidden: { opacity: 0, y: 20 },
  show:   { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 90, damping: 18 } },
}

export function LandingView({ onLogin, onDemo }: LandingProps) {
  return (
    <div style={{ position: "absolute", inset: 0, overflowY: "auto", overflowX: "hidden", background: "var(--bg)", color: "var(--text)" }}>
      {/* статичный амбиент */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0,
        background:
          "radial-gradient(45vw 45vw at 15% 0%, rgba(160,224,171,0.10), transparent 60%)," +
          "radial-gradient(55vw 55vw at 90% 25%, rgba(255,172,46,0.09), transparent 60%)," +
          "radial-gradient(50vw 50vw at 40% 100%, rgba(165,45,37,0.07), transparent 60%)" }} />

      <div style={{ position: "relative", zIndex: 1, maxWidth: 1080, margin: "0 auto", padding: "0 24px" }}>
        {/* ── навбар ── */}
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

        {/* ── HERO ── */}
        <motion.section variants={container} initial="hidden" animate="show"
          style={{ paddingTop: "11vh", paddingBottom: "9vh", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center" }}>
          <motion.div variants={item}
            style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "5px 14px", borderRadius: "var(--radius-pill)",
              border: "1px solid var(--hairline)", background: "var(--surface-soft)", fontSize: 11.5, color: "var(--text-dim)", marginBottom: 28 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#a0e0ab" }} />
            Автономная команда AI-агентов · SaaS
          </motion.div>

          <motion.h1 variants={item} className="display"
            style={{ fontSize: "clamp(40px, 7vw, 88px)", lineHeight: 1.02, fontWeight: 300, letterSpacing: "-0.02em", margin: 0, maxWidth: 900 }}>
            Ваш бизнес растит{" "}
            <span style={{ fontStyle: "italic", background: MERCURY, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
              целый офис
            </span>{" "}
            из AI
          </motion.h1>

          <motion.p variants={item}
            style={{ fontSize: "clamp(14px, 1.6vw, 17px)", color: "var(--muted)", lineHeight: 1.6, maxWidth: 560, marginTop: 24 }}>
            Директор, стратег, разработчики и маркетологи на базе AI сами исследуют рынок,
            строят стратегию, пишут код и приводят клиентов. Вы — ставите цель.
          </motion.p>

          <motion.div variants={item} style={{ display: "flex", gap: 12, marginTop: 36, flexWrap: "wrap", justifyContent: "center" }}>
            <CTA primary onClick={onLogin}>Запустить офис →</CTA>
            {onDemo && <CTA onClick={onDemo}>Посмотреть демо</CTA>}
          </motion.div>

          {/* визуальный оркестр-превью */}
          <motion.div variants={item} style={{ marginTop: 64, width: "100%" }}>
            <OrbitPreview />
          </motion.div>
        </motion.section>

        {/* ── РОСТЕР АГЕНТОВ (маркиза) ── */}
        <Reveal>
          <SectionLabel>Команда из коробки</SectionLabel>
          <Marquee />
        </Reveal>

        {/* ── КАК РАБОТАЕТ ── */}
        <Reveal>
          <SectionLabel>Как это работает</SectionLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16, marginTop: 8 }}>
            {STEPS.map((s, i) => (
              <Card key={i}>
                <div className="mono" style={{ fontSize: 12, color: "var(--mercury-a)", marginBottom: 12 }}>0{i + 1}</div>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>{s.title}</div>
                <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.6 }}>{s.body}</div>
              </Card>
            ))}
          </div>
        </Reveal>

        {/* ── ВОЗМОЖНОСТИ ── */}
        <Reveal>
          <SectionLabel>Что внутри</SectionLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, marginTop: 8 }}>
            {FEATURES.map((f, i) => (
              <Card key={i}>
                <div style={{ fontSize: 22, marginBottom: 12 }}>{f.icon}</div>
                <div style={{ fontSize: 14.5, fontWeight: 600, marginBottom: 6 }}>{f.title}</div>
                <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.55 }}>{f.body}</div>
              </Card>
            ))}
          </div>
        </Reveal>

        {/* ── ФИНАЛЬНЫЙ CTA ── */}
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

        {/* ── футер ── */}
        <footer style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "40px 0 32px", marginTop: 48,
          borderTop: "1px solid var(--hairline)", fontSize: 12, color: "var(--faint)", flexWrap: "wrap", gap: 12 }}>
          <span>© {new Date().getFullYear()} AI Office</span>
          <span style={{ display: "flex", gap: 18 }}>
            <a href="#" style={{ color: "var(--faint)", textDecoration: "none" }}>Условия</a>
            <a href="#" style={{ color: "var(--faint)", textDecoration: "none" }}>Конфиденциальность</a>
          </span>
        </footer>
      </div>
    </div>
  )
}

// ── контент ───────────────────────────────────────────────────────────────────
const STEPS = [
  { title: "Поставьте цель", body: "Опишите бизнес и задачу в брифе. Директор разбивает путь на этапы." },
  { title: "Агенты работают", body: "Команда исследует рынок, проектирует решение, пишет код и публикует сайты — автономно." },
  { title: "Вы получаете результат", body: "Лиды, лендинги, готовый код и отчёты. Вмешивайтесь и направляйте в любой момент." },
]
const FEATURES = [
  { icon: "🧭", title: "Директор-оркестратор", body: "Ставит задачи, открывает отделы и нанимает специалистов по необходимости." },
  { icon: "🔍", title: "Реальный веб-поиск", body: "Агенты исследуют рынок и конкурентов, а не выдумывают данные." },
  { icon: "💻", title: "Настоящий код", body: "Разработчики пишут код в рабочую папку и пушат в GitHub после вашего одобрения." },
  { icon: "🌐", title: "Лендинги и лиды", body: "Маркетолог публикует сайты, а формы собирают живые заявки." },
  { icon: "🔌", title: "Интеграции", body: "Telegram, GitHub и другие сервисы подключаются автоматически." },
  { icon: "💸", title: "Свой LLM-ключ", body: "Любой OpenAI-совместимый провайдер. Прозрачный учёт расхода токенов." },
]

const ROSTER = ["orchestrator", "researcher", "strategist", "architect", "cto", "developer", "cmo", "marketer", "sales_lead", "salesman", "hr", "analyst"]

function Marquee() {
  const items = [...ROSTER, ...ROSTER]
  return (
    <div style={{ position: "relative", overflow: "hidden", marginTop: 10,
      maskImage: "linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent)",
      WebkitMaskImage: "linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent)" }}>
      <motion.div
        animate={{ x: ["0%", "-50%"] }}
        transition={{ repeat: Infinity, duration: 38, ease: "linear" }}
        style={{ display: "flex", gap: 12, width: "max-content" }}>
        {items.map((role, i) => (
          <div key={i} className="card" style={{ borderRadius: "var(--radius-md)", padding: "14px 18px", width: 230, flexShrink: 0 }}>
            <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 4 }}>{ROLE_NAMES[role] || role}</div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5,
              display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
              {ROLE_DESC[role] || ""}
            </div>
          </div>
        ))}
      </motion.div>
    </div>
  )
}

// концентрические орбиты с ролями — лёгкий «оркестр»
function OrbitPreview() {
  const ring = (size: number, dur: number, dir: 1 | -1, dots: number) => (
    <motion.div
      animate={{ rotate: dir * 360 }} transition={{ repeat: Infinity, duration: dur, ease: "linear" }}
      style={{ position: "absolute", top: "50%", left: "50%", width: size, height: size, marginTop: -size / 2, marginLeft: -size / 2,
        borderRadius: "50%", border: "1px solid var(--hairline)" }}>
      {Array.from({ length: dots }).map((_, i) => {
        const a = (i / dots) * Math.PI * 2
        return <span key={i} style={{ position: "absolute", top: `calc(50% + ${Math.sin(a) * 50}% - 4px)`, left: `calc(50% + ${Math.cos(a) * 50}% - 4px)`,
          width: 8, height: 8, borderRadius: "50%", background: i === 0 ? "var(--mercury-a)" : "var(--hairline-strong)" }} />
      })}
    </motion.div>
  )
  return (
    <div style={{ position: "relative", height: 280 }}>
      {ring(280, 46, 1, 8)}
      {ring(190, 34, -1, 6)}
      {ring(110, 24, 1, 4)}
      <motion.div
        animate={{ scale: [1, 1.08, 1] }} transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
        style={{ position: "absolute", top: "50%", left: "50%", width: 60, height: 60, marginTop: -30, marginLeft: -30,
          borderRadius: "50%", background: MERCURY, boxShadow: "0 0 50px rgba(255,172,46,0.35)",
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, color: "#0a0a0a" }}>
        ⌘
      </motion.div>
    </div>
  )
}

// ── мелкие части ──────────────────────────────────────────────────────────────
function CTA({ children, onClick, primary }: { children: ReactNode; onClick?: () => void; primary?: boolean }) {
  return (
    <motion.button onClick={onClick} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
      style={{ padding: "13px 26px", borderRadius: "var(--radius-pill)", cursor: "pointer", fontSize: 14, fontWeight: 500,
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
function Card({ children }: { children: ReactNode }) {
  return (
    <motion.div whileHover={{ y: -3 }} transition={{ type: "spring", stiffness: 300, damping: 22 }}
      className="card" style={{ borderRadius: "var(--radius-md)", padding: 22 }}>
      {children}
    </motion.div>
  )
}
