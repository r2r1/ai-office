import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, Card, Empty, SectionLabel } from "./ui"
import { useThrottled } from "../hooks"

/* Иконки Google-сервисов отдельно — не эмодзи */
const GOOGLE_ICON = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
  </svg>
)

const GOOGLE_SERVICES = new Set(["google_sheets", "gmail", "google_calendar"])

function IntegCard({ integ, onRefresh }: { integ: any; onRefresh: () => void }) {
  const isOAuth   = Boolean(integ.oauth_url)
  const isGoogle  = GOOGLE_SERVICES.has(integ.name)
  const connected = integ.connected

  const handleConnect = () => {
    if (isOAuth) {
      // OAuth: редирект на страницу согласия
      window.location.href = integ.oauth_url
    }
  }

  return (
    <Card style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Шапка */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 22, lineHeight: 1, flexShrink: 0 }}>
          {isGoogle ? GOOGLE_ICON : (integ.icon || "🔌")}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 600, lineHeight: 1.2 }}>
            {integ.title || integ.name}
          </div>
          <div style={{ fontSize: 10.5, marginTop: 3, display: "flex", alignItems: "center", gap: 5 }}>
            {connected ? (
              <span style={{ color: "#a0e0ab", fontWeight: 500 }}>✓ Подключено</span>
            ) : (
              <span style={{ color: "var(--faint)" }}>Не подключено</span>
            )}
            {isOAuth && <span style={{
              fontSize: 9, padding: "1px 5px", borderRadius: 4,
              background: "rgba(66,133,244,0.12)", color: "#4285F4", fontWeight: 600,
              border: "1px solid rgba(66,133,244,0.25)",
            }}>OAuth 2.0</span>}
          </div>
        </div>
      </div>

      {/* Описание */}
      {integ.description && (
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.55 }}>
          {integ.description}
        </div>
      )}

      {/* Кнопка подключения (только для OAuth и непривязанных) */}
      {isOAuth && !connected && (
        <button
          onClick={handleConnect}
          style={{
            marginTop: 2,
            padding: "8px 14px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid rgba(66,133,244,0.45)",
            background: "rgba(66,133,244,0.10)",
            color: "#4285F4",
            fontSize: 12, fontWeight: 600, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
            transition: "background 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "rgba(66,133,244,0.18)")}
          onMouseLeave={e => (e.currentTarget.style.background = "rgba(66,133,244,0.10)")}
        >
          {GOOGLE_ICON}
          Войти через Google
        </button>
      )}

      {/* Для подключённых Google — кнопка отключить */}
      {isGoogle && connected && (
        <button
          onClick={async () => {
            await fetch("/auth/google/disconnect", { method: "POST" })
            onRefresh()
          }}
          style={{
            marginTop: 2, padding: "6px 12px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--hairline)", background: "transparent",
            color: "var(--muted)", fontSize: 11, cursor: "pointer",
            transition: "color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--text)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--muted)")}
        >
          Отключить
        </button>
      )}

      {/* Инструкция для обычных ключей */}
      {!isOAuth && integ.how_to && !connected && (
        <div style={{
          fontSize: 10.5, color: "var(--faint)", lineHeight: 1.4,
          borderTop: "1px solid var(--hairline-soft)", paddingTop: 8, whiteSpace: "pre-line",
        }}>
          {integ.how_to}
        </div>
      )}
    </Card>
  )
}

export function ConnectionsView() {
  const { state } = useOffice()
  const [connections, setConnections]   = useState<any[]>([])
  const [integrations, setIntegrations] = useState<any[]>([])

  const refresh = () => {
    api.connections().then(d => setConnections(d.connections || []))
    api.integrations().then(d => setIntegrations(d.integrations || []))
  }

  const tick = useThrottled(state.feed.length, 2500)
  useEffect(refresh, [tick])

  // Если вернулись с OAuth (?connected=google) — обновляем список
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    if (p.get("connected") === "google") {
      refresh()
      window.history.replaceState({}, "", window.location.pathname)
    }
  }, [])

  return (
    <ViewShell>
      <ViewHead title="Доступы" sub="Подключения к внешним сервисам и API-ключи" />

      <ViewBody>
        {/* Каталог интеграций */}
        <SectionLabel style={{ marginBottom: 14 }}>
          Каталог интеграций · {integrations.length}
        </SectionLabel>
        {integrations.length === 0 ? (
          <Empty icon="🔌" text="Каталог не загружен" hint="Убедитесь, что сервер запущен" />
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
            gap: 10, marginBottom: 32,
          }}>
            {integrations.map((integ: any, i: number) => (
              <IntegCard key={i} integ={integ} onRefresh={refresh} />
            ))}
          </div>
        )}

        {/* Сохранённые ключи */}
        <SectionLabel style={{ marginBottom: 14 }}>
          Сохранённые ключи · {connections.length}
        </SectionLabel>
        {connections.length === 0 ? (
          <Empty icon="🔑" text="Нет сохранённых доступов"
            hint="Когда агент запросит API-ключ и вы его введёте — он появится здесь автоматически" />
        ) : (
          <div style={{ display: "grid", gap: 8 }}>
            {connections.map((c: any, i: number) => (
              <div key={i} className="card"
                style={{ borderRadius: "var(--radius-md)", padding: "13px 18px",
                  display: "flex", alignItems: "center", gap: 14 }}>
                <span style={{ fontSize: 20 }}>
                  {c.name === "google" ? GOOGLE_ICON : "🔌"}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{c.name}</div>
                  {c.note && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{c.note}</div>}
                </div>
                <span style={{ fontSize: 10.5, color: "#a0e0ab", fontWeight: 500 }}>✓ Активно</span>
              </div>
            ))}
          </div>
        )}
      </ViewBody>
    </ViewShell>
  )
}
