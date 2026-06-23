import type { Section } from "../types"

const MERCURY_AMBER = "#ffac2e"

const NAV: Array<{ id: Section; icon: string; label: string; group: "top" | "bottom" }> = [
  { id: "office",      icon: "⊞",  label: "Офис",    group: "top" },
  { id: "project",     icon: "◉",  label: "Проект",  group: "top" },
  { id: "team",        icon: "◈",  label: "Команда", group: "top" },
  { id: "chats",       icon: "◻",  label: "Чаты",    group: "top" },
  { id: "results",     icon: "⊟",  label: "Итоги",   group: "top" },
  { id: "connections", icon: "🔌", label: "Доступы", group: "bottom" },
  { id: "account",     icon: "⊙",  label: "Аккаунт", group: "bottom" },
]

interface NavRailProps {
  active: Section
  onChange: (s: Section) => void
  orientation?: "vertical" | "horizontal"
}

export function NavRail({ active, onChange, orientation = "vertical" }: NavRailProps) {
  if (orientation === "horizontal") {
    return (
      <div style={{
        display: "flex", gap: 2, background: "var(--surface)", border: "1px solid var(--hairline)",
        borderRadius: "var(--radius-pill)", padding: "4px 6px",
        backdropFilter: "blur(28px) saturate(160%)", overflowX: "auto",
      }}>
        {NAV.map(item => {
          const isActive = item.id === active
          return (
            <button key={item.id} onClick={() => onChange(item.id)}
              style={{
                display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
                padding: "5px 10px", borderRadius: "var(--radius-pill)", border: "none", cursor: "pointer",
                background: isActive ? "var(--hairline-strong)" : "transparent",
                color: isActive ? "var(--text)" : "var(--muted)",
                transition: "all 0.15s", fontFamily: "var(--font-sans)", minWidth: 48,
              }}>
              <span style={{ fontSize: 13, lineHeight: 1, color: isActive ? MERCURY_AMBER : "inherit" }}>{item.icon}</span>
              <span style={{ fontSize: 8.5, letterSpacing: "0.5px", textTransform: "uppercase", fontWeight: isActive ? 500 : 400 }}>
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
    <nav style={{
      width: 72, flexShrink: 0, display: "flex", flexDirection: "column",
      justifyContent: "space-between", paddingTop: 6, paddingBottom: 8,
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {top.map(item => <NavItem key={item.id} item={item} active={active} onChange={onChange} />)}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
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
        display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
        padding: "9px 6px", borderRadius: "var(--radius-md)", border: "none", cursor: "pointer",
        background: isActive ? "var(--hairline-soft)" : "transparent",
        color: isActive ? "var(--text)" : "var(--muted)",
        position: "relative", transition: "all 0.15s", fontFamily: "var(--font-sans)", width: "100%",
      }}
      onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "var(--surface-soft)" }}
      onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent" }}>
      {isActive && (
        <span style={{
          position: "absolute", left: 0, top: "22%", bottom: "22%", width: 3,
          borderRadius: "0 3px 3px 0",
          background: "linear-gradient(180deg, #a0e0ab, #ffac2e 50%, #a52d25)",
        }} />
      )}
      <span style={{ fontSize: 15, lineHeight: 1, color: isActive ? MERCURY_AMBER : "inherit" }}>{item.icon}</span>
      <span style={{
        fontSize: 8.5, letterSpacing: "0.5px", textTransform: "uppercase",
        fontWeight: isActive ? 500 : 400, lineHeight: 1,
      }}>{item.label}</span>
    </button>
  )
}
