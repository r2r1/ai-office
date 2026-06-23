import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName } from "../../data/roles"
import { ViewShell, ViewHead, SubTabs, ViewBody, Card, Empty, Pill, MercuryBar, SectionLabel } from "./ui"

const TABS = [
  { id: "milestones", label: "Этапы" },
  { id: "tasks",      label: "Задачи" },
  { id: "results",    label: "Итоги" },
]

export function ProjectView() {
  const { state } = useOffice()
  const [tab, setTab] = useState("milestones")
  const [milestones, setMilestones] = useState<any[]>([])
  const [deliverables, setDeliverables] = useState<any[]>([])
  const tasks = state.plan.tasks || []

  useEffect(() => {
    api.milestones().then(d => setMilestones(d.stages || []))
    api.deliverables().then(d => setDeliverables(d.deliverables || []))
  }, [state.feed.length])

  const tabsWithBadges = TABS.map(t => ({
    ...t,
    badge: t.id === "tasks" ? tasks.filter((x: any) => x.status === "in_progress").length
      : t.id === "milestones" ? milestones.length
      : t.id === "results" ? deliverables.length
      : undefined,
  }))

  const metrics = [
    { label: "Выполнено задач",  value: `${state.plan.progress.done}/${state.plan.progress.total}`, icon: "✓" },
    { label: "Общий прогресс",   value: `${state.progress.percent}%`,                               icon: "◎" },
    { label: "Лиды",             value: String(state.leads.length),                                  icon: "◈" },
    { label: "Сайтов",           value: String(state.sites.length),                                  icon: "⊟" },
    { label: "Расход",           value: `$${state.cost.toFixed(4)}`,                                 icon: "💸" },
  ]

  return (
    <ViewShell>
      <ViewHead title="Проект" sub={state.ready ? state.progress.note || "Офис работает" : "Ожидание брифа"} />
      <SubTabs tabs={tabsWithBadges} active={tab} onChange={setTab} />

      {tab === "milestones" && <MilestonesTab milestones={milestones} progress={state.progress} />}
      {tab === "tasks"      && <TasksTab tasks={tasks} metrics={metrics} />}
      {tab === "results"    && <ResultsTab deliverables={deliverables} />}
    </ViewShell>
  )
}

// ── Этапы ────────────────────────────────────────────────────────────────────
function MilestonesTab({ milestones, progress }: { milestones: any[]; progress: any }) {
  if (milestones.length === 0) return (
    <ViewBody>
      <Empty icon="◎" text="Этапы проекта ещё не сформированы"
        hint="Директор составит план после получения брифа и стратегии" />
    </ViewBody>
  )

  const stages = progress.stages || []
  const currentId = progress.current

  return (
    <ViewBody>
      <MercuryBar percent={progress.percent} style={{ marginBottom: 28 }} />
      <div style={{ display: "grid", gap: 12 }}>
        {milestones.map((m: any, i: number) => {
          const stageInfo = stages.find((s: any) => s.id === m.id)
          const isCurrent = m.id === currentId
          const isDone = stageInfo?.status === "done"
          return (
            <Card key={m.id || i} style={{ position: "relative", overflow: "hidden",
              borderColor: isCurrent ? "rgba(255,172,46,0.3)" : isDone ? "rgba(160,224,171,0.2)" : undefined }}>
              {isCurrent && <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: "var(--mercury-a)" }} />}
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, paddingLeft: isCurrent ? 8 : 0 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
                    <span className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>Этап {i + 1}</span>
                    {isCurrent && <Pill accent>В работе</Pill>}
                    {isDone && <Pill color="#a0e0ab">Готово</Pill>}
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)", marginBottom: 6, lineHeight: 1.3 }}>{m.title || m.name || m.id}</div>
                  {m.description && <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{m.description}</div>}
                  {m.summary && <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 8, lineHeight: 1.5, borderLeft: "2px solid var(--hairline-strong)", paddingLeft: 10 }}>{m.summary}</div>}
                </div>
                <div className="mono" style={{ fontSize: 22, color: isDone ? "#a0e0ab" : isCurrent ? "var(--mercury-a)" : "var(--faint)", flexShrink: 0 }}>
                  {isDone ? "✓" : isCurrent ? "▶" : String(i + 1).padStart(2, "0")}
                </div>
              </div>
            </Card>
          )
        })}
      </div>
    </ViewBody>
  )
}

// ── Задачи (Kanban) ───────────────────────────────────────────────────────────
const COLS = [
  { key: "pending",     label: "В очереди",  dot: "var(--whisper)" },
  { key: "in_progress", label: "В работе",   dot: "var(--mercury-a)" },
  { key: "done",        label: "Готово",      dot: "#a0e0ab" },
]

function TasksTab({ tasks, metrics }: { tasks: any[]; metrics: { label: string; value: string; icon: string }[] }) {
  return (
    <ViewBody>
      {/* метрики */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginBottom: 28 }}>
        {metrics.map(m => (
          <div key={m.label} className="glass" style={{ borderRadius: "var(--radius-md)", padding: "14px 16px" }}>
            <div className="display" style={{ fontSize: 26, color: "var(--text)", lineHeight: 1 }}>{m.value}</div>
            <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 6 }}>{m.label}</div>
          </div>
        ))}
      </div>

      {tasks.length === 0 ? (
        <Empty icon="◉" text="План задач появится после старта офиса"
          hint="Директор сформирует доску после получения стратегии" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
          {COLS.map(col => {
            const items = tasks.filter((t: any) => t.status === col.key)
            return (
              <div key={col.key} style={{ background: "var(--surface-soft)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-md)", padding: 12 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: col.dot, display: "inline-block" }} />
                    <span style={{ fontSize: 11.5, fontWeight: 500, color: "var(--text-dim)" }}>{col.label}</span>
                  </div>
                  <span style={{ fontSize: 10, color: "var(--muted)" }}>{items.length}</span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {items.map((t: any) => (
                    <div key={t.id} style={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-sm)", padding: "10px 12px" }}>
                      <div style={{ fontSize: 12.5, color: col.key === "done" ? "var(--muted)" : "var(--text)", lineHeight: 1.35,
                        textDecoration: col.key === "done" ? "line-through" : "none", marginBottom: 8 }}>
                        {t.title}
                      </div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                        <Pill accent={col.key === "in_progress"}>{roleName(t.role)}</Pill>
                        {t.done_criterion && col.key !== "done" && (
                          <span style={{ fontSize: 10, color: "#6f8a6a", lineHeight: 1.3 }}>✓ {t.done_criterion}</span>
                        )}
                      </div>
                    </div>
                  ))}
                  {items.length === 0 && <div style={{ fontSize: 11, color: "var(--faint)", textAlign: "center", padding: "16px 0" }}>—</div>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </ViewBody>
  )
}

// ── Итоги / Результаты ────────────────────────────────────────────────────────
function ResultsTab({ deliverables }: { deliverables: any[] }) {
  if (deliverables.length === 0) return (
    <ViewBody>
      <Empty icon="◎" text="Готовые материалы появятся здесь"
        hint="Результаты работы агентов — стратегия, ТЗ, код и другие артефакты" />
    </ViewBody>
  )

  return (
    <ViewBody>
      <SectionLabel style={{ marginBottom: 16 }}>Готовые материалы · {deliverables.length}</SectionLabel>
      <div style={{ display: "grid", gap: 12 }}>
        {deliverables.map((d: any, i: number) => (
          <Card key={i}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }}>
              <Pill accent>{roleName(d.role)}</Pill>
              <span style={{ fontSize: 12.5, color: "var(--text)", fontWeight: 500 }}>{d.title}</span>
            </div>
            {(d.content || d.result) && (
              <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.6,
                display: "-webkit-box", WebkitLineClamp: 5, WebkitBoxOrient: "vertical", overflow: "hidden",
                whiteSpace: "pre-wrap", borderTop: "1px solid var(--hairline-soft)", paddingTop: 10, marginTop: 4 }}>
                {d.content || d.result}
              </div>
            )}
          </Card>
        ))}
      </div>
    </ViewBody>
  )
}
