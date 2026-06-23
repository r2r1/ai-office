import { useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { ViewShell, ViewHead, SubTabs, ViewBody, Empty } from "./ui"

const FILTERS = [
  { id: "all",    label: "Все" },
  { id: "work",   label: "Работа" },
  { id: "system", label: "Система" },
  { id: "error",  label: "Ошибки" },
]

const KIND_COLOR: Record<string, string> = {
  error:   "#cf6679",
  done:    "#a0e0ab",
  speech:  "var(--text-dim)",
  thinking:"var(--mercury-a)",
  system:  "var(--muted)",
  hired:   "#a0c0ff",
  default: "var(--text-dim)",
}

function filterFeed(feed: any[], filter: string) {
  if (filter === "all")    return feed
  if (filter === "error")  return feed.filter(f => f.kind === "error")
  if (filter === "system") return feed.filter(f => ["system", "hired"].includes(f.kind))
  if (filter === "work")   return feed.filter(f => ["speech", "thinking", "done", "task_done", "file_written"].includes(f.kind))
  return feed
}

export function EventsView() {
  const { state } = useOffice()
  const [filter, setFilter] = useState("all")

  const errors = state.feed.filter(f => f.kind === "error").length
  const tabs = FILTERS.map(f => ({
    ...f,
    badge: f.id === "error" ? errors : undefined,
  }))

  const visible = filterFeed([...state.feed].reverse(), filter)

  return (
    <ViewShell>
      <ViewHead title="Журнал" sub={`${state.feed.length} событий · поток SSE в реальном времени`} />
      <SubTabs tabs={tabs} active={filter} onChange={setFilter} />

      {visible.length === 0 ? (
        <ViewBody>
          <Empty icon="◻" text={state.feed.length === 0 ? "Журнал пуст — запустите офис" : "Нет событий по этому фильтру"} />
        </ViewBody>
      ) : (
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 28px 24px" }}>
          {visible.map(f => (
            <div key={f.id} style={{ display: "flex", gap: 12, padding: "10px 0",
              borderBottom: "1px solid var(--hairline-soft)", animation: "fade-in 0.25s ease" }}>
              <span style={{ fontSize: 15, flexShrink: 0, paddingTop: 1 }}>{f.icon}</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                {f.who && (
                  <span className="mono" style={{ fontSize: 10, color: "var(--muted)", marginRight: 8 }}>{f.who}</span>
                )}
                <span style={{ fontSize: 12.5, lineHeight: 1.5, color: KIND_COLOR[f.kind] ?? KIND_COLOR.default,
                  wordBreak: "break-word" }}>
                  {f.text}
                </span>
              </div>
              {f.ts && (
                <span className="mono" style={{ fontSize: 9.5, color: "var(--faint)", flexShrink: 0, paddingTop: 2 }}>
                  {new Date(f.ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </ViewShell>
  )
}
