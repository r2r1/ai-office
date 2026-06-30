import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName } from "../../data/roles"
import type { ReactNode } from "react"
import { ViewShell, ViewHead, SubTabs, ViewBody, Card, Empty, Pill, MercuryBar } from "./ui"
import { Modal, ModalSection, ModalPre } from "../components/Modal"
import { useThrottled } from "../hooks"

type ModalContent = { title: ReactNode; subtitle?: ReactNode; body: ReactNode } | null

const TABS = [
  { id: "milestones", label: "Этапы" },
  { id: "tasks",      label: "Задачи" },
]

export function ProjectView() {
  const { state } = useOffice()
  const [tab, setTab] = useState("milestones")
  const [milestones, setMilestones] = useState<any[]>([])
  const tasks = state.plan.tasks || []
  const tick = useThrottled(state.feed.length, 2500)
  const [modal, setModal] = useState<ModalContent>(null)

  useEffect(() => {
    api.milestones().then(d => setMilestones(d.stages || []))
  }, [tick])

  const tabsWithBadges = TABS.map(t => ({
    ...t,
    badge: t.id === "tasks" ? tasks.filter((x: any) => x.status === "in_progress").length
      : t.id === "milestones" ? milestones.length
      : undefined,
  }))

  return (
    <ViewShell>
      <ViewHead title="Проект" sub={state.ready ? state.progress.note || "План работы офиса" : "Ожидание брифа"} />
      <SubTabs tabs={tabsWithBadges} active={tab} onChange={setTab} />

      {tab === "milestones" && <MilestonesTab milestones={milestones} progress={state.progress} onOpen={setModal} />}
      {tab === "tasks"      && <TasksTab tasks={tasks} />}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.title} subtitle={modal?.subtitle}>
        {modal?.body}
      </Modal>
    </ViewShell>
  )
}

// ── Этапы ────────────────────────────────────────────────────────────────────
function stageModal(m: any, idx: number): ModalContent {
  const items = m.items || []
  return {
    title: m.title || m.name || m.id,
    subtitle: `Этап ${idx + 1} · ${m.status === "done" ? "готов" : m.status === "active" ? "в работе" : "ожидает"}`,
    body: (
      <>
        {m.description && (
          <ModalSection label="Описание">
            <div style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.6 }}>{m.description}</div>
          </ModalSection>
        )}
        {m.summary && (
          <ModalSection label="Что достигнуто">
            <ModalPre>{m.summary}</ModalPre>
          </ModalSection>
        )}
        {items.length > 0 && (
          <ModalSection label={`Записи о работе · ${items.length}`}>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {items.map((it: any, i: number) => (
                <div key={i} style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.55, paddingLeft: 12,
                  borderLeft: "2px solid var(--hairline-strong)" }}>
                  {it.role && <span style={{ color: "var(--mercury-a)", marginRight: 6 }}>{roleName(it.role)}</span>}
                  {it.text}
                </div>
              ))}
            </div>
          </ModalSection>
        )}
        {!m.description && !m.summary && items.length === 0 && (
          <div style={{ color: "var(--muted)", fontSize: 13 }}>По этому этапу пока нет записей.</div>
        )}
      </>
    ),
  }
}

function MilestonesTab({ milestones, progress, onOpen }: { milestones: any[]; progress: any; onOpen: (c: ModalContent) => void }) {
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
            <Card key={m.id || i} onClick={() => onOpen(stageModal({ ...m, status: stageInfo?.status }, i))}
              style={{ position: "relative", overflow: "hidden",
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
                  {m.description && <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5,
                    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{m.description}</div>}
                  {m.summary && <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 8, lineHeight: 1.5, borderLeft: "2px solid var(--hairline-strong)", paddingLeft: 10,
                    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{m.summary}</div>}
                  <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 8 }}>Нажмите, чтобы открыть полностью →</div>
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

function TasksTab({ tasks }: { tasks: any[] }) {
  return (
    <ViewBody>
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

