import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, Card } from "./ui"

export function AccountView() {
  const { state } = useOffice()
  const [model, setModel] = useState("")
  const [saved, setSaved] = useState(false)

  useEffect(() => { api.models().then(m => setModel(m.current || m.default || "")) }, [])

  async function saveModel() {
    await api.setModel(model.trim())
    setSaved(true); setTimeout(() => setSaved(false), 1500)
  }

  return (
    <ViewShell>
      <ViewHead title="Аккаунт" sub="Рабочее пространство и настройки" />
      <ViewBody style={{ maxWidth: 560 }}>
        <Card style={{ marginBottom: 16 }}>
          <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 12 }}>Рабочее пространство</div>
          <Field label="ID" value={state.workspace?.id || "—"} />
          <Field label="Название" value={state.workspace?.name || "—"} />
          <Field label="Тариф" value={state.workspace?.plan || "—"} />
          <Field label="Статус офиса" value={state.ready ? "работает" : "ожидает бриф"} accent={state.ready} />
        </Card>

        <Card>
          <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 12 }}>Модель LLM офиса</div>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={model} onChange={e => setModel(e.target.value)} placeholder="например glm-4.5-flash"
              style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)", borderRadius: 0, padding: "10px 14px", color: "var(--text)", fontSize: 13, outline: "none" }} />
            <button onClick={saveModel} style={{ border: "none", borderRadius: "var(--radius-pill)", padding: "0 20px",
              background: "var(--text)", color: "var(--bg)", cursor: "pointer", fontSize: 13, fontWeight: 500 }}>
              {saved ? "✓" : "Сохранить"}
            </button>
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8 }}>Можно сменить в любой момент. Расход за сессию: <b style={{ color: "var(--text-dim)" }}>${state.cost.toFixed(4)}</b></div>
        </Card>
      </ViewBody>
    </ViewShell>
  )
}

function Field({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--hairline-soft)" }}>
      <span style={{ fontSize: 12, color: "var(--muted)" }}>{label}</span>
      <span style={{ fontSize: 12.5, color: accent ? "#a0e0ab" : "var(--text-dim)" }}>{value}</span>
    </div>
  )
}
