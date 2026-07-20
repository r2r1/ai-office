import { Suspense, lazy, useCallback, useEffect, useState } from "react"
import { motion } from "motion/react"
import { OfficeProvider } from "../data/OfficeProvider"
import { LandingView } from "./landing/LandingView"
import { AuthModal } from "./auth/AuthModal"
import { api, setAuthExpiredHandler } from "../data/api"

// Посетитель лендинга ещё не авторизован — незачем качать весь авторизованный
// App (все 9 вкладок, ProjectView на 1164 строки и т.д.) вместе с публичной
// страницей. Раньше App импортировался статически прямо здесь — единственный
// бандл выходил 567KB/174KB gzip (Vite сам предупреждал при сборке), и его
// целиком получал каждый, кто просто зашёл посмотреть лендинг.
const App = lazy(() => import("./App"))

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"
type Phase = "loading" | "landing" | "app"

export function Gate() {
  const [phase, setPhase] = useState<Phase>("loading")
  const [authOpen, setAuthOpen] = useState(false)
  const [flags, setFlags] = useState({ github: false, google: false, dev: false, demo: false })
  // Истёкшая сессия (round2 audit, N9): раньше проверка auth была ТОЛЬКО при
  // монтировании — если сессия протухала посреди работы (14-дневный TTL,
  // ручной logout в другой вкладке), все вкладки молча показывали пустые
  // списки без единого "войдите заново". api.setAuthExpiredHandler ловит
  // первый же 401 от любого запроса и сбрасывает приложение на лендинг.
  const [sessionExpired, setSessionExpired] = useState(false)

  const check = useCallback(async () => {
    const [me, bs] = await Promise.all([api.me(), api.briefStatus()])
    setFlags({ github: !!me?.github_available, google: !!me?.google_available, dev: !!me?.dev_login, demo: !!bs?.demo })
    if (me?.authenticated) { setPhase("app"); return }
    setPhase("landing")
  }, [])

  useEffect(() => { check() }, [check])

  useEffect(() => {
    setAuthExpiredHandler(() => {
      setSessionExpired(true)
      setPhase("landing")
      setAuthOpen(true)
    })
    return () => setAuthExpiredHandler(null)
  }, [])

  if (phase === "loading") return <Splash />
  if (phase === "app") return (
    <OfficeProvider>
      <Suspense fallback={<Splash />}><App /></Suspense>
    </OfficeProvider>
  )

  return (
    <>
      <LandingView
        onLogin={() => setAuthOpen(true)}
        onDemo={flags.demo ? () => setPhase("app") : undefined}
        notice={sessionExpired ? "Сессия истекла — войдите заново, чтобы продолжить." : undefined}
      />
      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        githubAvailable={flags.github}
        googleAvailable={flags.google}
        devLogin={flags.dev}
        onSuccess={() => { setAuthOpen(false); setSessionExpired(false); setPhase("app") }}
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
