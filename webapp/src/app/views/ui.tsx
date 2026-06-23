import { useState } from "react"
import type { ReactNode, CSSProperties } from "react"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

export function ViewShell({ children }: { children: ReactNode }) {
  return <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>{children}</div>
}

export function ViewHead({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div style={{ padding: "24px 28px 16px", flexShrink: 0, display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
      <div>
        <div className="display" style={{ fontSize: 30, color: "var(--text)", lineHeight: 1.05 }}>{title}</div>
        {sub != null && <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 7, lineHeight: 1.4 }}>{sub}</div>}
      </div>
      {right}
    </div>
  )
}

// ── Sub-tab bar (горизонтальные вкладки внутри раздела) ───────────────────────
export interface TabDef { id: string; label: string; badge?: number }

export function SubTabs({ tabs, active, onChange }: { tabs: TabDef[]; active: string; onChange: (id: string) => void }) {
  return (
    <div style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--hairline)", flexShrink: 0, paddingLeft: 28, paddingRight: 28, overflowX: "auto" }}>
      {tabs.map(t => {
        const isActive = t.id === active
        return (
          <button key={t.id} onClick={() => onChange(t.id)}
            style={{ display: "flex", alignItems: "center", gap: 7, padding: "11px 16px", fontSize: 12.5, fontWeight: isActive ? 500 : 400,
              color: isActive ? "var(--text)" : "var(--muted)", background: "none", border: "none",
              borderBottom: isActive ? "2px solid var(--mercury-a)" : "2px solid transparent",
              marginBottom: -1, cursor: "pointer", whiteSpace: "nowrap", transition: "color 0.15s, border-color 0.15s",
              fontFamily: "var(--font-sans)" }}>
            {t.label}
            {t.badge != null && t.badge > 0 && (
              <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 99, background: isActive ? "rgba(255,172,46,0.15)" : "var(--hairline-soft)",
                color: isActive ? "var(--mercury-a)" : "var(--muted)", border: `1px solid ${isActive ? "rgba(255,172,46,0.3)" : "var(--hairline)"}` }}>
                {t.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// хук для управления sub-tabs с запоминанием состояния
export function useSubTab(tabs: TabDef[], initial?: string) {
  const [active, setActive] = useState(initial || tabs[0]?.id || "")
  return { active, setActive, tabs }
}

export function ViewBody({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div style={{ flex: 1, overflowY: "auto", padding: "20px 28px 28px", ...style }}>{children}</div>
}

export function SectionLabel({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1.5px", margin: "0 0 12px", ...style }}>{children}</div>
}

export function Card({ children, style, onClick }: { children: ReactNode; style?: CSSProperties; onClick?: () => void }) {
  const hover = !!onClick
  return (
    <div className="glass" onClick={onClick}
      style={{ borderRadius: "var(--radius-md)", padding: 16, cursor: hover ? "pointer" : "default",
        transition: "border-color 0.18s, transform 0.18s, box-shadow 0.18s", ...style }}
      onMouseEnter={hover ? e => { (e.currentTarget as HTMLElement).style.transform = "translateY(-1px)"; (e.currentTarget as HTMLElement).style.borderColor = "var(--hairline-strong)" } : undefined}
      onMouseLeave={hover ? e => { (e.currentTarget as HTMLElement).style.transform = ""; (e.currentTarget as HTMLElement).style.borderColor = "" } : undefined}>
      {children}
    </div>
  )
}

export function Empty({ icon, text, hint }: { icon?: string; text: string; hint?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "52px 24px", gap: 10, textAlign: "center" }}>
      {icon && <div style={{ fontSize: 32, opacity: 0.3 }}>{icon}</div>}
      <div style={{ fontSize: 13, color: "var(--muted)" }}>{text}</div>
      {hint && <div style={{ fontSize: 11, color: "var(--faint)", maxWidth: 280, lineHeight: 1.5 }}>{hint}</div>}
    </div>
  )
}

export function Pill({ children, accent, color }: { children: ReactNode; accent?: boolean; color?: string }) {
  const c = color ?? (accent ? "rgba(255,172,46,0.4)" : "var(--hairline)")
  const tc = color ? "#fff" : accent ? "var(--mercury-a)" : "var(--text-dim)"
  return (
    <span style={{ fontSize: 10, padding: "2px 10px", borderRadius: "var(--radius-pill)", border: `1px solid ${c}`,
      color: tc, whiteSpace: "nowrap", background: color ? color + "22" : undefined }}>
      {children}
    </span>
  )
}

export function MercuryBar({ percent, style }: { percent: number; style?: CSSProperties }) {
  return (
    <div style={{ height: 3, borderRadius: 99, background: "var(--hairline-strong)", overflow: "hidden", ...style }}>
      <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, percent))}%`, background: MERCURY,
        borderRadius: 99, transition: "width 0.6s var(--ease-out)" }} />
    </div>
  )
}

export const STATUS_COLOR: Record<string, string> = {
  active: "#a0e0ab", thinking: "#ffac2e", done: "var(--text-dim)", idle: "var(--whisper)",
}
