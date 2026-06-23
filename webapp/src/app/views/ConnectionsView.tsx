import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, Card, Empty, SectionLabel } from "./ui"

export function ConnectionsView() {
  const { state } = useOffice()
  const [connections, setConnections]   = useState<any[]>([])
  const [integrations, setIntegrations] = useState<any[]>([])

  useEffect(() => {
    api.connections().then(d => setConnections(d.connections || []))
    api.integrations().then(d => setIntegrations(d.integrations || []))
  }, [state.feed.length])

  return (
    <ViewShell>
      <ViewHead title="Доступы" sub="Подключения к внешним сервисам и API-ключи" />

      <ViewBody>
        {/* Каталог интеграций */}
        <SectionLabel style={{ marginBottom: 14 }}>
          Каталог интеграций · {integrations.length}
        </SectionLabel>
        {integrations.length === 0 ? (
          <Empty icon="🔌" text="Каталог интеграций не загружен"
            hint="Убедитесь, что сервер запущен" />
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: 10, marginBottom: 32 }}>
            {integrations.map((integ: any, i: number) => (
              <Card key={i} style={{ padding: "16px 18px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
                  <span style={{ fontSize: 24, lineHeight: 1 }}>{integ.icon || "🔌"}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{integ.name}</div>
                    <div style={{ fontSize: 10.5, marginTop: 2 }}>
                      {integ.connected
                        ? <span style={{ color: "#a0e0ab" }}>✅ Подключено</span>
                        : <span style={{ color: "var(--faint)" }}>⚪ Не подключено</span>}
                    </div>
                  </div>
                </div>
                {integ.description && (
                  <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{integ.description}</div>
                )}
                {integ.how_to && !integ.connected && (
                  <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 8, lineHeight: 1.4,
                    borderTop: "1px solid var(--hairline-soft)", paddingTop: 8 }}>
                    {integ.how_to}
                  </div>
                )}
              </Card>
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
              <div key={i} className="glass"
                style={{ borderRadius: "var(--radius-md)", padding: "13px 18px",
                  display: "flex", alignItems: "center", gap: 14 }}>
                <span style={{ fontSize: 20 }}>🔌</span>
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
