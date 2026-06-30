import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, Card, SectionLabel, Pill, MercuryBar } from "./ui"
import type { Section } from "../types"

const DEPT_NAMES: Record<string, string> = { tech: "Технический", marketing: "Маркетинг", sales: "Продажи" }

interface DashboardViewProps {
  onNavigate?: (s: Section) => void
}

export function DashboardView({ onNavigate }: DashboardViewProps) {
  const { state } = useOffice()
  const [health, setHealth] = useState<any>(null)
  const [autonomy, setAutonomy] = useState<any>(null)
  const [initiatives, setInitiatives] = useState<any[]>([])
  const [milestones, setMilestones] = useState<any[]>([])

  useEffect(() => {
    api.get("/api/health").then(setHealth).catch(() => {})
    api.get("/api/autonomy").then(setAutonomy).catch(() => {})
    api.get("/api/initiatives").then(d => setInitiatives(d?.pending || [])).catch(() => {})
    api.milestones().then(d => setMilestones(d.stages || []))
  }, [state.feed.length])

  const currentStage = milestones.find((m: any) => m.id === state.progress.current)
    || milestones.find((m: any) => m.status === "active")

  const metrics = [
    { label: "Задачи",   value: `${state.plan.progress.done}/${state.plan.progress.total}` },
    { label: "Прогресс", value: `${state.progress.percent}%` },
    { label: "Лиды",     value: String(state.leads.length) },
    { label: "Сайты",    value: String(state.sites.length) },
    { label: "Расход",   value: `$${state.cost.toFixed(4)}` },
  ]

  async function handleInitiative(iid: string, action: "accept" | "reject") {
    await api.post(`/api/initiative/${iid}/${action}`, {})
    setInitiatives(prev => prev.filter(i => i.id !== iid))
  }

  return (
    <ViewShell>
      <ViewHead title="Сводка" sub={state.ready ? "Состояние компании на текущий момент" : "Офис ожидает бриф"} />
      <ViewBody>
        {/* Прогресс по проекту + текущий этап */}
        <MercuryBar percent={state.progress.percent} style={{ marginBottom: 10 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
          <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {currentStage ? <>Сейчас: <b style={{ color: "var(--text)" }}>{currentStage.title || currentStage.name}</b></> : (state.progress.note || "—")}
          </div>
          <button onClick={() => onNavigate?.("project")}
            style={linkBtn}>Доска задач →</button>
        </div>

        {/* Здоровье отделов */}
        {health && (
          <>
            <SectionLabel>Здоровье компании {health.status} {health.company}/100</SectionLabel>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 24 }}>
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

        {/* Инициативы CEO */}
        {initiatives.length > 0 && (
          <>
            <SectionLabel>💡 Инициативы CEO · {initiatives.length}</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
              {initiatives.map((ini: any) => (
                <Card key={ini.id} style={{ borderLeft: "3px solid var(--mercury-a)", padding: "14px 16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500, marginBottom: 5 }}>{ini.title}</div>
                      <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5, marginBottom: 5 }}>{ini.rationale}</div>
                      {ini.expected_outcome && <Pill accent>📈 {ini.expected_outcome}</Pill>}
                      {ini.estimated_effort && <span style={{ fontSize: 10.5, color: "var(--muted)", marginLeft: 8 }}>Усилий: {ini.estimated_effort}</span>}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                      <button onClick={() => handleInitiative(ini.id, "accept")}
                        style={{ padding: "6px 12px", borderRadius: "var(--radius-pill)", fontSize: 11, cursor: "pointer",
                          border: "1px solid #a0e0ab", background: "rgba(160,224,171,0.15)", color: "#a0e0ab" }}>✅ Принять</button>
                      <button onClick={() => handleInitiative(ini.id, "reject")}
                        style={{ padding: "6px 12px", borderRadius: "var(--radius-pill)", fontSize: 11, cursor: "pointer",
                          border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)" }}>✖</button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Уровень автономности */}
        {autonomy && (
          <>
            <SectionLabel>Автономность офиса</SectionLabel>
            <Card style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px", marginBottom: 24 }}>
              <span style={{ fontSize: 22 }}>{autonomy.icon}</span>
              <div>
                <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{autonomy.name}</div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>{autonomy.desc}</div>
              </div>
              <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
                {["scout", "guided", "trusted", "autonomous"].map(lvl => (
                  <button key={lvl} onClick={() => api.post("/api/autonomy", { level: lvl }).then(() => api.get("/api/autonomy").then(setAutonomy))}
                    style={{ padding: "4px 10px", borderRadius: "var(--radius-pill)", fontSize: 10, cursor: "pointer",
                      border: `1px solid ${autonomy.level === lvl ? "var(--mercury-a)" : "var(--hairline)"}`,
                      background: autonomy.level === lvl ? "rgba(160,224,171,0.15)" : "transparent",
                      color: autonomy.level === lvl ? "var(--mercury-a)" : "var(--text-dim)" }}>{lvl}</button>
                ))}
              </div>
            </Card>
          </>
        )}

        {/* Метрики */}
        <SectionLabel>Ключевые метрики</SectionLabel>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 24 }}>
          {metrics.map(m => (
            <Card key={m.label}>
              <div className="display" style={{ fontSize: 28, color: "var(--text)", lineHeight: 1 }}>{m.value}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 7 }}>{m.label}</div>
            </Card>
          ))}
        </div>

        {/* Быстрые ссылки */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button onClick={() => onNavigate?.("project")} style={linkCard}>📋 План и задачи →</button>
          <button onClick={() => onNavigate?.("results")} style={linkCard}>📦 Результаты →</button>
          <button onClick={() => onNavigate?.("team")} style={linkCard}>👥 Команда →</button>
        </div>
      </ViewBody>
    </ViewShell>
  )
}

const linkBtn: React.CSSProperties = {
  fontSize: 11.5, color: "var(--mercury-a)", background: "transparent",
  border: "1px solid var(--hairline)", borderRadius: "var(--radius-pill)",
  padding: "5px 12px", cursor: "pointer",
}

const linkCard: React.CSSProperties = {
  flex: "1 1 160px", textAlign: "left", fontSize: 13, color: "var(--text-dim)",
  background: "var(--surface-soft)", border: "1px solid var(--hairline)",
  borderRadius: "var(--radius-md)", padding: "14px 16px", cursor: "pointer",
}
