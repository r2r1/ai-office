import { useEffect, useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import { useOffice, refreshData } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName } from "../../data/roles"
import type { ReactNode } from "react"
import { ViewShell, ViewHead, SubTabs, ViewBody, Card, Empty, Pill, MercuryBar, SectionLabel, Disclosure, ShowMore } from "./ui"
import { useThrottled } from "../hooks"

// Карта сайта (рефакторинг 2026-07-08 — смена паттерна с inline-аккордеона на
// master-detail): список инициатив/проектов/процессов — компактные строки,
// клик по любой ОТКРЫВАЕТ ОТДЕЛЬНЫЙ экран деталей (не разворачивается на
// месте) с кнопкой "Назад" — тот же принцип навигации, что везде в вебе
// (список → карточка → назад), вместо неглубокого аккордеона, который плохо
// масштабируется на пункты действий (принять/отклонить/пауза/удалить).
const TABS = [
  { id: "initiatives", label: "Инициативы" },
  { id: "projects",    label: "Проекты" },
  { id: "processes",   label: "Процессы" },
  { id: "spec",        label: "Спецификация" },
]

// Что именно открыто в детальном экране — единственный "роутер" внутри вкладки
// (без react-router: state, а не URL, но тот же принцип master → detail).
type Selected =
  | { kind: "initiative"; id: string }
  | { kind: "project"; id: string }
  | { kind: "process"; id: string }
  | { kind: "sales" }

interface ProjectViewProps {
  /** Глубокая ссылка — открыть конкретный проект сразу (например, после принятия
   * инициативы на Сводке), не заставляя искать его в списке. */
  focusProjectId?: string
  onFocusHandled?: () => void
}

export function ProjectView({ focusProjectId, onFocusHandled }: ProjectViewProps = {}) {
  const { state } = useOffice()
  const [tab, setTab] = useState("initiatives")
  const [projects, setProjects] = useState<any[]>([])
  const [initiatives, setInitiatives] = useState<any[]>([])
  const [researchingInitiatives, setResearchingInitiatives] = useState<any[]>([])
  const [leadsSummary, setLeadsSummary] = useState<{ statuses: string[]; labels: Record<string, string>; leads: any[] }>({ statuses: [], labels: {}, leads: [] })
  const [processes, setProcesses] = useState<any[]>([])
  const [selected, setSelected] = useState<Selected | null>(null)
  const [details, setDetails] = useState<Record<string, any>>({})
  const tick = useThrottled(state.feed.length, 2500)

  const refreshProcesses = () => api.processes().then(d => setProcesses(d.processes || []))
  const refreshInitiatives = () => api.initiatives().then(d => {
    setInitiatives(d.pending || [])
    setResearchingInitiatives(d.researching || [])
  })

  useEffect(() => {
    api.projects().then(d => setProjects(d.projects || []))
    refreshInitiatives()
    api.leads().then(d => setLeadsSummary(d))
    refreshProcesses()
  }, [tick])

  // Детали открытого проекта — подгружаются при открытии и обновляются каждый
  // тик, пока экран открыт (живой прогресс), как и раньше при inline-раскрытии.
  useEffect(() => {
    if (selected?.kind !== "project") return
    api.projectDetail(selected.id).then(d => setDetails(prev => ({ ...prev, [selected.id]: d })))
  }, [tick, selected]) // eslint-disable-line

  // Глубокая ссылка: как только список проектов подгружен — открываем экран проекта.
  useEffect(() => {
    if (!focusProjectId) return
    const p = projects.find((x: any) => x.id === focusProjectId)
    if (p) {
      setTab("projects")
      setSelected({ kind: "project", id: p.id })
      onFocusHandled?.()
    }
  }, [focusProjectId, projects]) // eslint-disable-line

  async function acceptInitiative(iid: string) {
    const r = await api.acceptInitiative(iid)
    setInitiatives(prev => prev.filter(i => i.id !== iid))
    const d = await api.projects()
    setProjects(d.projects || [])
    // Принятая инициатива стала конкретным проектом — переключаемся на вкладку
    // «Проекты» и сразу открываем его экран, не заставляя искать глазами в
    // списке (BOS §5: decision spawn_project).
    if (r?.project_id) { setTab("projects"); setSelected({ kind: "project", id: r.project_id }) }
    else setSelected(null)
  }

  async function rejectInitiative(iid: string) {
    await api.rejectInitiative(iid)
    setInitiatives(prev => prev.filter(i => i.id !== iid))
    setSelected(null)
  }

  async function proposeInitiative(title: string, idea: string) {
    await api.proposeInitiative(title, idea)
    await refreshInitiatives()
  }

  async function createProcess(title: string, role: string, instruction: string) {
    await api.createProcess(title, role, instruction)
    await refreshProcesses()
  }
  async function pauseProcess(id: string) { await api.pauseProcess(id); await refreshProcesses() }
  async function resumeProcess(id: string) { await api.resumeProcess(id); await refreshProcesses() }
  async function deleteProcess(id: string) {
    await api.deleteProcess(id)
    setSelected(null)
    await refreshProcesses()
  }

  const refreshProjects = () => api.projects().then(d => setProjects(d.projects || []))
  async function pauseProject(id: string) { await api.pauseProject(id); await refreshProjects() }
  async function resumeProject(id: string) { await api.resumeProject(id); await refreshProjects() }
  // Приоритет очереди: фронт всегда шлёт ПОЛНЫЙ порядок текущей очереди —
  // индекс в списке становится priority на бэкенде (см. projects.reorder_queue).
  async function reorderQueue(order: string[]) {
    setProjects(prev => {
      const byId = new Map(prev.map(p => [p.id, p]))
      order.forEach((id, i) => { const p = byId.get(id); if (p) p.priority = i })
      return [...prev]
    })
    await api.reorderProjectsQueue(order)
  }

  const hasSalesProcess = leadsSummary.leads.length > 0
  const tabsWithBadges = TABS.map(t => ({
    ...t,
    badge: t.id === "initiatives" ? (initiatives.length + researchingInitiatives.length || undefined)
      : t.id === "projects" ? (projects.length || undefined)
      : t.id === "processes" ? (processes.length + (hasSalesProcess ? 1 : 0) || undefined)
      : undefined,
  }))

  return (
    <ViewShell>
      <ViewHead title="Работа" sub={state.ready ? state.progress.note || "План работы офиса" : "Ожидание брифа"} />
      <AnimatePresence mode="wait" initial={false}>
        {selected ? (
          <motion.div key="detail" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}
            initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 16 }}
            transition={{ duration: 0.18, ease: "easeOut" }}>
            <DetailScreen
              selected={selected} onBack={() => setSelected(null)}
              initiatives={initiatives} processes={processes} projects={projects}
              details={details} leadsSummary={leadsSummary}
              onAccept={acceptInitiative} onReject={rejectInitiative}
              onPause={pauseProcess} onResume={resumeProcess} onDelete={deleteProcess}
              onPauseProject={pauseProject} onResumeProject={resumeProject}
            />
          </motion.div>
        ) : (
          <motion.div key="list" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}
            initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.18, ease: "easeOut" }}>
            <SubTabs tabs={tabsWithBadges} active={tab} onChange={setTab} />
            {tab === "initiatives" && (
              <InitiativesTab initiatives={initiatives} researching={researchingInitiatives}
                onOpen={id => setSelected({ kind: "initiative", id })} onPropose={proposeInitiative} />
            )}
            {tab === "projects" && (
              <ProjectsOnlyTab projects={projects} onOpen={id => setSelected({ kind: "project", id })}
                onReorderQueue={reorderQueue} />
            )}
            {tab === "processes" && (
              <ProcessesTab leadsSummary={leadsSummary} processes={processes}
                onOpenProcess={id => setSelected({ kind: "process", id })}
                onOpenSales={() => setSelected({ kind: "sales" })}
                onCreateProcess={createProcess} />
            )}
            {tab === "spec" && <SpecTab tick={tick} />}
          </motion.div>
        )}
      </AnimatePresence>
    </ViewShell>
  )
}

// Work.type (BOS §5) — бейдж, чтобы список не выглядел так, будто Process и
// Initiative — это Project без даты окончания (семантика прогресса разная).
const WORK_TYPE_BADGE: Record<string, { icon: string; label: string }> = {
  project: { icon: "🎯", label: "Проект" },
  process: { icon: "🔄", label: "Процесс" },
  initiative: { icon: "💡", label: "Инициатива" },
}

// ── Шапка любого детального экрана: кнопка "Назад" + тип + заголовок + статус.
// Единая для инициативы/проекта/процесса — так пользователь учит паттерн один
// раз и узнаёт его везде (navigation-consistency). ──────────────────────────
function DetailHeader({ badge, statusPill, title, sub, onBack, actions }: {
  badge: { icon: string; label: string }; statusPill?: ReactNode; title: string; sub?: string
  onBack: () => void; actions?: ReactNode
}) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 14, padding: "14px 28px",
      borderBottom: "1px solid var(--hairline)", flexShrink: 0, flexWrap: "wrap",
    }}>
      <button onClick={onBack}
        style={{
          display: "flex", alignItems: "center", gap: 6, flexShrink: 0, marginTop: 2,
          padding: "8px 14px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
          border: "1px solid var(--hairline-strong)", background: "var(--surface-soft)", color: "var(--text)",
        }}>
        ← Назад к работе
      </button>
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, flexWrap: "wrap" }}>
          <Pill>{badge.icon} {badge.label}</Pill>
          {statusPill}
        </div>
        <div style={{ fontSize: 18, fontWeight: 600, color: "var(--text)", lineHeight: 1.3 }}>{title}</div>
        {sub && <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>{sub}</div>}
      </div>
      {actions && <div style={{ display: "flex", gap: 8, flexShrink: 0, marginTop: 2 }}>{actions}</div>}
    </div>
  )
}

// ── Роутер детального экрана: по selected.kind достаёт нужную сущность из уже
// загруженных списков и рендерит её экран. Сущность могла исчезнуть (принята/
// отклонена/удалена только что) — тогда мягкий фолбэк вместо пустого экрана. ──
function DetailScreen({ selected, onBack, initiatives, processes, projects, details, leadsSummary, onAccept, onReject, onPause, onResume, onDelete, onPauseProject, onResumeProject }: {
  selected: Selected; onBack: () => void
  initiatives: any[]; processes: any[]; projects: any[]; details: Record<string, any>
  leadsSummary: { statuses: string[]; labels: Record<string, string>; leads: any[] }
  onAccept: (id: string) => void; onReject: (id: string) => void
  onPause: (id: string) => void; onResume: (id: string) => void; onDelete: (id: string) => void
  onPauseProject: (id: string) => void; onResumeProject: (id: string) => void
}) {
  if (selected.kind === "initiative") {
    const ini = initiatives.find(i => i.id === selected.id)
    if (!ini) return <GoneScreen onBack={onBack} text="Эта инициатива уже обработана." />
    return <InitiativeDetailScreen initiative={ini} onBack={onBack}
      onAccept={() => onAccept(ini.id)} onReject={() => onReject(ini.id)} />
  }
  if (selected.kind === "process") {
    const proc = processes.find(p => p.id === selected.id)
    if (!proc) return <GoneScreen onBack={onBack} text="Этот процесс удалён." />
    return <ProcessDetailScreen proc={proc} onBack={onBack}
      onPause={() => onPause(proc.id)} onResume={() => onResume(proc.id)} onDelete={() => onDelete(proc.id)} />
  }
  if (selected.kind === "sales") {
    return <SalesProcessDetailScreen summary={leadsSummary} onBack={onBack} />
  }
  const proj = projects.find(p => p.id === selected.id)
  if (!proj) return <GoneScreen onBack={onBack} text="Проект не найден." />
  return <ProjectDetailScreen project={proj} detail={details[proj.id]} onBack={onBack}
    onPause={() => onPauseProject(proj.id)} onResume={() => onResumeProject(proj.id)} />
}

function GoneScreen({ onBack, text }: { onBack: () => void; text: string }) {
  return (
    <>
      <DetailHeader badge={{ icon: "—", label: "Недоступно" }} title="" onBack={onBack} />
      <ViewBody><Empty icon="🕊️" text={text} /></ViewBody>
    </>
  )
}

// ── Инициативы: предлагает AI (opportunity-события) ИЛИ сам предприниматель.
// Жизненный цикл: researching (глубокий анализ идёт) → pending (ждёт решения,
// с готовым анализом) → accept (становится проектом) / reject. Список — только
// заголовок+суть, решение принимается на отдельном экране (клик по строке). ──
function InitiativesTab({ initiatives, researching, onOpen, onPropose }: {
  initiatives: any[]; researching: any[]
  onOpen: (id: string) => void
  onPropose: (title: string, idea: string) => void
}) {
  const isEmpty = initiatives.length === 0 && researching.length === 0
  return (
    <ViewBody>
      {isEmpty && (
        <Empty icon="💡" text="Инициатив пока нет"
          hint="AI предложит их сам по мере наблюдений, или предложи свою идею ниже" />
      )}
      <div style={{ display: "grid", gap: 10, marginBottom: 20 }}>
        {researching.map((ini: any) => (
          <ResearchingInitiativeRow key={ini.id} initiative={ini} />
        ))}
        {initiatives.map((ini: any) => (
          <InitiativeRow key={ini.id} initiative={ini} onClick={() => onOpen(ini.id)} />
        ))}
      </div>
      <NewInitiativeForm onPropose={onPropose} />
    </ViewBody>
  )
}

function NewInitiativeForm({ onPropose }: { onPropose: (title: string, idea: string) => void }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [idea, setIdea] = useState("")
  const [busy, setBusy] = useState(false)

  if (!open) return (
    <button onClick={() => setOpen(true)}
      style={{ padding: "10px 18px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
        border: "1px dashed var(--hairline-strong)", background: "transparent", color: "var(--text-dim)" }}>
      + Предложить свою идею
    </button>
  )

  async function submit() {
    if (!title.trim()) return
    setBusy(true)
    await onPropose(title.trim(), idea.trim())
    setBusy(false); setOpen(false); setTitle(""); setIdea("")
  }

  const inputStyle = {
    width: "100%", padding: "9px 12px", borderRadius: "var(--radius-md)",
    border: "1px solid var(--hairline-strong)", background: "var(--surface)",
    color: "var(--text)", fontSize: 12.5, fontFamily: "var(--font-sans)",
  } as const

  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <SectionLabel>Своя идея</SectionLabel>
      <input style={inputStyle} placeholder="Название идеи" value={title} onChange={e => setTitle(e.target.value)} autoFocus />
      <textarea style={{ ...inputStyle, resize: "vertical" }} rows={2}
        placeholder="Опиши мысль в двух словах — глубокий анализ офис сделает сам"
        value={idea} onChange={e => setIdea(e.target.value)} />
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={submit} disabled={busy || !title.trim()}
          style={{ padding: "8px 16px", borderRadius: "var(--radius-pill)", fontSize: 12, cursor: "pointer",
            border: "none", background: "var(--mercury-a)", color: "var(--on-accent)", fontWeight: 600,
            opacity: busy || !title.trim() ? 0.6 : 1 }}>
          {busy ? "…" : "Отправить на анализ"}
        </button>
        <button onClick={() => setOpen(false)}
          style={{ padding: "8px 16px", borderRadius: "var(--radius-pill)", fontSize: 12, cursor: "pointer",
            border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)" }}>
          Отмена
        </button>
      </div>
    </Card>
  )
}

function ResearchingInitiativeRow({ initiative: ini }: { initiative: any }) {
  return (
    <Card style={{ cursor: "default", opacity: 0.85 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
        <Pill>{WORK_TYPE_BADGE.initiative.icon} {WORK_TYPE_BADGE.initiative.label}</Pill>
        <Pill>⏳ Идёт анализ…</Pill>
      </div>
      <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)", marginBottom: 4 }}>{ini.title}</div>
      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>
        Офис проводит глубокое исследование, прежде чем спросить решение — обычно 1 цикл.
      </div>
    </Card>
  )
}

// Общий "заголовок строки списка" — карточка кликабельна целиком и ведёт на
// отдельный экран (стрелка → вместо шеврона раскрытия ▸, чтобы визуально не
// путать навигацию со старым инлайн-аккордеоном).
function ListRow({ badge, statusPill, title, sub, onClick, extra }: {
  badge: { icon: string; label: string }; statusPill?: ReactNode; title: string; sub?: ReactNode; onClick: () => void
  /** Доп. интерактивный контроль в строке (например стрелки приоритета очереди)
   * — стоит МЕЖДУ текстом и стрелкой перехода, сам гасит клик, чтобы не
   * триггерить навигацию на экран деталей. */
  extra?: ReactNode
}) {
  return (
    <Card onClick={onClick} style={{ cursor: "pointer" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
            <Pill>{badge.icon} {badge.label}</Pill>
            {statusPill}
          </div>
          <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)", marginBottom: 6, lineHeight: 1.3 }}>{title}</div>
          {sub}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          {extra}
          <div className="mono" style={{ fontSize: 15, color: "var(--faint)", marginTop: 2 }}>→</div>
        </div>
      </div>
    </Card>
  )
}

function InitiativeRow({ initiative: ini, onClick }: { initiative: any; onClick: () => void }) {
  return (
    <ListRow badge={WORK_TYPE_BADGE.initiative} onClick={onClick}
      statusPill={<Pill accent>Ждёт решения</Pill>}
      title={ini.title}
      sub={ini.expected_outcome && <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>📈 {ini.expected_outcome}</div>} />
  )
}

// ── Проекты: только Project (разовая работа с началом и концом) ─────────────
function ProjectsOnlyTab({ projects, onOpen, onReorderQueue }: {
  projects: any[]; onOpen: (id: string) => void; onReorderQueue: (order: string[]) => void
}) {
  const active = projects.filter((p: any) => p.status === "active")
  const paused = projects.filter((p: any) => p.status === "paused")
  // "queued" — параллельный Work, ждущий свободного слота (см. project_limits) —
  // раньше падал в ту же корзину, что и "закрытые", и выглядел завершённым,
  // хотя ещё не начинался. Порядок — приоритет (меньше = раньше активируется,
  // см. projects.reorder_queue), не просто дата создания.
  const queued = [...projects.filter((p: any) => p.status === "queued")]
    .sort((a, b) => (a.priority ?? a.created_ts ?? 0) - (b.priority ?? b.created_ts ?? 0))
  const closed = [...projects.filter((p: any) => p.status === "done")].reverse()

  function moveQueue(id: string, dir: -1 | 1) {
    const ids = queued.map((p: any) => p.id)
    const i = ids.indexOf(id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    onReorderQueue(ids)
  }

  if (projects.length === 0) return (
    <ViewBody>
      <Empty icon="🎯" text="Проектов пока нет"
        hint="Появится, как только примешь инициативу или офис соберёт план по брифу" />
    </ViewBody>
  )

  return (
    <ViewBody>
      <div style={{ display: "grid", gap: 10 }}>
        {[...active, ...paused].map((p: any) => (
          <ProjectRow key={p.id} project={p} onClick={() => onOpen(p.id)} />
        ))}
        {queued.map((p: any, i: number) => (
          <ProjectRow key={p.id} project={p} onClick={() => onOpen(p.id)}
            onMoveUp={i > 0 ? () => moveQueue(p.id, -1) : undefined}
            onMoveDown={i < queued.length - 1 ? () => moveQueue(p.id, 1) : undefined} />
        ))}
        {closed.map((p: any) => (
          <ProjectRow key={p.id} project={p} onClick={() => onOpen(p.id)} />
        ))}
      </div>
    </ViewBody>
  )
}

function ProjectRow({ project: p, onClick, onMoveUp, onMoveDown }: {
  project: any; onClick: () => void; onMoveUp?: () => void; onMoveDown?: () => void
}) {
  const lb = p.left_behind || {}
  const isActive = p.status === "active"
  const isQueued = p.status === "queued"
  const isPaused = p.status === "paused"
  const typeBadge = WORK_TYPE_BADGE[p.type || "project"]
  // Стрелки приоритета очереди — не навигация, поэтому гасим клик по строке
  // (stopPropagation), иначе стрелка одновременно открывала бы экран проекта.
  // Хит-зона каждой кнопки — 44×44 (touch-target-size), визуальный чип внутри
  // компактнее — раздувать саму иконку до 44px незачем, только область клика.
  const queueControls = (onMoveUp || onMoveDown) && (
    <div style={{ display: "flex", flexDirection: "column" }} onClick={e => e.stopPropagation()}>
      <button onClick={onMoveUp} disabled={!onMoveUp} title="Поднять в очереди" aria-label="Поднять в очереди"
        style={{ width: 44, height: 22, display: "flex", alignItems: "center", justifyContent: "center",
          border: "none", background: "transparent", padding: 0,
          color: onMoveUp ? "var(--text-dim)" : "var(--faint)", cursor: onMoveUp ? "pointer" : "default" }}>
        <span style={{ width: 22, height: 18, display: "flex", alignItems: "center", justifyContent: "center",
          border: "1px solid var(--hairline)", borderRadius: 4, background: "var(--surface-soft)", fontSize: 10 }}>▲</span>
      </button>
      <button onClick={onMoveDown} disabled={!onMoveDown} title="Опустить в очереди" aria-label="Опустить в очереди"
        style={{ width: 44, height: 22, display: "flex", alignItems: "center", justifyContent: "center",
          border: "none", background: "transparent", padding: 0,
          color: onMoveDown ? "var(--text-dim)" : "var(--faint)", cursor: onMoveDown ? "pointer" : "default" }}>
        <span style={{ width: 22, height: 18, display: "flex", alignItems: "center", justifyContent: "center",
          border: "1px solid var(--hairline)", borderRadius: 4, background: "var(--surface-soft)", fontSize: 10 }}>▼</span>
      </button>
    </div>
  )
  return (
    <ListRow badge={typeBadge} onClick={onClick} extra={queueControls}
      statusPill={isActive ? <Pill accent>Активный</Pill>
        : isQueued ? <Pill color="var(--warning)">⏳ В очереди</Pill>
        : isPaused ? <Pill>⏸ На паузе</Pill>
        : <Pill color="var(--success)">Закрыт</Pill>}
      title={p.title}
      sub={
        <>
          {p.goal && <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{p.goal}</div>}
          {p.status === "done" && (
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 8, display: "flex", gap: 14, flexWrap: "wrap" }}>
              <span>✓ задач: {lb.tasks_done ?? 0}/{lb.tasks_total ?? 0}</span>
              <span>🌐 сайтов: {(lb.sites || []).length}</span>
              <span>👤 лидов: {lb.leads_count ?? 0}</span>
            </div>
          )}
        </>
      } />
  )
}

// ── Процессы: непрерывная работа — конвейер Instance (продажи) ИЛИ
// повторяющееся действие (контент-завод и т.п.). AI сам решает при закрытии
// проекта, не стоит ли превратить его в процесс (см. src/office/loop.py). ──
function ProcessesTab({ leadsSummary, processes, onOpenProcess, onOpenSales, onCreateProcess }: {
  leadsSummary: { statuses: string[]; labels: Record<string, string>; leads: any[] }
  processes: any[]
  onOpenProcess: (id: string) => void; onOpenSales: () => void
  onCreateProcess: (title: string, role: string, instruction: string) => void
}) {
  const hasSalesProcess = leadsSummary.leads.length > 0
  const isEmpty = !hasSalesProcess && processes.length === 0

  return (
    <ViewBody>
      {isEmpty && (
        <Empty icon="🔄" text="Процессов пока нет"
          hint="Появится сам, когда офис решит, что завершённый проект стоит вести постоянно — или заведи свой ниже" />
      )}
      <div style={{ display: "grid", gap: 10, marginBottom: 20 }}>
        {hasSalesProcess && (
          <ListRow badge={WORK_TYPE_BADGE.process} onClick={onOpenSales}
            statusPill={<Pill color="var(--success)">Идёт постоянно</Pill>}
            title="Продажи"
            sub={<div style={{ fontSize: 12, color: "var(--muted)" }}>{leadsSummary.leads.length} лид(ов) в потоке</div>} />
        )}
        {processes.map((p: any) => (
          <ListRow key={p.id} badge={WORK_TYPE_BADGE.process} onClick={() => onOpenProcess(p.id)}
            statusPill={p.status === "active" ? <Pill color="var(--success)">Идёт постоянно</Pill> : <Pill>На паузе</Pill>}
            title={p.title}
            sub={<div style={{ fontSize: 12, color: "var(--muted)" }}>
              {roleName(p.role)} · каждый цикл{p.run_count ? ` · запусков: ${p.run_count}` : ""}
            </div>} />
        ))}
      </div>
      <NewProcessForm onCreate={onCreateProcess} />
    </ViewBody>
  )
}

// Процесс не обязан быть Instance-конвейером (продажи) — это ЛЮБОЕ повторяющееся
// действие: «контент-завод», «ежедневная аналитика рынка». v1-каданс — только
// «каждый цикл офиса» (см. src/office/processes.py); свою задачу процесс ставит
// заново, как только предыдущая закрыта.
const RECURRING_ROLES = ["researcher", "marketer", "analyst", "salesman", "developer", "integrator", "hr"]

function NewProcessForm({ onCreate }: { onCreate: (title: string, role: string, instruction: string) => void }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [role, setRole] = useState(RECURRING_ROLES[0])
  const [instruction, setInstruction] = useState("")
  const [busy, setBusy] = useState(false)

  if (!open) return (
    <button onClick={() => setOpen(true)}
      style={{ padding: "10px 18px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
        border: "1px dashed var(--hairline-strong)", background: "transparent", color: "var(--text-dim)" }}>
      + Новый процесс (повторяющееся действие)
    </button>
  )

  async function submit() {
    if (!title.trim() || !instruction.trim()) return
    setBusy(true)
    await onCreate(title.trim(), role, instruction.trim())
    setBusy(false); setOpen(false); setTitle(""); setInstruction("")
  }

  const inputStyle = {
    width: "100%", padding: "9px 12px", borderRadius: "var(--radius-md)",
    border: "1px solid var(--hairline-strong)", background: "var(--surface)",
    color: "var(--text)", fontSize: 12.5, fontFamily: "var(--font-sans)",
  } as const

  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <SectionLabel>Новый процесс</SectionLabel>
      <input style={inputStyle} placeholder="Название (например: Контент-завод)" value={title} onChange={e => setTitle(e.target.value)} autoFocus />
      <select style={inputStyle} value={role} onChange={e => setRole(e.target.value)}>
        {RECURRING_ROLES.map(r => <option key={r} value={r}>{roleName(r)}</option>)}
      </select>
      <textarea style={{ ...inputStyle, resize: "vertical" }} rows={2}
        placeholder="Что делать каждый цикл (например: написать и опубликовать пост дня по нише клиента)"
        value={instruction} onChange={e => setInstruction(e.target.value)} />
      <div style={{ fontSize: 11, color: "var(--faint)" }}>
        Каданс v1: каждый цикл офиса, как только предыдущая задача процесса закрыта.
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={submit} disabled={busy || !title.trim() || !instruction.trim()}
          style={{ padding: "8px 16px", borderRadius: "var(--radius-pill)", fontSize: 12, cursor: "pointer",
            border: "none", background: "var(--mercury-a)", color: "var(--on-accent)", fontWeight: 600,
            opacity: busy || !title.trim() || !instruction.trim() ? 0.6 : 1 }}>
          {busy ? "…" : "Создать процесс"}
        </button>
        <button onClick={() => setOpen(false)}
          style={{ padding: "8px 16px", borderRadius: "var(--radius-pill)", fontSize: 12, cursor: "pointer",
            border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)" }}>
          Отмена
        </button>
      </div>
    </Card>
  )
}

// ── Экран инициативы: обоснование + анализ + предпросмотр задач + решение. ──
function InitiativeDetailScreen({ initiative: ini, onBack, onAccept, onReject }: {
  initiative: any; onBack: () => void; onAccept: () => void; onReject: () => void
}) {
  return (
    <>
      <DetailHeader badge={WORK_TYPE_BADGE.initiative} title={ini.title} onBack={onBack}
        statusPill={<Pill accent>Ждёт решения</Pill>}
        actions={
          <>
            <button onClick={onAccept}
              style={{ padding: "9px 18px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
                border: "1px solid var(--success)", background: "rgba(160,224,171,0.15)", color: "var(--success)", fontWeight: 500 }}>
              ✅ Принять → создать проект
            </button>
            <button onClick={onReject}
              style={{ padding: "9px 18px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
                border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)" }}>
              ✖ Отклонить
            </button>
          </>
        } />
      <ViewBody>
        <div style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 720 }}>
          <div>
            <SectionLabel style={{ marginBottom: 8 }}>Почему сейчас</SectionLabel>
            <div style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.6 }}>{ini.rationale}</div>
          </div>
          {ini.research && (
            <div>
              <SectionLabel style={{ marginBottom: 8 }}>📊 Глубокий анализ офиса</SectionLabel>
              <div style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.65, whiteSpace: "pre-wrap" }}>{ini.research}</div>
            </div>
          )}
          {ini.expected_outcome && (
            <div>
              <SectionLabel style={{ marginBottom: 8 }}>Ожидаемый результат</SectionLabel>
              <div style={{ fontSize: 13, color: "var(--text-dim)" }}>{ini.expected_outcome}
                {ini.estimated_effort && <span style={{ color: "var(--faint)" }}> · усилий: {ini.estimated_effort}</span>}</div>
            </div>
          )}
          {(ini.tasks || []).length > 0 && (
            <div>
              <SectionLabel style={{ marginBottom: 8 }}>Если принять — появится Проект с задачами · {ini.tasks.length}</SectionLabel>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {ini.tasks.map((t: any, i: number) => (
                  <div key={i} style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.4, paddingLeft: 12, borderLeft: "2px solid var(--hairline-strong)" }}>
                    {t.title} <span style={{ color: "var(--faint)" }}>· {roleName(t.role)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </ViewBody>
    </>
  )
}

// ── Экран повторяющегося процесса: что делает + история запусков + управление. ──
function ProcessDetailScreen({ proc, onBack, onPause, onResume, onDelete }: {
  proc: any; onBack: () => void; onPause: () => void; onResume: () => void; onDelete: () => void
}) {
  const isActive = proc.status === "active"
  return (
    <>
      <DetailHeader badge={WORK_TYPE_BADGE.process} title={proc.title} onBack={onBack}
        sub={`${roleName(proc.role)} · каждый цикл`}
        statusPill={isActive ? <Pill color="var(--success)">Идёт постоянно</Pill> : <Pill>На паузе</Pill>}
        actions={
          <>
            {isActive ? (
              <button onClick={onPause} style={{ padding: "9px 16px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
                border: "1px solid var(--hairline-strong)", background: "var(--surface-soft)", color: "var(--text-dim)" }}>⏸ Пауза</button>
            ) : (
              <button onClick={onResume} style={{ padding: "9px 16px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
                border: "1px solid rgba(160,224,171,0.4)", background: "rgba(160,224,171,0.1)", color: "var(--success)" }}>▶ Возобновить</button>
            )}
            <button onClick={onDelete} style={{ padding: "9px 16px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
              border: "1px solid var(--hairline)", background: "transparent", color: "var(--faint)" }}>Удалить</button>
          </>
        } />
      <ViewBody>
        <div style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 720 }}>
          <div>
            <SectionLabel style={{ marginBottom: 8 }}>Что делает каждый цикл</SectionLabel>
            <div style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.6 }}>{proc.instruction}</div>
          </div>
          <div style={{ fontSize: 12, color: "var(--faint)" }}>
            {proc.run_count ? `Запусков: ${proc.run_count} · ` : ""}
            {proc.last_run_ts
              ? `Последний запуск: ${new Date(proc.last_run_ts * 1000).toLocaleString("ru", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}`
              : "Ещё не запускался — задача появится в ближайшем цикле офиса"}
          </div>
        </div>
      </ViewBody>
    </>
  )
}

// ── Экран процесса продаж: Instance по стадиям (полный kanban — во вкладке «Лиды»). ──
function SalesProcessDetailScreen({ summary, onBack }: {
  summary: { statuses: string[]; labels: Record<string, string>; leads: any[] }; onBack: () => void
}) {
  const counts = summary.statuses.map(s => ({
    id: s, label: summary.labels[s] || s,
    count: summary.leads.filter((l: any) => (l.status || "new") === s).length,
  }))
  return (
    <>
      <DetailHeader badge={WORK_TYPE_BADGE.process} title="Продажи" onBack={onBack}
        statusPill={<Pill color="var(--success)">Идёт постоянно</Pill>}
        sub={`${summary.leads.length} лид(ов) в потоке — у процесса нет «% выполнено», только стадия каждого элемента`} />
      <ViewBody>
        <SectionLabel style={{ marginBottom: 8 }}>Instance по стадиям</SectionLabel>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          {counts.map(c => (
            <div key={c.id} style={{ padding: "6px 12px", borderRadius: "var(--radius-md)", border: "1px solid var(--hairline)", background: "var(--surface-soft)" }}>
              <div style={{ fontSize: 9.5, color: "var(--muted)", textTransform: "uppercase" }}>{c.label}</div>
              <div className="mono" style={{ fontSize: 15, color: "var(--text)" }}>{c.count}</div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11.5, color: "var(--faint)" }}>Полная доска с карточками, историей и follow-up — во вкладке «Лиды».</div>
      </ViewBody>
    </>
  )
}

// ── Экран проекта: прогресс → команда → этапы → сценарий → задачи → артефакты.
// Это и есть Work → Stage → Task → Subtask из BOS §5, теперь на отдельном
// экране вместо инлайн-раскрытия. ────────────────────────────────────────────
const DEPT_NAMES: Record<string, string> = { tech: "Технический", marketing: "Маркетинг", sales: "Продажи" }

function ProjectDetailScreen({ project: p, detail, onBack, onPause, onResume }: {
  project: any; detail: any; onBack: () => void; onPause: () => void; onResume: () => void
}) {
  const isActive = p.status === "active"
  const isQueued = p.status === "queued"
  const isPaused = p.status === "paused"
  const isOngoing = isActive || isQueued || isPaused  // разовые Project ставятся на паузу, закрытые (done) — уже история
  const typeBadge = WORK_TYPE_BADGE[p.type || "project"]
  return (
    <>
      {/* sub дублирует title, когда goal при создании не задали отдельно —
          реальный кейс со скриншота: "Привлекать больше клиентов..." дважды,
          слово в слово. Не показываем подзаголовок, если он идентичен заголовку. */}
      <DetailHeader badge={typeBadge} title={p.title} onBack={onBack}
        sub={p.goal && p.goal !== p.title ? p.goal : undefined}
        statusPill={isActive ? <Pill accent>Активный</Pill>
          : isQueued ? <Pill color="var(--warning)">⏳ В очереди</Pill>
          : isPaused ? <Pill>⏸ На паузе</Pill>
          : <Pill color="var(--success)">Закрыт</Pill>}
        actions={isOngoing && p.type === "project" ? (
          isPaused ? (
            <button onClick={onResume} style={{ padding: "9px 16px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
              border: "1px solid rgba(160,224,171,0.4)", background: "rgba(160,224,171,0.1)", color: "var(--success)" }}>▶ Возобновить</button>
          ) : (
            <button onClick={onPause} style={{ padding: "9px 16px", borderRadius: "var(--radius-pill)", fontSize: 12.5, cursor: "pointer",
              border: "1px solid var(--hairline-strong)", background: "var(--surface-soft)", color: "var(--text-dim)" }}>⏸ Пауза</button>
          )
        ) : undefined} />
      <ViewBody>
        {isPaused && (
          <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 16, padding: "10px 14px",
            background: "var(--surface-soft)", borderRadius: "var(--radius-md)", border: "1px solid var(--hairline)" }}>
            ⏸ Проект на паузе — команда не берёт по нему новых задач. Уже начатое доделывается, слот освобождён для очереди.
          </div>
        )}
        {!detail ? (
          <div style={{ fontSize: 12, color: "var(--faint)" }}>Загрузка…</div>
        ) : (
          <ProjectDetailBody project={p} detail={detail} />
        )}
      </ViewBody>
    </>
  )
}

function ProjectDetailBody({ project: p, detail }: { project: any; detail: any }) {
  const isActive = p.status === "active" || p.status === "paused"
  const tasks: any[] = detail.tasks || []
  const stages = (detail.milestones?.stages || []).filter((s: any) => s.item_count > 0 || s.status !== "pending")
  const sites: any[] = detail.sites || []
  const deliverables: any[] = detail.deliverables || []
  const progress = detail.progress || {}
  const lb = p.left_behind || {}

  // Команда проекта: реальная кросс-функциональность (BOS §5 — «несколько
  // воркеров и взаимодействие разных отделов, как в реальной компании»), а не
  // догадка — считается из ролей/отделов задач, которые ЭТОТ Work реально
  // породил, включая уже закрытые (история, кто участвовал).
  const roleCounts = new Map<string, number>()
  const depts = new Set<string>()
  tasks.forEach((t: any) => {
    if (t.role) roleCounts.set(t.role, (roleCounts.get(t.role) || 0) + 1)
    if (t.department) depts.add(t.department)
  })

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {isActive && (
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>Прогресс · {progress.done ?? 0}/{progress.total ?? 0} задач</SectionLabel>
          <MercuryBar percent={progress.percent ?? 0} />
        </div>
      )}

      {roleCounts.size > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>
            Команда проекта · {roleCounts.size} {roleCounts.size === 1 ? "роль" : "ролей"}
            {depts.size > 1 ? ` · ${depts.size} отдела` : ""}
          </SectionLabel>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <ShowMore items={[...roleCounts.entries()]} initial={5}
              render={([role, count]) => (
                <Pill key={role}>{roleName(role)}{count > 1 ? ` × ${count}` : ""}</Pill>
              )}
              moreLabel={n => `+${n}`} />
          </div>
          {depts.size > 1 && (
            <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 8 }}>
              Совместная работа отделов: {[...depts].map(d => DEPT_NAMES[d] || d).join(" + ")}
            </div>
          )}
        </div>
      )}

      {p.status === "done" && (
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>Что оставил после себя</SectionLabel>
          <div style={{ fontSize: 12.5, color: "var(--text-dim)", display: "flex", gap: 16, flexWrap: "wrap" }}>
            <span>✓ задач: {lb.tasks_done ?? 0}/{lb.tasks_total ?? 0}</span>
            <span>🌐 сайтов: {(lb.sites || []).length}</span>
            <span>👤 лидов: {lb.leads_count ?? 0}</span>
          </div>
        </div>
      )}

      {stages.length > 0 && (() => {
        const current = stages.find((s: any) => s.status === "active") || stages.find((s: any) => s.status !== "done")
        const doneCount = stages.filter((s: any) => s.status === "done").length
        return (
          <Disclosure count={stages.length}
            summary={
              <SectionLabel style={{ marginBottom: 0 }}>
                Этапы · {doneCount}/{stages.length} завершено{current ? ` · сейчас: ${current.title}` : ""}
              </SectionLabel>
            }>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {stages.map((s: any) => (
                <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                  <span style={{ color: s.status === "done" ? "var(--success)" : s.status === "active" ? "var(--mercury-a)" : "var(--faint)" }}>
                    {s.status === "done" ? "✓" : s.status === "active" ? "▶" : "○"}
                  </span>
                  <span style={{ color: "var(--text-dim)" }}>{s.title}</span>
                </div>
              ))}
            </div>
          </Disclosure>
        )
      })()}

      {tasks.some((t: any) => (t.deps || []).length > 0) && (
        <Disclosure summary={<SectionLabel style={{ marginBottom: 0 }}>Сценарий выполнения (граф зависимостей)</SectionLabel>}>
          <div style={{ fontSize: 11, color: "var(--faint)", marginBottom: 10 }}>
            План составлен ДО начала работы — офис действует по нему, а не придумывает следующий шаг на ходу.
          </div>
          <TaskGraph tasks={tasks} />
        </Disclosure>
      )}

      <div>
        <SectionLabel style={{ marginBottom: 8 }}>Задачи · {tasks.length}</SectionLabel>
        <ProjectTaskTree tasks={tasks} />
      </div>

      {(sites.length > 0 || deliverables.length > 0) && (
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>Артефакты · {sites.length + deliverables.length}</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {sites.map((s: any) => (
              <a key={s.slug} href={s.url || `/site/${s.slug}`} target="_blank" rel="noreferrer"
                style={{ fontSize: 12.5, color: "var(--mercury-a)", textDecoration: "none", display: "flex", alignItems: "center", gap: 6 }}>
                🌐 {s.title || s.slug} <span style={{ color: "var(--faint)", fontSize: 11 }}>↗</span>
              </a>
            ))}
            {deliverables.map((d: any, i: number) => (
              <ArtifactRow key={i} d={d} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const ARTIFACT_PREVIEW_LEN = 220

// Короткая строка «что сделано» + опциональная кнопка «Показать полностью»
// вместо полного содержимого артефакта инлайн (реальный баг: сюда попадал
// весь контекст задачи целиком — брифом, ТЗ, памятью — на весь экран).
function ArtifactRow({ d }: { d: any }) {
  const [open, setOpen] = useState(false)
  const content = (d.content || "").trim()
  const isLong = content.length > ARTIFACT_PREVIEW_LEN
  return (
    <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.4 }}>
      {/* line-clamp вместо slice(0,100) — раньше резало строку по символам
          (реальный баг на скриншоте: "ЗАДАЧА ВЫПОЛНЕНА, КОГД" обрывалось
          прямо посреди слова). CSS-перенос уважает границы слов сам. */}
      <div style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
        📝 {d.task} <span style={{ color: "var(--faint)" }}>· {roleName(d.role)}</span>
      </div>
      {content && (
        <>
          {open && (
            <div style={{ marginTop: 6, padding: "8px 10px", background: "var(--surface-soft)",
              borderLeft: "2px solid var(--hairline-strong)", borderRadius: 4, fontSize: 12,
              whiteSpace: "pre-wrap", wordBreak: "break-word", color: "var(--text-dim)" }}>
              {content}
            </div>
          )}
          {isLong && (
            <button onClick={() => setOpen(v => !v)}
              style={{ marginTop: 4, fontSize: 11, color: "var(--mercury-a)", background: "transparent",
                border: "none", cursor: "pointer", padding: 0, textDecoration: "underline" }}>
              {open ? "Свернуть ↑" : "Показать полный результат →"}
            </button>
          )}
        </>
      )}
    </div>
  )
}

// ── Сценарий-граф: план-граф зависимостей задач, составленный ДО начала
// работы (orchestrator.plan_tasks/generate_initiative) — пользователь видит,
// что будет происходить, а не только что уже случилось; офис исполняет по
// нему же (plan.py уважает deps), не придумывает порядок на лету. Колонки —
// топологические уровни (шаг зависит только от предыдущих шагов). ──────────
function TaskGraph({ tasks }: { tasks: any[] }) {
  const byId = new Map(tasks.map((t: any) => [t.id, t]))
  const levelCache = new Map<string, number>()
  function levelOf(t: any): number {
    if (levelCache.has(t.id)) return levelCache.get(t.id)!
    levelCache.set(t.id, 0) // защита от циклов в данных — не должно быть, но не вешаем UI
    const deps = (t.deps || []).filter((d: string) => byId.has(d) && d !== t.id)
    const lvl = deps.length === 0 ? 0 : 1 + Math.max(...deps.map((d: string) => levelOf(byId.get(d))))
    levelCache.set(t.id, lvl)
    return lvl
  }
  const columns: Record<number, any[]> = {}
  tasks.forEach((t: any) => { const l = levelOf(t); (columns[l] = columns[l] || []).push(t) })
  const maxLevel = Math.max(0, ...Object.keys(columns).map(Number))
  const dotColor = (t: any) => t.status === "done" ? "var(--success)" : t.status === "in_progress" ? "var(--mercury-a)"
    : t.status === "blocked" ? "var(--danger-soft)" : "var(--whisper)"

  return (
    <div style={{ display: "flex", gap: 18, overflowX: "auto", paddingBottom: 6, marginBottom: 14 }}>
      {Array.from({ length: maxLevel + 1 }, (_, lvl) => (
        <div key={lvl} style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 170, flexShrink: 0 }}>
          <div className="mono" style={{ fontSize: 9, color: "var(--faint)", textAlign: "center", textTransform: "uppercase" }}>Шаг {lvl + 1}</div>
          {(columns[lvl] || []).map((t: any) => (
            <div key={t.id} style={{
              padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--hairline)",
              background: "var(--surface)", display: "flex", flexDirection: "column", gap: 4,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: dotColor(t), flexShrink: 0 }} />
                <span style={{ fontSize: 11.5, color: t.status === "done" ? "var(--muted)" : "var(--text-dim)",
                  textDecoration: t.status === "done" ? "line-through" : "none", lineHeight: 1.3 }}>{t.title}</span>
              </div>
              <span style={{ fontSize: 9.5, color: "var(--faint)", paddingLeft: 12 }}>{roleName(t.role)}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// ── Задачи проекта: kanban по статусу + вложенность parent_id (Task→Subtask,
//    BOS §5 — вложенность вместо отдельной сущности Subtask) ─────────────────
const COLS = [
  { key: "pending",     label: "В очереди",  dot: "var(--whisper)" },
  { key: "in_progress", label: "В работе",   dot: "var(--mercury-a)" },
  { key: "done",        label: "Готово",      dot: "var(--success)" },
  { key: "blocked",     label: "Заблокированы", dot: "var(--danger-soft)" },
  // skipped — задача снята офисом (роль без отдела-исполнителя), НЕ выполнена.
  { key: "skipped",     label: "Пропущены",  dot: "var(--muted)" },
]

function ProjectTaskTree({ tasks }: { tasks: any[] }) {
  const [unblocking, setUnblocking] = useState<string>("")
  const hasBlocked = tasks.some((t: any) => t.status === "blocked")
  const hasSkipped = tasks.some((t: any) => t.status === "skipped")
  const cols = COLS.filter(c =>
    (c.key !== "blocked" || hasBlocked) && (c.key !== "skipped" || hasSkipped))

  const byId = new Map(tasks.map((t: any) => [t.id, t]))
  const childrenOf = (id: string) => tasks.filter((t: any) => t.parent && t.parent === id)
  // Корень дерева: без parent, ИЛИ parent указывает на задачу другого проекта/
  // несуществующую — тогда она тоже верхнего уровня, а не теряется молча.
  const isRoot = (t: any) => !t.parent || !byId.has(t.parent)

  const unblock = async (id: string) => {
    setUnblocking(id)
    await api.unblockTask(id)
    await refreshData(["plan"])
    setUnblocking("")
  }

  if (tasks.length === 0) return (
    <div style={{ fontSize: 12.5, color: "var(--faint)" }}>У этого проекта пока нет своих задач.</div>
  )

  function renderTask(t: any, depth: number) {
    const children = childrenOf(t.id)
    return (
      <div key={t.id} style={{ marginLeft: depth * 16 }}>
        <div style={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-sm)",
          padding: "10px 12px", marginBottom: children.length > 0 ? 6 : 0 }}>
          <div style={{ fontSize: 12.5, color: t.status === "done" ? "var(--muted)" : "var(--text)", lineHeight: 1.35,
            textDecoration: t.status === "done" ? "line-through" : "none", marginBottom: 8 }}>
            {t.title}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <Pill accent={t.status === "in_progress"}>{roleName(t.role)}</Pill>
            {(t.attempts || 0) > 0 && t.status !== "done" && (
              <Pill color="var(--warning)">попытка {t.attempts}</Pill>
            )}
            {t.done_criterion && t.status !== "done" && t.status !== "blocked" && (
              <span style={{ fontSize: 10, color: "var(--success-dim)", lineHeight: 1.3 }}>✓ {t.done_criterion}</span>
            )}
          </div>
          {t.status === "blocked" && (
            <div style={{ marginTop: 8 }}>
              {t.blocked_reason && (
                <div style={{ fontSize: 10.5, color: "var(--danger-soft)", lineHeight: 1.4, marginBottom: 8 }}>
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
        {children.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, borderLeft: "2px solid var(--hairline-strong)", paddingLeft: 10 }}>
            {children.map((c: any) => renderTask(c, 0))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
      gap: 14, alignItems: "start" }}>
      {cols.map(col => {
        const items = tasks.filter((t: any) => t.status === col.key && isRoot(t))
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
              {items.map((t: any) => renderTask(t, 0))}
              {items.length === 0 && <div style={{ fontSize: 11, color: "var(--faint)", textAlign: "center", padding: "16px 0" }}>—</div>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Спецификация (контракт приёмки) — компания-широкий, не привязан к одному
//    Work: собирается из брифа + ВСЕГО план-графа (см. src/office/specification.py) ──
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
          {confirmed ? <Pill color="var(--success)">✓ Подтверждена</Pill> : (
            <button onClick={confirm} disabled={confirming}
              style={{ fontSize: 12, padding: "8px 14px", borderRadius: 8, cursor: "pointer",
                background: "var(--mercury-a)", border: "none", color: "var(--on-accent)", fontWeight: 600 }}>
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
                <span style={{ color: "var(--success-dim)", marginRight: 6 }}>✓</span>{c}
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
