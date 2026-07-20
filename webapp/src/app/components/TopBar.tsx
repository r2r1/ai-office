import type { Theme } from "../types"

// var(--mercury) из design.css — раньше был отдельным литералом, идентичным
// токену (production-readiness worklist п.37).
const MERCURY = "var(--mercury)"

interface TopBarProps {
  progress: number
  progressNote: string
  cost: number
  connected?: boolean
  theme: Theme
  onToggleTheme: () => void
  isMobile: boolean
  understanding?: { score: number } | null
  officePaused?: boolean
  onToggleOffice?: () => void
  autonomyLevel?: string
  health?: { company: number; status: string } | null
  trust?: { company: number; streak: number } | null
  qualityMode?: { icon: string; label: string } | null
  /** Один клик — один попап со всеми статусами разом (Понимание/Здоровье/
   * Доверие/Автономность/Качество). Раньше это были 4 отдельные кнопки,
   * ведущие в 2 разных места, плюс отдельный попап — визуальный шум
   * (governance-виджеты, найдено при аудите функционала). */
  onStatusClick?: () => void
  /** Бюджетный лимит (0 = не задан — платёжная система ещё не подключена,
   * это временная замена «пополнения»): показываем остаток рядом с расходом,
   * клик ведёт на «Настройки → Лимиты», где его можно поднять. */
  limitTotalUsd?: number
  limitOverLimit?: boolean
  onOpenLimits?: () => void
}

export function TopBar({ progress, progressNote, cost, connected, theme, onToggleTheme, isMobile, understanding, officePaused, onToggleOffice, autonomyLevel, health, trust, qualityMode, onStatusClick, limitTotalUsd, limitOverLimit, onOpenLimits }: TopBarProps) {
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
          // Раньше эта строка была обрезана многоточием и НИЧЕГО не делала по
          // клику — единственное окно в "мысли CEO" прямо сейчас было
          // нечитаемым (найдено при живом аудите). title даёт нативный тултип
          // с полным текстом; onClick открывает попап "Статус офиса" (тот же,
          // что и справа) — полная хронология с этой же мыслью решения есть
          // в Сводка → Прозрачность, но туда нужна отдельная навигация,
          // которой TopBar не управляет.
          <button onClick={onStatusClick} title={progressNote || undefined}
            className="topbar-progress-note mono"
            style={{ fontSize: 10, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden",
              textOverflow: "ellipsis", background: "none", border: "none", padding: 0, textAlign: "left",
              cursor: progressNote ? "pointer" : "default", font: "inherit" }}>
            {progressNote || "—"}
          </button>
        )}
      </div>

      {/* Связь + расход + модель + тема */}
      <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 8 : 12, flexShrink: 0 }}>
        {/* Раньше разрыв связи был виден только по title-тултипу на точке (легко
            пропустить) — аудит §4.4: пользователь не понимал, что интерфейс
            "замер" из-за обрыва SSE, а не завис. Текстовая подпись появляется
            только когда реально не подключено — не занимает место в норме. */}
        <div title={connected ? "онлайн" : "переподключение…"}
          style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {!connected && !isMobile && (
            <span style={{ fontSize: 11, color: "var(--muted)" }}>переподключение…</span>
          )}
          <span style={{
            width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
            background: connected ? "var(--success)" : "var(--mercury-a)",
            boxShadow: connected ? "0 0 6px rgba(160,224,171,0.6)" : "0 0 6px rgba(255,172,46,0.6)",
            animation: connected ? "none" : "mercury-pulse 1.2s ease-in-out infinite",
          }} />
        </div>
         {!isMobile && cost > 0 && (
          <div onClick={onOpenLimits} title={limitTotalUsd ? "Потрачено / осталось — открыть Лимиты" : "Расход — открыть Лимиты"}
            style={{
            padding: "5px 12px", borderRadius: "var(--radius-pill)",
            background: limitOverLimit ? "rgba(224,85,90,0.12)" : "var(--surface-soft)",
            border: `1px solid ${limitOverLimit ? "var(--danger)" : "var(--hairline)"}`,
            fontSize: 11, fontFamily: "var(--font-mono)", color: limitOverLimit ? "var(--danger)" : "var(--text-dim)",
            display: "flex", alignItems: "center", gap: 4, cursor: onOpenLimits ? "pointer" : "default",
          }}>
            <span style={{ opacity: 0.6 }}>$</span>
            {cost.toFixed(4)}
            {!!limitTotalUsd && (
              <span style={{ opacity: 0.7 }}>&nbsp;/ осталось ${Math.max(0, limitTotalUsd - cost).toFixed(2)}</span>
            )}
          </div>
        )}
        {!isMobile && (understanding != null || health || trust || autonomyLevel || qualityMode) && (
          <StatusBadge understanding={understanding} health={health} trust={trust}
            autonomyLevel={autonomyLevel} qualityMode={qualityMode} onClick={onStatusClick} />
        )}
        <OfficeToggle paused={!!officePaused} onClick={onToggleOffice} isMobile={isMobile} />
        <button
          className="btn btn-icon btn-ghost"
          onClick={onToggleTheme}
          title={theme === "dark" ? "Светлая тема" : "Темная тема"}
          style={{ fontSize: 16 }}
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
      </div>
    </header>
  )
}

/** Кнопка Пауза / Возобновить офис. */
function OfficeToggle({ paused, onClick, isMobile }: { paused: boolean; onClick?: () => void; isMobile: boolean }) {
  return (
    <button
      className={`btn btn-toggle${paused ? " is-on" : ""}`}
      onClick={onClick}
      title={paused ? "Возобновить работу офиса" : "Поставить офис на паузу"}
      style={{ padding: isMobile ? "6px 8px" : "5px 11px", gap: isMobile ? 0 : 5, height: "auto" }}>
      <span style={{ fontSize: 13 }}>{paused ? "▶" : "⏸"}</span>
      {!isMobile && <span className="mono" style={{ fontSize: 11 }}>{paused ? "Пауза" : "Стоп"}</span>}
    </button>
  )
}

const AUTONOMY_ICONS: Record<string, string> = { scout: "🔍", guided: "🤝", trusted: "✅", autonomous: "🚀" }

/** Один сводный индикатор вместо четырёх отдельных кнопок (Понимание/Здоровье/
 * Доверие/Автономность/Качество) — клик открывает один попап со всеми
 * разделами. Показывает самый по смыслу "тревожный" из показателей компактно;
 * остальное — внутри попапа. */
function StatusBadge({ understanding, health, trust, autonomyLevel, qualityMode, onClick }: {
  understanding?: { score: number } | null
  health?: { company: number; status: string } | null
  trust?: { company: number; streak: number } | null
  autonomyLevel?: string
  qualityMode?: { icon: string; label: string } | null
  onClick?: () => void
}) {
  const healthColor = health ? (health.company >= 75 ? "var(--success)" : health.company >= 45 ? "var(--mercury-a)" : "var(--danger)") : "var(--text-dim)"
  return (
    <button
      className="btn btn-ghost btn-pill"
      onClick={onClick}
      title="Статус офиса: понимание бизнеса, здоровье, доверие, автономность, качество"
      style={{ gap: 8, borderColor: "var(--hairline)" }}>
      {health && (
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: healthColor, flexShrink: 0 }} />
      )}
      {autonomyLevel && <span style={{ fontSize: 13 }}>{AUTONOMY_ICONS[autonomyLevel] || "🔍"}</span>}
      {understanding != null && (
        <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>{understanding.score}%</span>
      )}
      {trust && (
        <span className="mono" style={{ fontSize: 11, color: "var(--faint)" }}>🤝{trust.company}</span>
      )}
      {qualityMode && <span style={{ fontSize: 12 }}>{qualityMode.icon}</span>}
    </button>
  )
}

