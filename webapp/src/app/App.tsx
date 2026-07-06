import { useState, useEffect, useCallback, useRef } from "react"
import { AnimatePresence, motion } from "motion/react"
import { TopBar } from "./components/TopBar"
import { NavRail } from "./components/NavRail"
import { TabBridge } from "./components/TabBridge"
import { OfficeView } from "./components/OfficeView"
import { RightPanel } from "./components/RightPanel"
import { ProjectView } from "./views/ProjectView"
import { DashboardView } from "./views/DashboardView"
import { CompanyView } from "./views/CompanyView"
import { ChatsView } from "./views/ChatsView"
import { TeamView } from "./views/TeamView"
import { ScenarioView } from "./views/ScenarioView"
import { LeadsView } from "./views/LeadsView"
import { AccountView } from "./views/AccountView"
import { useOfficeSelector, useUnread } from "../data/OfficeProvider"
import { OnboardingFlow } from "./onboarding/OnboardingFlow"
import { api } from "../data/api"
import type { Section, Theme } from "./types"

/** Маленький чип-счётчик слоя памяти. */
function MemChip({ label }: { label: string }) {
  return (
    <span className="mono" style={{
      fontSize: 10, padding: "2px 7px", borderRadius: "var(--radius-pill)",
      background: "var(--surface-soft)", border: "1px solid var(--hairline)",
      color: "var(--text-dim)",
    }}>{label}</span>
  )
}

/** Один показатель внутри попапа "Статус офиса" — клик уводит на подробности
 * (Сводка/Компания), не открывает ещё один попап поверх попапа. */
function StatusChip({ label, value, color, onClick }: { label: string; value: string; color?: string; onClick?: () => void }) {
  return (
    <button onClick={onClick} style={{
      display: "flex", flexDirection: "column", gap: 2, padding: "6px 10px",
      borderRadius: "var(--radius-md)", border: "1px solid var(--hairline)",
      background: "var(--surface-soft)", cursor: onClick ? "pointer" : "default", textAlign: "left",
    }}>
      <span style={{ fontSize: 9.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.4px" }}>{label}</span>
      <span className="mono" style={{ fontSize: 12, color: color || "var(--text)" }}>{value}</span>
    </button>
  )
}

export default function App() {
  // Дефолт — Сводка (Command Center): что реально решить сегодня (Gap до
  // цели, инициативы, здоровье), а не анимация. «Офис» — живая сцена компании,
  // важная и эмоциональная, но НЕ то, с чем работают каждый день — остаётся
  // отдельным пунктом NavRail, просто больше не встречает пользователя первым
  // (продуктовый аудит сессии: экран без единой активной задачи не может быть
  // домом продукта). Первый визит после онбординга — отдельная ветка ниже.
  const [view, setView]             = useState<Section>("dashboard")
  // Режим раздела «Офис»: изо-сцена (флагман) или органиграмма/сценарии графа.
  const [officeMode, setOfficeMode] = useState<"scene" | "graph">("scene")
  const [theme, setTheme]           = useState<Theme>("dark")
  const [selectedAgent, setSelectedAgent] = useState<string | undefined>()
  const [panelOpen, setPanelOpen]   = useState(true)
  const [isMobile, setIsMobile]     = useState(
    typeof window !== "undefined" ? window.innerWidth < 760 : false,
  )
  // Только нужные срезы — App.tsx всегда смонтирован, и раньше useOffice() (весь
  // state) заставлял перерисовываться ВСЁ дерево на каждое SSE-событие (аудит
  // фронтенда: подтормаживание ввода при активном офисе). Теперь ре-рендер только
  // когда конкретно эти поля реально меняются.
  const progressPercent = useOfficeSelector(s => s.progress.percent)
  const progressNote = useOfficeSelector(s => s.progress.note)
  const cost = useOfficeSelector(s => s.cost)
  const connected = useOfficeSelector(s => s.connected)
  const ready = useOfficeSelector(s => s.ready)
  const unread = useUnread()
  const rowRef = useRef<HTMLDivElement>(null)
  // Чаты больше не отдельный пункт NavRail — бейдж непрочитанного переезжает
  // на «Команду» (оттуда теперь открывается инбокс).
  const navBadges = { team: unread.total }

  // Morning Digest
  const [digest, setDigest] = useState<any>(null)
  const [digestOpen, setDigestOpen] = useState(false)
  // Company Understanding
  const [understanding, setUnderstanding] = useState<any>(null)
  const [understandingOpen, setUnderstandingOpen] = useState(false)
  // Память офиса (трёхслойная)
  const [memory, setMemory] = useState<any>(null)
  // Autonomy level + Health + Trust (живые индикаторы governance)
  const [autonomyLevel, setAutonomyLevel] = useState<string>("")
  const [health, setHealth] = useState<{ company: number; status: string } | null>(null)
  const [trust, setTrust] = useState<{ company: number; streak: number } | null>(null)
  const [qualityMode, setQualityMode] = useState<{ icon: string; label: string } | null>(null)
  // Office pause/resume
  const [officePaused, setOfficePaused] = useState(false)
  // Онбординг показан локально пока бэкенд не подтвердил готовность брифа
  const [onboarded, setOnboarded] = useState(false)
  // Минимальный онбординг (BOS §5) отправляет бриф СРАЗУ (brief.set_brief
  // происходит в начале BOOTSTRAP, чтобы офис мог исследовать в фоне, пока
  // клиент смотрит "Офис изучает…" → результат → интеграции) — ready
  // становится true задолго до onDone(). Без этого флага гейт ниже терял
  // OnboardingFlow из-под ног ровно в момент, когда должны были появиться
  // экраны результата (реальный баг, пойман на живом прогоне).
  const [onboardingStarted, setOnboardingStarted] = useState(false)
  // Глубокая ссылка «открыть конкретный проект» — например, после принятия
  // инициативы (Сводка), чтобы не заставлять искать его самому в списке Работы.
  const [focusProjectId, setFocusProjectId] = useState<string | undefined>()

  const openAgent = useCallback((id: string) => { setSelectedAgent(id); setView("chats") }, [])
  const openChat  = useCallback((id: string) => { setSelectedAgent(id); setView("chats") }, [])

  function changeView(s: Section) {
    if (s !== "chats") setSelectedAgent(undefined)
    setView(s)
  }

  function goToProject(projectId: string) {
    setFocusProjectId(projectId)
    setView("project")
  }

  // Всплывающие попапы ("Пока тебя не было" / "Понимание компании") — контекст
  // прихода на страницу, не то, что должно висеть поверх контента после
  // навигации на другой раздел (реальный баг: обе всплывашки — абсолютно
  // спозиционированные поверх ВСЕГО контента, а не только шапки — оставались
  // открытыми поверх модалки проекта/другой вкладки после перехода).
  const [firstView] = useState(view)
  useEffect(() => {
    if (view === firstView) return  // не гасим при самом первом рендере
    setUnderstandingOpen(false)
    setDigestOpen(false)
  }, [view]) // eslint-disable-line

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 760px)")
    const update = () => setIsMobile(mq.matches)
    update(); mq.addEventListener("change", update)
    return () => mq.removeEventListener("change", update)
  }, [])

  useEffect(() => { document.documentElement.setAttribute("data-theme", theme) }, [theme])

  // Загружаем дайджест при старте (однократно)
  useEffect(() => {
    api.digest().then(d => {
      if (d && d.count > 0) { setDigest(d); setDigestOpen(true) }
    })
  }, [])

  async function handleToggleOffice() {
    if (officePaused) {
      await api.officeResume()
      setOfficePaused(false)
    } else {
      await api.officePause()
      setOfficePaused(true)
    }
  }

  // Единый поллинг вместо двух независимых таймеров (аудит фронтенда: были
  // отдельные интервалы на паузу-офиса и на understanding/knowledge/autonomy/
  // health/trust/capabilities — теперь один цикл, один набор запросов на тик).
  useEffect(() => {
    const load = () => {
      api.officeStatus().then(s => { if (s) setOfficePaused(s.paused) })
      api.understanding().then(u => { if (u) setUnderstanding(u) })
      api.knowledge().then(m => { if (m) setMemory(m) })
      api.get("/api/autonomy").then(a => { if (a?.level) setAutonomyLevel(a.level) }).catch(() => {})
      api.get("/api/health").then(h => { if (h?.company !== undefined) setHealth({ company: h.company, status: h.status }) }).catch(() => {})
      api.get("/api/trust").then(t => { if (t?.company !== undefined) setTrust({ company: t.company, streak: t.streak || 0 }) }).catch(() => {})
      api.get("/api/quality-modes").then(c => {
        const m = (c?.modes || []).find((x: any) => x.id === c?.mode)
        if (m) setQualityMode({ icon: m.icon, label: m.label })
      }).catch(() => {})
    }
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [])

  const isOffice = view === "office"
  const gap = isMobile ? 8 : 12

  // Онбординг: офис ещё не получил бриф → ведём клиента через CEO-интервью.
  // onboardingStarted держит поток на экране, даже когда ready успел стать
  // true раньше, чем клиент дошёл до "Готово" (см. комментарий у объявления).
  if ((ready === false || onboardingStarted) && !onboarded) {
    return <OnboardingFlow onStart={() => setOnboardingStarted(true)}
      onDone={() => { setOnboarded(true); setView("office") }} />
  }

  return (
    <div style={{
      display: "flex", flexDirection: "column", width: "100vw", height: "100vh",
      background: "var(--bg-grad, var(--bg))", color: "var(--text)", position: "relative",
      transition: "background 0.4s ease, color 0.4s ease", overflow: "hidden",
    }}>
      {/* ── Статичный Mercury-амбиент (рисуется один раз, без анимаций/фильтров → 0 нагрузки на GPU) ── */}
      <div style={{
        position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0,
        opacity: "var(--blob-opacity)" as unknown as number, transition: "opacity 0.4s ease",
        background:
          "radial-gradient(40vw 40vw at 12% 8%, rgba(160,224,171,0.07), transparent 60%)," +
          "radial-gradient(48vw 48vw at 88% 42%, rgba(255,172,46,0.06), transparent 60%)," +
          "radial-gradient(42vw 42vw at 30% 96%, rgba(165,45,37,0.05), transparent 60%)",
      }} />

      {/* ── Контент ── */}
      <div style={{
        position: "relative", zIndex: 2, display: "flex", flexDirection: "column",
        width: "100%", height: "100%", padding: isMobile ? 8 : 14, gap,
      }}>
        <TopBar progress={progressPercent} progressNote={progressNote}
          cost={cost} connected={connected}
          theme={theme} onToggleTheme={() => setTheme(t => t === "dark" ? "light" : "dark")}
          isMobile={isMobile}
          understanding={understanding}
          officePaused={officePaused}
          onToggleOffice={handleToggleOffice}
          autonomyLevel={autonomyLevel}
          health={health} trust={trust}
          qualityMode={qualityMode}
          onStatusClick={() => setUnderstandingOpen(o => !o)} />

        {/* Morning Digest — появляется поверх контента при наличии событий */}
        <AnimatePresence>
          {digestOpen && digest && (
            <motion.div
              initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}
              style={{
                position: "absolute", top: isMobile ? 64 : 70, left: isMobile ? 8 : 14, right: isMobile ? 8 : 14,
                zIndex: 100, background: "var(--surface)",
                border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-lg)",
                boxShadow: "var(--shadow)", padding: "14px 16px", maxWidth: 520,
              }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
                  ☀ Пока тебя не было ({digest.since})
                </div>
                <button onClick={() => setDigestOpen(false)}
                  style={{ background: "none", border: "none", cursor: "pointer",
                    color: "var(--muted)", fontSize: 16, lineHeight: 1, padding: "0 2px" }}>×</button>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {digest.items.slice(0, 6).map((item: any, i: number) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ fontSize: 14, flexShrink: 0, marginTop: 1 }}>{item.icon}</span>
                    <span style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.4 }}>{item.text}</span>
                  </div>
                ))}
                {digest.count > 6 && (
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                    и ещё {digest.count - 6} событий...
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Единый попап "Статус офиса" — раньше это были 4 отдельные кнопки
            топбара (Здоровье/Доверие/Автономность/Качество), уводящие в 2
            разных места, плюс отдельный попап "Понимание компании" —
            governance-виджеты дублировали смысл друг друга и захламляли
            топбар (найдено при аудите функционала). Теперь один клик — один
            попап со всеми разделами. */}
        <AnimatePresence>
          {understandingOpen && understanding && (
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: -8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: -8 }}
              transition={{ duration: 0.2 }}
              style={{
                position: "absolute", top: isMobile ? 64 : 70, right: isMobile ? 8 : 14,
                zIndex: 100, background: "var(--surface)",
                border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-lg)",
                boxShadow: "var(--shadow)", padding: "16px", width: 300, maxHeight: "70vh", overflowY: "auto",
              }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Статус офиса</div>
                <button onClick={() => setUnderstandingOpen(false)}
                  style={{ background: "none", border: "none", cursor: "pointer",
                    color: "var(--muted)", fontSize: 16 }}>×</button>
              </div>

              {(health || trust || autonomyLevel || qualityMode) && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14, paddingBottom: 14, borderBottom: "1px solid var(--hairline)" }}>
                  {health && (
                    <StatusChip label="Здоровье работы" value={`${health.status} ${health.company}`}
                      color={health.company >= 75 ? "#a0e0ab" : health.company >= 45 ? "#ffac2e" : "#e05a5a"}
                      onClick={() => { changeView("dashboard"); setUnderstandingOpen(false) }} />
                  )}
                  {trust && (
                    <StatusChip label="Доверие" value={`🤝 ${trust.company}`}
                      color={trust.company >= 70 ? "#a0e0ab" : trust.company >= 40 ? "#ffac2e" : "var(--text-dim)"}
                      onClick={() => { changeView("dashboard"); setUnderstandingOpen(false) }} />
                  )}
                  {autonomyLevel && (
                    <StatusChip label="Автономность" value={autonomyLevel}
                      onClick={() => { changeView("dashboard"); setUnderstandingOpen(false) }} />
                  )}
                  {qualityMode && (
                    <StatusChip label="Качество" value={`${qualityMode.icon} ${qualityMode.label}`}
                      onClick={() => { changeView("company"); setUnderstandingOpen(false) }} />
                  )}
                </div>
              )}

              {/* Раньше называлось "Понимание компании" — визуально рядом со "Здоровьем
                  работы" (то же число 0-100, тот же попап), но это разные показатели:
                  здесь — сколько данных о бизнесе есть у офиса (заполненность анкеты
                  онбординга), там — качество текущей работы отделов. Похожие названия
                  рядом реально путали (найдено при аудите). */}
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8, fontWeight: 600 }}>🧠 Данные о бизнесе — {understanding.score}%</div>
              <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: -6, marginBottom: 8 }}>
                Что офис узнал о вас на онбординге (не путать со «Здоровьем работы» выше)
              </div>
              {understanding.items.map((item: any, i: number) => (
                <div key={i} style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 5, display: "flex", gap: 6 }}>
                  <span>{item.icon}</span><span>{item.label}</span>
                </div>
              ))}
              {understanding.missing.length > 0 && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--hairline)" }}>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>Чтобы стать умнее:</div>
                  {understanding.missing.slice(0, 4).map((item: any, i: number) => (
                    <div key={i} style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 5 }}>
                      <span style={{ marginRight: 5 }}>{item.icon}</span>
                      <span style={{ fontWeight: 500 }}>{item.label}</span>
                      {item.hint && <div style={{ color: "var(--muted)", marginLeft: 18, marginTop: 1 }}>{item.hint}</div>}
                    </div>
                  ))}
                </div>
              )}
              {memory && memory.count > 0 && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--hairline)" }}>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
                    <span>🧩 Память офиса</span>
                    <span className="mono" style={{ opacity: 0.7 }}>{memory.count} фактов</span>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {memory.layers.user > 0 && <MemChip label={`клиент ${memory.layers.user}`} />}
                    {memory.layers.global > 0 && <MemChip label={`бизнес ${memory.layers.global}`} />}
                    {memory.layers.department > 0 && <MemChip label={`отделы ${memory.layers.department}`} />}
                  </div>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        <div ref={rowRef} style={{ flex: 1, display: "flex", flexDirection: isMobile ? "column" : "row", minHeight: 0, gap, position: "relative" }}>

          {!isMobile && <TabBridge active={view} enabled={!isMobile} containerRef={rowRef} />}
          {!isMobile && <NavRail active={view} onChange={changeView} badges={navBadges} />}

          {/* Основная область: glass-островок */}
          <div id="main-panel" className="glass" style={{ flex: 1, minWidth: 0, position: "relative", 
            borderRadius: isMobile ? "var(--radius-lg)" : "var(--radius-xl)", overflow: "hidden",
            transition: "background 0.4s ease, border-color 0.4s ease" }}>
            {/* Офис / Сценарии — переключатель вида одного раздела, не два пункта
                NavRail (карта сайта, рефакторинг 2026-07-05): изо-сцена и
                органиграмма показывают одну и ту же компанию под разными углами. */}
            {view === "office" && (
              <div style={{ position: "absolute", top: 14, right: 14, zIndex: 10, display: "flex", gap: 2,
                padding: 3, borderRadius: "var(--radius-pill)", background: "var(--surface-soft)",
                border: "1px solid var(--hairline)" }}>
                {(["scene", "graph"] as const).map(m => (
                  <button key={m} onClick={() => setOfficeMode(m)}
                    style={{
                      padding: "6px 14px", borderRadius: "var(--radius-pill)", border: "none", cursor: "pointer",
                      fontSize: 12, fontWeight: 500, transition: "background 0.15s, color 0.15s",
                      background: officeMode === m ? "var(--mercury-a)" : "transparent",
                      color: officeMode === m ? "#0a0a0a" : "var(--text-dim)",
                    }}>
                    {m === "scene" ? "Офис" : "Сценарии"}
                  </button>
                ))}
              </div>
            )}
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={view === "office" ? `office-${officeMode}` : view}
                style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column" }}
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}>
                {view === "office" && officeMode === "scene" && <OfficeView onOpenAgent={openAgent} />}
                {view === "office" && officeMode === "graph" && <ScenarioView onOpenChat={openChat} />}
                {view === "dashboard"   && <DashboardView onNavigate={changeView} onOpenProject={goToProject} />}
                {view === "project"     && <ProjectView focusProjectId={focusProjectId} onFocusHandled={() => setFocusProjectId(undefined)} />}
                {view === "team"        && <TeamView onOpenChat={openChat} onOpenInbox={() => openChat("")} />}
                {view === "leads"       && <LeadsView />}
                {view === "chats"       && <ChatsView initialAgent={selectedAgent} />}
                {view === "company"     && <CompanyView />}
                {view === "account"     && <AccountView />}
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Правая панель — только на офисе и не мобайл */}
          {isOffice && !isMobile && (
            <RightPanel collapsed={!panelOpen} onToggle={() => setPanelOpen(p => !p)} />
          )}

          {isMobile && (
            <div style={{ display: "flex", justifyContent: "center", paddingBottom: 4, width: "100%", minWidth: 0 }}>
              <NavRail active={view} onChange={changeView} orientation="horizontal" badges={navBadges} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
