// IA-пересборка (вариант C, живой дизайн-аудит): раньше Хранилище/Доступы/
// Приложения/MCP-серверы были вперемешку с Профилем/Ролями в одном списке
// из 10 под-вкладок "Компании" — один смысл ("внешний мир и инфраструктура"),
// разбросанный по трём вкладкам без общего дома. Теперь это один раздел.
import { useEffect, useState } from "react"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, SubTabs, useSubTab, Card, SectionLabel, Empty, Pill } from "./ui"
import { FileExplorer } from "./FileExplorer"
import { ConnectionsBody } from "./ConnectionsView"

const TABS = [
  { id: "storage", label: "Хранилище" },
  { id: "access", label: "Доступы" },
  { id: "apps", label: "Приложения" },
  { id: "mcp", label: "MCP-серверы" },
]

interface ResourcesViewProps {
  /** Глубокая ссылка «открыть папку проекта в Хранилище» (кнопка на
   * странице проекта — раньше туда нельзя было попасть иначе, чем вручную
   * искать папку в общем дереве файлов). */
  focusStorageProject?: string
  onFocusHandled?: () => void
}

export function ResourcesView({ focusStorageProject, onFocusHandled }: ResourcesViewProps = {}) {
  const { active, setActive } = useSubTab(TABS, focusStorageProject ? "storage" : undefined)
  return (
    <ViewShell>
      <ViewHead title="Ресурсы" sub="Хранилище, доступы, приложения и MCP-серверы офиса" />
      <SubTabs tabs={TABS} active={active} onChange={setActive} />
      {active === "storage" && <StorageTab focusProject={active === "storage" ? focusStorageProject : undefined} onFocusHandled={onFocusHandled} />}
      {active === "access" && <AccessTab />}
      {active === "apps" && <AppsTab />}
      {active === "mcp" && <McpServersTab />}
    </ViewShell>
  )
}

// ── Хранилище: сколько занимает место (как в iPhone/ОС) + дерево файлов ───────
function bytesFmt(n: number): string {
  if (!n) return "0 Б"
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
  let i = 0; let v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function StorageTab({ focusProject, onFocusHandled }: { focusProject?: string; onFocusHandled?: () => void }) {
  const [files, setFiles] = useState<any[]>([])
  const [usage, setUsage] = useState<any>(null)
  useEffect(() => {
    api.files().then(d => setFiles(d.files || []))
    api.storageUsage().then(setUsage)
  }, [])
  useEffect(() => { if (focusProject) onFocusHandled?.() }, [focusProject]) // eslint-disable-line

  const projects: { name: string; bytes: number; is_project?: boolean }[] = usage?.workspace?.projects || []
  const sysBytes = usage?.system_data?.bytes || 0
  const docker = usage?.docker || { available: false, total_bytes: 0, containers: [] }
  const sandboxImg = usage?.shared_sandbox_image_bytes || 0
  const total = usage?.total_bytes || 0

  // Сегменты полосы — доля от total, минимум 2% визуально, чтобы мелкие
  // категории (system_data) не исчезали совсем при доминирующем workspace.
  const segments = [
    { label: "Файлы проектов", bytes: projects.reduce((s, p) => s + p.bytes, 0), color: "var(--mercury-a)" },
    { label: "Системные данные", bytes: sysBytes, color: "#7a8cd6" },
    { label: "Docker (приложения и MCP)", bytes: docker.total_bytes || 0, color: "#a0e0ab" },
  ].filter(s => s.bytes > 0)

  return (
    <ViewBody>
      <SectionLabel>Использование памяти</SectionLabel>
      <Card style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
          <div className="mono" style={{ fontSize: 20, color: "var(--text)" }}>{bytesFmt(total)}</div>
          <div style={{ fontSize: 11, color: "var(--faint)" }}>всего у тенанта</div>
        </div>
        {segments.length > 0 && (
          <div style={{ display: "flex", height: 8, borderRadius: 999, overflow: "hidden", background: "var(--hairline)", marginBottom: 14 }}>
            {segments.map(s => (
              <div key={s.label} style={{ width: `${Math.max(2, (s.bytes / total) * 100)}%`, background: s.color }} title={`${s.label}: ${bytesFmt(s.bytes)}`} />
            ))}
          </div>
        )}
        <div style={{ display: "grid", gap: 8 }}>
          {segments.map(s => (
            <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
              <span style={{ color: "var(--text-dim)", flex: 1 }}>{s.label}</span>
              <span className="mono" style={{ color: "var(--muted)" }}>{bytesFmt(s.bytes)}</span>
            </div>
          ))}
          {sandboxImg > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, marginTop: 4, paddingTop: 8, borderTop: "1px solid var(--hairline)" }}>
              <span style={{ color: "var(--faint)", flex: 1 }}>Образ песочницы (общий для всех тенантов, не ваш личный расход)</span>
              <span className="mono" style={{ color: "var(--faint)" }}>{bytesFmt(sandboxImg)}</span>
            </div>
          )}
          {!docker.available && (
            <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 4 }}>
              Docker недоступен или выключен — раздел «Docker» не учтён в подсчёте.
            </div>
          )}
        </div>
      </Card>

      {projects.length > 0 && (
        <>
          <SectionLabel>Папки в Хранилище</SectionLabel>
          <div style={{ display: "grid", gap: 6, marginBottom: 20 }}>
            {projects.map((p: any) => (
              <div key={p.name || "—"} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5,
                padding: "8px 12px", background: "var(--surface-soft)", borderRadius: "var(--radius-sm)", border: "1px solid var(--hairline)" }}>
                <span style={{ color: "var(--text-dim)", flex: 1, fontFamily: "var(--font-mono)", fontSize: 11.5 }}>{p.name || "(корень workspace)"}</span>
                {p.is_project === false && <span style={{ fontSize: 10, color: "var(--faint)" }}>общее</span>}
                <span className="mono" style={{ color: "var(--muted)" }}>{bytesFmt(p.bytes)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {docker.containers?.length > 0 && (
        <>
          <SectionLabel>Docker-контейнеры</SectionLabel>
          <div style={{ display: "grid", gap: 6, marginBottom: 20 }}>
            {docker.containers.map((c: any) => (
              <div key={c.name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5,
                padding: "8px 12px", background: "var(--surface-soft)", borderRadius: "var(--radius-sm)", border: "1px solid var(--hairline)" }}>
                <span style={{ color: "var(--text-dim)", flex: 1, fontFamily: "var(--font-mono)", fontSize: 11.5 }}>{c.name}</span>
                <span className="mono" style={{ color: "var(--muted)" }}>{bytesFmt(c.bytes)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <SectionLabel>Файлы</SectionLabel>
      <div style={{ flex: 1, minHeight: 400, display: "flex" }}>
        <FileExplorer files={files} initialProjectFilter={focusProject} />
      </div>
    </ViewBody>
  )
}

// ── Доступы: полный каталог интеграций + сохранённые ключи (OAuth) ────────────
function AccessTab() {
  return <ConnectionsBody />
}

// ── Приложения: постоянный self-host сторонних open-source сервисов
// (office/tenant_apps.py, host_app) — API-ключи/значения env, docker-compose.yml,
// пауза/возобновление/удаление. Другая сущность, чем «Доступы» (там — учётные
// данные для интеграций, которые дёргает сам офис; здесь — постоянные сервисы,
// которые офис для тенанта развернул и держит живыми). ────────────────────────
const APP_STATUS_UI: Record<string, { label: string; color?: string; accent?: boolean }> = {
  running: { label: "Работает", color: "var(--success)" },
  stopped: { label: "На паузе", color: undefined },
  starting: { label: "Запускается", color: "var(--warning)" },
  error: { label: "Ошибка", color: "var(--danger)" },
}

function AppsTab() {
  const [apps, setApps] = useState<any[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => api.hostedApps().then(d => { setApps(d.apps || []); setLoading(false) })
  useEffect(() => { load() }, [])

  if (loading) return <ViewBody><div style={{ fontSize: 12, color: "var(--faint)" }}>Загрузка…</div></ViewBody>

  if (apps.length === 0) return (
    <ViewBody>
      <Empty icon="🧩" text="Постоянных приложений пока нет"
        hint="Появится, когда офис поднимет self-hosted сервис (например Postiz) через host_app — с вашего явного разрешения в чате" />
    </ViewBody>
  )

  return (
    <ViewBody>
      <SectionLabel>Постоянные приложения · {apps.length}</SectionLabel>
      <div style={{ display: "grid", gap: 10 }}>
        {apps.map((a: any) => {
          const st = APP_STATUS_UI[a.status] || { label: a.status }
          return (
            <Card key={a.id} onClick={() => setSelectedId(a.id === selectedId ? null : a.id)}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)" }}>{a.label}</div>
                  <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>порт {a.host_port} · id {a.id}</div>
                </div>
                <Pill color={st.color}>{st.label}</Pill>
              </div>
              {selectedId === a.id && <AppDetail app={a} onChanged={load} />}
            </Card>
          )
        })}
      </div>
    </ViewBody>
  )
}

function AppDetail({ app, onChanged }: { app: any; onChanged: () => void }) {
  const [detail, setDetail] = useState<any>(null)
  const [logs, setLogs] = useState<string>("")
  const [showLogs, setShowLogs] = useState(false)
  const [showCompose, setShowCompose] = useState(false)
  const [busy, setBusy] = useState(false)
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  useEffect(() => { api.hostedAppDetail(app.id).then(setDetail) }, [app.id])

  const copy = (key: string, value: string) => {
    navigator.clipboard?.writeText(value).catch(() => {})
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(k => (k === key ? null : k)), 1500)
  }

  const pauseOrResume = async () => {
    setBusy(true)
    if (app.status === "running") await api.pauseHostedApp(app.id)
    else await api.resumeHostedApp(app.id)
    setBusy(false)
    onChanged()
  }

  const remove = async () => {
    if (!confirm(`Удалить «${app.label}» насовсем? Данные стека (volume) будут потеряны.`)) return
    setBusy(true)
    await api.removeHostedApp(app.id)
    setBusy(false)
    onChanged()
  }

  const loadLogs = async () => {
    setShowLogs(v => !v)
    if (!showLogs) { const d = await api.hostedAppLogs(app.id); setLogs(d.logs || "") }
  }

  const inputStyle = {
    width: "100%", padding: "8px 10px", borderRadius: "var(--radius-sm)",
    border: "1px solid var(--hairline)", background: "var(--surface-soft)",
    color: "var(--text)", fontSize: 12, fontFamily: "var(--font-mono)",
  } as const

  return (
    <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--hairline)",
      display: "flex", flexDirection: "column", gap: 14 }} onClick={e => e.stopPropagation()}>
      {detail?.env_values && Object.keys(detail.env_values).length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>Значения (API-ключи и т.п.)</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {Object.entries(detail.env_values).map(([k, v]) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", minWidth: 140, flexShrink: 0 }}>{k}</div>
                <input style={inputStyle} readOnly value={String(v)} onClick={e => (e.target as HTMLInputElement).select()} />
                <button onClick={() => copy(k, String(v))}
                  style={{ fontSize: 11, padding: "6px 10px", borderRadius: "var(--radius-sm)", cursor: "pointer",
                    border: "1px solid var(--hairline)", background: "var(--surface-soft)", color: "var(--text-dim)", flexShrink: 0 }}>
                  {copiedKey === k ? "✓" : "Копировать"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button onClick={pauseOrResume} disabled={busy || app.status === "starting"}
          style={{ fontSize: 12, padding: "8px 14px", borderRadius: "var(--radius-pill)", cursor: "pointer",
            border: "1px solid var(--hairline-strong)", background: "var(--surface-soft)", color: "var(--text-dim)",
            opacity: busy ? 0.6 : 1 }}>
          {app.status === "running" ? "⏸ Пауза" : "▶ Возобновить"}
        </button>
        <button onClick={loadLogs}
          style={{ fontSize: 12, padding: "8px 14px", borderRadius: "var(--radius-pill)", cursor: "pointer",
            border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)" }}>
          {showLogs ? "Скрыть логи" : "Показать логи"}
        </button>
        <button onClick={() => setShowCompose(v => !v)}
          style={{ fontSize: 12, padding: "8px 14px", borderRadius: "var(--radius-pill)", cursor: "pointer",
            border: "1px solid var(--hairline)", background: "transparent", color: "var(--text-dim)" }}>
          {showCompose ? "Скрыть docker-compose.yml" : "Показать docker-compose.yml"}
        </button>
        <button onClick={remove} disabled={busy}
          style={{ fontSize: 12, padding: "8px 14px", borderRadius: "var(--radius-pill)", cursor: "pointer",
            border: "1px solid var(--hairline)", background: "transparent", color: "var(--faint)", marginLeft: "auto" }}>
          Удалить насовсем
        </button>
      </div>

      {showLogs && (
        <pre style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-dim)",
          background: "var(--surface-soft)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-sm)",
          padding: 12, maxHeight: 240, overflow: "auto", whiteSpace: "pre-wrap" }}>{logs || "Логов пока нет."}</pre>
      )}
      {showCompose && detail?.compose_yaml && (
        <pre style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-dim)",
          background: "var(--surface-soft)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-sm)",
          padding: 12, maxHeight: 320, overflow: "auto", whiteSpace: "pre-wrap" }}>{detail.compose_yaml}</pre>
      )}
    </div>
  )
}

function McpServersTab() {
  const [servers, setServers] = useState<any[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => api.mcpServers().then(d => { setServers(d.servers || []); setLoading(false) })
  useEffect(() => { load() }, [])

  if (loading) return <ViewBody><div style={{ fontSize: 12, color: "var(--faint)" }}>Загрузка…</div></ViewBody>

  if (servers.length === 0) return (
    <ViewBody>
      <Empty icon="🔌" text="Тенантских MCP-серверов пока нет"
        hint="Подключается агентом (register_external_api/discover_resource), когда офис находит внешний сервис по вашей задаче — исполняется в изолированной Docker-песочнице, не на хосте напрямую" />
    </ViewBody>
  )

  return (
    <ViewBody>
      <SectionLabel>Подключённые MCP-серверы · {servers.length}</SectionLabel>
      <div style={{ display: "grid", gap: 10 }}>
        {servers.map((s: any) => (
          <Card key={s.id} onClick={() => setSelectedId(s.id === selectedId ? null : s.id)}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)" }}>{s.label}</div>
                <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4, fontFamily: "var(--font-mono)" }}>
                  {s.command}{s.args?.length ? " " + s.args.join(" ") : ""}
                </div>
              </div>
              <Pill color={s.allow_network ? "var(--warning)" : undefined}>
                {s.allow_network ? "сеть разрешена" : "без сети"}
              </Pill>
            </div>
            {selectedId === s.id && <McpServerDetail server={s} onChanged={load} />}
          </Card>
        ))}
      </div>
    </ViewBody>
  )
}

function McpServerDetail({ server, onChanged }: { server: any; onChanged: () => void }) {
  const [detail, setDetail] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  useEffect(() => { api.mcpServerDetail(server.id).then(setDetail) }, [server.id])

  const copy = (key: string, value: string) => {
    navigator.clipboard?.writeText(value).catch(() => {})
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(k => (k === key ? null : k)), 1500)
  }

  const remove = async () => {
    if (!confirm(`Отключить «${server.label}» насовсем? Агенты потеряют доступ к его инструментам.`)) return
    setBusy(true)
    await api.removeMcpServer(server.id)
    setBusy(false)
    onChanged()
  }

  const inputStyle = {
    width: "100%", padding: "8px 10px", borderRadius: "var(--radius-sm)",
    border: "1px solid var(--hairline)", background: "var(--surface-soft)",
    color: "var(--text)", fontSize: 12, fontFamily: "var(--font-mono)",
  } as const

  return (
    <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--hairline)",
      display: "flex", flexDirection: "column", gap: 14 }} onClick={e => e.stopPropagation()}>
      {detail?.env_values && Object.keys(detail.env_values).length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>Переменные окружения</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {Object.entries(detail.env_values).map(([k, v]) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", minWidth: 140, flexShrink: 0 }}>{k}</div>
                <input style={inputStyle} readOnly value={String(v)} onClick={e => (e.target as HTMLInputElement).select()} />
                <button onClick={() => copy(k, String(v))}
                  style={{ fontSize: 11, padding: "6px 10px", borderRadius: "var(--radius-sm)", cursor: "pointer",
                    border: "1px solid var(--hairline)", background: "var(--surface-soft)", color: "var(--text-dim)", flexShrink: 0 }}>
                  {copiedKey === k ? "✓" : "Копировать"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ fontSize: 11.5, color: "var(--muted)" }}>
        Подключён {detail?.created_ts ? new Date(detail.created_ts * 1000).toLocaleString("ru-RU") : "—"} ·
        исполняется в Docker-песочнице (без доступа к файлам хоста)
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button onClick={remove} disabled={busy}
          style={{ fontSize: 12, padding: "8px 14px", borderRadius: "var(--radius-pill)", cursor: "pointer",
            border: "1px solid var(--hairline)", background: "transparent", color: "var(--faint)", marginLeft: "auto" }}>
          Отключить насовсем
        </button>
      </div>
    </div>
  )
}
