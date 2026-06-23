import { useState, useEffect, useRef, useCallback } from "react"
import { AnimatePresence, motion } from "motion/react"
import { TopBar } from "./components/TopBar"
import { NavRail } from "./components/NavRail"
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
  const spotlightRef = useRef<HTMLDivElement>(null)
  const { state } = useOffice()

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

  useEffect(() => {
    function onMove(e: PointerEvent) {
      const el = spotlightRef.current
      if (el) { el.style.setProperty("--mx", `${e.clientX}px`); el.style.setProperty("--my", `${e.clientY}px`) }
    }
    window.addEventListener("pointermove", onMove)
    return () => window.removeEventListener("pointermove", onMove)
  }, [])

  const isOffice = view === "office"
  const gap = isMobile ? 8 : 12

  return (
    <div style={{
      display: "flex", flexDirection: "column", width: "100vw", height: "100vh",
      background: "var(--bg)", color: "var(--text)", position: "relative",
      transition: "background 0.4s ease, color 0.4s ease", overflow: "hidden",
    }}>
      {/* ── Амбиент Mercury ── */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, overflow: "hidden",
        opacity: "var(--blob-opacity)" as unknown as number, transition: "opacity 0.4s ease" }}>
        <div style={{ position: "absolute", top: "-15%", left: "-10%", width: "55vw", height: "55vw",
          background: "radial-gradient(circle at 50% 50%, rgba(160,224,171,0.10), transparent 60%)",
          filter: "blur(60px)", animation: "blob-drift-a 28s ease-in-out infinite" }} />
        <div style={{ position: "absolute", top: "40%", right: "-20%", width: "60vw", height: "60vw",
          background: "radial-gradient(circle at 50% 50%, rgba(255,172,46,0.09), transparent 60%)",
          filter: "blur(80px)", animation: "blob-drift-b 34s ease-in-out infinite" }} />
        <div style={{ position: "absolute", bottom: "-25%", left: "20%", width: "50vw", height: "50vw",
          background: "radial-gradient(circle at 50% 50%, rgba(165,45,37,0.07), transparent 60%)",
          filter: "blur(70px)", animation: "blob-drift-c 40s ease-in-out infinite" }} />
        <svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.5 }}>
          <defs>
            <linearGradient id="merc" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%"   stopColor="#a0e0ab" stopOpacity="0" />
              <stop offset="20%"  stopColor="#a0e0ab" />
              <stop offset="50%"  stopColor="#ffac2e" />
              <stop offset="80%"  stopColor="#a52d25" />
              <stop offset="100%" stopColor="#a52d25" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d="M -100,500 C 300,300 500,700 800,450 S 1300,200 1700,500" fill="none"
            stroke="url(#merc)" strokeWidth="1.5" strokeDasharray="1200"
            style={{ animation: "ribbon-flow 14s ease-in-out infinite" }} />
          <path d="M -100,650 C 350,500 650,800 950,550 S 1400,350 1700,600" fill="none"
            stroke="url(#merc)" strokeWidth="1" strokeDasharray="1200"
            style={{ animation: "ribbon-flow 18s ease-in-out infinite 4s" }} />
        </svg>
      </div>

      {/* Спотлайт */}
      <div ref={spotlightRef} className="mouse-spot" style={{
        position: "fixed", inset: 0, pointerEvents: "none", zIndex: 1,
        background: "radial-gradient(600px circle at var(--mx,50%) var(--my,50%), rgba(255,172,46,0.08), transparent 50%)",
        mixBlendMode: "screen",
      }} />

      {/* Grain */}
      <div style={{
        position: "fixed", inset: "-50%", pointerEvents: "none", zIndex: 1,
        opacity: "var(--grain-opacity)" as unknown as number,
        backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        animation: "grain 8s steps(6) infinite", mixBlendMode: "overlay",
      }} />

      {/* ── Контент ── */}
      <div style={{
        position: "relative", zIndex: 2, display: "flex", flexDirection: "column",
        width: "100%", height: "100%", padding: isMobile ? 8 : 14, gap,
      }}>
        <TopBar progress={state.progress.percent} progressNote={state.progress.note}
          cost={state.cost} model={state.model} connected={state.connected}
          theme={theme} onToggleTheme={() => setTheme(t => t === "dark" ? "light" : "dark")} isMobile={isMobile} />

        <div style={{ flex: 1, display: "flex", flexDirection: isMobile ? "column" : "row", minHeight: 0, gap }}>
          {!isMobile && <NavRail active={view} onChange={changeView} />}

          {/* Основная область: glass-карточка */}
          <div style={{ flex: 1, minWidth: 0, position: "relative", overflow: "hidden",
            borderRadius: isMobile ? "var(--radius-lg)" : "var(--radius-xl)",
            background: "var(--surface)",
            backdropFilter: "blur(28px) saturate(160%)", WebkitBackdropFilter: "blur(28px) saturate(160%)",
            border: "1px solid var(--hairline)", boxShadow: "var(--shadow-lg), 0 1px 0 var(--inset-hi) inset",
            transition: "background 0.4s ease, border-color 0.4s ease" }}>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={view}
                style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column" }}
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}>
                {view === "office"      && <OfficeView onOpenAgent={openAgent} />}
                {view === "project"     && <ProjectView />}
                {view === "team"        && <TeamView onOpenChat={openChat} />}
                {view === "chats"       && <ChatsView initialAgent={selectedAgent} />}
                {view === "results"     && <ResultsView />}
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
