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
  isMobile: boolean
}

export function TopBar({ progress, progressNote, cost, model, connected, theme, onToggleTheme, isMobile }: TopBarProps) {
  return (
    <header style={{
      display: "flex", alignItems: "center", gap: isMobile ? 10 : 16,
      height: 52, flexShrink: 0, padding: isMobile ? "0 12px" : "0 18px",
      borderRadius: "var(--radius-lg)", position: "relative", overflow: "hidden",
      background: "var(--surface)", backdropFilter: "blur(28px) saturate(160%)", WebkitBackdropFilter: "blur(28px) saturate(160%)",
      border: "1px solid var(--hairline)", boxShadow: "var(--shadow), 0 1px 0 var(--inset-hi) inset",
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
          <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)", padding: "3px 12px",
            border: "1px solid var(--hairline)", borderRadius: "var(--radius-pill)" }}>
            ${cost.toFixed(4)}
          </span>
        )}
        {!isMobile && model && (
          <span className="mono hide-mobile" style={{ fontSize: 11, color: "var(--muted)" }}>{model}</span>
        )}
        <button onClick={onToggleTheme} title="Тема" style={{
          width: 30, height: 30, borderRadius: "var(--radius-pill)", cursor: "pointer",
          border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)", fontSize: 14,
          display: "flex", alignItems: "center", justifyContent: "center", transition: "color 0.2s, border-color 0.2s",
        }}>
          {theme === "dark" ? "◐" : "◑"}
        </button>
      </div>
    </header>
  )
}
