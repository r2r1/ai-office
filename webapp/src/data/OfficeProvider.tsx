import { createContext, useContext, useEffect, useMemo, useRef, useSyncExternalStore, type ReactNode } from "react"
import { api } from "./api"
import { roleName, roleIcon, workerDisplayName, roleFromAgentId } from "./roles"
import type { Worker, WorkerStatus } from "../app/types"

// BOS §12 п.4: backend отдаёт worker_id рядом с deprecated agent_id (см. office/bus.py,
// server.py `_with_worker_id`). Читаем предпочтительно worker_id, agent_id — фолбэк
// на переходный период (в т.ч. для уже сохранённой на диске истории старых прогонов).
function wid(o: any): string { return o?.worker_id ?? o?.agent_id ?? "" }

export interface FeedItem { id: number; icon: string; who: string; text: string; kind: "" | "system" | "done" | "error" | "mistake" }
export interface ProgressState { percent: number; note: string; stages: any[]; current: string }
export interface PlanState { generated: boolean; tasks: any[]; progress: { done: number; total: number } }
// Сводка личного чата с агентом (из /api/threads) — для бейджей непрочитанного.
export interface ThreadSummary { last_text: string; last_ts: number; last_from: string; unanswered: number }

export interface OfficeState {
  connected: boolean
  ready: boolean | null
  workspace: { id: string; name: string; plan: string } | null
  agents: Record<string, Worker>
  feed: FeedItem[]
  progress: ProgressState
  cost: number
  costAgents: any[]
  leads: any[]
  sites: any[]
  plan: PlanState
  model: string
  threads: Record<string, ThreadSummary>
  threadsSeen: Record<string, number>
}

// seen-состояние личных чатов переживает перезагрузку страницы (бэкенд его не хранит).
const SEEN_KEY = "ai-office:threads-seen"
function loadSeen(): Record<string, number> {
  try { return JSON.parse(localStorage.getItem(SEEN_KEY) || "{}") } catch { return {} }
}

const initialState: OfficeState = {
  connected: false, ready: null, workspace: null, agents: {}, feed: [],
  progress: { percent: 0, note: "", stages: [], current: "" },
  cost: 0, costAgents: [], leads: [], sites: [],
  plan: { generated: false, tasks: [], progress: { done: 0, total: 0 } },
  model: "",
  threads: {}, threadsSeen: loadSeen(),
}

let _feedId = 0
function feed(state: OfficeState, icon: string, who: string, text: string, kind: FeedItem["kind"]): FeedItem[] {
  const item: FeedItem = { id: ++_feedId, icon, who, text: (text || "").slice(0, 600), kind }
  return [item, ...state.feed].slice(0, 400)
}

function upsertAgent(state: OfficeState, id: string, patch: Partial<Worker>): Record<string, Worker> {
  const prev = state.agents[id]
  // developer_2 → developer; developer_p1_1143 (project-scoped, Фаза 2) → developer —
  // чтобы события (thinking/speech) по ещё не «нанятому» агенту не плодили
  // фантомную роль "unknown" (или, раньше, ложную "developer_p1" — см.
  // roleFromAgentId docstring в data/roles.ts).
  const role = patch.role || prev?.role || roleFromAgentId(id) || "unknown"
  const next: Worker = {
    id, role,
    name: workerDisplayName(id, role),
    emoji: roleIcon(role),
    status: (patch.status || prev?.status || "idle") as WorkerStatus,
    lastMessage: patch.lastMessage ?? prev?.lastMessage ?? "",
    // Раньше upsertAgent НЕ переносил projectId из prev — первое же живое
    // событие (hired/speech/thinking/task_done) по агенту, уже закреплённому
    // за проектом (Фаза 2/4), тихо стирало эту привязку в UI-состоянии до
    // следующего полного /api/agents (реальный баг, пойман при живой проверке
    // бейджа проекта на карточке команды — TeamView).
    projectId: patch.projectId ?? prev?.projectId ?? "",
  }
  return { ...state.agents, [id]: next }
}

type Action =
  | { t: "connected"; v: boolean }
  | { t: "seed"; partial: Partial<OfficeState> }
  | { t: "agents"; list: any[] }
  | { t: "event"; e: any }
  | { t: "threads"; summaries: Record<string, ThreadSummary> }
  | { t: "threadSeen"; agentId: string; ts: number }

function reducer(state: OfficeState, action: Action): OfficeState {
  switch (action.t) {
    case "connected": return { ...state, connected: action.v }
    case "seed": return { ...state, ...action.partial }
    case "threads": return { ...state, threads: action.summaries }
    case "threadSeen": {
      const cur = state.threadsSeen[action.agentId] || 0
      if (action.ts <= cur) return state
      const threadsSeen = { ...state.threadsSeen, [action.agentId]: action.ts }
      try { localStorage.setItem(SEEN_KEY, JSON.stringify(threadsSeen)) } catch { /* private mode */ }
      return { ...state, threadsSeen }
    }
    case "agents": {
      const agents: Record<string, Worker> = {}
      for (const a of action.list) {
        const id = wid(a)
        agents[id] = {
          id, role: a.role, name: workerDisplayName(id, a.role),
          emoji: roleIcon(a.role), status: (a.status || "idle") as WorkerStatus, lastMessage: a.last_message || "",
          projectId: a.project_id || "",
        }
      }
      return { ...state, agents }
    }
    case "event": {
      const e = action.e
      const hist = !!e.historical
      const eid = wid(e)
      switch (e.type) {
        case "hired": {
          const agents = upsertAgent(state, eid, { role: e.role, status: e.status || "idle", lastMessage: e.last_message || "" })
          return { ...state, agents, feed: hist ? state.feed : feed(state, "👋", "", `${roleName(e.role)} нанят`, "system") }
        }
        case "speech": case "thinking": {
          const agents = upsertAgent(state, eid, { status: "thinking", lastMessage: e.text })
          const a = agents[eid]
          return { ...state, agents, feed: hist ? state.feed : feed(state, roleIcon(a.role), a.name, e.text, "") }
        }
        case "task_done": {
          const agents = upsertAgent(state, eid, { status: "done", lastMessage: (e.summary || "").slice(0, 80) })
          return { ...state, agents, feed: hist ? state.feed : feed(state, "✅", agents[eid].name, e.summary || "задача выполнена", "done") }
        }
        case "error": {
          const a = state.agents[eid]
          return { ...state, feed: hist ? state.feed : feed(state, "⚠️", a?.name || "", e.text, "error") }
        }
        case "progress":
          return { ...state, progress: { percent: e.percent ?? state.progress.percent, note: e.note ?? state.progress.note, stages: e.stages ?? state.progress.stages, current: e.current ?? state.progress.current } }
        case "system":
          return { ...state, feed: hist ? state.feed : feed(state, "🏢", "", e.text, "system") }
        case "agent_message": {
          // Вопрос/сообщение агента в личный чат. Без этого кейса вопросы агентов
          // не показывались (feed.length не менялся → чат не перезагружался).
          if (hist || e.from === "user") return state
          const a = state.agents[eid]
          const who = a?.name || ""
          const isQ = e.kind === "question"
          return { ...state, feed: feed(state, isQ ? "❓" : "💬", who,
            (isQ ? "Вопрос: " : "") + (e.text || ""), "system") }
        }
        case "department_event":
          return { ...state, feed: hist ? state.feed : feed(state, "📨", "", e.text || "Сигнал отдела", "system") }
        case "lead_captured":
          return { ...state, feed: hist ? state.feed : feed(state, "🎯", "", e.text || "Новая заявка", "done") }
        case "file_written":
          return { ...state, feed: hist ? state.feed : feed(state, "💻", "", `Файл записан: ${e.path || ""}`, "system") }
        case "integration_used":
          return { ...state, feed: hist ? state.feed : feed(state, "🔌", "", e.text || "Внешний сервис", "system") }
        case "connection_added":
          return { ...state, feed: hist ? state.feed : feed(state, "🔌", "", `Доступ «${e.connection?.name || ""}» сохранён`, "system") }
        case "mistake_acknowledged":
          // Голос офиса (портрет §5b/§13): явное признание ошибки — отдельный
          // kind, не смешивать с обычным "error", чтобы UI мог со временем
          // отличить визуально «офис сам сказал» от «упало само».
          return { ...state, feed: hist ? state.feed : feed(state, "⚠️", "", e.text || "", "mistake") }
        default:
          return state
      }
    }
  }
}

// Непрочитанные личные чаты: какие агенты ждут внимания и сколько всего.
export interface UnreadInfo { byAgent: Record<string, number>; total: number }

interface OfficeCtx {
  state: OfficeState
  refresh: (what?: RefreshKey[]) => void
  unread: UnreadInfo
  markThreadSeen: (agentId: string, ts?: number) => void
}
type RefreshKey = "agents" | "progress" | "costs" | "leads" | "sites" | "plan"

// ── Внешний стор (не React state) ────────────────────────────────────────────
// Раньше состояние жило в useReducer внутри OfficeProvider, а Context отдавал
// НОВЫЙ объект {state, ...} на каждый dispatch — это заставляло перерисовываться
// ВСЁ дерево компонентов на каждое SSE-событие (аудит фронтенда: подтормаживал
// ввод в чат и анимации агентов при активном офисе). Теперь состояние — модульный
// синглтон + подписчики; компоненты через useSyncExternalStore подписываются на
// СВОЙ срез (useOfficeSelector) и перерисовываются только когда РЕЗУЛЬТАТ селектора
// реально изменился — reducer уже сохраняет ссылочную стабильность полей, которые
// не затронуты конкретным событием ({...state, agents: ...} не трогает state.feed).
let officeState: OfficeState = initialState
const listeners = new Set<() => void>()

function getSnapshot(): OfficeState {
  return officeState
}

function dispatch(action: Action): void {
  officeState = reducer(officeState, action)
  listeners.forEach(l => l())
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

/** Подписка на ПРОИЗВОЛЬНЫЙ срез состояния — компонент перерисовывается только
 * когда возвращаемое селектором значение реально изменилось (Object.is). */
export function useOfficeSelector<T>(selector: (s: OfficeState) => T): T {
  useAssertMounted()
  return useSyncExternalStore(subscribe, () => selector(officeState))
}

async function loadThreads() {
  const t = await api.threads()
  dispatch({ t: "threads", summaries: t.threads || {} })
}

// Экспорт для view-слоя: точечно подтянуть данные после действия пользователя
// (например, разблокировка задачи), не дожидаясь SSE-события.
export async function refreshData(what: RefreshKey[]) { return refresh(what) }

// state.ready читается один раз из /api/brief/status при монтировании
// OfficeProvider (до онбординга — честно false). OnboardingFlow.onDone()
// переключает App.tsx на вид "office" локальным флагом, но раньше НИЧЕГО не
// сообщало общему стору — "Работа"/"Аккаунт" показывали "ожидает брифа"
// вечно после онбординга, до жёсткой перезагрузки страницы (найдено при
// живом дизайн-аудите). Вызывается сразу после завершения онбординга.
export function markReady(): void {
  dispatch({ t: "seed", partial: { ready: true } })
}

async function refresh(what: RefreshKey[] = ["progress", "costs", "leads", "sites", "plan"]) {
  const partial: Partial<OfficeState> = {}
  await Promise.all(what.map(async k => {
    if (k === "agents") { dispatch({ t: "agents", list: await api.agents() }); return }
    if (k === "progress") partial.progress = await api.progress()
    if (k === "costs") { const c = await api.costs(); partial.cost = c?.total?.cost || 0; partial.costAgents = c?.agents || [] }
    if (k === "leads") partial.leads = (await api.leads()).leads || []
    if (k === "sites") partial.sites = (await api.sites()).sites || []
    if (k === "plan") partial.plan = await api.plan()
  }))
  if (Object.keys(partial).length) dispatch({ t: "seed", partial })
}

export function markThreadSeen(agentId: string, ts?: number): void {
  dispatch({ t: "threadSeen", agentId, ts: ts ?? Date.now() / 1000 })
}

const MountedCtx = createContext(false)

export function OfficeProvider({ children }: { children: ReactNode }) {
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    let cancelled = false
    const cleanups: Array<() => void> = []
    ;(async () => {
      const [me, bs] = await Promise.all([api.me(), api.briefStatus()])
      if (cancelled) return
      dispatch({ t: "seed", partial: { workspace: me?.workspace || null, ready: !!bs?.ready } })
      // начальный снапшот данных
      dispatch({ t: "agents", list: await api.agents() })
      const hist = await api.history()
      for (const ev of hist.events || []) dispatch({ t: "event", e: { ...ev, historical: true } })
      await refresh(["progress", "costs", "leads", "sites", "plan"])
      await loadThreads()
      // текущая модель офиса — для плашки в топбаре
      const minfo = await api.models()
      if (!cancelled && minfo?.default) dispatch({ t: "seed", partial: { model: minfo.default } })

      // живой поток. EventSource переподключается сам (браузерная реализация
      // SSE-протокола) — но раньше это было ЕДИНСТВЕННОЕ, что происходило при
      // разрыве: события, случившиеся в окне обрыва (агент что-то сделал, пока
      // связи не было), терялись безвозвратно — agents/plan/costs/leads/sites
      // оставались устаревшими до ручной перезагрузки страницы (аудит §4.4).
      // Теперь при КАЖДОМ повторном onopen (не первом) — полный ресинк среза
      // состояния, не только "зелёная точка".
      let hasConnectedBefore = false
      const es = new EventSource("/events")
      esRef.current = es
      es.onopen = () => {
        dispatch({ t: "connected", v: true })
        if (hasConnectedBefore) {
          void (async () => {
            dispatch({ t: "agents", list: await api.agents() })
            await refresh(["progress", "costs", "leads", "sites", "plan"])
            await loadThreads()
          })()
        }
        hasConnectedBefore = true
      }
      es.onerror = () => dispatch({ t: "connected", v: false })
      es.onmessage = (m) => {
        let e: any
        try { e = JSON.parse(m.data) } catch { return }
        dispatch({ t: "event", e })
        if (e.historical) return
        // side-effects: подтягиваем данные по релевантным событиям (как в game.js)
        if (e.type === "task_done") refresh(["costs"])
        else if (e.type === "lead_captured") refresh(["leads"])
        else if (e.type === "integration_used" && e.integration === "website") refresh(["leads", "sites"])
        else if (e.type === "system" && /Задач|Доск|план|📋|📌|опубликован|🌐/i.test(e.text || "")) refresh(["plan", "sites"])
        // новое сообщение/вопрос в личном чате → обновляем сводку непрочитанного
        if (e.type === "agent_message") loadThreads()
      }

      // фоллбэк-поллинг сводки чатов (на случай пропущенных SSE-событий)
      const pollThreads = setInterval(loadThreads, 20000)
      cleanups.push(() => clearInterval(pollThreads))
    })()
    return () => { cancelled = true; esRef.current?.close(); cleanups.forEach(fn => fn()) }
  }, [])

  return <MountedCtx.Provider value={true}>{children}</MountedCtx.Provider>
}

function useAssertMounted(): void {
  const mounted = useContext(MountedCtx)
  if (!mounted) throw new Error("useOffice must be used within OfficeProvider")
}

/** Только сводка непрочитанных личных чатов — перерисовывается лишь когда
 * state.threads/threadsSeen реально меняются (не на каждое SSE-событие в целом).
 * Чат «непрочитан», если последнее сообщение НЕ от пользователя и пришло позже,
 * чем пользователь в последний раз открывал этот чат. */
export function useUnread(): UnreadInfo {
  const threads = useOfficeSelector(s => s.threads)
  const threadsSeen = useOfficeSelector(s => s.threadsSeen)
  return useMemo<UnreadInfo>(() => {
    const byAgent: Record<string, number> = {}
    let total = 0
    for (const [aid, s] of Object.entries(threads)) {
      const fresh = s.last_from !== "user" && s.last_ts > (threadsSeen[aid] || 0)
      if (fresh) { byAgent[aid] = s.unanswered > 0 ? s.unanswered : 1; total += 1 }
    }
    return { byAgent, total }
  }, [threads, threadsSeen])
}

/** Полное состояние + действия — для нечастых потребителей (обратная
 * совместимость: перерисовывается на любое изменение, как раньше). Горячие
 * компоненты должны переходить на useOfficeSelector/useUnread под свой срез. */
export function useOffice(): OfficeCtx {
  useAssertMounted()
  const state = useSyncExternalStore(subscribe, getSnapshot)
  const unread = useUnread()
  return { state, refresh, unread, markThreadSeen }
}
