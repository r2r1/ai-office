import { useEffect, useState } from "react"
import { useOffice, refreshData } from "../../data/OfficeProvider"
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
  { id: "projects",   label: "Проекты" },
  { id: "spec",       label: "Спецификация" },
]

export function ProjectView() {
  const { state } = useOffice()
  const [tab, setTab] = useState("milestones")
  const [milestones, setMilestones] = useState<any[]>([])
  const [projects, setProjects] = useState<any[]>([])
  const tasks = state.plan.tasks || []
  const tick = useThrottled(state.feed.length, 2500)
  const [modal, setModal] = useState<ModalContent>(null)

  useEffect(() => {
    api.milestones().then(d => setMilestones(d.stages || []))
    api.projects().then(d => setProjects(d.projects || []))
  }, [tick])

  const tabsWithBadges = TABS.map(t => ({
    ...t,
    badge: t.id === "tasks" ? tasks.filter((x: any) => x.status === "in_progress").length
      : t.id === "milestones" ? milestones.length
      : t.id === "projects" ? (projects.length || undefined)
      : undefined,
  }))

  return (
    <ViewShell>
      <ViewHead title="Проект" sub={state.ready ? state.progress.note || "План работы офиса" : "Ожидание брифа"} />
      <SubTabs tabs={tabsWithBadges} active={tab} onChange={setTab} />

      {tab === "milestones" && <MilestonesTab milestones={milestones} progress={state.progress} onOpen={setModal} />}
      {tab === "tasks"      && <TasksTab tasks={tasks} />}
      {tab === "projects"   && <ProjectsTab projects={projects} />}
      {tab === "spec"       && <SpecTab tick={tick} />}

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
  { key: "blocked",     label: "Заблокированы", dot: "#e08a8a" },
  // skipped — задача снята офисом (роль без отдела-исполнителя), НЕ выполнена.
  { key: "skipped",     label: "Пропущены",  dot: "var(--muted)" },
]

function TasksTab({ tasks }: { tasks: any[] }) {
  const [unblocking, setUnblocking] = useState<string>("")
  const hasBlocked = tasks.some((t: any) => t.status === "blocked")
  const hasSkipped = tasks.some((t: any) => t.status === "skipped")
  // Колонки «Заблокированы»/«Пропущены» показываем только когда в них есть задачи.
  const cols = COLS.filter(c =>
    (c.key !== "blocked" || hasBlocked) && (c.key !== "skipped" || hasSkipped))

  const unblock = async (id: string) => {
    setUnblocking(id)
    await api.unblockTask(id)
    await refreshData(["plan"])  // сразу показать задачу в очереди, не ждать SSE
    setUnblocking("")
  }

  return (
    <ViewBody>
      {tasks.length === 0 ? (
        <Empty icon="◉" text="План задач появится после старта офиса"
          hint="Директор сформирует доску после получения стратегии" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
          {cols.map(col => {
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
                        {(t.attempts || 0) > 0 && col.key !== "done" && (
                          <Pill color="#e0b06a">попытка {t.attempts}</Pill>
                        )}
                        {t.done_criterion && col.key !== "done" && col.key !== "blocked" && (
                          <span style={{ fontSize: 10, color: "#6f8a6a", lineHeight: 1.3 }}>✓ {t.done_criterion}</span>
                        )}
                      </div>
                      {col.key === "blocked" && (
                        <div style={{ marginTop: 8 }}>
                          {t.blocked_reason && (
                            <div style={{ fontSize: 10.5, color: "#e08a8a", lineHeight: 1.4, marginBottom: 8 }}>
                              ⛔ {t.blocked_reason}
                            </div>
                          )}
                          <button onClick={() => unblock(t.id)} disabled={unblocking === t.id}
                            style={{ fontSize: 11, padding: "5px 10px", borderRadius: 6, cursor: "pointer",
                              background: "var(--surface-soft)", border: "1px solid var(--hairline-strong)",
                              color: "var(--text-dim)" }}>
                            {unblocking === t.id ? "…" : "↩ Вернуть в работу"}
                          </button>
                        </div>
                      )}
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

// ── Проекты ───────────────────────────────────────────────────────────────────
function ProjectsTab({ projects }: { projects: any[] }) {
  if (projects.length === 0) return (
    <ViewBody>
      <Empty icon="📁" text="Проектов пока нет"
        hint="Первый проект появится вместе с планом задач" />
    </ViewBody>
  )
  return (
    <ViewBody>
      <div style={{ display: "grid", gap: 12 }}>
        {[...projects].reverse().map((p: any) => {
          const lb = p.left_behind || {}
          const isActive = p.status === "active"
          return (
            <Card key={p.id} style={{ borderColor: isActive ? "rgba(255,172,46,0.3)" : undefined }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
                    {isActive ? <Pill accent>Активный</Pill> : <Pill color="#a0e0ab">Закрыт</Pill>}
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)", marginBottom: 6, lineHeight: 1.3 }}>{p.title}</div>
                  {p.goal && <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{p.goal}</div>}
                  {p.status === "done" && (
                    <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 8, display: "flex", gap: 14, flexWrap: "wrap" }}>
                      <span>✓ задач: {lb.tasks_done ?? 0}/{lb.tasks_total ?? 0}</span>
                      <span>🌐 сайтов: {(lb.sites || []).length}</span>
                      <span>👤 лидов: {lb.leads_count ?? 0}</span>
                    </div>
                  )}
                </div>
                <div className="mono" style={{ fontSize: 22, color: isActive ? "var(--mercury-a)" : "#a0e0ab", flexShrink: 0 }}>
                  {isActive ? "▶" : "✓"}
                </div>
              </div>
            </Card>
          )
        })}
      </div>
    </ViewBody>
  )
}

// ── Спецификация (контракт приёмки) ──────────────────────────────────────────
function SpecTab({ tick }: { tick: number }) {
  const [spec, setSpec] = useState<any>(null)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => { api.specification().then(setSpec) }, [tick])

  const confirm = async () => {
    setConfirming(true)
    const r = await api.confirmSpecification()
    if (r?.specification) setSpec(r.specification)
    setConfirming(false)
  }

  if (!spec || !(spec.functions || []).length) return (
    <ViewBody>
      <Empty icon="📜" text="Спецификация ещё не сформирована"
        hint="Появится вместе с планом задач: что делаем и когда это успех" />
    </ViewBody>
  )

  const confirmed = spec.status === "confirmed"
  return (
    <ViewBody>
      <Card style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text)", marginBottom: 4 }}>
              Контракт приёмки {confirmed ? "— подтверждён вами" : "— черновик"}
            </div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>
              Что офис собирается сделать и по каким критериям работа считается выполненной.
            </div>
          </div>
          {confirmed ? <Pill color="#a0e0ab">✓ Подтверждена</Pill> : (
            <button onClick={confirm} disabled={confirming}
              style={{ fontSize: 12, padding: "8px 14px", borderRadius: 8, cursor: "pointer",
                background: "var(--mercury-a)", border: "none", color: "#1a1408", fontWeight: 600 }}>
              {confirming ? "…" : "Подтвердить спецификацию"}
            </button>
          )}
        </div>
      </Card>
      {spec.goal && (
        <Card style={{ marginBottom: 14 }}>
          <SectionMini>Цель</SectionMini>
          <div style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.5 }}>{spec.goal}</div>
          {spec.niche && <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>Бизнес: {spec.niche}{spec.audience ? ` · Аудитория: ${spec.audience}` : ""}</div>}
        </Card>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
        <Card>
          <SectionMini>Что делаем · {(spec.functions || []).length}</SectionMini>
          <ol style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 7 }}>
            {(spec.functions || []).map((f: string, i: number) => (
              <li key={i} style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45 }}>{f}</li>
            ))}
          </ol>
        </Card>
        <Card>
          <SectionMini>Когда это успех · {(spec.success_criteria || []).length}</SectionMini>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {(spec.success_criteria || []).map((c: string, i: number) => (
              <div key={i} style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45 }}>
                <span style={{ color: "#6f8a6a", marginRight: 6 }}>✓</span>{c}
              </div>
            ))}
            {(spec.success_criteria || []).length === 0 && (
              <div style={{ fontSize: 12, color: "var(--faint)" }}>Критерии появятся вместе с задачами плана</div>
            )}
          </div>
        </Card>
      </div>
    </ViewBody>
  )
}

function SectionMini({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: 0.6, textTransform: "uppercase",
    color: "var(--muted)", marginBottom: 10 }}>{children}</div>
}

