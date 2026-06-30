import { useEffect, useState } from "react"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, SubTabs, useSubTab, Card, SectionLabel, Empty } from "./ui"
import { ModelPicker, type Preset } from "../components/ModelPicker"
import { FileExplorer } from "./FileExplorer"

const GROWTH_STYLES = [
  { id: "aggressive", label: "Агрессивный — скорость важнее осторожности" },
  { id: "stable", label: "Устойчивый — надёжность важнее скорости" },
  { id: "premium", label: "Премиальный — лучше меньше, но безупречно" },
  { id: "experimental", label: "Экспериментальный — гипотезы и итерации" },
]
const RISK = [
  { id: "low", label: "Низкий" },
  { id: "medium", label: "Средний" },
  { id: "high", label: "Высокий" },
]

const TABS = [
  { id: "profile", label: "Профиль" },
  { id: "intellect", label: "Интеллект" },
  { id: "limits", label: "Лимиты" },
  { id: "storage", label: "Хранилище" },
  { id: "access", label: "Доступы" },
]

export function CompanyView() {
  const { active, setActive } = useSubTab(TABS)
  return (
    <ViewShell>
      <ViewHead title="Компания" sub="Характер, интеллект, лимиты и хранилище офиса" />
      <SubTabs tabs={TABS} active={active} onChange={setActive} />
      {active === "profile" && <ProfileTab />}
      {active === "intellect" && <IntellectTab />}
      {active === "limits" && <LimitsTab />}
      {active === "storage" && <StorageTab />}
      {active === "access" && <AccessTab />}
    </ViewShell>
  )
}

// ── Профиль: философия + конституция ──────────────────────────────────────────
function ProfileTab() {
  const [phil, setPhil] = useState<any>(null)
  const [cons, setCons] = useState<any>(null)
  const [newRule, setNewRule] = useState("")
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get("/api/philosophy").then(p => p && setPhil(p))
    api.get("/api/constitution").then(c => c && setCons(c))
  }, [])

  function flash() { setSaved(true); setTimeout(() => setSaved(false), 1600) }
  function savePhil(patch: any) {
    const next = { ...phil, ...patch }; setPhil(next)
    api.post("/api/philosophy", next).then(flash)
  }
  function addRule() {
    const r = newRule.trim(); if (!r) return
    const rules = [...(cons?.custom_rules || []), r]
    const next = { ...cons, custom_rules: rules }; setCons(next); setNewRule("")
    api.post("/api/constitution", { custom_rules: rules }).then(flash)
  }
  function removeRule(r: string) {
    const rules = (cons?.custom_rules || []).filter((x: string) => x !== r)
    const next = { ...cons, custom_rules: rules }; setCons(next)
    api.post("/api/constitution", { custom_rules: rules }).then(flash)
  }

  if (!phil) return <ViewBody><Empty text="Загрузка…" /></ViewBody>

  return (
    <ViewBody style={{ maxWidth: 620 }}>
      {saved && <div style={{ fontSize: 11, color: "#a0e0ab", marginBottom: 10 }}>сохранено ✓</div>}
      <SectionLabel>Философия компании</SectionLabel>
      <Card style={{ marginBottom: 18, display: "flex", flexDirection: "column", gap: 14 }}>
        <TextField label="Миссия — зачем компания существует" value={phil.mission}
          onSave={v => savePhil({ mission: v })} placeholder="Например: помогать малому бизнесу выходить онлайн" />
        <TextField label="Что для вас успех" value={phil.success_means}
          onSave={v => savePhil({ success_means: v })} placeholder="Например: 50 платящих клиентов за квартал" />
        <TextField label="Чем никогда не жертвуем" value={phil.never_sacrifice}
          onSave={v => savePhil({ never_sacrifice: v })} placeholder="Например: качеством продукта, честностью" />
        <SelectField label="Стиль роста" value={phil.growth_style} options={GROWTH_STYLES}
          onChange={v => savePhil({ growth_style: v })} />
        <SelectField label="Аппетит к риску" value={phil.risk_appetite} options={RISK}
          onChange={v => savePhil({ risk_appetite: v })} />
      </Card>

      <SectionLabel>Конституция — правила, которые офис не нарушит</SectionLabel>
      <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {(cons?.custom_rules || []).length === 0 && (
          <div style={{ fontSize: 12, color: "var(--muted)" }}>Правил пока нет. Добавьте, что офису делать нельзя.</div>
        )}
        {(cons?.custom_rules || []).map((r: string, i: number) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--text-dim)" }}>
            <span style={{ color: "var(--mercury-a)" }}>•</span>
            <span style={{ flex: 1 }}>{r}</span>
            <button onClick={() => removeRule(r)}
              style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer", fontSize: 14 }}>×</button>
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <input value={newRule} onChange={e => setNewRule(e.target.value)}
            onKeyDown={e => e.key === "Enter" && addRule()}
            placeholder="Например: не подключать платные конструкторы без разрешения"
            style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "9px 12px", color: "var(--text)", fontSize: 12, outline: "none" }} />
          <button onClick={addRule}
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-md)", padding: "0 16px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13 }}>Добавить</button>
        </div>
      </Card>
    </ViewBody>
  )
}

// ── Интеллект: модель офиса + по ролям (Phase 2 добавит режимы качества) ───────
function IntellectTab() {
  const [model, setModel] = useState("")
  const [presets, setPresets] = useState<Preset[]>([])
  const [roles, setRoles] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.models().then(m => { setModel(m.default || ""); setPresets(m.presets || []); setRoles(m.per_role || {}) })
  }, [])
  function flash() { setSaved(true); setTimeout(() => setSaved(false), 1600) }

  return (
    <ViewBody style={{ maxWidth: 620 }}>
      {saved && <div style={{ fontSize: 11, color: "#a0e0ab", marginBottom: 10 }}>сохранено ✓</div>}
      <SectionLabel>🧠 Базовая модель офиса</SectionLabel>
      <Card style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 12 }}>
          На этой модели по умолчанию работают <b style={{ color: "var(--text-dim)" }}>все агенты</b>.
          Дешевле — экономнее, мощнее — умнее.
        </div>
        <ModelPicker value={model} presets={presets}
          onSave={v => { setModel(v); api.setModel(v).then(flash) }} />
      </Card>
      <div style={{ fontSize: 11.5, color: "var(--faint)", lineHeight: 1.55 }}>
        Скоро здесь появятся режимы качества (🟣 Экономия → ⚫ Эксперт) с автоматическим
        выбором лучших моделей под тип задачи.
      </div>
    </ViewBody>
  )
}

// ── Лимиты: бюджет + авто-пауза ───────────────────────────────────────────────
function LimitsTab() {
  const [lim, setLim] = useState<any>(null)
  const [total, setTotal] = useState("")
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get("/api/limits").then(l => { if (l) { setLim(l); setTotal(String(l.total_usd || "")) } })
  }, [])

  function save() {
    api.post("/api/limits", { total_usd: parseFloat(total) || 0 }).then(l => {
      if (l) setLim(l); setSaved(true); setTimeout(() => setSaved(false), 1600)
    })
  }

  if (!lim) return <ViewBody><Empty text="Загрузка…" /></ViewBody>
  const pct = lim.total_usd > 0 ? Math.min(100, (lim.spent / lim.total_usd) * 100) : 0

  return (
    <ViewBody style={{ maxWidth: 560 }}>
      <SectionLabel>Бюджетный лимит</SectionLabel>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 14 }}>
          При достижении лимита офис автоматически встаёт на паузу — деньги не списываются дальше.
          0 = без лимита.
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 14, color: "var(--text-dim)" }}>$</span>
          <input value={total} onChange={e => setTotal(e.target.value)} type="number" min="0" step="0.5"
            placeholder="0" onKeyDown={e => e.key === "Enter" && save()}
            style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "9px 12px", color: "var(--text)", fontSize: 13, outline: "none" }} />
          <button onClick={save}
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-md)", padding: "0 18px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13 }}>Сохранить</button>
        </div>
        {saved && <div style={{ fontSize: 11, color: "#a0e0ab", marginTop: 8 }}>сохранено ✓</div>}
      </Card>

      <SectionLabel>Текущий расход</SectionLabel>
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 13, color: "var(--text)" }}>Потрачено</span>
          <span className="mono" style={{ fontSize: 13, color: lim.over_limit ? "#e05a5a" : "var(--text-dim)" }}>
            ${lim.spent.toFixed(4)}{lim.total_usd > 0 ? ` / $${lim.total_usd}` : ""}
          </span>
        </div>
        {lim.total_usd > 0 && (
          <div style={{ height: 4, background: "var(--hairline)", borderRadius: 2, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${pct}%`, transition: "width 0.5s",
              background: pct >= 100 ? "#e05a5a" : pct >= 75 ? "#ffac2e" : "#a0e0ab" }} />
          </div>
        )}
        {lim.over_limit && <div style={{ fontSize: 11, color: "#e05a5a", marginTop: 8 }}>⛔ Лимит достигнут — офис на паузе</div>}
      </Card>
    </ViewBody>
  )
}

// ── Хранилище: дерево файлов workspace ────────────────────────────────────────
function StorageTab() {
  const [files, setFiles] = useState<any[]>([])
  useEffect(() => { api.files().then(d => setFiles(d.files || [])) }, [])
  return <FileExplorer files={files} />
}

// ── Доступы: статусы интеграций (OAuth — этап подготовки) ─────────────────────
function AccessTab() {
  const [items, setItems] = useState<any[]>([])
  useEffect(() => { api.integrations().then(d => setItems(d.integrations || [])) }, [])
  return (
    <ViewBody style={{ maxWidth: 620 }}>
      <SectionLabel>Подготовка: подключения и интеграции</SectionLabel>
      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 16 }}>
        Прежде чем офис начнёт работать с внешними системами, подключите нужные сервисы.
        OAuth-интеграции (Google, GitHub) авторизуются в один клик во вкладке «Доступы».
      </div>
      {items.length === 0 ? <Empty text="Список интеграций загружается…" /> : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
          {items.map((it: any) => (
            <Card key={it.name}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, color: "var(--text)" }}>{it.title || it.name}</span>
                <span style={{ fontSize: 11, color: it.connected ? "#a0e0ab" : "var(--faint)" }}>
                  {it.connected ? "● подключено" : "○ нет"}
                </span>
              </div>
              {it.how_to && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.4 }}>{it.how_to}</div>}
            </Card>
          ))}
        </div>
      )}
    </ViewBody>
  )
}

// ── Мелкие поля ───────────────────────────────────────────────────────────────
function TextField({ label, value, onSave, placeholder }: { label: string; value: string; onSave: (v: string) => void; placeholder?: string }) {
  const [v, setV] = useState(value || "")
  useEffect(() => setV(value || ""), [value])
  return (
    <div>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 5 }}>{label}</div>
      <input value={v} onChange={e => setV(e.target.value)} onBlur={() => v !== value && onSave(v)}
        onKeyDown={e => e.key === "Enter" && v !== value && onSave(v)} placeholder={placeholder}
        style={{ width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-md)", padding: "9px 12px", color: "var(--text)", fontSize: 13, outline: "none" }} />
    </div>
  )
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: { id: string; label: string }[]; onChange: (v: string) => void }) {
  return (
    <div>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 5 }}>{label}</div>
      <select value={value} onChange={e => onChange(e.target.value)}
        style={{ width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-md)", padding: "9px 12px", color: "var(--text)", fontSize: 13, outline: "none", cursor: "pointer" }}>
        {options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
      </select>
    </div>
  )
}
