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
import type { Section, Theme } from "./types"

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

  const isOffice = view === "office"
  const gap = isMobile ? 8 : 12

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
          onOpenAccount={() => changeView("account")} isMobile={isMobile} />

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
