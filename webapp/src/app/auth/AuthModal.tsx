import { useEffect, useRef, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { api } from "../../data/api"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface AuthModalProps {
  open: boolean
  onClose: () => void
  onSuccess: () => void
  githubAvailable: boolean
  googleAvailable?: boolean
  devLogin: boolean
}

type Mode = "choose" | "github" | "email"

export function AuthModal({ open, onClose, onSuccess, githubAvailable, googleAvailable, devLogin }: AuthModalProps) {
  const [mode, setMode] = useState<Mode>("choose")

  useEffect(() => { if (open) setMode("choose") }, [open])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={onClose}
          style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center",
            background: "rgba(0,0,0,0.55)", backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)", padding: 20 }}>
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 320, damping: 28 }}
            onClick={e => e.stopPropagation()}
            className="glass"
            style={{ width: "100%", maxWidth: 420, borderRadius: "var(--radius-xl)", padding: 32, position: "relative" }}>

            <button onClick={onClose} aria-label="Закрыть"
              style={{ position: "absolute", top: 16, right: 16, width: 30, height: 30, border: "1px solid var(--hairline)",
                borderRadius: "50%", background: "transparent", color: "var(--muted)", cursor: "pointer", fontSize: 15 }}>
              x
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
              <span style={{ width: 9, height: 9, borderRadius: "50%", background: MERCURY, boxShadow: "0 0 12px rgba(255,172,46,0.6)" }} />
              <span style={{ fontSize: 14, letterSpacing: "0.5px" }}>AI <em style={{ fontFamily: "var(--font-display)", color: "var(--muted)" }}>office</em></span>
            </div>

            <AnimatePresence mode="wait">
              {mode === "choose" && (
                <Pane key="choose">
                  <Title>Вход в офис</Title>
                  <Sub>Подключите аккаунт, чтобы запустить свою команду AI-агентов.</Sub>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 22 }}>
                    {githubAvailable && (
                      <BigButton onClick={() => setMode("github")} primary>
                        <GitHubGlyph /> Продолжить через GitHub
                      </BigButton>
                    )}
                    {googleAvailable && (
                      <BigButton onClick={() => { window.location.href = "/auth/google/start?mode=login" }}>
                        <GoogleGlyph /> Продолжить через Google
                      </BigButton>
                    )}
                    {devLogin && (
                      <BigButton onClick={() => setMode("email")}>
                        Войти по email
                      </BigButton>
                    )}
                    {!githubAvailable && !googleAvailable && !devLogin && (
                      <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.6 }}>
                        Методы входа не настроены.
                      </div>
                    )}
                  </div>
                </Pane>
              )}
              {mode === "github" && <GitHubPane key="github" onBack={() => setMode("choose")} onSuccess={onSuccess} />}
              {mode === "email"  && <EmailPane  key="email"  onBack={() => setMode("choose")} onSuccess={onSuccess} />}
            </AnimatePresence>

            <div style={{ marginTop: 22, fontSize: 10.5, color: "var(--faint)", textAlign: "center", lineHeight: 1.5 }}>
              Продолжая, вы соглашаетесь с условиями использования сервиса.
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function GitHubPane({ onBack, onSuccess }: { onBack: () => void; onSuccess: () => void }) {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState("")
  const [polling, setPolling] = useState(false)
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    let stop = false
    ;(async () => {
      const d = await api.githubDeviceStart()
      if (stop) return
      if (!d || d.error) { setError(d?.error || "Не удалось начать вход"); return }
      setData(d); setPolling(true)
      const interval = (d.interval || 5) * 1000
      const poll = async () => {
        const r = await api.githubDevicePoll(d.device_code)
        if (stop) return
        if (r?.ok) { onSuccess(); return }
        if (r?.error && !["authorization_pending", "slow_down", ""].includes(r.error)) {
          setError(r.error === "expired_token" ? "Код истёк — начните заново" : r.error); setPolling(false); return
        }
        timer.current = setTimeout(poll, interval)
      }
      timer.current = setTimeout(poll, interval)
    })()
    return () => { stop = true; clearTimeout(timer.current) }
  }, []) // eslint-disable-line

  async function copyCode() {
    if (!data?.user_code) return
    try { await navigator.clipboard.writeText(data.user_code); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* noop */ }
  }

  return (
    <Pane>
      <BackLink onClick={onBack} />
      <Title>Вход через GitHub</Title>
      {error ? (
        <ErrorBox text={error} />
      ) : !data ? (
        <Sub>Запрашиваем код...</Sub>
      ) : (
        <>
          <Sub>1. Скопируйте код 2. Откройте GitHub и вставьте его.</Sub>
          <button onClick={copyCode}
            style={{ width: "100%", marginTop: 18, padding: "16px 18px", borderRadius: "var(--radius-md)",
              background: "var(--surface-soft)", border: "1px dashed var(--hairline-strong)", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span className="mono" style={{ fontSize: 26, letterSpacing: "6px", color: "var(--text)" }}>{data.user_code}</span>
            <span style={{ fontSize: 11, color: copied ? "#a0e0ab" : "var(--muted)" }}>{copied ? "скопировано" : "копировать"}</span>
          </button>
          <a href={data.verification_uri} target="_blank" rel="noreferrer"
            style={{ display: "block", marginTop: 12, textAlign: "center", padding: "12px", borderRadius: "var(--radius-pill)",
              background: MERCURY, color: "#0a0a0a", fontWeight: 500, fontSize: 13.5, textDecoration: "none" }}>
            Открыть GitHub
          </a>
          {polling && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16, fontSize: 12, color: "var(--muted)" }}>
              <Spinner /> Ждём подтверждения...
            </div>
          )}
        </>
      )}
    </Pane>
  )
}

function EmailPane({ onBack, onSuccess }: { onBack: () => void; onSuccess: () => void }) {
  const [email, setEmail] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  async function submit() {
    if (!email.includes("@") || busy) { setError("Введите корректный email"); return }
    setBusy(true); setError("")
    const r = await api.devLogin(email.trim())
    setBusy(false)
    if (r?.ok) onSuccess()
    else setError(r?.error || "Не удалось войти")
  }

  return (
    <Pane>
      <BackLink onClick={onBack} />
      <Title>Вход по email</Title>
      <Sub>Быстрый вход для разработки и тестирования.</Sub>
      <input value={email} onChange={e => setEmail(e.target.value)} onKeyDown={e => e.key === "Enter" && submit()}
        placeholder="you@company.com" autoFocus type="email"
        style={{ width: "100%", marginTop: 18, padding: "12px 16px", borderRadius: "var(--radius-md)",
          background: "var(--surface-soft)", border: "1px solid var(--hairline)", color: "var(--text)", fontSize: 14, outline: "none" }}
        onFocus={e => (e.currentTarget.style.borderColor = "rgba(255,172,46,0.45)")}
        onBlur={e => (e.currentTarget.style.borderColor = "var(--hairline)")} />
      {error && <ErrorBox text={error} />}
      <button onClick={submit} disabled={busy}
        style={{ width: "100%", marginTop: 12, padding: "12px", borderRadius: "var(--radius-pill)", border: "none",
          background: busy ? "var(--ghost)" : MERCURY, color: busy ? "var(--muted)" : "#0a0a0a", fontWeight: 500, fontSize: 13.5, cursor: "pointer" }}>
        {busy ? "Входим..." : "Войти"}
      </button>
    </Pane>
  )
}

function Pane({ children }: { children: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.2 }}>
      {children}
    </motion.div>
  )
}
function Title({ children }: { children: React.ReactNode }) {
  return <div className="display" style={{ fontSize: 24, color: "var(--text)", marginBottom: 6 }}>{children}</div>
}
function Sub({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.55 }}>{children}</div>
}
function BackLink({ onClick }: { onClick: () => void }) {
  return <button onClick={onClick} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 12, padding: 0, marginBottom: 14 }}>← назад</button>
}
function BigButton({ children, onClick, primary }: { children: React.ReactNode; onClick: () => void; primary?: boolean }) {
  return (
    <button onClick={onClick}
      style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, padding: "13px 18px",
        borderRadius: "var(--radius-pill)", cursor: "pointer", fontSize: 13.5, fontWeight: 500,
        border: primary ? "none" : "1px solid var(--hairline-strong)",
        background: primary ? "var(--text)" : "transparent", color: primary ? "var(--bg)" : "var(--text)",
        transition: "opacity 0.15s" }}
      onMouseEnter={e => (e.currentTarget.style.opacity = "0.86")}
      onMouseLeave={e => (e.currentTarget.style.opacity = "1")}>
      {children}
    </button>
  )
}
function ErrorBox({ text }: { text: string }) {
  return <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: "var(--radius-sm)", background: "rgba(207,102,121,0.1)",
    border: "1px solid rgba(207,102,121,0.3)", color: "#e89", fontSize: 12, lineHeight: 1.5 }}>{text}</div>
}
function Spinner() {
  return <motion.span animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.9, ease: "linear" }}
    style={{ width: 13, height: 13, borderRadius: "50%", border: "2px solid var(--hairline-strong)", borderTopColor: "var(--mercury-a)", display: "inline-block" }} />
}
function GitHubGlyph() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
      <path d="M12 2C6.48 2 2 6.58 2 12.26c0 4.5 2.87 8.32 6.84 9.67.5.1.68-.22.68-.48l-.01-1.7c-2.78.62-3.37-1.37-3.37-1.37-.46-1.18-1.11-1.5-1.11-1.5-.9-.63.07-.62.07-.62 1 .07 1.53 1.05 1.53 1.05.89 1.56 2.34 1.11 2.91.85.09-.66.35-1.11.63-1.36-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.27 2.75 1.05a9.4 9.4 0 0 1 5 0c1.91-1.32 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.81-4.57 5.06.36.32.68.94.68 1.9l-.01 2.82c0 .27.18.59.69.48A10.02 10.02 0 0 0 22 12.26C22 6.58 17.52 2 12 2z"/>
    </svg>
  )
}
function GoogleGlyph() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  )
}
