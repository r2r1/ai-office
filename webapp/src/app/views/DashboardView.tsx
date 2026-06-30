import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName } from "../../data/roles"
import { ViewShell, ViewHead, ViewBody, Card, Empty, Pill } from "./ui"

const DEPT_NAMES: Record<string, string> = { tech: "Технический", marketing: "Маркетинг", sales: "Продажи" }

const COLS = [
  { key: "pending", label: "В очереди" },
  { key: "in_progress", label: "В работе" },
  { key: "done", label: "Готово" },
]

export function DashboardView() {
  const { state } = useOffice()
  const [deliverables, setDeliverables] = useState<any[]>([])
  const [health, setHealth] = useState<any>(null)
  const [autonomy, setAutonomy] = useState<any>(null)
  const tasks = state.plan.tasks || []

  useEffect(() => { api.deliverables().then(d => setDeliverables(d.deliverables || [])) }, [state.feed.length])
  useEffect(() => {
    api.get("/api/health").then(setHealth).catch(() => {})
    api.get("/api/autonomy").then(setAutonomy).catch(() => {})
  }, [state.feed.length])

  const metrics = [
    { label: "Выполнено задач", value: `${state.plan.progress.done}/${state.plan.progress.total}` },
    { label: "Заявки", value: String(state.leads.length) },
    { label: "Сайты", value: String(state.sites.length) },
    { label: "Прогресс", value: `${state.progress.percent}%` },
    { label: "Расход", value: `$${state.cost.toFixed(4)}` },
  ]

  return (
    <ViewShell>
      <ViewHead title="Сводка" sub={state.ready ? "Что компания сделала на текущий момент" : "Офис ожидает бриф"} />
      <ViewBody>
        {/* Health Score по отделам */}
        {health && (
          <>
            <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", margin: "4px 0 12px" }}>
              Здоровье компании {health.status} {health.company}/100
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
              {Object.entries<any>(health.departments || {}).map(([dept, ds]) => (
                <Card key={dept}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontSize: 13, color: "var(--text)" }}>{DEPT_NAMES[dept] || dept}</span>
                    <span>{ds.status} <span className="mono" style={{ fontSize: 12, color: "var(--text-dim)" }}>{ds.score}</span></span>
                  </div>
                  <div style={{ height: 4, background: "var(--hairline)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${ds.score}%`, background: ds.score >= 75 ? "#a0e0ab" : ds.score >= 45 ? "#ffac2e" : "#e05a5a", transition: "width 0.5s" }} />
                  </div>
                  {ds.issues?.length > 0 && (
                    <div style={{ marginTop: 6, fontSize: 10, color: "#ffac2e" }}>⚠ {ds.issues.join(" · ")}</div>
                  )}
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Уровень автономности */}
        {autonomy && (
          <div style={{ marginBottom: 20 }}>
            <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 10 }}>Автономность офиса</div>
            <Card style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px" }}>
              <span style={{ fontSize: 22 }}>{autonomy.icon}</span>
              <div>
                <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{autonomy.name}</div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>{autonomy.desc}</div>
              </div>
              <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                {["scout","guided","trusted","autonomous"].map(lvl => (
                  <button key={lvl} onClick={() => api.post("/api/autonomy", { level: lvl }).then(() => api.get("/api/autonomy").then(setAutonomy))}
                    style={{ padding: "4px 10px", borderRadius: "var(--radius-pill)", fontSize: 10, cursor: "pointer",
                      border: `1px solid ${autonomy.level === lvl ? "var(--mercury-a)" : "var(--hairline)"}`,
                      background: autonomy.level === lvl ? "rgba(160,224,171,0.15)" : "transparent",
                      color: autonomy.level === lvl ? "var(--mercury-a)" : "var(--text-dim)" }}>
                    {lvl}
                  </button>
                ))}
              </div>
            </Card>
          </div>
        )}

        {/* метрики */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 24 }}>
          {metrics.map(m => (
            <Card key={m.label}>
              <div className="display" style={{ fontSize: 30, color: "var(--text)", lineHeight: 1 }}>{m.value}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 7 }}>{m.label}</div>
            </Card>
          ))}
        </div>

        {/* доска задач */}
        <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", margin: "4px 0 12px" }}>Доска задач</div>
        {tasks.length === 0 ? <Empty text="План задач появится после старта офиса" /> : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 14, marginBottom: 26 }}>
            {COLS.map(col => {
              const items = tasks.filter((t: any) => t.status === col.key)
              return (
                <div key={col.key} style={{ background: "var(--surface-soft)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-md)", padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 10 }}>
                    <span>{col.label}</span><span style={{ color: "var(--muted)" }}>{items.length}</span>
                  </div>
                  {items.map((t: any) => (
                    <div key={t.id} style={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-sm)", padding: "10px 11px", marginBottom: 8 }}>
                      <div style={{ fontSize: 12.5, color: col.key === "done" ? "var(--text-dim)" : "var(--text)", lineHeight: 1.35, textDecoration: col.key === "done" ? "line-through" : "none" }}>{t.title}</div>
                      <div style={{ marginTop: 7, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                        <Pill accent={col.key === "in_progress"}>{roleName(t.role)}</Pill>
                        {t.done_criterion && col.key !== "done" && <span style={{ fontSize: 10, color: "#6f8a6a" }}>✓ {t.done_criterion}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        )}

        {/* лиды */}
        <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", margin: "4px 0 12px" }}>Заявки ({state.leads.length})</div>
        {state.leads.length === 0 ? <Empty text="Лиды появятся, когда сайт начнёт собирать заявки" /> : (
          <div style={{ display: "grid", gap: 8, marginBottom: 26 }}>
            {state.leads.slice(0, 12).map((l: any, i: number) => (
              <Card key={i} style={{ padding: "10px 14px" }}>
                <div style={{ fontSize: 13, color: "var(--text)" }}>{l.name || "—"} · <span style={{ color: "var(--text-dim)" }}>{l.contact || l.phone || ""}</span></div>
                {l.message && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>{l.message}</div>}
              </Card>
            ))}
          </div>
        )}

        {/* результаты */}
        <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", margin: "4px 0 12px" }}>Результаты</div>
        {deliverables.length === 0 ? <Empty text="Готовые материалы появятся здесь" /> : (
          <div style={{ display: "grid", gap: 10 }}>
            {deliverables.slice(0, 10).map((d: any, i: number) => (
              <Card key={i}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: "var(--mercury-a)" }}>{roleName(d.role)}</span>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>{d.title}</span>
                </div>
                <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5, display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                  {d.content || d.result || ""}
                </div>
              </Card>
            ))}
          </div>
        )}
      </ViewBody>
    </ViewShell>
  )
}
