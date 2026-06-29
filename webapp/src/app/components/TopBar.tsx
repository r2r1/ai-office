import { useState } from "react"
import type { Theme } from "../types"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

interface TopBarProps {
  progress: number
  progressNote: string
  cost: number
  model: string
  connected?: boolean
  theme: Theme
  onToggleTheme: () => void
  onOpenAccount?: () => void
  isMobile: boolean
  understanding?: { score: number } | null
  onUnderstandingClick?: () => void
}

export function TopBar({ progress, progressNote, cost, model, connected, theme, onToggleTheme, onOpenAccount, isMobile, understanding, onUnderstandingClick }: TopBarProps) {
  return (
    <header style={{
      display: "flex", alignItems: "center", gap: isMobile ? 10 : 16,
      height: 56, flexShrink: 0, padding: isMobile ? "0 12px" : "0 18px",
      borderRadius: "var(--radius-lg)", position: "relative", overflow: "hidden",
      background: "var(--surface)",
      backdropFilter: "blur(30px) saturate(180%)", WebkitBackdropFilter: "blur(30px) saturate(180%)",
      border: "1px solid var(--hairline-strong)", boxShadow: "var(--shadow), 0 1px 0 var(--inset-hi) inset",
      transition: "background 0.4s ease, border-color 0.4s ease",
    }}>
      {/* верхний световой штрих */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 1,
        background: "linear-gradient(90deg, transparent, var(--inset-hi), transparent)" }} />

      {/* Логотип */}
      <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 7 : 9, flexShrink: 0 }}>
        <div style={{ width: 7, height: 7, borderRadius: "50%", background: MERCURY,
          boxShadow: "0 0 8px rgba(255,172,46,0.5)", animation: "mercury-pulse 2.4s ease infinite" }} />
        <div style={{ fontSize: isMobile ? 13 : 14, fontWeight: 500, letterSpacing: "0.5px", textTransform: "uppercase", color: "var(--text)" }}>
          AI <span className="display" style={{ textTransform: "none", letterSpacing: 0, fontStyle: "italic", fontSize: isMobile ? 13 : 15, marginLeft: 1 }}>office</span>
        </div>
      </div>

      {!isMobile && <div style={{ width: 1, height: 20, background: "var(--hairline)", flexShrink: 0 }} />}

      {/* Прогресс */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4, minWidth: 0, maxWidth: 360 }}>
        <div style={{ position: "relative", height: 3, borderRadius: "var(--radius-pill)",
          background: isMobile ? "transparent" : "var(--hairline-strong)", overflow: "hidden" }}>
          <div style={{ position: "absolute", top: 0, left: 0, height: "100%", width: `${progress}%`,
            background: MERCURY, borderRadius: "var(--radius-pill)", transition: "width 0.5s var(--ease-out)" }} />
        </div>
        {!isMobile && (
          <div className="topbar-progress-note mono" style={{ fontSize: 10, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {progressNote || "—"}
          </div>
        )}
      </div>

      {/* Связь + расход + модель + тема */}
      <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 8 : 12, flexShrink: 0 }}>
        <span title={connected ? "онлайн" : "подключение…"} style={{
          width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
          background: connected ? "#a0e0ab" : "var(--whisper)",
          boxShadow: connected ? "0 0 6px rgba(160,224,171,0.6)" : "none",
        }} />
         {!isMobile && cost > 0 && (
          <div style={{
            padding: "5px 12px", borderRadius: "var(--radius-pill)",
            background: "var(--surface-soft)", border: "1px solid var(--hairline)",
            fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-dim)",
            display: "flex", alignItems: "center", gap: 4
          }}>
            <span style={{ opacity: 0.6 }}>$</span>
            {cost.toFixed(4)}
          </div>
        )}
        {!isMobile && understanding != null && (
          <UnderstandingBadge score={understanding.score} onClick={onUnderstandingClick} />
        )}
        {!isMobile && <ModelPlaque model={model} onOpenAccount={onOpenAccount} />}
        <button 
          onClick={onToggleTheme} 
          title={theme === "dark" ? "Светлая тема" : "Темная тема"}
          style={{
            width: 32, height: 32, borderRadius: "var(--radius-md)", cursor: "pointer",
            border: "1px solid var(--hairline)", background: "transparent", 
            color: "var(--text-dim)", fontSize: 16,
            display: "flex", alignItems: "center", justifyContent: "center", 
            transition: "all 0.2s ease",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = "var(--surface-soft)"
            e.currentTarget.style.color = "var(--text)"
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = "transparent"
            e.currentTarget.style.color = "var(--text-dim)"
          }}
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
      </div>
    </header>
  )
}

/** Индикатор «Понимание компании X%». Кликабелен — открывает попап. */
function UnderstandingBadge({ score, onClick }: { score: number; onClick?: () => void }) {
  const [hover, setHover] = useState(false)
  const color = score >= 70 ? "#a0e0ab" : score >= 40 ? "#ffac2e" : "var(--text-dim)"
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      title="Насколько офис знает твой бизнес"
      style={{
        display: "flex", alignItems: "center", gap: 6, padding: "5px 10px",
        borderRadius: "var(--radius-pill)", border: "1px solid var(--hairline)",
        background: hover ? "var(--surface-soft)" : "transparent",
        cursor: "pointer", transition: "all 0.2s ease",
      }}>
      <span style={{ fontSize: 13 }}>🧠</span>
      <span className="mono" style={{ fontSize: 11, color }}>
        {score}%
      </span>
    </button>
  )
}

/** Плашка текущей модели офиса + понятная подсказка при наведении. */
function ModelPlaque({ model, onOpenAccount }: { model: string; onOpenAccount?: () => void }) {
  const [hover, setHover] = useState(false)
  return (
    <div style={{ position: "relative" }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
     <button onClick={onOpenAccount}
        style={{
          display: "flex", alignItems: "center", gap: 8, padding: "5px 12px",
          borderRadius: "var(--radius-pill)", border: "1px solid var(--hairline)",
          background: hover ? "var(--surface-soft)" : "transparent",
          cursor: onOpenAccount ? "pointer" : "default",
          transition: "all 0.2s ease",
        }}>
        <span style={{ fontSize: 14, lineHeight: 1 }}>🧠</span>
        <span className="mono" style={{ 
          fontSize: 11, color: "var(--text-dim)", maxWidth: 120,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" 
        }}>
          {model || "Загрузка..."}
        </span>
      </button>

      
    </div>
  )
}
