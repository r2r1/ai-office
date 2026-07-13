import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, SubTabs, Card, SectionLabel, Pill, MercuryBar, ShowMore } from "./ui"
import { BusinessDashboard } from "./BusinessDashboard"
import type { Section } from "../types"

const DEPT_NAMES: Record<string, string> = { tech: "Технический", marketing: "Маркетинг", sales: "Продажи" }

interface DashboardViewProps {
  onNavigate?: (s: Section) => void
  /** Открыть конкретный проект во вкладке «Проект» (после принятия инициативы). */
  onOpenProject?: (projectId: string) => void
}

const TABS = [
  { id: "office",   label: "Офис" },
  { id: "business", label: "Бизнес" },
  { id: "transparency", label: "Прозрачность" },
]

export function DashboardView({ onNavigate, onOpenProject }: DashboardViewProps) {
  const { state } = useOffice()
  const [tab, setTab] = useState("office")
  const [health, setHealth] = useState<any>(null)
  const [autonomy, setAutonomy] = useState<any>(null)
  const [initiatives, setInitiatives] = useState<any[]>([])
  const [milestones, setMilestones] = useState<any[]>([])
  const [gaps, setGaps] = useState<any[]>([])
  // Результат последнего accept — показываем "стало проектом «X»" вместо тишины.
  const [acceptedResult, setAcceptedResult] = useState<{ title: string; projectId: string; projectTitle: string } | null>(null)

  useEffect(() => {
    api.get("/api/health").then(setHealth).catch(() => {})
    api.get("/api/autonomy").then(setAutonomy).catch(() => {})
    api.get("/api/initiatives").then(d => setInitiatives(d?.pending || [])).catch(() => {})
    api.milestones().then(d => setMilestones(d.stages || []))
    api.gap().then(d => setGaps(d.gaps || [])).catch(() => {})
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

  async function handleInitiative(iid: string, action: "accept" | "reject", override = false) {
    const ini = initiatives.find(i => i.id === iid)
    const r = await api.post(`/api/initiative/${iid}/${action}`, action === "accept" ? { override } : {})
    // Гейт вердикта (docs/product-capability-gaps.md п.6): исследование сказало
    // "не стоит" — сервер отказал без override. Не тихо проглатываем, а явно
    // переспрашиваем: владелец видит рекомендацию и решает сам ещё раз.
    if (r?.error === "initiative_blocked") {
      const confirmed = window.confirm(
        `⚠️ Офис рекомендует НЕ делать эту инициативу.\n\n${r.research || r.message}\n\nВсё равно принять?`
      )
      if (confirmed) {
        await handleInitiative(iid, "accept", true)
      }
      return
    }
    setInitiatives(prev => prev.filter(i => i.id !== iid))
    if (action === "accept" && r?.project_id && ini) {
      setAcceptedResult({ title: ini.title, projectId: r.project_id, projectTitle: r.project_title || ini.title })
    }
  }

  return (
    <ViewShell>
      <ViewHead title="Сводка" sub={state.ready ? "Состояние компании на текущий момент" : "Офис ожидает бриф"} />
      <SubTabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "business" ? <BusinessDashboard /> : tab === "transparency" ? <TransparencyTab /> : (
      <ViewBody>
        {/* Gap до цели — заголовок Command Center: разрыв между тем, где
            компания хочет быть, и где она сейчас (BOS §3 Gap Analysis). Раньше
            это вычислялось бэкендом (src/office/gap.py) и никогда не
            показывалось — единственный экран продукта обязан начинаться с
            этого, а не с анимации или общих цифр. */}
        {gaps.length > 0 && (
          <div style={{ marginBottom: 22 }}>
            <SectionLabel>🎯 До цели</SectionLabel>
            <div style={{ display: "grid", gap: 10 }}>
              <ShowMore items={gaps} initial={3}
                render={(g: any, i: number) => (
                  <Card key={i} style={{
                    borderLeft: `3px solid ${g.met ? "var(--success)" : "var(--mercury-a)"}`,
                    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap",
                  }}>
                    <div style={{ fontSize: 13, color: "var(--text)" }}>{g.title}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span className="mono" style={{ fontSize: 13, color: "var(--text-dim)" }}>
                        {g.current} <span style={{ color: "var(--faint)" }}>из</span> {g.desired}
                      </span>
                      {g.met ? <Pill color="var(--success)">✓ достигнута</Pill> : <Pill accent>разрыв {g.gap}</Pill>}
                    </div>
                  </Card>
                )} />
            </div>
          </div>
        )}

        {/* Прогресс по проекту + текущий этап */}
        <MercuryBar percent={state.progress.percent} style={{ marginBottom: 10 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
          <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {currentStage ? <>Сейчас: <b style={{ color: "var(--text)" }}>{currentStage.title || currentStage.name}</b></> : (state.progress.note || "—")}
          </div>
          <button onClick={() => onNavigate?.("project")}
            style={linkBtn}>Доска задач →</button>
        </div>

        {/* Результат последнего accept — куда делась принятая инициатива */}
        {acceptedResult && (
          <Card style={{ borderLeft: "3px solid var(--success)", padding: "12px 16px", marginBottom: 18,
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
              ✅ «{acceptedResult.title}» стала проектом «<b style={{ color: "var(--text)" }}>{acceptedResult.projectTitle}</b>»
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => { onOpenProject?.(acceptedResult.projectId); setAcceptedResult(null) }}
                style={{ padding: "6px 12px", borderRadius: "var(--radius-pill)", fontSize: 11, cursor: "pointer",
                  border: "1px solid var(--hairline-strong)", background: "var(--surface-soft)", color: "var(--text)" }}>
                Открыть →
              </button>
              <button onClick={() => setAcceptedResult(null)}
                style={{ padding: "6px 10px", borderRadius: "var(--radius-pill)", fontSize: 11, cursor: "pointer",
                  border: "none", background: "transparent", color: "var(--muted)" }}>×</button>
            </div>
          </Card>
        )}

        {/* Инициативы CEO — решения ждут пользователя, поэтому идут ДО
            статусных виджетов (Command Center: сначала «что решить», потом
            «как дела»). */}
        {initiatives.length > 0 && (
          <>
            <SectionLabel>💡 Инициативы CEO · {initiatives.length}</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
              <ShowMore items={initiatives} initial={3} render={(ini: any) => (
                <Card key={ini.id} style={{ borderLeft: "3px solid var(--mercury-a)", padding: "14px 16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500, marginBottom: 5 }}>{ini.title}</div>
                      <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5, marginBottom: 5 }}>{ini.rationale}</div>
                      {ini.recommendation === "no-go" && (
                        <div style={{ fontSize: 11, color: "var(--danger, #e05a5a)", marginBottom: 5 }}>
                          ⚠️ Офис рекомендует не делать
                        </div>
                      )}
                      {ini.expected_outcome && <Pill accent>📈 {ini.expected_outcome}</Pill>}
                      {ini.estimated_effort && <span style={{ fontSize: 10.5, color: "var(--muted)", marginLeft: 8 }}>Усилий: {ini.estimated_effort}</span>}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                      <button onClick={() => handleInitiative(ini.id, "accept")}
                        style={{ padding: "6px 12px", borderRadius: "var(--radius-pill)", fontSize: 11, cursor: "pointer",
                          border: "1px solid var(--success)", background: "rgba(160,224,171,0.15)", color: "var(--success)" }}>✅ Принять</button>
                      <button onClick={() => handleInitiative(ini.id, "reject")}
                        style={{ padding: "6px 12px", borderRadius: "var(--radius-pill)", fontSize: 11, cursor: "pointer",
                          border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)" }}>✖</button>
                    </div>
                  </div>
                </Card>
              )} />
            </div>
          </>
        )}

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
                    <div style={{ height: "100%", width: `${ds.score}%`, background: ds.score >= 75 ? "var(--success)" : ds.score >= 45 ? "var(--mercury-a)" : "var(--danger)", transition: "width 0.5s" }} />
                  </div>
                  {ds.issues?.length > 0 && (
                    <div style={{ marginTop: 6, fontSize: 10, color: "var(--mercury-a)" }}>⚠ {ds.issues.join(" · ")}</div>
                  )}
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

        {/* Опубликованные сайты — раньше их можно было найти только через
            глубокую навигацию в файловом хранилище проекта; здесь видно
            сразу, сколько их и куда каждый ведёт. */}
        {state.sites.length > 0 && (
          <>
            <SectionLabel>🌐 Опубликованные сайты · {state.sites.length}</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
              {state.sites.map((s: any) => (
                <Card key={s.slug} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "10px 14px" }}>
                  <span style={{ fontSize: 12.5, color: "var(--text)" }}>{s.title || s.slug}</span>
                  <a href={s.url || `/site/${s.slug}`} target="_blank" rel="noreferrer"
                    style={{ fontSize: 12, color: "var(--mercury-a)", textDecoration: "none", display: "flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
                    Открыть <span style={{ fontSize: 11 }}>↗</span>
                  </a>
                </Card>
              ))}
            </div>
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
          <button onClick={() => onNavigate?.("project")} style={linkCard}>📋 План, задачи и артефакты проектов →</button>
          <button onClick={() => onNavigate?.("team")} style={linkCard}>👥 Команда →</button>
        </div>
      </ViewBody>
      )}
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

// ── Прозрачность: намерения владельца + хронология решений офиса ──────────────
// Раньше это существовало только как API (/api/intents, /api/observability/*) —
// намерение владельца интерпретировалось молча, а решения CEO нельзя было
// проследить нигде, кроме как через curl. Здесь — минимальный, но полный путь:
// список → клик по решению → цепочка промпт→исполнение→изменение мира.
const SOURCE_UI: Record<string, { label: string; color?: string }> = {
  decision: { label: "решение", color: "var(--mercury-a)" },
  prompt:   { label: "промпт" },
  trace:    { label: "исполнение" },
  snapshot: { label: "срез мира", color: "var(--success)" },
}

function TransparencyTab() {
  const [intents, setIntents] = useState<any[]>([])
  const [timeline, setTimeline] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [openDecision, setOpenDecision] = useState<string | null>(null)
  const [chain, setChain] = useState<any>(null)

  useEffect(() => {
    Promise.all([api.intents(), api.observabilityTimeline(150)]).then(([i, t]) => {
      setIntents(i.intents || [])
      setTimeline([...(t.timeline || [])].reverse())
      setLoading(false)
    })
  }, [])

  const openChain = async (id: string) => {
    if (openDecision === id) { setOpenDecision(null); return }
    setOpenDecision(id)
    setChain(null)
    const d = await api.observabilityDecision(id)
    setChain(d)
  }

  if (loading) return <ViewBody><div style={{ fontSize: 12, color: "var(--faint)" }}>Загрузка…</div></ViewBody>

  return (
    <ViewBody>
      <SectionLabel>Намерения владельца · {intents.length}</SectionLabel>
      {intents.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--faint)", marginBottom: 24 }}>
          Пока нет ни одного намерения — появится, когда вы напишете офису задачу в чате
          или пройдёте онбординг.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 8, marginBottom: 24 }}>
          <ShowMore items={intents} initial={4} render={(it: any) => (
            <Card key={it.id} style={{ padding: "12px 14px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
                <div style={{ fontSize: 12.5, color: "var(--text)", flex: 1 }}>{it.text}</div>
                <Pill color={it.status === "interpreted" ? "var(--success)" : "var(--warning)"}>
                  {it.status === "interpreted" ? "понято" : "получено"}
                </Pill>
              </div>
              {it.interpretation?.directive && (
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 7, borderTop: "1px solid var(--hairline)", paddingTop: 7 }}>
                  → {it.interpretation.directive}
                  {it.interpretation.tasks_added > 0 && ` · задач добавлено: ${it.interpretation.tasks_added}`}
                </div>
              )}
            </Card>
          )} />
        </div>
      )}

      <SectionLabel>Хронология офиса · последние {timeline.length}</SectionLabel>
      {timeline.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--faint)" }}>
          Хронология пуста за последний час — офис ничего не делал или на паузе.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 6 }}>
          {timeline.map((e: any, i: number) => {
            const src = SOURCE_UI[e.source] || { label: e.source }
            const clickable = e.source === "decision"
            return (
              <div key={i}>
                <Card
                  onClick={clickable ? () => openChain(e.id) : undefined}
                  style={{ padding: "9px 13px", display: "flex", alignItems: "center", gap: 10,
                    cursor: clickable ? "pointer" : "default" }}>
                  <Pill color={src.color}>{src.label}</Pill>
                  <div style={{ fontSize: 12, color: "var(--text-dim)", flex: 1, minWidth: 0,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {e.kind}{e.made_by ? ` · ${e.made_by}` : e.agent ? ` · ${e.agent}` : ""}
                    {e.thought ? ` — ${e.thought}` : ""}
                  </div>
                  <div className="mono" style={{ fontSize: 10.5, color: "var(--faint)", flexShrink: 0 }}>
                    {e.t ? new Date(e.t * 1000).toLocaleTimeString("ru-RU") : ""}
                  </div>
                </Card>
                {openDecision === e.id && (
                  <Card style={{ marginTop: 4, padding: "14px 16px", background: "var(--surface-soft)" }}>
                    {!chain ? (
                      <div style={{ fontSize: 12, color: "var(--faint)" }}>Загрузка цепочки…</div>
                    ) : chain.error ? (
                      <div style={{ fontSize: 12, color: "var(--faint)" }}>Не найдено.</div>
                    ) : (
                      <div style={{ display: "grid", gap: 10, fontSize: 12 }}>
                        <div>
                          <div style={{ color: "var(--muted)", fontSize: 10.5, textTransform: "uppercase", marginBottom: 3 }}>Мысль решения</div>
                          <div style={{ color: "var(--text-dim)" }}>{chain.decision?.thought || "—"}</div>
                        </div>
                        <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                          <span style={{ color: "var(--muted)" }}>Уверенность: <b style={{ color: "var(--text)" }}>{chain.decision?.confidence ?? "—"}%</b></span>
                          <span style={{ color: "var(--muted)" }}>Промпт: <b style={{ color: "var(--text)" }}>
                            {chain.prompt ? `${chain.prompt.system_chars}+${chain.prompt.task_chars} симв.` : "не найден"}</b></span>
                          <span style={{ color: "var(--muted)" }}>Исполнение: <b style={{ color: "var(--text)" }}>{(chain.trace || []).length} записей</b></span>
                        </div>
                        {chain.world_diff && (
                          <div>
                            <div style={{ color: "var(--muted)", fontSize: 10.5, textTransform: "uppercase", marginBottom: 3 }}>Что изменилось в мире</div>
                            {chain.world_diff.note ? (
                              <div style={{ color: "var(--faint)" }}>{chain.world_diff.note}</div>
                            ) : chain.world_diff.empty ? (
                              <div style={{ color: "var(--faint)" }}>Мир не изменился.</div>
                            ) : (
                              <div className="mono" style={{ color: "var(--text-dim)", fontSize: 11, lineHeight: 1.6, whiteSpace: "pre-line" }}>
                                {[
                                  ...Object.keys(chain.world_diff.added || {}).map(k => `+ ${k}`),
                                  ...Object.keys(chain.world_diff.removed || {}).map(k => `− ${k}`),
                                  ...Object.keys(chain.world_diff.changed || {}).map(k => `~ ${k}`),
                                ].slice(0, 8).join("\n") || "без изменений"}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </Card>
                )}
              </div>
            )
          })}
        </div>
      )}
    </ViewBody>
  )
}
