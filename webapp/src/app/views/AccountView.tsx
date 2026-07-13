import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, Card } from "./ui"

export function AccountView() {
  const { state } = useOffice()
  // Раньше "Название" показывало сырой workspace-слаг (marina.pekarnya) —
  // владелец бизнеса видел системное имя аккаунта вместо названия своего
  // дела (найдено при живом дизайн-аудите). Ниша/бриф — источник настоящего
  // названия, если он уже собран; slug остаётся честным fallback до брифа.
  const [businessName, setBusinessName] = useState<string>("")
  useEffect(() => { api.briefStatus().then(d => setBusinessName(d?.brief?.niche || "")) }, [])

  return (
    <ViewShell>
      <ViewHead title="Аккаунт" sub="Рабочее пространство, тариф и системные настройки" />
      <ViewBody style={{ maxWidth: 560 }}>
        <Card style={{ marginBottom: 16 }}>
          <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 12 }}>Рабочее пространство</div>
          <Field label="ID" value={state.workspace?.id || "—"} />
          <Field label="Название" value={businessName || state.workspace?.name || "—"} />
          <Field label="Статус офиса" value={state.ready ? "работает" : "ожидает бриф"} accent={!!state.ready} />
        </Card>

        {/* Тариф и платежи (витрина; реальная оплата подключается отдельно) */}
        <Card style={{ marginBottom: 16 }}>
          <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 12 }}>Тариф и платежи</div>
          <Field label="Текущий тариф" value={state.workspace?.plan || "Базовый"} />
          <Field label="Расход за сессию" value={`$${state.cost.toFixed(4)}`} />
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 12 }}>
            <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>
              Лимиты расхода — в разделе «Компания → Лимиты».
            </div>
            <button disabled title="Скоро"
              style={{ border: "1px solid var(--hairline)", borderRadius: "var(--radius-pill)", padding: "9px 18px",
                background: "transparent", color: "var(--faint)", cursor: "not-allowed", fontSize: 13, whiteSpace: "nowrap" }}>
              Пополнить
            </button>
          </div>
        </Card>

        <Card style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
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
