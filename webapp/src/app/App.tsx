import { useState, useEffect, useCallback, useRef } from "react"
import { AnimatePresence, motion } from "motion/react"
import { TopBar } from "./components/TopBar"
import { NavRail } from "./components/NavRail"
import { TabBridge } from "./components/TabBridge"
import { OfficeView } from "./components/OfficeView"
import { RightPanel } from "./components/RightPanel"
import { ProjectView } from "./views/ProjectView"
import { ChatsView } from "./views/ChatsView"
import { TeamView } from "./views/TeamView"
import { ResultsView } from "./views/ResultsView"
import { ConnectionsView } from "./views/ConnectionsView"
import { AccountView } from "./views/AccountView"
import { useOffice } from "../data/OfficeProvider"
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

export default function App() {
  const [view, setView]             = useState<Section>("team")
  const [theme, setTheme]           = useState<Theme>("dark")
  const [selectedAgent, setSelectedAgent] = useState<string | undefined>()
  const [panelOpen, setPanelOpen]   = useState(true)
  const [isMobile, setIsMobile]     = useState(
    typeof window !== "undefined" ? window.innerWidth < 760 : false,
  )
  const { state } = useOffice()
  const rowRef = useRef<HTMLDivElement>(null)

  // Morning Digest
  const [digest, setDigest] = useState<any>(null)
  const [digestOpen, setDigestOpen] = useState(false)
  // Company Understanding
  const [understanding, setUnderstanding] = useState<any>(null)
  const [understandingOpen, setUnderstandingOpen] = useState(false)
  // Память офиса (трёхслойная)
  const [memory, setMemory] = useState<any>(null)
  // Office pause/resume
  const [officePaused, setOfficePaused] = useState(false)
  // Онбординг показан локально пока бэкенд не подтвердил готовность брифа
  const [onboarded, setOnboarded] = useState(false)

  const openAgent = useCallback((id: string) => { setSelectedAgent(id); setView("chats") }, [])
  const openChat  = useCallback((id: string) => { setSelectedAgent(id); setView("chats") }, [])

  function changeView(s: Section) {
    if (s !== "chats") setSelectedAgent(undefined)
    setView(s)
  }

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

  // Статус офиса (пауза)
  useEffect(() => {
    api.officeStatus().then(s => { if (s) setOfficePaused(s.paused) })
    const t = setInterval(() => {
      api.officeStatus().then(s => { if (s) setOfficePaused(s.paused) })
    }, 15000)
    return () => clearInterval(t)
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

  // Загружаем понимание компании + память офиса
  useEffect(() => {
    const load = () => {
      api.understanding().then(u => { if (u) setUnderstanding(u) })
      api.knowledge().then(m => { if (m) setMemory(m) })
    }
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  const isOffice = view === "office"
  const gap = isMobile ? 8 : 12

  // Онбординг: офис ещё не получил бриф → ведём клиента через CEO-интервью.
  if (state.ready === false && !onboarded) {
    return <OnboardingFlow onDone={() => { setOnboarded(true); setView("office") }} />
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
        <TopBar progress={state.progress.percent} progressNote={state.progress.note}
          cost={state.cost} model={state.model} connected={state.connected}
          theme={theme} onToggleTheme={() => setTheme(t => t === "dark" ? "light" : "dark")}
          onOpenAccount={() => changeView("account")} isMobile={isMobile}
          understanding={understanding}
          onUnderstandingClick={() => setUnderstandingOpen(o => !o)}
          officePaused={officePaused}
          onToggleOffice={handleToggleOffice} />

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

        {/* Попап "Понимание компании" */}
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
                boxShadow: "var(--shadow)", padding: "16px", width: 280,
              }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Понимание компании</div>
                <button onClick={() => setUnderstandingOpen(false)}
                  style={{ background: "none", border: "none", cursor: "pointer",
                    color: "var(--muted)", fontSize: 16 }}>×</button>
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
          {!isMobile && <NavRail active={view} onChange={changeView} />}

          {/* Основная область: glass-островок */}
          <div id="main-panel" className="glass" style={{ flex: 1, minWidth: 0, position: "relative", 
            borderRadius: isMobile ? "var(--radius-lg)" : "var(--radius-xl)", overflow: "hidden",
            transition: "background 0.4s ease, border-color 0.4s ease" }}>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={view}
                style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column" }}
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}>
                {view === "office"      && <OfficeView onOpenAgent={openAgent} />}
                {view === "project"     && <ProjectView />}
                {view === "team"        && <TeamView onOpenChat={openChat} />}
                {view === "results"     && <ResultsView />}
                {view === "chats"       && <ChatsView initialAgent={selectedAgent} />}
                {view === "connections" && <ConnectionsView />}
                {view === "account"     && <AccountView />}
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Правая панель — только на офисе и не мобайл */}
          {isOffice && !isMobile && (
            <RightPanel collapsed={!panelOpen} onToggle={() => setPanelOpen(p => !p)} />
          )}

          {isMobile && (
            <div style={{ display: "flex", justifyContent: "center", paddingBottom: 4 }}>
              <NavRail active={view} onChange={changeView} orientation="horizontal" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
