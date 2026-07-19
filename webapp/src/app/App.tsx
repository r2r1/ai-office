import { useState, useEffect, useCallback, useRef, Suspense, lazy } from "react"
import { AnimatePresence, motion } from "motion/react"
import { TopBar } from "./components/TopBar"
import { NavRail } from "./components/NavRail"
import { TabBridge } from "./components/TabBridge"
import { OfficeView } from "./components/OfficeView"
import { RightPanel } from "./components/RightPanel"
import { useOfficeSelector, useUnread, markReady } from "../data/OfficeProvider"
import { api } from "../data/api"
import type { Section, Theme } from "./types"

// Вкладки рендерятся ПО ОДНОЙ за раз (переключатель view ниже) — идеальная
// граница код-сплиттинга: клиент, который весь визит смотрит только «Сводку»,
// раньше всё равно качал ProjectView (1164 строки), CompanyView (778 строк) и
// остальные 7 вкладок в одном общем бандле. OnboardingFlow — тоже: нужен
// ровно один раз в жизни тенанта, но раньше грузился всем и всегда.
const ProjectView   = lazy(() => import("./views/ProjectView").then(m => ({ default: m.ProjectView })))
const DashboardView = lazy(() => import("./views/DashboardView").then(m => ({ default: m.DashboardView })))
// IA-пересборка (вариант C, живой дизайн-аудит): бывшая "Компания" (10 под-
// вкладок вперемешку) разделена на SettingsView (кто мы/куда идём/аккаунт) и
// ResourcesView (Хранилище/Доступы/Приложения/MCP) — Роли/Скиллы переехали в
// TeamView, к живым агентам тех же ролей.
const SettingsView  = lazy(() => import("./views/SettingsView").then(m => ({ default: m.SettingsView })))
const ResourcesView = lazy(() => import("./views/ResourcesView").then(m => ({ default: m.ResourcesView })))
const ChatsView     = lazy(() => import("./views/ChatsView").then(m => ({ default: m.ChatsView })))
const TeamView      = lazy(() => import("./views/TeamView").then(m => ({ default: m.TeamView })))
const ScenarioView  = lazy(() => import("./views/ScenarioView").then(m => ({ default: m.ScenarioView })))
// "Лиды" → "Результаты" (product-manager разбор): лиды — один из ИСХОДОВ
// работы, не процесс наравне с "Работа"/"Команда"; реестр типов результата
// (results.py), сейчас Лиды+Сайты.
const ResultsView   = lazy(() => import("./views/ResultsView").then(m => ({ default: m.ResultsView })))
const OnboardingFlow = lazy(() => import("./onboarding/OnboardingFlow").then(m => ({ default: m.OnboardingFlow })))

// Разбивка Company Understanding по доменам (understanding.py.payload()["domains"])
// — backend уже считал это, но фронт нигде не показывал (найдено при добавлении
// Confidence): "Продажи 12%" мотивирует подключить CRM сильнее общего процента.
const DOMAIN_LABELS: Record<string, string> = {
  business: "Бизнес", marketing: "Маркетинг", sales: "Продажи", finance: "Финансы", team: "Команда",
}

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
  const [isMobile, setIsMobile]     = useState(
    typeof window !== "undefined" ? window.innerWidth < 760 : false,
  )
  // Режим раздела «Офис»: изо-сцена (флагман) или органиграмма/сценарии графа.
  // На узком viewport фиксированная многоколоночная изо-сцена физически не
  // помещается (комнаты обрезаются, подписи агентов накладываются друг на
  // друга — реальный баг со скриншотов) — «Сценарии» уже адаптированы под
  // мобильный как вертикальный список, поэтому там дефолт другой.
  const [officeMode, setOfficeMode] = useState<"scene" | "graph">(isMobile ? "graph" : "scene")
  const [theme, setTheme]           = useState<Theme>("dark")
  const [selectedAgent, setSelectedAgent] = useState<string | undefined>()
  const [panelOpen, setPanelOpen]   = useState(true)
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
  const newLeads = useOfficeSelector(s => s.leads.filter((l: any) => (l.status || "new") === "new").length)
  // Чаты больше не отдельный пункт NavRail — бейдж непрочитанного переезжает
  // на «Команду» (оттуда теперь открывается инбокс).
  const navBadges = { team: unread.total, results: newLeads }

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
  // Office pause/resume — reason различает «остановил администратор» от
  // «упёрлись в бюджетный лимит», это два разных сообщения клиенту (живой
  // фидбек: раньше пауза была видна только крошечной иконкой ⏸ в TopBar,
  // без объяснения ПОЧЕМУ и что делать).
  const [officePaused, setOfficePaused] = useState(false)
  const [officePauseReason, setOfficePauseReason] = useState("")
  const [limitInfo, setLimitInfo] = useState<{ spent: number; total_usd: number; over_limit: boolean } | null>(null)
  const [focusSettingsTab, setFocusSettingsTab] = useState<string | undefined>()
  const goToLimits = useCallback(() => { setFocusSettingsTab("limits"); setView("settings") }, [])
  // Онбординг показан локально пока бэкенд не подтвердил готовность брифа
  const [onboarded, setOnboarded] = useState(false)
  // Минимальный онбординг (BOS §5) отправляет бриф СРАЗУ (brief.set_brief
  // происходит в начале BOOTSTRAP, чтобы офис мог исследовать в фоне, пока
  // клиент смотрит "Офис изучает…" → результат → интеграции) — ready
  // становится true задолго до onDone(). Без этого флага гейт ниже терял
  // OnboardingFlow из-под ног ровно в момент, когда должны были появиться
  // экраны результата (реальный баг, пойман на живом прогоне).
  const [onboardingStarted, setOnboardingStarted] = useState(false)
  // Дашборд ждёт подтверждения владельца (портрет §23), а страница, на
  // которой этот клик делается (result-фаза OnboardingFlow), была закрыта/
  // перезагружена ДО клика — обычный гейт ниже (`ready === false`) уже не
  // видит этот случай (бриф давно готов), `onboardingStarted` сброшен новым
  // mount'ом. Без этого владелец физически не может разблокировать office/
  // loop.py, застрявший перед architect.run_async — реальный найденный
  // разрыв, проверяется через тот же blocking-флаг, что и backend-гейт.
  const [dashboardBlocking, setDashboardBlocking] = useState(false)
  useEffect(() => {
    if (ready !== true || onboardingStarted || onboarded) return
    api.onboardingResult().then(d => { if (d?.blocking) setDashboardBlocking(true) }).catch(() => {})
  }, [ready, onboardingStarted, onboarded])
  // Глубокая ссылка «открыть конкретный проект» — например, после принятия
  // инициативы (Сводка), чтобы не заставлять искать его самому в списке Работы.
  const [focusProjectId, setFocusProjectId] = useState<string | undefined>()
  // Глубокая ссылка «открыть папку ЭТОГО проекта в Хранилище» — раньше из
  // страницы проекта нельзя было попасть в его же папку иначе, чем вручную
  // искать её в общем дереве файлов (живой дизайн-аудит).
  const [focusStorageProject, setFocusStorageProject] = useState<string | undefined>()

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

  function goToStorage(workspaceDir: string) {
    setFocusStorageProject(workspaceDir || "")
    setView("resources")
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
      api.officeStatus().then(s => { if (s) { setOfficePaused(s.paused); setOfficePauseReason(s.reason || "") } })
      api.get("/api/limits").then(l => { if (l) setLimitInfo({ spent: l.spent || 0, total_usd: l.total_usd || 0, over_limit: !!l.over_limit }) }).catch(() => {})
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
  if ((ready === false || onboardingStarted || dashboardBlocking) && !onboarded) {
    return (
      <Suspense fallback={null}>
        <OnboardingFlow onStart={() => setOnboardingStarted(true)} forceResultPhase={dashboardBlocking}
          onDone={() => { markReady(); setOnboarded(true); setView("office") }} />
      </Suspense>
    )
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
          limitTotalUsd={limitInfo?.total_usd} limitOverLimit={limitInfo?.over_limit} onOpenLimits={goToLimits}
          onStatusClick={() => setUnderstandingOpen(o => !o)} />

        {/* Офис остановлен — админом, бюджетным лимитом или самим клиентом.
            Раньше об этом говорила только крошечная иконка ⏸ в TopBar (легко
            пропустить); теперь — явная плашка с причиной и, если дело в
            деньгах, кнопкой на «Лимиты» (реальную оплату подключим отдельно —
            пока «пополнить» значит поднять total_usd). */}
        {(officePaused || limitInfo?.over_limit) && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
            padding: "10px 16px", borderRadius: "var(--radius-lg)",
            background: limitInfo?.over_limit ? "rgba(224,85,90,0.12)" : "var(--surface-card)",
            border: `1px solid ${limitInfo?.over_limit ? "var(--danger)" : "var(--hairline-strong)"}`,
            fontSize: 13, color: "var(--text)", flexWrap: "wrap",
          }}>
            <span>
              {officePaused
                ? `⏸ Офис на паузе${officePauseReason ? ` — ${officePauseReason}` : "."}`
                : "⚠ Бюджетный лимит исчерпан — офис вот-вот встанет на паузу."}
            </span>
            {limitInfo?.over_limit ? (
              <button onClick={goToLimits}
                style={{ border: "1px solid var(--danger)", borderRadius: "var(--radius-md)", padding: "6px 14px",
                  background: "transparent", color: "var(--danger)", cursor: "pointer", fontSize: 12, flexShrink: 0 }}>
                Пополнить
              </button>
            ) : (
              <button onClick={handleToggleOffice}
                style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-md)", padding: "6px 14px",
                  background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 12, flexShrink: 0 }}>
                Возобновить
              </button>
            )}
          </div>
        )}

        {/* Morning Digest — появляется поверх контента при наличии событий */}
        <AnimatePresence>
          {digestOpen && digest && (
            <motion.div
              initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}
              style={{
                position: "absolute", top: isMobile ? 64 : 70, left: isMobile ? 8 : 14, right: isMobile ? 8 : 14,
                zIndex: 100, background: "var(--surface-card)",
                border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-lg)",
                boxShadow: "var(--shadow)", padding: "14px 16px", maxWidth: 520,
                // Явно завязано на digestOpen, НЕ на факт присутствия в DOM (issue #12):
                // если AnimatePresence по какой-то причине не завершит exit-анимацию
                // (например setDigestOpen(false) прилетел в том же тике, что смена view,
                // см. эффект выше), «призрачный» узел остаётся в DOM невидимым, но с
                // pointer-events по умолчанию — и перехватывает клики по NavRail/контенту
                // под собой НАВСЕГДА, до ручного location.reload(). Раньше это заметили
                // только визуально («не то, что должно висеть поверх контента»), но не
                // как потерю кликабельности НАВСЕГДА — реальный кейс живого прогона.
                pointerEvents: digestOpen ? "auto" : "none",
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
                zIndex: 100, background: "var(--surface-card)",
                border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-lg)",
                boxShadow: "var(--shadow)", padding: "16px", width: 300, maxHeight: "70vh", overflowY: "auto",
                // См. комментарий у digest-попапа выше (issue #12) — тот же защитный приём.
                pointerEvents: understandingOpen ? "auto" : "none",
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
                      onClick={() => { changeView("settings"); setUnderstandingOpen(false) }} />
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

              {understanding.domains && Object.keys(understanding.domains).length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  {Object.entries(DOMAIN_LABELS).map(([key, label]) => {
                    const v = understanding.domains[key] ?? 0
                    // Фаза 3 (docs/first-investigation-plan-2026-07-16.md): гранулярный
                    // чек-лист — ПОД-УРОВЕНЬ внутри этого же домена (не отдельная
                    // структура) — "Бизнес 40%" сам по себе ничего не говорит владельцу,
                    // а "✓ продукты ○ рынок ○ регион" сразу видно, чего конкретно не хватает.
                    const checklistForDomain = (understanding.checklist || []).filter((c: any) => c.domain === key)
                    return (
                      <div key={key} style={{ marginBottom: 8 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 10.5, color: "var(--text-dim)", width: 70, flexShrink: 0 }}>{label}</span>
                          <div style={{ flex: 1, height: 4, borderRadius: 2, background: "var(--hairline)", overflow: "hidden" }}>
                            <div style={{ width: `${v}%`, height: "100%", borderRadius: 2,
                              background: v >= 60 ? "#a0e0ab" : v >= 30 ? "#ffac2e" : "var(--faint)" }} />
                          </div>
                          <span className="mono" style={{ fontSize: 9.5, color: "var(--faint)", width: 26, textAlign: "right" }}>{v}%</span>
                        </div>
                        {checklistForDomain.length > 0 && (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "3px 10px", marginTop: 3, marginLeft: 78 }}>
                            {checklistForDomain.map((c: any) => (
                              <span key={c.label} style={{ fontSize: 10, color: c.done ? "#a0e0ab" : "var(--faint)" }}>
                                {c.done ? "✓" : "○"} {c.label}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {typeof understanding.confidence === "number" && (
                <div style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--hairline)" }}>
                  <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 600, marginBottom: 4 }}>
                    🎯 Уверенность в выводах — {understanding.confidence}%
                  </div>
                  <div style={{ fontSize: 10, color: "var(--faint)", marginBottom: 6 }}>
                    Насколько можно доверять оценке (не путать с «Данные о бизнесе» выше — там сколько
                    известно, здесь — насколько это проверено, а не просто со слов)
                  </div>
                  {(understanding.confidence_reasons || []).map((r: string, i: number) => (
                    <div key={i} style={{ fontSize: 10.5, color: "var(--text-dim)", marginBottom: 2 }}>· {r}</div>
                  ))}
                </div>
              )}

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
            {/* mode="wait" убран (реальный баг, найден живым тестом): если exit-анимация
                уходящего вида по любой причине не завершается (застряла/анимация
                прервана внешним событием), "wait" держит старый child примонтированным
                НАВСЕГДА и никогда не монтирует новый — навигация выглядит полностью
                мёртвой (клик по NavRail регистрируется, view меняется в состоянии,
                но экран не переключается ни разу, ни при повторных попытках). Основная
                навигация продукта не должна зависеть от завершения декоративного
                перехода — то же архитектурное решение, что уже применялось для
                Digest/Understanding-попапов (issue #12). Default-режим монтирует новый
                view сразу же, не дожидаясь ухода старого. */}
            <AnimatePresence initial={false}>
              <motion.div key={view === "office" ? `office-${officeMode}` : view}
                style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column" }}
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                // pointerEvents: "none" В САМОМ exit-варианте (не только в стилях) —
                // применяется framer-motion СРАЗУ на старте exit (строковое свойство не
                // тянется), а не после завершения анимации. Живой тест этой же сессии
                // показал, что exit может не долетать доunmount вообще (см. комментарий
                // у AnimatePresence выше) — без этого призрачный узел с прошлым видом мог
                // бы бесконечно перехватывать клики поверх уже смонтированного нового вида.
                exit={{ opacity: 0, y: -6, pointerEvents: "none" }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}>
                <Suspense fallback={null}>
                  {view === "office" && officeMode === "scene" && <OfficeView onOpenAgent={openAgent} />}
                  {view === "office" && officeMode === "graph" && <ScenarioView onOpenChat={openChat} />}
                  {view === "dashboard"   && <DashboardView onNavigate={changeView} onOpenProject={goToProject} />}
                  {view === "project"     && <ProjectView focusProjectId={focusProjectId} onFocusHandled={() => setFocusProjectId(undefined)} onOpenStorage={goToStorage} />}
                  {view === "team"        && <TeamView onOpenChat={openChat} onOpenInbox={() => openChat("")} />}
                  {view === "results"     && <ResultsView />}
                  {view === "chats"       && <ChatsView initialAgent={selectedAgent} />}
                  {view === "resources"   && <ResourcesView focusStorageProject={focusStorageProject} onFocusHandled={() => setFocusStorageProject(undefined)} />}
                  {view === "settings"    && <SettingsView initialTab={focusSettingsTab} onInitialTabHandled={() => setFocusSettingsTab(undefined)} />}
                </Suspense>
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
