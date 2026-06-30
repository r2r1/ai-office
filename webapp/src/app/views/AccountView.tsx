import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, Card } from "./ui"
import { ModelPicker, type Preset } from "../components/ModelPicker"

export function AccountView() {
  const { state } = useOffice()
  const [model, setModel] = useState("")
  const [presets, setPresets] = useState<Preset[]>([])
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.models().then(m => { setModel(m.default || ""); setPresets(m.presets || []) })
  }, [])

  async function saveModel(next: string) {
    const m = next.trim()
    if (!m) return
    setModel(m)
    await api.setModel(m)
    setSaved(true); setTimeout(() => setSaved(false), 1800)
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
          <Field label="Статус офиса" value={state.ready ? "работает" : "ожидает бриф"} accent={!!state.ready} />
        </Card>

        <Card>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 4 }}>
            <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px" }}>🧠 Модель офиса</div>
            {saved && <span style={{ fontSize: 11, color: "#a0e0ab" }}>сохранено ✓</span>}
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 14 }}>
            На этой AI-модели по умолчанию работают <b style={{ color: "var(--text-dim)" }}>все агенты</b>.
            Дешевле — экономнее, мощнее — умнее. Выберите из списка или впишите свою.
          </div>
          <ModelPicker value={model} presets={presets} onSave={saveModel} />
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 12 }}>
            Расход за сессию: <b style={{ color: "var(--text-dim)" }}>${state.cost.toFixed(4)}</b>
          </div>
        </Card>

        <Card style={{ marginTop: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--text)" }}>Логи работы офиса</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>Полный текстовый отчёт: бриф, команда, этапы, события, результаты</div>
          </div>
          <a href="/api/logs" download
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-pill)", padding: "9px 18px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13, textDecoration: "none", whiteSpace: "nowrap" }}>
            ↓ Скачать логи
          </a>
        </Card>

        <Card style={{ marginTop: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--text)" }}>Сессия</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>Выйти из аккаунта и вернуться на главную</div>
          </div>
          <button onClick={async () => { await api.logout(); window.location.reload() }}
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-pill)", padding: "9px 18px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13 }}>
            Выйти
          </button>
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
