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
  leads: () => getJSON<{ leads: any[] }>("/api/leads", { leads: [] }),
  sites: () => getJSON<{ sites: any[] }>("/api/sites", { sites: [] }),
  plan: () => getJSON<any>("/api/plan", { generated: false, tasks: [], progress: { done: 0, total: 0 } }),
  deliverables: () => getJSON<{ deliverables: any[] }>("/api/deliverables", { deliverables: [] }),
  files: () => getJSON<{ files: any[] }>("/api/files", { files: [] }),
  connections: () => getJSON<{ connections: any[] }>("/api/connections", { connections: [] }),
  threads: () => getJSON<{ threads: Record<string, any> }>("/api/threads", { threads: {} }),
  thread: (id: string) => getJSON<{ agent_id: string; messages: any[] }>(`/api/thread/${id}`, { agent_id: id, messages: [] }),
  // ВАЖНО: бэкенд /api/ask читает поле `message`, а /api/chat — поле `text`.
  ask: (agentId: string, text: string) => postJSON<any>("/api/ask", { agent_id: agentId, message: text }, null),
  chatGet: () => getJSON<{ messages: any[] }>("/api/chat", { messages: [] }),
  chatPost: (message: string) => postJSON<any>("/api/chat", { text: message }, null),
  agentDetail: (id: string) => getJSON<any>(`/api/agent/${id}`, {}),
  setAgentModel: (id: string, model: string) => postJSON<any>(`/api/agent/${id}/model`, { model }, null),
  milestones: () => getJSON<any>("/api/milestones", { stages: [] }),
  integrations: () => getJSON<any>("/api/integrations", { integrations: [] }),
  // /api/file отдаёт СЫРОЙ текст — читаем как текст, не как JSON.
  fileContent: async (path: string) => ({ content: await getText(`/api/file?path=${encodeURIComponent(path)}`) }),
  rawUrl: (path: string) => `/api/raw/${path.split("/").map(encodeURIComponent).join("/")}`,
  runFile: (path: string) => postJSON<any>("/api/run", { path }, { ok: false, output: "Ошибка запроса" }),
  terminal: (cmd: string, cwd = "") => postJSON<any>("/api/terminal", { cmd, cwd }, { ok: false, output: "Ошибка запроса" }),
  models: () => getJSON<any>("/api/models", { default: "", presets: [], per_agent: {}, per_role: {} }),
  setModel: (model: string) => postJSON<any>("/api/model", { model }, null),
  digest: () => getJSON<any>("/api/digest", { items: [], count: 0, since: "", is_first: true }),
  understanding: () => getJSON<any>("/api/understanding", { score: 0, items: [], missing: [] }),
  knowledge: () => getJSON<any>("/api/knowledge", { facts: [], count: 0, layers: { global: 0, user: 0, department: 0 } }),
  departmentEvents: () => getJSON<any>("/api/department-events", { events: [], pending: 0 }),
  onboardingModes: () => getJSON<any>("/api/onboarding/modes", { modes: [] }),
  onboardingFinish: (mode: string, answers: any[]) => postJSON<any>("/api/onboarding/finish", { mode, answers }, null),
  officeStatus: () => getJSON<any>("/api/office/status", { paused: false, reason: "" }),
  officePause: () => postJSON<any>("/api/office/pause", {}, null),
  officeResume: () => postJSON<any>("/api/office/resume", {}, null),
  // ── авторизация ──
  devLogin: (email: string) => postJSON<any>("/auth/dev-login", { email }, null),
  githubDeviceStart: () => postJSON<any>("/auth/github/device/start", {}, null),
  githubDevicePoll: (device_code: string) => postJSON<any>("/auth/github/device/poll", { device_code }, null),
  logout: () => postJSON<any>("/auth/logout", {}, null),
  get: (url: string) => getJSON<any>(url, null),
  post: (url: string, body: unknown = {}) => postJSON<any>(url, body, null),
  del: async (url: string) => {
    try {
      const r = await fetch(url, { method: "DELETE", credentials: "same-origin" })
      return await r.json().catch(() => ({ ok: r.ok }))
    } catch { return null }
  },
}

export { getJSON, postJSON }
