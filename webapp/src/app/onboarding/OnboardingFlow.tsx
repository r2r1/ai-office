import { useEffect, useMemo, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { api } from "../../data/api"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface Mode { key: string; title: string; icon: string; intro: string; questions: { dimension: string; question: string }[] }
interface Props { onDone: () => void }

// Отделы, которые «рождаются» на финале (визуальное строительство, item 5).
const BIRTH = [
  { role: "orchestrator", icon: "🧭", name: "CEO", lead: true },
  { role: "researcher", icon: "🔍", name: "Ресёрч" },
  { role: "strategist", icon: "📋", name: "Стратегия" },
  { role: "architect", icon: "🏗️", name: "Архитектура" },
  { role: "hr", icon: "👔", name: "HR" },
]

const DIM_LABEL: Record<string, string> = {
  product: "Продукт", client: "Клиент", revenue: "Экономика", goal: "Цель", constraints: "Ограничения",
}

type Phase = "mode" | "interview" | "building"

export function OnboardingFlow({ onDone }: Props) {
  const [modes, setModes] = useState<Mode[]>([])
  const [phase, setPhase] = useState<Phase>("mode")
  const [mode, setMode] = useState<Mode | null>(null)
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<string[]>([])
  const [draft, setDraft] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.onboardingModes().then(d => setModes(d.modes || [])) }, [])

  const total = mode?.questions.length || 5
  const studied = useMemo(() => Math.round((answers.filter(a => a && a.trim()).length / total) * 100), [answers, total])

  function pickMode(m: Mode) {
    setMode(m); setAnswers(new Array(m.questions.length).fill("")); setStep(0); setDraft(""); setPhase("interview")
  }

  function commitAndNext() {
    if (!mode) return
    const next = [...answers]; next[step] = draft; setAnswers(next)
    if (step + 1 < mode.questions.length) {
      setStep(step + 1); setDraft(next[step + 1] || "")
    } else {
      finish(next)
    }
  }

  function back() {
    if (step === 0) { setPhase("mode"); setMode(null); return }
    const prev = step - 1; setStep(prev); setDraft(answers[prev] || "")
  }

  async function finish(finalAnswers: string[]) {
    if (!mode) return
    setBusy(true)
    const payload = mode.questions.map((q, i) => ({ dimension: q.dimension, question: q.question, answer: finalAnswers[i] || "" }))
    await api.onboardingFinish(mode.key, payload)
    setBusy(false)
    setPhase("building")
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
        {phase === "mode" && (
          <motion.div key="mode" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
            style={{ position: "relative", width: "100%", maxWidth: 720, textAlign: "center" }}>
            <CeoBadge />
            <h1 className="display" style={{ fontSize: 30, margin: "18px 0 8px", fontWeight: 600 }}>С чего начнём?</h1>
            <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 28 }}>
              CEO задаст несколько вопросов и соберёт под вас команду.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
              {modes.map(m => (
                <motion.button key={m.key} onClick={() => pickMode(m)}
                  whileHover={{ y: -4 }} whileTap={{ scale: 0.98 }}
                  style={{
                    textAlign: "left", padding: "20px 18px", borderRadius: "var(--radius-lg)", cursor: "pointer",
                    background: "var(--surface)", border: "1px solid var(--hairline-strong)", color: "var(--text)",
                  }}>
                  <div style={{ fontSize: 30, marginBottom: 10 }}>{m.icon}</div>
                  <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{m.title}</div>
                  <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45 }}>{m.intro}</div>
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}

        {phase === "interview" && mode && (
          <motion.div key="interview" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
            style={{ position: "relative", width: "100%", maxWidth: 560 }}>
            {/* прогресс «Компания изучена на X%» */}
            <div style={{ marginBottom: 22 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)", marginBottom: 7 }}>
                <span>Компания изучена на</span>
                <span className="mono" style={{ color: studied >= 60 ? "#a0e0ab" : "#ffac2e" }}>{studied}%</span>
              </div>
              <div style={{ height: 4, borderRadius: 999, background: "var(--hairline-strong)", overflow: "hidden" }}>
                <motion.div animate={{ width: `${studied}%` }} transition={{ duration: 0.5 }}
                  style={{ height: "100%", background: MERCURY, borderRadius: 999 }} />
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <CeoBadge small />
              <div className="mono" style={{ fontSize: 10, letterSpacing: "1.5px", textTransform: "uppercase", color: "var(--faint)" }}>
                {DIM_LABEL[mode.questions[step].dimension] || "Вопрос"} · {step + 1}/{mode.questions.length}
              </div>
            </div>

            <AnimatePresence mode="wait">
              <motion.h2 key={step} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.25 }}
                style={{ fontSize: 21, fontWeight: 600, lineHeight: 1.35, margin: "0 0 18px" }}>
                {mode.questions[step].question}
              </motion.h2>
            </AnimatePresence>

            <textarea value={draft} onChange={e => setDraft(e.target.value)} autoFocus rows={4}
              placeholder="Ответьте своими словами…"
              onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) commitAndNext() }}
              style={{
                width: "100%", resize: "vertical", padding: "13px 15px", fontSize: 14, lineHeight: 1.5,
                borderRadius: "var(--radius-md)", border: "1px solid var(--hairline-strong)",
                background: "var(--surface-soft)", color: "var(--text)", fontFamily: "inherit", outline: "none",
              }} />

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 18 }}>
              <button onClick={back} disabled={busy}
                style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 13, padding: "8px 4px" }}>
                ← Назад
              </button>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                {step + 1 < mode.questions.length && (
                  <button onClick={() => { setDraft(""); commitAndNext() }} disabled={busy}
                    style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer", fontSize: 12 }}>
                    Пропустить
                  </button>
                )}
                <motion.button onClick={commitAndNext} disabled={busy} whileTap={{ scale: 0.97 }}
                  style={{
                    padding: "10px 22px", borderRadius: "var(--radius-pill)", border: "none", cursor: "pointer",
                    background: MERCURY, color: "#0b0b0b", fontSize: 13, fontWeight: 600, opacity: busy ? 0.6 : 1,
                  }}>
                  {busy ? "Собираю офис…" : step + 1 < mode.questions.length ? "Дальше" : "Запустить офис →"}
                </motion.button>
              </div>
            </div>
          </motion.div>
        )}

        {phase === "building" && (
          <BuildingScene key="building" onDone={onDone} />
        )}
      </AnimatePresence>
    </div>
  )
}

/** Финал: CEO появляется первым, отделы рождаются каскадом (item 5). */
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
