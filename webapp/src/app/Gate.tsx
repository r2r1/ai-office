import { useCallback, useEffect, useState } from "react"
import { motion } from "motion/react"
import App from "./App"
import { OfficeProvider } from "../data/OfficeProvider"
import { LandingView } from "./landing/LandingView"
import { AuthModal } from "./auth/AuthModal"
import { api } from "../data/api"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"
type Phase = "loading" | "landing" | "app"

export function Gate() {
  const [phase, setPhase] = useState<Phase>("loading")
  const [authOpen, setAuthOpen] = useState(false)
  const [flags, setFlags] = useState({ github: false, dev: false, demo: false })

  const check = useCallback(async () => {
    const [me, bs] = await Promise.all([api.me(), api.briefStatus()])
    setFlags({ github: !!me?.github_available, dev: !!me?.dev_login, demo: !!bs?.demo })
    if (me?.authenticated) { setPhase("app"); return }
    setPhase("landing")
  }, [])

  useEffect(() => { check() }, [check])

  if (phase === "loading") return <Splash />
  if (phase === "app") return <OfficeProvider><App /></OfficeProvider>

  return (
    <>
      <LandingView
        onLogin={() => setAuthOpen(true)}
        onDemo={flags.demo ? () => setPhase("app") : undefined}
      />
      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        githubAvailable={flags.github}
        devLogin={flags.dev}
        onSuccess={() => { setAuthOpen(false); setPhase("app") }}
      />
    </>
  )
}

function Splash() {
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", gap: 16, background: "var(--bg)", color: "var(--text)" }}>
      <motion.span
        animate={{ scale: [1, 1.25, 1], opacity: [0.7, 1, 0.7] }}
        transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
        style={{ width: 12, height: 12, borderRadius: "50%", background: MERCURY, boxShadow: "0 0 18px rgba(255,172,46,0.6)" }} />
      <span style={{ fontSize: 12, color: "var(--muted)", letterSpacing: "0.5px" }}>Загрузка офиса…</span>
    </div>
  )
}
