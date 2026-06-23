import type { Section } from "../types"
import { Icon } from "./icons"

const MERCURY_AMBER = "#ffac2e"

const NAV: Array<{ id: Section; label: string; group: "top" | "bottom" }> = [
  { id: "office",      label: "Офис",    group: "top" },
  { id: "project",     label: "Проект",  group: "top" },
  { id: "team",        label: "Команда", group: "top" },
  { id: "chats",       label: "Чаты",    group: "top" },
  { id: "results",     label: "Итоги",   group: "top" },
  { id: "connections", label: "Доступы", group: "bottom" },
  { id: "account",     label: "Аккаунт", group: "bottom" },
]

interface NavRailProps {
  active: Section
  onChange: (s: Section) => void
  orientation?: "vertical" | "horizontal"
}

export function NavRail({ active, onChange, orientation = "vertical" }: NavRailProps) {
  if (orientation === "horizontal") {
    return (
      <div className="glass" style={{
        display: "flex", gap: 2, borderRadius: "var(--radius-pill)", padding: "5px 7px", overflowX: "auto",
      }}>
        {NAV.map(item => {
          const isActive = item.id === active
          return (
            <button key={item.id} onClick={() => onChange(item.id)}
              style={{
                display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
                padding: "6px 11px", borderRadius: "var(--radius-pill)", border: "none", cursor: "pointer",
                background: isActive ? "var(--hairline-strong)" : "transparent",
                color: isActive ? MERCURY_AMBER : "var(--muted)",
                transition: "all 0.15s", fontFamily: "var(--font-sans)", minWidth: 50,
              }}>
              <Icon name={item.id} size={17} />
              <span style={{ fontSize: 8.5, letterSpacing: "0.4px", textTransform: "uppercase",
                fontWeight: isActive ? 500 : 400, color: isActive ? "var(--text)" : "inherit" }}>
                {item.label}
              </span>
            </button>
          )
        })}
      </div>
    )
  }

  const top    = NAV.filter(n => n.group === "top")
  const bottom = NAV.filter(n => n.group === "bottom")

  return (
    <nav className="glass" style={{
      width: 76, flexShrink: 0, display: "flex", flexDirection: "column",
      justifyContent: "space-between", padding: "12px 8px",
      borderRadius: "var(--radius-xl)",
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {top.map(item => <NavItem key={item.id} item={item} active={active} onChange={onChange} />)}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {bottom.map(item => <NavItem key={item.id} item={item} active={active} onChange={onChange} />)}
      </div>
    </nav>
  )
}

function NavItem({ item, active, onChange }: { item: typeof NAV[0]; active: Section; onChange: (s: Section) => void }) {
  const isActive = item.id === active
  return (
    <button onClick={() => onChange(item.id)}
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", gap: 5,
        padding: "10px 4px", borderRadius: "var(--radius-md)", border: "none", cursor: "pointer",
        background: isActive ? "var(--hairline-soft)" : "transparent",
        color: isActive ? MERCURY_AMBER : "var(--muted)",
        position: "relative", transition: "all 0.15s", fontFamily: "var(--font-sans)", width: "100%",
      }}
      onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "var(--surface-soft)" }}
      onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent" }}>
      {isActive && (
        <span style={{
          position: "absolute", left: -8, top: "24%", bottom: "24%", width: 3,
          borderRadius: "0 3px 3px 0",
          background: "linear-gradient(180deg, #a0e0ab, #ffac2e 50%, #a52d25)",
        }} />
      )}
      <Icon name={item.id} size={19} strokeWidth={isActive ? 1.9 : 1.7} />
      <span style={{
        fontSize: 8.5, letterSpacing: "0.4px", textTransform: "uppercase",
        fontWeight: isActive ? 500 : 400, lineHeight: 1, color: isActive ? "var(--text)" : "inherit",
      }}>{item.label}</span>
    </button>
  )
}
