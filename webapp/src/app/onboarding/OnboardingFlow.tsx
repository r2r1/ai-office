import { useEffect, useRef, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { api } from "../../data/api"
import { useOfficeSelector } from "../../data/OfficeProvider"
import { IntegCard } from "../views/ConnectionsView"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface Props {
  onDone: () => void
  /** Вызывается ДО отправки брифа — App.tsx держит поток на онбординге, даже
   * если ready успеет стать true раньше, чем клиент дойдёт до onDone (см.
   * комментарий у onboardingStarted в App.tsx). */
  onStart: () => void
}

// Отделы, которые «рождаются» на финале (визуальное строительство).
const BIRTH = [
  { role: "orchestrator", icon: "🧭", name: "CEO", lead: true },
  { role: "researcher", icon: "🔍", name: "Ресёрч" },
  { role: "strategist", icon: "📋", name: "Стратегия" },
  { role: "architect", icon: "🏗️", name: "Архитектура" },
  { role: "hr", icon: "👔", name: "HR" },
]

// Минимальный онбординг (BOS §5): "широкий, маленький, необязательный".
// Раньше — 3 жёстких сценария × 5 фиксированных вопросов, скан сайта первым
// шагом ДАЖЕ для тех, у кого сайта физически нет ("Хочу открыть компанию" /
// "Есть идея"). Теперь: 1 свободное поле (широкое — пишет как хочет, от
// одного слова до абзаца) + необязательная ссылка → офис сам исследует и
// ПРОАКТИВНО показывает результат (аналитика/точки роста/инициативы), а не
// молча начинает работу за спиной клиента.
type Phase = "input" | "analyzing" | "result" | "integrations" | "building"

export function OnboardingFlow({ onDone, onStart }: Props) {
  const [phase, setPhase] = useState<Phase>("input")
  const [text, setText] = useState("")
  const [url, setUrl] = useState("")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ analysis: string[]; growth_points: string[]; initiatives: any[] }>(
    { analysis: [], growth_points: [], initiatives: [] })
  const [integrations, setIntegrations] = useState<any[]>([])

  async function start() {
    setBusy(true)
    onStart()  // ДО await — App.tsx должен зафиксировать "мы в потоке" раньше,
               // чем ready успеет стать true (brief.set_brief происходит в
               // начале BOOTSTRAP, не в конце)
    await api.briefStart(text.trim(), url.trim()).catch(() => null)
    setBusy(false)
    setPhase("analyzing")
  }

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--bg-grad, var(--bg))", color: "var(--text)", padding: 20, overflow: "auto",
    }}>
      {/* амбиент */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none",
        background:
          "radial-gradient(40vw 40vw at 15% 10%, rgba(160,224,171,0.08), transparent 60%)," +
          "radial-gradient(48vw 48vw at 85% 80%, rgba(255,172,46,0.07), transparent 60%)" }} />

      <AnimatePresence mode="wait">
        {phase === "input" && (
          <motion.div key="input" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
            style={{ position: "relative", width: "100%", maxWidth: 560, textAlign: "center" }}>
            <CeoBadge />
            <h1 className="display" style={{ fontSize: 28, margin: "18px 0 8px", fontWeight: 600 }}>
              Расскажите о деле
            </h1>
            <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 24 }}>
              В двух словах или подробно — как удобно. Есть бизнес, только открываетесь
              или просто идея — офис разберётся сам.
            </p>

            <textarea value={text} onChange={e => setText(e.target.value)} autoFocus rows={4}
              placeholder="Например: делаю торты на заказ, хочу больше клиентов…"
              style={{
                width: "100%", resize: "vertical", padding: "13px 15px", fontSize: 14, lineHeight: 1.5,
                borderRadius: "var(--radius-md)", border: "1px solid var(--hairline-strong)",
                background: "var(--surface-soft)", color: "var(--text)", fontFamily: "inherit", outline: "none",
                marginBottom: 10,
              }} />
            <input value={url} onChange={e => setUrl(e.target.value)}
              placeholder="Сайт или соцсеть, если есть (необязательно)"
              onKeyDown={e => { if (e.key === "Enter") start() }}
              style={{
                width: "100%", padding: "11px 14px", fontSize: 13, borderRadius: "var(--radius-md)",
                border: "1px solid var(--hairline)", background: "var(--surface-soft)",
                color: "var(--text)", outline: "none", marginBottom: 20,
              }} />

            <motion.button onClick={start} disabled={busy} whileTap={{ scale: 0.97 }}
              style={{
                width: "100%", padding: "13px 20px", borderRadius: "var(--radius-pill)", border: "none", cursor: "pointer",
                background: MERCURY, color: "#0b0b0b", fontSize: 13, fontWeight: 600, opacity: busy ? 0.6 : 1,
              }}>
              {busy ? "Запускаю…" : text.trim() ? "Начать →" : "Разберитесь сами →"}
            </motion.button>
          </motion.div>
        )}

        {phase === "analyzing" && (
          <AnalyzingScreen key="analyzing" onReady={r => { setResult(r); setPhase("result") }} />
        )}

        {phase === "result" && (
          <ResultScreen key="result" result={result}
            onContinue={async () => {
              const d = await api.suggestedIntegrations().catch(() => ({ integrations: [] }))
              if (d.integrations && d.integrations.length > 0) {
                setIntegrations(d.integrations)
                setPhase("integrations")
              } else {
                setPhase("building")
              }
            }} />
        )}

        {phase === "integrations" && (
          <IntegrationsScreen key="integrations" integrations={integrations}
            onContinue={() => setPhase("building")} />
        )}

        {phase === "building" && (
          <BuildingScene key="building" onDone={onDone} />
        )}
      </AnimatePresence>
    </div>
  )
}

// ── "Офис изучает…" — живой статус вместо немой анимации ────────────────────
// Опрашивает /api/onboarding/result (готовность) и параллельно показывает
// РЕАЛЬНЫЕ события из общей ленты офиса (useOfficeSelector — тот же SSE-поток,
// что и остальное приложение, уже подключён к этому моменту), а не выдуманный
// прогресс-бар.
function AnalyzingScreen({ onReady }: { onReady: (r: any) => void }) {
  const feed = useOfficeSelector(s => s.feed)
  const latest = feed[0]?.text || ""
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      const d = await api.onboardingResult().catch(() => ({ ready: false }))
      if (cancelled) return
      if (d.ready) { onReady(d); return }
      pollRef.current = window.setTimeout(poll, 2500)
    }
    poll()
    return () => { cancelled = true; if (pollRef.current) clearTimeout(pollRef.current) }
  }, []) // eslint-disable-line

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      style={{ position: "relative", textAlign: "center", width: "100%", maxWidth: 480 }}>
      <motion.div animate={{ scale: [1, 1.12, 1] }} transition={{ repeat: Infinity, duration: 1.8, ease: "easeInOut" }}
        style={{
          width: 64, height: 64, borderRadius: "50%", margin: "0 auto 20px", display: "flex",
          alignItems: "center", justifyContent: "center", fontSize: 28,
          background: "var(--surface)", border: "1px solid rgba(255,172,46,0.6)",
          boxShadow: "0 0 26px rgba(255,172,46,0.3)",
        }}>🧭</motion.div>
      <h1 className="display" style={{ fontSize: 22, fontWeight: 600, marginBottom: 10 }}>Офис изучает ваше дело…</h1>
      <AnimatePresence mode="wait">
        <motion.p key={latest} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
          style={{ color: "var(--muted)", fontSize: 13, minHeight: 20, padding: "0 20px" }}>
          {latest || "Собираю команду и провожу первое исследование рынка…"}
        </motion.p>
      </AnimatePresence>
    </motion.div>
  )
}

// ── Результат: аналитика + точки роста + инициативы на выбор ────────────────
function ResultScreen({ result, onContinue }: { result: any; onContinue: () => void }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [decided, setDecided] = useState<Set<string>>(new Set())

  async function decide(id: string, action: "accept" | "reject") {
    setBusy(id)
    await api.post(`/api/initiative/${id}/${action}`, {}).catch(() => null)
    setDecided(prev => new Set(prev).add(id))
    setBusy(null)
  }

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
      style={{ position: "relative", width: "100%", maxWidth: 640, maxHeight: "88vh", overflowY: "auto" }}>
      <div style={{ textAlign: "center", marginBottom: 22 }}>
        <CeoBadge small />
        <h1 className="display" style={{ fontSize: 24, fontWeight: 600, margin: "14px 0 6px" }}>Вот что понял офис</h1>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>Дальше решаете вы — можно принять, отклонить или пропустить всё</p>
      </div>

      {result.analysis?.length > 0 && (
        <Section title="Аналитика">
          {result.analysis.map((a: string, i: number) => (
            <Bullet key={i} icon="📊" text={a} delay={i * 0.06} />
          ))}
        </Section>
      )}

      {result.growth_points?.length > 0 && (
        <Section title="Точки роста">
          {result.growth_points.map((g: string, i: number) => (
            <Bullet key={i} icon="🌱" text={g} delay={i * 0.06} />
          ))}
        </Section>
      )}

      {result.initiatives?.length > 0 && (
        <Section title="Предложенные инициативы">
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {result.initiatives.map((ini: any) => (
              <div key={ini.id} style={{
                padding: "14px 16px", borderRadius: "var(--radius-lg)", background: "var(--surface)",
                border: "1px solid var(--hairline-strong)", opacity: decided.has(ini.id) ? 0.45 : 1,
                transition: "opacity 0.2s",
              }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginBottom: 5 }}>{ini.title}</div>
                {ini.rationale && <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5, marginBottom: 8 }}>{ini.rationale}</div>}
                {ini.expected_outcome && (
                  <div style={{ fontSize: 11, color: "var(--mercury-a)", marginBottom: 10 }}>📈 {ini.expected_outcome}</div>
                )}
                {!decided.has(ini.id) && (
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => decide(ini.id, "accept")} disabled={busy === ini.id}
                      style={{ padding: "7px 14px", borderRadius: "var(--radius-pill)", fontSize: 12, cursor: "pointer",
                        border: "1px solid #a0e0ab", background: "rgba(160,224,171,0.15)", color: "#a0e0ab" }}>
                      ✅ Начать с этого
                    </button>
                    <button onClick={() => decide(ini.id, "reject")} disabled={busy === ini.id}
                      style={{ padding: "7px 14px", borderRadius: "var(--radius-pill)", fontSize: 12, cursor: "pointer",
                        border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)" }}>
                      Не сейчас
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {!result.analysis?.length && !result.growth_points?.length && !result.initiatives?.length && (
        <div style={{ textAlign: "center", color: "var(--muted)", fontSize: 13, padding: "20px 0" }}>
          Офис пока не набрал материала для анализа — начнём работу, дальше он изучит всё сам.
        </div>
      )}

      <motion.button onClick={onContinue} whileTap={{ scale: 0.97 }}
        style={{
          width: "100%", marginTop: 22, padding: "13px 20px", borderRadius: "var(--radius-pill)", border: "none",
          cursor: "pointer", background: MERCURY, color: "#0b0b0b", fontSize: 13, fontWeight: 600,
        }}>
        Продолжить →
      </motion.button>
    </motion.div>
  )
}

// ── Интеграции в момент пиковой мотивации (не спрятаны в настройках) ─────────
function IntegrationsScreen({ integrations, onContinue }: { integrations: any[]; onContinue: () => void }) {
  const [, force] = useState(0)
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
      style={{ position: "relative", width: "100%", maxWidth: 520, textAlign: "center" }}>
      <CeoBadge small />
      <h1 className="display" style={{ fontSize: 22, fontWeight: 600, margin: "14px 0 6px" }}>Подключим сразу?</h1>
      <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 20 }}>
        По вашему описанию офису пригодятся эти сервисы — можно позже, в «Компания → Доступы»
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, textAlign: "left", marginBottom: 20 }}>
        {integrations.map(i => (
          <IntegCard key={i.name} integ={i} onRefresh={() => force(n => n + 1)} />
        ))}
      </div>
      <motion.button onClick={onContinue} whileTap={{ scale: 0.97 }}
        style={{
          width: "100%", padding: "13px 20px", borderRadius: "var(--radius-pill)", border: "none", cursor: "pointer",
          background: MERCURY, color: "#0b0b0b", fontSize: 13, fontWeight: 600,
        }}>
        Готово →
      </motion.button>
    </motion.div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <div className="mono" style={{ fontSize: 10, letterSpacing: "1.5px", textTransform: "uppercase",
        color: "var(--faint)", marginBottom: 10 }}>{title}</div>
      {children}
    </div>
  )
}

function Bullet({ icon, text, delay }: { icon: string; text: string; delay: number }) {
  return (
    <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay }}
      style={{ display: "flex", gap: 10, fontSize: 13, color: "var(--text-dim)", lineHeight: 1.5, padding: "5px 0" }}>
      <span style={{ flexShrink: 0 }}>{icon}</span>
      <span>{text}</span>
    </motion.div>
  )
}

/** Финал: CEO появляется первым, отделы рождаются каскадом. */
function BuildingScene({ onDone }: { onDone: () => void }) {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    if (shown < BIRTH.length) {
      const t = setTimeout(() => setShown(shown + 1), shown === 0 ? 500 : 650)
      return () => clearTimeout(t)
    }
    const t = setTimeout(onDone, 1100)
    return () => clearTimeout(t)
  }, [shown, onDone])

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      style={{ position: "relative", textAlign: "center", width: "100%", maxWidth: 620 }}>
      <h1 className="display" style={{ fontSize: 26, fontWeight: 600, marginBottom: 8 }}>Собираем вашу команду…</h1>
      <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 36 }}>Рождается компания под вашу задачу</p>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-end", gap: 18, flexWrap: "wrap", minHeight: 110 }}>
        {BIRTH.map((b, i) => (
          <AnimatePresence key={b.role}>
            {i < shown && (
              <motion.div
                initial={{ opacity: 0, y: 20, scale: 0.5 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ type: "spring", stiffness: 240, damping: 18 }}
                style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                <div style={{
                  width: b.lead ? 60 : 48, height: b.lead ? 60 : 48, borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: b.lead ? 28 : 22,
                  background: "var(--surface)", border: `1px solid ${b.lead ? "rgba(255,172,46,0.6)" : "var(--hairline-strong)"}`,
                  boxShadow: b.lead ? "0 0 24px rgba(255,172,46,0.3)" : "var(--shadow)",
                }}>{b.icon}</div>
                <div className="mono" style={{ fontSize: 9, letterSpacing: "1px", textTransform: "uppercase",
                  color: b.lead ? "var(--text-dim)" : "var(--faint)" }}>{b.name}</div>
              </motion.div>
            )}
          </AnimatePresence>
        ))}
      </div>
    </motion.div>
  )
}

/** Аватар CEO с пульсом. */
function CeoBadge({ small }: { small?: boolean }) {
  const s = small ? 40 : 64
  return (
    <motion.div
      initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 240, damping: 18 }}
      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: s, height: s, borderRadius: "50%", fontSize: small ? 20 : 30,
        background: "var(--surface)", border: "1px solid rgba(255,172,46,0.6)",
        boxShadow: "0 0 26px rgba(255,172,46,0.3)" }}>
      🧭
    </motion.div>
  )
}
