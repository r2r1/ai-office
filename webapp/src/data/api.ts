// Тонкая обёртка над fetch: тот же origin (FastAPI отдаёт /webapp), cookie-сессия идёт сама.
async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url, { credentials: "same-origin" })
    if (!r.ok) return fallback
    return (await r.json()) as T
  } catch {
    return fallback
  }
}

async function postJSON<T>(url: string, body: unknown, fallback: T): Promise<T> {
  try {
    const r = await fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!r.ok) return fallback
    return (await r.json()) as T
  } catch {
    return fallback
  }
}

// Как postJSON, но читает JSON-тело даже при !ok (403 и т.п.) — эндпоинты вроде
// /api/run и /api/terminal возвращают понятную причину отказа (например, «код
// выполнения отключён оператором») в теле 403, а не только в статусе; обычный
// postJSON эту причину теряет, подменяя её generic-фолбэком.
async function postJSONReadBody<T>(url: string, body: unknown, fallback: T): Promise<T> {
  try {
    const r = await fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    try {
      return (await r.json()) as T
    } catch {
      return fallback
    }
  } catch {
    return fallback
  }
}

// Для эндпоинтов, отдающих сырой текст (не JSON), например содержимое файла.
async function getText(url: string): Promise<string> {
  try {
    const r = await fetch(url, { credentials: "same-origin" })
    if (!r.ok) return ""
    return await r.text()
  } catch {
    return ""
  }
}

export const api = {
  me: () => getJSON<any>("/api/me", {}),
  briefStatus: () => getJSON<{ ready: boolean; demo: boolean; brief: any }>("/api/brief/status", { ready: false, demo: false, brief: null }),
  agents: () => getJSON<any[]>("/api/agents", []),
  history: () => getJSON<{ events: any[]; results: Record<string, string> }>("/api/history", { events: [], results: {} }),
  progress: () => getJSON<any>("/api/progress", { percent: 0, note: "", stages: [], current: "" }),
  costs: () => getJSON<any>("/api/costs", { total: { cost: 0 }, agents: [] }),
  leads: () => getJSON<{ leads: any[]; statuses: string[]; labels: Record<string, string> }>(
    "/api/leads", { leads: [], statuses: [], labels: {} }),
  setLeadStatus: (id: string, status: string, note = "") =>
    postJSON<any>(`/api/leads/${id}/status`, { status, note }, null),
  addLeadNote: (id: string, text: string) =>
    postJSON<any>(`/api/leads/${id}/note`, { text }, null),
  sendLeadFollowup: (id: string, text: string) =>
    postJSONReadBody<any>(`/api/leads/${id}/followup`, { text }, { ok: false, error: "Ошибка запроса" }),
  // ── Личный Telegram (MTProto) — интерактивный вход, не обычный cred-флоу ──
  tgConfig: () => getJSON<{ has_default_creds: boolean }>(
    "/api/integrations/telegram_personal/config", { has_default_creds: false }),
  tgLoginStart: (phone: string, api_id = "", api_hash = "") =>
    postJSONReadBody<any>("/api/integrations/telegram_personal/login/start",
      { phone, api_id, api_hash }, { ok: false, error: "Ошибка запроса" }),
  tgLoginConfirm: (code: string, password = "") =>
    postJSONReadBody<any>("/api/integrations/telegram_personal/login/confirm",
      { code, password }, { ok: false, error: "Ошибка запроса" }),
  tgLoginCancel: () => postJSON<any>("/api/integrations/telegram_personal/login/cancel", {}, null),
  sites: () => getJSON<{ sites: any[] }>("/api/sites", { sites: [] }),
  plan: () => getJSON<any>("/api/plan", { generated: false, tasks: [], progress: { done: 0, total: 0 } }),
  deliverables: () => getJSON<{ deliverables: any[] }>("/api/deliverables", { deliverables: [] }),
  files: () => getJSON<{ files: any[] }>("/api/files", { files: [] }),
  connections: () => getJSON<{ connections: any[] }>("/api/connections", { connections: [] }),
  threads: () => getJSON<{ threads: Record<string, any> }>("/api/threads", { threads: {} }),
  thread: (id: string) => getJSON<{ agent_id: string; worker_id: string; messages: any[] }>(`/api/thread/${id}`, { agent_id: id, worker_id: id, messages: [] }),
  // ВАЖНО: бэкенд /api/ask читает поле `message`, а /api/chat — поле `text`.
  // worker_id — предпочтительное имя (BOS §12 п.4); бэкенд принимает и deprecated agent_id.
  ask: (workerId: string, text: string) => postJSON<any>("/api/ask", { worker_id: workerId, message: text }, null),
  chatGet: () => getJSON<{ messages: any[] }>("/api/chat", { messages: [] }),
  chatPost: (message: string) => postJSON<any>("/api/chat", { text: message }, null),
  agentDetail: (id: string) => getJSON<any>(`/api/agent/${id}`, {}),
  setAgentModel: (id: string, model: string) => postJSON<any>(`/api/agent/${id}/model`, { model }, null),
  milestones: () => getJSON<any>("/api/milestones", { stages: [] }),
  integrations: () => getJSON<any>("/api/integrations", { integrations: [] }),
  digitalInfrastructure: () => getJSON<any>("/api/digital-infrastructure", { sources: [] }),
  // /api/file отдаёт СЫРОЙ текст — читаем как текст, не как JSON.
  fileContent: async (path: string) => ({ content: await getText(`/api/file?path=${encodeURIComponent(path)}`) }),
  rawUrl: (path: string) => `/api/raw/${path.split("/").map(encodeURIComponent).join("/")}`,
  runFile: (path: string) => postJSONReadBody<any>("/api/run", { path }, { ok: false, output: "Ошибка запроса" }),
  terminal: (cmd: string, cwd = "") => postJSONReadBody<any>("/api/terminal", { cmd, cwd }, { ok: false, output: "Ошибка запроса" }),
  models: () => getJSON<any>("/api/models", { default: "", presets: [], per_agent: {}, per_role: {} }),
  setModel: (model: string) => postJSON<any>("/api/model", { model }, null),
  digest: () => getJSON<any>("/api/digest", { items: [], count: 0, since: "", is_first: true }),
  understanding: () => getJSON<any>("/api/understanding", { score: 0, items: [], missing: [] }),
  knowledge: () => getJSON<any>("/api/knowledge", { facts: [], count: 0, layers: { global: 0, user: 0, department: 0 } }),
  departmentEvents: () => getJSON<any>("/api/department-events", { events: [], pending: 0 }),
  // ── BOS-ядро: World Model, цели, проекты, спецификация, намерения ──
  world: () => getJSON<any>("/api/world", null),
  objectives: () => getJSON<{ objectives: any[] }>("/api/objectives", { objectives: [] }),
  addObjective: (title: string, desired = "", measured_by = "") =>
    postJSON<any>("/api/objectives", { title, desired, measured_by }, null),
  updateObjective: (id: string, patch: Record<string, unknown>) =>
    postJSON<any>("/api/objectives", { id, ...patch }, null),
  projects: () => getJSON<{ projects: any[]; active: any; active_count: number; max_active: number }>(
    "/api/projects", { projects: [], active: null, active_count: 0, max_active: 3 }),
  setProjectLimit: (max_active: number) => postJSON<any>("/api/projects/limit", { max_active }, null),
  pauseProject: (id: string) => postJSON<any>(`/api/project/${id}/pause`, {}, null),
  resumeProject: (id: string) => postJSON<any>(`/api/project/${id}/resume`, {}, null),
  reorderProjectsQueue: (order: string[]) => postJSON<any>("/api/projects/reorder", { order }, null),
  initiatives: () => getJSON<{ pending: any[]; researching: any[]; pending_count: number; total: number }>("/api/initiatives", { pending: [], researching: [], pending_count: 0, total: 0 }),
  proposeInitiative: (title: string, idea: string) => postJSON<any>("/api/initiatives", { title, idea }, null),
  acceptInitiative: (id: string) => postJSON<any>(`/api/initiative/${id}/accept`, {}, null),
  rejectInitiative: (id: string) => postJSON<any>(`/api/initiative/${id}/reject`, {}, null),
  gap: () => getJSON<{ gaps: any[] }>("/api/gap", { gaps: [] }),
  // ── Бизнес-дашборд: системные карточки + кастомные графики по запросу ──
  dashboard: () => getJSON<{ widgets: any[] }>("/api/dashboard", { widgets: [] }),
  dashboardRequest: (text: string) =>
    postJSON<{ ok: boolean; widget?: any; reason?: string; initiative_id?: string }>(
      "/api/dashboard/request", { text }, { ok: false, reason: "Ошибка запроса" }),
  dashboardSetLayout: (id: string, x: number, y: number, w: number, h: number) =>
    postJSON<any>("/api/dashboard/layout", { id, x, y, w, h }, null),
  dashboardRemove: (id: string) => postJSON<any>("/api/dashboard/remove", { id }, null),
  processes: () => getJSON<{ processes: any[] }>("/api/processes", { processes: [] }),
  createProcess: (title: string, role: string, instruction: string) =>
    postJSON<any>("/api/processes", { title, role, instruction }, null),
  pauseProcess: (id: string) => postJSON<any>(`/api/process/${id}/pause`, {}, null),
  resumeProcess: (id: string) => postJSON<any>(`/api/process/${id}/resume`, {}, null),
  deleteProcess: (id: string) => postJSON<any>(`/api/process/${id}/delete`, {}, null),
  projectDetail: (id: string) => getJSON<{ project: any; tasks: any[]; progress: any; milestones: any; sites: any[]; deliverables: any[] }>(`/api/project/${id}`, { project: null, tasks: [], progress: {}, milestones: {}, sites: [], deliverables: [] }),
  specification: () => getJSON<any>("/api/specification", { status: "none" }),
  confirmSpecification: (note = "") => postJSON<any>("/api/specification/confirm", { note }, null),
  intents: () => getJSON<{ intents: any[] }>("/api/intents", { intents: [] }),
  unblockTask: (id: string) => postJSON<any>(`/api/task/${id}/unblock`, {}, null),
  onboardingModes: () => getJSON<any>("/api/onboarding/modes", { modes: [] }),
  onboardingScan: (url: string) => postJSON<any>("/api/onboarding/scan", { url }, null),
  onboardingFinish: (mode: string, answers: any[], scan?: any) =>
    postJSON<any>("/api/onboarding/finish", { mode, answers, scan }, null),
  // Минимальный онбординг (BOS §5): 1 необязательное поле + необязательная ссылка.
  briefStart: (input: string, url = "") => postJSON<any>("/api/brief/start", { input, url }, null),
  onboardingResult: () => getJSON<any>("/api/onboarding/result",
    { ready: false, analysis: [], growth_points: [], initiatives: [] }),
  suggestedIntegrations: () => getJSON<{ integrations: any[] }>(
    "/api/onboarding/suggested-integrations", { integrations: [] }),
  officeStatus: () => getJSON<any>("/api/office/status", { paused: false, reason: "" }),
  officePause: () => postJSON<any>("/api/office/pause", {}, null),
  officeResume: () => postJSON<any>("/api/office/resume", {}, null),
  // ── Сценарии: живая диаграмма оргструктуры (docs/scenario-graph-tab-spec.md) ──
  orgGraph: () => getJSON<{ nodes: any[]; edges: any[] }>("/api/org-graph", { nodes: [], edges: [] }),
  pauseAgent: (id: string) => postJSON<any>(`/api/agent/${id}/pause`, {}, null),
  resumeAgent: (id: string) => postJSON<any>(`/api/agent/${id}/resume`, {}, null),
  reassignTask: (taskId: string, agentId: string) =>
    postJSONReadBody<any>(`/api/task/${taskId}/reassign`, { agent_id: agentId }, { ok: false, error: "Ошибка запроса" }),
  // ── авторизация ──
  devLogin: (email: string) => postJSON<any>("/auth/dev-login", { email }, null),
  githubDeviceStart: () => postJSON<any>("/auth/github/device/start", {}, null),
  githubDevicePoll: (device_code: string) => postJSON<any>("/auth/github/device/poll", { device_code }, null),
  logout: () => postJSON<any>("/auth/logout", {}, null),
  get: (url: string) => getJSON<any>(url, null),
  post: (url: string, body: unknown = {}) => postJSON<any>(url, body, null),
  // ── Приложения тенанта (office/tenant_apps.py) — постоянный self-host сторонних сервисов ──
  hostedApps: () => getJSON<{ apps: any[] }>("/api/apps", { apps: [] }),
  hostedAppDetail: (id: string) => getJSON<any>(`/api/apps/${id}`, null),
  hostedAppLogs: (id: string, tail = 100) => getJSON<{ logs: string }>(`/api/apps/${id}/logs?tail=${tail}`, { logs: "" }),
  pauseHostedApp: (id: string) => postJSON<any>(`/api/apps/${id}/pause`, {}, null),
  resumeHostedApp: (id: string) => postJSON<any>(`/api/apps/${id}/resume`, {}, null),
  removeHostedApp: (id: string) => api.del(`/api/apps/${id}`),
  // ── Тенантские MCP-серверы (office/mcp_tenant_servers.py) — подключает агент, владелец просматривает/отключает ──
  mcpServers: () => getJSON<{ servers: any[] }>("/api/mcp-servers", { servers: [] }),
  mcpServerDetail: (id: string) => getJSON<any>(`/api/mcp-servers/${id}`, null),
  removeMcpServer: (id: string) => api.del(`/api/mcp-servers/${id}`),
  del: async (url: string) => {
    try {
      const r = await fetch(url, { method: "DELETE", credentials: "same-origin" })
      return await r.json().catch(() => ({ ok: r.ok }))
    } catch { return null }
  },
}

export { getJSON, postJSON }
