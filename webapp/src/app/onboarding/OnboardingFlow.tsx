import { useEffect, useRef, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { api } from "../../data/api"
import { useOfficeSelector } from "../../data/OfficeProvider"
import { useThrottled } from "../hooks"
import { IntegCard } from "../views/ConnectionsView"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface Props {
  onDone: () => void
  /** Вызывается ДО отправки брифа — App.tsx держит поток на онбординге, даже
   * если ready успеет стать true раньше, чем клиент дойдёт до onDone (см.
   * комментарий у onboardingStarted в App.tsx). */
  onStart: () => void
  /** Восстановление после перезагрузки/закрытой вкладки МЕЖДУ тем, как бриф
   * стал готов, и тем, как владелец подтвердил первый дашборд (портрет §23) —
   * без этого office/loop.py ждёт подтверждения, которое НЕЧЕМ дать: обычный
   * гейт App.tsx (`ready === false`) уже не срабатывает, `onboardingStarted`
   * сброшен новым mount'ом. Пропускает chat/analyzing, сразу грузит и
   * показывает result-фазу. Реальный найденный разрыв, не гипотетический —
   * см. docs/handoff.md, тот же класс проблемы, что и `onboardingStarted`. */
  forceResultPhase?: boolean
}

// Отделы, которые «рождаются» на финале (визуальное строительство).
const BIRTH = [
  { role: "orchestrator", icon: "🧭", name: "CEO", lead: true },
  { role: "researcher", icon: "🔍", name: "Ресёрч" },
  { role: "strategist", icon: "📋", name: "Стратегия" },
  { role: "architect", icon: "🏗️", name: "Архитектура" },
  { role: "hr", icon: "👔", name: "HR" },
]

// Первое расследование компании (docs/first-investigation-plan-2026-07-16.md,
// Фаза 5): раньше "start()" слал текст в /api/brief/start — одноразовый LLM-
// вызов БЕЗ поиска и без диалога (office/investigation.py, Фаза 4, оставался
// недостижим из обычной регистрации — реальный разрыв между тем, что построено,
// и тем, что реально видит пользователь). Теперь первое сообщение и вся
// дальнейшая переписка идут через /api/chat — тот же живой агентский диалог,
// что и обычный чат с CEO, просто начатый до того, как бриф готов.
type Phase = "chat" | "analyzing" | "result" | "integrations" | "building"

// Чипы ниш — точка входа с нулём символов текста (принцип "усилие тратит
// офис, а не пользователь"): один тап уже даёт агенту достаточно, чтобы
// начать расследование (нишу дальше уточнит сам через web_search/вопрос).
const NICHE_CHIPS = ["Мебель", "Стройка и ремонт", "Красота и здоровье", "Еда и кафе",
  "Услуги на дому", "Недвижимость", "Автосервис", "Онлайн-магазин"]

// Ключ sessionStorage, которым ScanBox на лендинге (LandingView.tsx) делится
// результатом Instant Learning (issue #19) — здесь подхватываем его и
// вкладываем в ПЕРВОЕ сообщение расследования, чтобы агент не спрашивал сайт
// повторно и не сканировал его второй раз сам.
const LANDING_SCAN_KEY = "aioffice_landing_scan"

export function OnboardingFlow({ onDone, onStart, forceResultPhase }: Props) {
  // Ленивый инициализатор — читает ТЕКУЩЕЕ значение пропа РОВНО ОДИН раз при
  // маунте компонента, не подписывается на его дальнейшие изменения. Если бы
  // сюда попадало живое значение пропа, дашборд мог бы дёрнуть фазу назад на
  // "result" посреди обычного чата, случайно совпади живой ready-опрос с
  // моментом, когда пользователь уже сам продвинулся дальше по шагам.
  const [phase, setPhase] = useState<Phase>(() => forceResultPhase ? "result" : "chat")
  const [result, setResult] = useState<{ analysis: string[]; growth_points: string[]; initiatives: any[] }>(
    { analysis: [], growth_points: [], initiatives: [] })
  const [integrations, setIntegrations] = useState<any[]>([])
  const [landingScan, setLandingScan] = useState<{ url: string; result: any } | null>(null)
  const [started, setStarted] = useState(false)

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(LANDING_SCAN_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw)
      if (parsed?.url && parsed?.result) setLandingScan(parsed)
    } catch { /* приватный режим браузера / битый JSON — просто без подсказки */ }
  }, [])

  // Восстановление: догружаем сам результат для result-фазы, в которую нас
  // с ходу поставил ленивый initializer выше (тот знает только ЧТО показать
  // фазу, не ЧЕМ её наполнить).
  useEffect(() => {
    if (phase !== "result" || result.analysis.length || result.growth_points.length || result.initiatives.length) return
    api.onboardingResult().then(d => { if (d?.ready) setResult(d) }).catch(() => {})
  }, []) // eslint-disable-line

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
        {phase === "chat" && (
          <InvestigationChat key="chat" landingScan={landingScan}
            onFirstMessage={() => { if (!started) { onStart(); setStarted(true) } }}
            onBriefReady={() => setPhase("analyzing")} />
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

// ── Первое расследование: живой чат вместо формы ─────────────────────────────
// До первого сообщения — чипы ниш (0 символов текста) + свободное поле, тот же
// экран, что раньше. После первого сообщения — та же переписка, что обычный
// чат с CEO (office_chat/api.chatGet/api.chatPost), только начатая ДО того, как
// бриф готов: агент сам решает, спросить коротко или пойти искать (office/
// investigation.py, Фаза 4). Опрашиваем /api/brief/status — как только ready,
// сообщаем родителю переключиться на "analyzing" (реальный BOOTSTRAP уже идёт).
function InvestigationChat({ landingScan, onFirstMessage, onBriefReady }: {
  landingScan: { url: string; result: any } | null
  onFirstMessage: () => void
  onBriefReady: () => void
}) {
  const [messages, setMessages] = useState<any[]>([])
  const [pending, setPending] = useState<any[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const feedLength = useOfficeSelector(s => s.feed.length)
  const feedRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<number | null>(null)
  const chatting = messages.length > 0 || pending.length > 0

  async function load() {
    const data = await api.chatGet().catch(() => ({ messages: [] }))
    const server = data.messages || []
    setMessages(server)
    setPending(p => p.filter(pm => !server.some((sm: any) => sm.from === "user" && sm.text === pm.text)))
  }
  const tick = useThrottled(feedLength, 2000)
  useEffect(() => { if (chatting) load() }, [tick]) // eslint-disable-line

  useEffect(() => { feedRef.current?.scrollTo(0, feedRef.current.scrollHeight) }, [messages, pending])

  // Пока идёт диалог (бриф ещё не готов) — проверяем готовность отдельно от
  // общей ленты: BOOTSTRAP может начаться на том же ходу, что закрыл диалог,
  // и владелец не должен ждать следующего тика общей ленты, чтобы увидеть это.
  useEffect(() => {
    if (!chatting) return
    let cancelled = false
    async function poll() {
      const d = await api.briefStatus().catch(() => ({ ready: false }))
      if (cancelled) return
      if (d.ready) { onBriefReady(); return }
      pollRef.current = window.setTimeout(poll, 2000)
    }
    poll()
    return () => { cancelled = true; if (pollRef.current) clearTimeout(pollRef.current) }
  }, [chatting]) // eslint-disable-line

  async function send(text: string) {
    const clean = text.trim()
    if (!clean || sending) return
    setSending(true)
    onFirstMessage()
    // Находка со скана лендинга (Instant Learning) — вкладываем в ПЕРВОЕ
    // сообщение расследования как контекст, не как отдельный API-параметр:
    // агент сам решает, как этим воспользоваться, вместо отдельного скан-пути.
    const withContext = (!chatting && landingScan)
      ? `${clean}\n\n(Уже посмотрели наш сайт ${landingScan.url}: ${landingScan.result.headline || "нашли кое-что"})`
      : clean
    setPending(p => [...p, { from: "user", text: clean, ts: Date.now() / 1000 }])
    setInput("")
    try {
      await api.chatPost(withContext)
      try { sessionStorage.removeItem(LANDING_SCAN_KEY) } catch { /* noop */ }
    } finally {
      setSending(false)
      setTimeout(load, 500)
    }
  }

  const allMessages = [...messages, ...pending]

  return (
    <motion.div key="chat" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
      style={{ position: "relative", width: "100%", maxWidth: 560, textAlign: "center" }}>
      <CeoBadge small={chatting} />
      <h1 className="display" style={{ fontSize: chatting ? 20 : 28, margin: "18px 0 8px", fontWeight: 600 }}>
        {chatting ? "Первое расследование" : "Расскажите о деле"}
      </h1>
      {!chatting && (
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 20 }}>
          В двух словах или подробно — как удобно. Есть бизнес, только открываетесь
          или просто идея — офис сам разберётся и всё, что можно, узнает сам.
        </p>
      )}

      {!chatting && landingScan && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, textAlign: "left", fontSize: 12.5,
          color: "var(--mercury-a)", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-md)", padding: "10px 14px", marginBottom: 16 }}>
          <span aria-hidden>✓</span>
          <span>Уже посмотрел {landingScan.url} — {landingScan.result.headline?.toLowerCase() || "учту это в работе"}</span>
        </div>
      )}

      {!chatting && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", marginBottom: 16 }}>
          {NICHE_CHIPS.map(chip => (
            <button key={chip} onClick={() => send(chip)} disabled={sending}
              style={{ fontSize: 12.5, padding: "7px 14px", borderRadius: "var(--radius-pill)", cursor: "pointer",
                border: "1px solid var(--hairline-strong)", background: "var(--surface-soft)", color: "var(--text-dim)" }}>
              {chip}
            </button>
          ))}
        </div>
      )}

      {chatting && (
        <div ref={feedRef} style={{ textAlign: "left", maxHeight: "48vh", overflowY: "auto",
          border: "1px solid var(--hairline)", borderRadius: "var(--radius-md)",
          background: "var(--surface-soft)", padding: 14, marginBottom: 12, display: "flex",
          flexDirection: "column", gap: 10 }}>
          {allMessages.map((m, i) => (
            <div key={m.id || i} style={{ alignSelf: m.from === "user" ? "flex-end" : "flex-start",
              maxWidth: "85%", padding: "8px 12px", borderRadius: "var(--radius-md)", fontSize: 13, lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              background: m.from === "user" ? MERCURY : "var(--surface)",
              color: m.from === "user" ? "#0b0b0b" : "var(--text)",
              border: m.from === "user" ? "none" : "1px solid var(--hairline)" }}>
              {m.text}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        {!chatting ? (
          <textarea value={input} onChange={e => setInput(e.target.value)} autoFocus rows={3} maxLength={2000}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input || "Не знаю, с чего начать — разберитесь сами") } }}
            placeholder="Например: делаю торты на заказ, хочу больше клиентов…"
            style={{
              width: "100%", resize: "vertical", padding: "13px 15px", fontSize: 14, lineHeight: 1.5,
              borderRadius: "var(--radius-md)", border: "1px solid var(--hairline-strong)",
              background: "var(--surface-soft)", color: "var(--text)", fontFamily: "inherit", outline: "none",
            }} />
        ) : (
          <input value={input} onChange={e => setInput(e.target.value)} autoFocus maxLength={2000}
            onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); send(input) } }}
            placeholder="Ответьте здесь…"
            style={{ flex: 1, padding: "11px 14px", fontSize: 13, borderRadius: "var(--radius-pill)",
              border: "1px solid var(--hairline)", background: "var(--surface-soft)",
              color: "var(--text)", outline: "none" }} />
        )}
      </div>

      <motion.button onClick={() => send(input || "Не знаю, с чего начать — разберитесь сами")}
        disabled={sending} whileTap={{ scale: 0.97 }}
        style={{
          width: "100%", marginTop: 10, padding: chatting ? "10px 20px" : "13px 20px",
          borderRadius: "var(--radius-pill)", border: "none", cursor: "pointer",
          background: MERCURY, color: "#0b0b0b", fontSize: 13, fontWeight: 600, opacity: sending ? 0.6 : 1,
        }}>
        {sending ? "…" : chatting ? "Отправить →" : input.trim() ? "Начать →" : "Разберитесь сами →"}
      </motion.button>
    </motion.div>
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
  // Раньше не было НИКАКОГО индикатора хода дела, кроме смены текста — на
  // реальном прогоне это занимает 40+ секунд, и без движения/счётчика
  // владелец бизнеса не понимает, зависло ли (найдено при живом аудите).
  // Бэкенд не даёт фиксированных шагов — честная неопределённая полоса
  // (не выдуманный процент) + секундомер вместо тишины.
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function poll() {
      if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null }
      const d = await api.onboardingResult().catch(() => ({ ready: false }))
      if (cancelled) return
      if (d.ready) { onReady(d); return }
      pollRef.current = window.setTimeout(poll, 2500)
    }
    poll()
    // Фоновая вкладка: Chromium троттлит/замораживает setTimeout в неактивных
    // табах (Intensive Timer Throttling) — реальный кейс: онбординг завис на
    // "Офис изучает…", хотя бэкенд уже отдавал ready:true несколько минут,
    // потому что вкладка была неактивна и таймер не тикал. Возврат фокуса
    // должен немедленно перепроверить готовность, а не ждать след. тик.
    function onVisible() {
      if (document.visibilityState === "visible") poll()
    }
    document.addEventListener("visibilitychange", onVisible)
    window.addEventListener("focus", onVisible)
    return () => {
      cancelled = true
      if (pollRef.current) clearTimeout(pollRef.current)
      document.removeEventListener("visibilitychange", onVisible)
      window.removeEventListener("focus", onVisible)
    }
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
      <div style={{ width: "60%", maxWidth: 200, height: 3, borderRadius: 999, background: "var(--hairline)",
        margin: "18px auto 8px", overflow: "hidden" }}>
        <motion.div
          animate={{ x: ["-100%", "220%"] }}
          transition={{ repeat: Infinity, duration: 1.6, ease: "easeInOut" }}
          style={{ width: "35%", height: "100%", borderRadius: 999, background: MERCURY }} />
      </div>
      <div className="mono" style={{ fontSize: 11, color: "var(--faint)" }}>
        {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")} — обычно занимает около минуты
      </div>
    </motion.div>
  )
}

// ── Результат: аналитика + точки роста + инициативы на выбор ────────────────
function ResultScreen({ result, onContinue }: { result: any; onContinue: () => void }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  // Клик по «Продолжить» — единственное место, где владелец подтверждает
  // первый дашборд (портрет §23). До этого office/loop.py держит BOOTSTRAP
  // на паузе перед проектированием ТЗ — эндпоинт делает клик содержательным
  // для бэкенда, а не только сменой фазы во фронтовом состоянии.
  // ⚠️ api.ts.postJSON НИКОГДА не бросает (сам ловит ошибку сети и молча
  // возвращает fallback=null) — .catch() здесь был мёртвым кодом, реальный
  // провал никак не отличался от успеха, и onContinue() срабатывал ВСЕГДА
  // (production-readiness worklist п.1). Если подтверждение не долетело —
  // office/loop.py остаётся в бесконечном ожидании, а владелец уже смотрит
  // следующий экран и не знает, что офис застрял. Теперь смотрим на сам
  // ответ (r?.ok), а не на факт отсутствия исключения.
  const [confirmError, setConfirmError] = useState(false)
  async function confirmAndContinue() {
    setConfirming(true)
    setConfirmError(false)
    const r = await api.confirmOnboardingResult()
    setConfirming(false)
    if (!r?.ok) { setConfirmError(true); return }
    onContinue()
  }
  // Map, не Set: раньше принятая и отклонённая инициатива выглядели ОДИНАКОВО
  // (просто тускнели) — активное согласие читалось как «отключено», тот же
  // визуальный язык, что и disabled-состояние (найдено при аудите). Теперь
  // принято/отклонено — два разных состояния, не один и тот же дым.
  const [decided, setDecided] = useState<Map<string, "accept" | "reject">>(new Map())
  const [decideError, setDecideError] = useState<string | null>(null)

  async function decide(id: string, action: "accept" | "reject") {
    setBusy(id)
    setDecideError(null)
    const r = await api.post(`/api/initiative/${id}/${action}`, {})
    setBusy(null)
    if (!r?.ok) { setDecideError(id); return }
    setDecided(prev => new Map(prev).set(id, action))
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
            <Bullet key={i} color="var(--mercury-a)" text={a} delay={i * 0.06} />
          ))}
        </Section>
      )}

      {result.growth_points?.length > 0 && (
        <Section title="Точки роста">
          {result.growth_points.map((g: string, i: number) => (
            <Bullet key={i} color="#a0e0ab" text={g} delay={i * 0.06} />
          ))}
        </Section>
      )}

      {result.initiatives?.length > 0 && (
        <Section title="Предложенные инициативы">
          {/* Живой аудит 2026-07-20: владелец, не принявший НИ ОДНУ карточку
              ниже, обнаруживал, что офис уже завёл и ведёт проект — без
              объяснения выглядело как «работа началась сама, непонятно
              почему». На деле офис ВСЕГДА начинает с базовой цели из брифа —
              карточки ниже НАДСТРОЙКА сверх нее, не условие старта. */}
          <div style={{ fontSize: 11.5, color: "var(--faint)", marginTop: -6, marginBottom: 12, lineHeight: 1.5 }}>
            Офис уже начинает работать над вашей целью из брифа — это не зависит
            от решения ниже. Карточки — ДОПОЛНИТЕЛЬНЫЕ возможности сверх этой
            работы; можно принять любую, все сразу или пропустить все.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {result.initiatives.map((ini: any) => {
              const verdict = decided.get(ini.id)
              return (
              <div key={ini.id} style={{
                padding: "14px 16px", borderRadius: "var(--radius-lg)", background: "var(--surface)",
                border: verdict === "accept" ? "1px solid #a0e0ab" : "1px solid var(--hairline-strong)",
                opacity: verdict === "reject" ? 0.45 : 1,
                transition: "opacity 0.2s, border-color 0.2s",
              }}>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, marginBottom: 5 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>{ini.title}</div>
                  {verdict === "accept" && (
                    <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 600, color: "#a0e0ab",
                      background: "rgba(160,224,171,0.15)", border: "1px solid #a0e0ab",
                      borderRadius: "var(--radius-pill)", padding: "2px 10px" }}>✓ Выбрано</span>
                  )}
                </div>
                {ini.rationale && <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5, marginBottom: 8 }}>{ini.rationale}</div>}
                {ini.expected_outcome && (
                  <div style={{ fontSize: 11, color: "var(--mercury-a)", marginBottom: 10 }}>📈 {ini.expected_outcome}</div>
                )}
                {!verdict && (
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
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
                    {decideError === ini.id && (
                      <span style={{ fontSize: 11, color: "#ff6b6b" }}>
                        Не сохранилось — проверьте связь и попробуйте ещё раз
                      </span>
                    )}
                  </div>
                )}
              </div>
            )})}
          </div>
        </Section>
      )}

      {!result.analysis?.length && !result.growth_points?.length && !result.initiatives?.length && (
        <div style={{ textAlign: "center", color: "var(--muted)", fontSize: 13, padding: "20px 0" }}>
          Офис пока не набрал материала для анализа — начнём работу, дальше он изучит всё сам.
        </div>
      )}

      {confirmError && (
        <div style={{ textAlign: "center", color: "#ff6b6b", fontSize: 12, marginTop: 22 }}>
          Не получилось передать подтверждение офису — проверьте связь и нажмите ещё раз.
        </div>
      )}
      <motion.button onClick={confirmAndContinue} disabled={confirming} whileTap={{ scale: 0.97 }}
        style={{
          width: "100%", marginTop: confirmError ? 8 : 22, padding: "13px 20px", borderRadius: "var(--radius-pill)", border: "none",
          cursor: confirming ? "default" : "pointer", background: MERCURY, color: "#0b0b0b", fontSize: 13, fontWeight: 600,
          opacity: confirming ? 0.7 : 1,
        }}>
        {confirming ? "Подтверждаю…" : "Продолжить →"}
      </motion.button>
    </motion.div>
  )
}

// ── Интеграции в момент пиковой мотивации (не спрятаны в настройках) ─────────
function IntegrationsScreen({ integrations, onContinue }: { integrations: any[]; onContinue: () => void }) {
  // Реальный найденный баг: onRefresh раньше был "const [, force] = useState(0)"
  // — чистая перерисовка без повторного запроса. IntegCard после успешного OAuth
  // зовёт onRefresh(), рассчитывая увидеть connected:true, но карточка брала это
  // поле из ТОГО ЖЕ пропса integrations (снятого один раз в начале онбординга,
  // ДО подключения) — кнопка «Подключить» оставалась активной даже после
  // реального успешного подключения. Теперь держим свою копию списка и правда
  // перезапрашиваем статус (api.integrations() — тот же источник, что и
  // ConnectionsView в «Ресурсы → Доступы»), обновляя только поле connected.
  const [items, setItems] = useState(integrations)
  useEffect(() => { setItems(integrations) }, [integrations])
  const refreshOne = () => {
    api.integrations().then(d => {
      const fresh = d.integrations || []
      setItems(prev => prev.map(i => {
        const f = fresh.find((x: any) => x.name === i.name)
        return f ? { ...i, connected: f.connected } : i
      }))
    }).catch(() => {})
  }
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
      style={{ position: "relative", width: "100%", maxWidth: 520, textAlign: "center" }}>
      <CeoBadge small />
      <h1 className="display" style={{ fontSize: 22, fontWeight: 600, margin: "14px 0 6px" }}>Подключим сразу?</h1>
      <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 20 }}>
        По вашему описанию офису пригодятся эти сервисы — можно позже, в «Ресурсы → Доступы»
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, textAlign: "left", marginBottom: 20 }}>
        {items.map(i => (
          <IntegCard key={i.name} integ={i} onRefresh={refreshOne} />
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

// Раньше маркер был эмодзи (📊/🌱) — рендерится с разным визуальным весом на
// разных ОС/шрифтах, расходится с дисциплиной остального интерфейса, где
// акценты — это токены-цвета, не картинки (найдено при живом дизайн-аудите).
// color задаёт смысл маркера (аналитика/точка роста) через тот же язык,
// что и остальной UI — точку, не эмодзи.
function Bullet({ color, text, delay }: { color?: string; text: string; delay: number }) {
  return (
    <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay }}
      style={{ display: "flex", gap: 10, fontSize: 13, color: "var(--text-dim)", lineHeight: 1.5, padding: "5px 0" }}>
      <span style={{ flexShrink: 0, width: 6, height: 6, borderRadius: "50%", marginTop: 6,
        background: color || "var(--mercury-a)" }} />
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
