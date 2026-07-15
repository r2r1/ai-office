import { motion, useMotionValue, useSpring, useScroll, useTransform, useReducedMotion, AnimatePresence } from "motion/react"
import { useRef, useState, useEffect } from "react"
import type { ReactNode } from "react"
import { ROLE_NAMES, ROLE_DESC } from "../../data/roles"
import { api } from "../../data/api"

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
        <MindFeed />
        <HowItWorks />
        <TeamHierarchy />
        <GrowthArc />
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

// ── HERO: асимметричный сплит — слева обещание, справа живой офис ─────────────
// Не орбита ролей вокруг центра (клише AI-лендингов) и не статичный скриншот —
// панель справа реально "живёт": статус меняется сам, отделы подсвечиваются
// по очереди. Это не декорация, а витрина реального артефакта продукта.
function Hero({ onLogin, onDemo }: { onLogin: () => void; onDemo?: () => void }) {
  return (
    <motion.section variants={container} initial="hidden" animate="show"
      style={{ paddingTop: "clamp(40px, 8vh, 88px)", paddingBottom: "9vh",
        display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: "6vw", alignItems: "center" }}
      className="hero-grid">
      <div>
        <motion.div variants={item}
          style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "5px 14px", borderRadius: "var(--radius-pill)",
            border: "1px solid var(--hairline)", background: "var(--surface-soft)", fontSize: 11.5, color: "var(--text-dim)", marginBottom: 22 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#a0e0ab" }} />
          Business Operating System
        </motion.div>

        <h1 className="display"
          style={{ fontSize: "clamp(34px, 5vw, 60px)", lineHeight: 1.1, fontWeight: 300, letterSpacing: "-0.02em", margin: 0 }}>
          <motion.span variants={item} style={{ display: "block" }}>Поставьте цель.</motion.span>
          <motion.span variants={item} style={{ display: "block", fontStyle: "italic", paddingBottom: 4,
            background: MERCURY, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
            Офис сам её достигнет.
          </motion.span>
        </h1>

        <motion.p variants={item}
          style={{ fontSize: "clamp(14px, 1.4vw, 16.5px)", color: "var(--muted)", lineHeight: 1.6, maxWidth: 460, marginTop: 20 }}>
          Не ассистент и не набор промптов. Живая операционная система компании:
          сама изучает рынок, решает, что делать дальше, и постепенно берёт бизнес на себя.
        </motion.p>

        <motion.div variants={item} style={{ marginTop: 30 }}>
          <ScanBox onLogin={onLogin} />
        </motion.div>
        <motion.div variants={item} style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
          <CTA primary magnetic onClick={onLogin}>Запустить офис →</CTA>
          {onDemo && <CTA onClick={onDemo}>Демо</CTA>}
        </motion.div>
      </div>

      <motion.div variants={item}>
        <OfficePreview />
      </motion.div>
    </motion.section>
  )
}

// ── SCAN BOX: первое расследование (не "скан сайта") ───────────────────────
// Ключевой продуктовый тезис (docs/architecture-improvements.md — Company
// Understanding как moat): AI должен показать, что уже понимает БИЗНЕС, ДО
// формы регистрации — не после. company_scan.scan() уже даёт находки и
// pain_points бесплатно ($0, без LLM); здесь — публичный вызов /api/onboarding/
// scan (см. server.py _PUBLIC_API) прямо с лендинга.
//
// Продуктовый разбор пользователя (issue: "онбординг как диалог, не экраны"):
// психология важнее данных — те же самые поля scan_result подаются как
// РАССЛЕДОВАНИЕ (детективный темп: находка → пауза → вывод → неожиданный
// инсайт), а не как дамп JSON разом. Названия действий — "познакомиться с
// компанией", не "сканировать сайт"; находки — "что я понял", не "проблемы".
// Полноценный редизайн в СТОРОНУ непрерывного диалога с CEO (вместо текущей
// последовательности фаз input→analyzing→result→integrations→building в
// OnboardingFlow.tsx) — отдельная, более крупная задача, эта правка её не
// заменяет, только меняет темп и тон уже существующего экрана.
type Phase = "idle" | "loading" | "discoveries" | "insight" | "more" | "stage" | "done" | "error"

// Гипотеза о стадии бизнеса (company_scan._stage_hypothesis, LLM + фолбэк на
// эвристику) — метки для кнопок-корректировок, если AI ошибся; ключи должны
// совпадать 1:1 с _STAGES в company_scan.py.
const STAGE_LABELS: Record<string, string> = {
  idea: "Только идея", launch: "Недавно запустились", growth: "Активно растём", mature: "Зрелая компания",
}
const SOCIAL_RU: Record<string, string> = {
  telegram: "Telegram", instagram: "Instagram", vk: "VK", whatsapp: "WhatsApp", youtube: "YouTube", facebook: "Facebook",
}

// Что именно AI "понял" на первый взгляд — построено из тех же полей detected,
// что уже приходят со scan(), просто поданных как последовательность открытий,
// а не единый список фактов.
function buildDiscoveries(result: any): string[] {
  if (!result?.ok) return []
  const d = result.detected || {}
  const out: string[] = ["Нашёл сайт"]
  const socialKey = Object.keys(d.socials || {})[0]
  if (socialKey) out.push(`Нашёл ${SOCIAL_RU[socialKey] || socialKey}`)
  if (d.title || d.meta_description) out.push("Понял, чем вы занимаетесь")
  if ((d.emails || []).length || (d.phones || []).length) out.push("Нашёл, как с вами связаться")
  return out
}

function ScanBox({ onLogin }: { onLogin: () => void }) {
  const [url, setUrl] = useState("")
  const [phase, setPhase] = useState<Phase>("idle")
  const [result, setResult] = useState<any>(null)
  const [shownDiscoveries, setShownDiscoveries] = useState(0)
  const [stageCorrected, setStageCorrected] = useState(false)
  const reduceMotion = useReducedMotion()
  const timers = useRef<number[]>([])

  function correctStage(key: string) {
    const corrected = { key, label: STAGE_LABELS[key], reason: "уточнено вами", confirmed: true }
    setResult((r: any) => r ? { ...r, stage: corrected } : r)
    setStageCorrected(true)
    try {
      const raw = sessionStorage.getItem("aioffice_landing_scan")
      if (raw) {
        const parsed = JSON.parse(raw)
        parsed.result.stage = corrected
        sessionStorage.setItem("aioffice_landing_scan", JSON.stringify(parsed))
      }
    } catch { /* приватный режим браузера */ }
  }

  const discoveries = buildDiscoveries(result)
  const points: string[] = result?.ok ? (result.pain_points || []) : []
  const surprise = points[0] || ""
  const restPoints = points.slice(1)

  useEffect(() => () => { timers.current.forEach(clearTimeout) }, [])

  // Детективный темп: находки одна за другой → короткая пауза «нашёл кое-что
  // интересное» → главный инсайт отдельно (не в общем списке) → остальное →
  // вопрос о стадии. Без reduceMotion — просто пропускаем прямо к финалу.
  function scheduleReveal(hasPoints: boolean) {
    const push = (fn: () => void, delay: number) => timers.current.push(window.setTimeout(fn, delay))
    if (reduceMotion) { setPhase(hasPoints ? "more" : "stage"); setShownDiscoveries(discoveries.length); return }
    setPhase("discoveries")
    discoveries.forEach((_, i) => push(() => setShownDiscoveries(i + 1), 500 + i * 550))
    const afterDiscoveries = 500 + discoveries.length * 550 + 350
    if (hasPoints) {
      push(() => setPhase("insight"), afterDiscoveries)
      push(() => setPhase("more"), afterDiscoveries + 1500)
    } else {
      push(() => setPhase("stage"), afterDiscoveries)
    }
  }

  async function run() {
    const v = url.trim()
    if (!v || phase === "loading") return
    setPhase("loading")
    setResult(null)
    setShownDiscoveries(0)
    setStageCorrected(false)
    try {
      const r = await api.onboardingScan(v)
      if (r && r.ok) {
        // сохраняем находки — онбординг после регистрации подхватит их и не
        // будет спрашивать заново то, что уже увидел на лендинге
        try { sessionStorage.setItem("aioffice_landing_scan", JSON.stringify({ url: v, result: r })) } catch { /* приватный режим браузера */ }
        setResult(r)
        scheduleReveal((r.pain_points || []).length > 0)
      } else {
        setResult(r)
        setPhase("error")
      }
    } catch {
      setPhase("error")
    }
  }

  const showStageAndOn = phase === "stage" || phase === "done"
  const showMoreAndOn = phase === "more" || showStageAndOn

  return (
    <div className="card" style={{ borderRadius: "var(--radius-lg)", padding: 16, maxWidth: 460 }}>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 10 }}>
        Прежде чем начать — покажите мне свою компанию
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input value={url} onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === "Enter" && run()}
          placeholder="например, mycompany.ru"
          aria-label="Ссылка на сайт компании"
          disabled={phase === "loading"}
          style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
            borderRadius: "var(--radius-pill)", padding: "10px 16px", color: "var(--text)",
            fontSize: 13, outline: "none", fontFamily: "var(--font-sans)" }} />
        <button onClick={run} disabled={!url.trim() || phase === "loading"}
          style={{ border: "none", borderRadius: "var(--radius-pill)", padding: "0 20px",
            background: url.trim() && phase !== "loading" ? MERCURY : "var(--ghost)",
            color: url.trim() && phase !== "loading" ? "#0a0a0a" : "var(--faint)",
            cursor: url.trim() ? "pointer" : "default", fontSize: 13, fontWeight: 600,
            fontFamily: "var(--font-sans)", whiteSpace: "nowrap" }}>
          {phase === "loading" ? "Знакомлюсь…" : "Начать исследование"}
        </button>
      </div>

      <AnimatePresence>
        {phase === "loading" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 12.5, color: "var(--muted)" }}>
            <motion.span animate={reduceMotion ? {} : { opacity: [1, 0.35, 1] }} transition={{ repeat: Infinity, duration: 1.2 }}
              style={{ width: 6, height: 6, borderRadius: "50%", background: "#a0e0ab", flexShrink: 0 }} />
            Изучаю компанию…
          </motion.div>
        )}

        {phase === "error" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ marginTop: 12, fontSize: 12.5, color: "var(--muted)" }}>
            Не удалось изучить этот адрес — ничего страшного, расскажете о бизнесе сами при запуске.
          </motion.div>
        )}

        {phase !== "idle" && phase !== "loading" && phase !== "error" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ marginTop: 14 }}>
            {discoveries.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: shownDiscoveries >= discoveries.length ? 12 : 0 }}>
                {discoveries.slice(0, shownDiscoveries).map((d, i) => (
                  <motion.div key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3 }}
                    style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5 }}>
                    <span style={{ color: "#a0e0ab", marginRight: 6 }}>✓</span>{d}
                  </motion.div>
                ))}
              </div>
            )}

            {points.length > 0 && (phase === "insight" || showMoreAndOn) && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                style={{ marginBottom: showMoreAndOn ? 10 : 0 }}>
                {phase === "insight" && (
                  <div style={{ fontSize: 11.5, color: "var(--faint)", marginBottom: 6, fontStyle: "italic" }}>
                    Нашёл кое-что интересное…
                  </div>
                )}
                <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 600, lineHeight: 1.5 }}>
                  Кстати — {surprise.charAt(0).toLowerCase() + surprise.slice(1)}
                </div>
              </motion.div>
            )}

            {points.length === 0 && showMoreAndOn && (
              <div style={{ fontSize: 12.5, color: "var(--text)", fontWeight: 600, marginBottom: 10 }}>
                На первый взгляд у вас уже неплохо настроено — копну глубже, когда продолжим.
              </div>
            )}

            {showMoreAndOn && restPoints.length > 0 && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}
                style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 12 }}>
                <div style={{ fontSize: 10.5, color: "var(--faint)" }}>Ещё заметил:</div>
                {restPoints.map((p, i) => (
                  <div key={i} style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>
                    <span style={{ color: "var(--mercury-a)", marginRight: 6 }}>•</span>{p}
                  </div>
                ))}
              </motion.div>
            )}

            {showStageAndOn && result?.stage && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                style={{ marginBottom: 12, padding: "10px 12px", borderRadius: "var(--radius-md)",
                  background: "var(--surface-soft)", border: "1px solid var(--hairline)" }}>
                <div style={{ fontSize: 12.5, color: "var(--text)" }}>
                  Кажется, вы {result.stage.label.toLowerCase()} — <span style={{ color: "var(--muted)" }}>{result.stage.reason}</span>. Поправьте меня, если ошибся.
                </div>
                {!stageCorrected && !result.stage.confirmed && (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                    <button onClick={() => { setStageCorrected(true); setPhase("done") }}
                      style={{ fontSize: 11, padding: "4px 10px", borderRadius: "var(--radius-pill)", cursor: "pointer",
                        border: "1px solid rgba(160,224,171,0.4)", background: "rgba(160,224,171,0.1)", color: "#a0e0ab" }}>
                      Верно
                    </button>
                    {Object.entries(STAGE_LABELS).filter(([k]) => k !== result.stage.key).map(([k, label]) => (
                      <button key={k} onClick={() => { correctStage(k); setPhase("done") }}
                        style={{ fontSize: 11, padding: "4px 10px", borderRadius: "var(--radius-pill)", cursor: "pointer",
                          border: "1px solid var(--hairline)", background: "transparent", color: "var(--muted)" }}>
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </motion.div>
            )}

            {(showStageAndOn || (!result?.stage && showMoreAndOn)) && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
                <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 8 }}>
                  Я могу продолжить изучение компании — для этого нужно сохранить исследование.
                </div>
                <CTA primary onClick={onLogin}>Продолжить исследование →</CTA>
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

const PREVIEW_ROOMS: { role: string; workers: string[]; tint: string }[] = [
  { role: "cto", workers: ["developer", "designer"], tint: "rgba(160,224,171,0.10)" },
  { role: "cmo", workers: ["marketer", "analyst"], tint: "rgba(255,172,46,0.10)" },
  { role: "sales_lead", workers: ["salesman"], tint: "rgba(165,45,37,0.08)" },
]
const LIVE_STATUSES = ["исследует рынок", "пишет код", "публикует лендинг", "отвечает лиду", "обновляет стратегию"]
function OfficePreview() {
  const reduceMotion = useReducedMotion()
  const [statusIdx, setStatusIdx] = useState(0)
  const [activeRoom, setActiveRoom] = useState(0)
  useEffect(() => {
    if (reduceMotion) return
    const t1 = setInterval(() => setStatusIdx(i => (i + 1) % LIVE_STATUSES.length), 2600)
    const t2 = setInterval(() => setActiveRoom(i => (i + 1) % PREVIEW_ROOMS.length), 2600)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [reduceMotion])

  return (
    <div className="card" style={{ borderRadius: "var(--radius-lg)", padding: 18, position: "relative", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)", letterSpacing: "1px" }}>ОФИС СЕЙЧАС</span>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)", minWidth: 120, justifyContent: "flex-end" }}>
          <motion.span animate={reduceMotion ? {} : { opacity: [1, 0.35, 1] }} transition={{ repeat: Infinity, duration: 2 }}
            style={{ width: 6, height: 6, borderRadius: "50%", background: "#a0e0ab", flexShrink: 0 }} />
          <AnimatePresence mode="wait">
            <motion.span key={statusIdx} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.3 }}>
              {LIVE_STATUSES[statusIdx]}
            </motion.span>
          </AnimatePresence>
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", borderRadius: "var(--radius-sm)",
        background: "var(--surface-soft)", border: "1px solid var(--hairline)", marginBottom: 10 }}>
        <span style={{ width: 26, height: 26, borderRadius: "50%", background: MERCURY, flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#0a0a0a" }}>
          {(ROLE_NAMES["orchestrator"] || "CEO").slice(0, 1)}
        </span>
        <div style={{ fontSize: 12.5, fontWeight: 600 }}>{ROLE_NAMES["orchestrator"] || "CEO"}</div>
        <span className="mono" style={{ fontSize: 9.5, color: "var(--mercury-a)", marginLeft: "auto" }}>ставит цели отделам</span>
      </div>
      <div style={{ display: "grid", gap: 8 }}>
        {PREVIEW_ROOMS.map((room, i) => (
          <motion.div key={room.role}
            initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0,
              borderColor: !reduceMotion && activeRoom === i ? "var(--mercury-a)" : "var(--hairline)",
              scale: !reduceMotion && activeRoom === i ? 1.015 : 1 }}
            transition={{ delay: i * 0.1, duration: 0.4 }}
            style={{ borderRadius: "var(--radius-sm)", border: "1px solid var(--hairline)", background: room.tint, padding: "10px 12px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>{ROLE_NAMES[room.role] || room.role}</span>
              <span className="mono" style={{ fontSize: 9.5, color: "var(--muted)" }}>{room.workers.length} в отделе</span>
            </div>
            <div style={{ display: "flex", gap: 5, marginTop: 7, flexWrap: "wrap" }}>
              {room.workers.map(w => (
                <span key={w} title={ROLE_NAMES[w] || w}
                  style={{ fontSize: 10, padding: "3px 8px", borderRadius: "var(--radius-pill)",
                    background: "var(--surface-card)", border: "1px solid var(--hairline-strong)", color: "var(--text-dim)" }}>
                  {ROLE_NAMES[w] || w}
                </span>
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

// ── MIND FEED: как офис думает — сигнал → решение → действие → память ─────────
// Не декоративная схема и не абстрактная маркетинговая метафора — это реальный
// цикл продукта (Event Layer → CEO decide → задача отдела → Knowledge/World
// Model), рассказанный как конкретная ситуация, а не список фич.
const MIND_STEPS = [
  { tag: "СИГНАЛ", color: "var(--text-dim)", text: "Три лида не ответили за 48 часов. Воронка проседает." },
  { tag: "РЕШЕНИЕ CEO", color: "var(--mercury-a)", text: "Приоритет смещён на реактивацию, задача уходит в продажи." },
  { tag: "ДЕЙСТВИЕ", color: "#a0e0ab", text: "Продажник запускает персональную серию сообщений, лид отвечает." },
  { tag: "ПАМЯТЬ", color: "var(--muted)", text: "Рабочий сценарий реактивации сохранён как знание отдела." },
]
function MindFeed() {
  return (
    <Reveal>
      <div className="display" style={{ fontSize: "clamp(24px, 3.4vw, 38px)", fontWeight: 300, maxWidth: 640 }}>
        Офис не ждёт команд. Он замечает, решает и делает.
      </div>
      <div style={{ display: "grid", gap: 10, marginTop: 32, maxWidth: 640 }}>
        {MIND_STEPS.map((s, i) => (
          <motion.div key={s.tag}
            initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.6 }}
            transition={{ duration: 0.45, delay: i * 0.12, ease: [0.16, 1, 0.3, 1] }}
            style={{ display: "flex", gap: 16, alignItems: "baseline", padding: "12px 0",
              borderBottom: i < MIND_STEPS.length - 1 ? "1px solid var(--hairline)" : "none" }}>
            <span className="mono" style={{ fontSize: 10, letterSpacing: "1px", color: s.color, width: 108, flexShrink: 0 }}>{s.tag}</span>
            <span style={{ fontSize: 14, color: "var(--text-dim)", lineHeight: 1.55 }}>{s.text}</span>
          </motion.div>
        ))}
      </div>
    </Reveal>
  )
}

// ── КАК ЭТО РАБОТАЕТ: шаги с прогресс-рейкой, привязанной к скроллу ───────────
function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.75", "end 0.6"] })
  const railHeight = useTransform(scrollYProgress, [0, 1], ["0%", "100%"])
  return (
    <Reveal>
      <div className="display" style={{ fontSize: "clamp(24px, 3.4vw, 38px)", fontWeight: 300, marginBottom: 32 }}>
        От цели до результата
      </div>
      <div ref={ref} style={{ position: "relative", display: "flex", flexDirection: "column", gap: 28, paddingLeft: 28 }}>
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
      <div className="display" style={{ fontSize: "clamp(24px, 3.4vw, 38px)", fontWeight: 300, marginBottom: 32 }}>
        Реальная оргструктура, не набор промптов
      </div>
      <div className="bento-grid" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gridAutoRows: 120, gridAutoFlow: "dense", gap: 14 }}>
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

// ── GROWTH ARC: офис накапливает знания о бизнесе со временем ─────────────────
// Заменяет типовую сетку из одинаковых feature-карточек с иконками (шаблонный
// приём AI-лендингов). Три асимметричные стадии + условная шкала "плотности
// знаний" вместо выдуманной точной статистики.
const GROWTH_STAGES = [
  { period: "Неделя 1", weight: 0.35, body: "Первые факты о рынке, первый лендинг, первые лиды в работе." },
  { period: "Месяц 1", weight: 0.65, body: "Проверенные гипотезы, рабочие сценарии продаж и контента, свои интеграции." },
  { period: "Месяц 3+", weight: 1, body: "Офис держит контекст компании лучше нового сотрудника и сам находит, что делать дальше." },
]
function GrowthArc() {
  return (
    <Reveal>
      <div className="display" style={{ fontSize: "clamp(24px, 3.4vw, 38px)", fontWeight: 300, marginBottom: 32, maxWidth: 640 }}>
        Офис не сбрасывает память. Он растёт вместе с бизнесом.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "0.8fr 1fr 1.3fr", gap: 16 }} className="growth-grid">
        {GROWTH_STAGES.map((stage, i) => (
          <motion.div key={stage.period} whileHover={{ y: -3 }} transition={{ type: "spring", stiffness: 300, damping: 22 }}
            className="card" style={{ borderRadius: "var(--radius-md)", padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="mono" style={{ fontSize: 10.5, color: "var(--faint)", letterSpacing: "1px" }}>{stage.period.toUpperCase()}</div>
            <div style={{ height: 5, borderRadius: "var(--radius-pill)", background: "var(--surface-soft)", overflow: "hidden" }}>
              <motion.div initial={{ scaleX: 0 }} whileInView={{ scaleX: stage.weight }} viewport={{ once: true }}
                transition={{ duration: 0.8, delay: i * 0.15, ease: [0.16, 1, 0.3, 1] }}
                style={{ height: "100%", width: "100%", transformOrigin: "left", background: MERCURY }} />
            </div>
            <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.6 }}>{stage.body}</div>
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
          Пусть офис управляет тем, что можно не делать руками
        </div>
        <p style={{ fontSize: 14, color: "var(--muted)", marginTop: 14, marginBottom: 28, position: "relative" }}>
          Вход через GitHub или email. Дальше, только ваша цель.
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
