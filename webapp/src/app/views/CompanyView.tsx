import { useEffect, useState } from "react"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, SubTabs, useSubTab, Card, SectionLabel, Empty, ShowMore, Pill } from "./ui"
import { ModelPicker, type Preset } from "../components/ModelPicker"
import { FileExplorer } from "./FileExplorer"
import { ConnectionsBody } from "./ConnectionsView"

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

// Порядок сгруппирован по смыслу (бизнес → команда → операции), а не как
// попало: профиль/цели — что за бизнес и куда идёт; роли/скиллы/интеллект —
// кто и как работает; лимиты/хранилище/доступы — операционные настройки.
// Раньше плоский порядок ощущался как настроечная панель обычной CRM без
// видимой логики (найдено при аудите).
const TABS = [
  { id: "profile", label: "Профиль" },
  { id: "goals", label: "Цели" },
  { id: "roles", label: "Роли" },
  { id: "skills", label: "Скиллы" },
  { id: "intellect", label: "Интеллект" },
  { id: "limits", label: "Лимиты" },
  { id: "storage", label: "Хранилище" },
  { id: "access", label: "Доступы" },
  { id: "apps", label: "Приложения" },
  { id: "mcp", label: "MCP-серверы" },
]

const DEPT_RU: Record<string, string> = { tech: "Технический", marketing: "Маркетинг", sales: "Продажи" }

export function CompanyView() {
  const { active, setActive } = useSubTab(TABS)
  return (
    <ViewShell>
      <ViewHead title="Компания" sub="Характер, интеллект, скиллы, лимиты и хранилище офиса" />
      <SubTabs tabs={TABS} active={active} onChange={setActive} />
      {active === "profile" && <ProfileTab />}
      {active === "goals" && <GoalsTab />}
      {active === "intellect" && <IntellectTab />}
      {active === "roles" && <RolesTab />}
      {active === "skills" && <SkillsTab />}
      {active === "limits" && <LimitsTab />}
      {active === "storage" && <StorageTab />}
      {active === "access" && <AccessTab />}
      {active === "apps" && <AppsTab />}
      {active === "mcp" && <McpServersTab />}
    </ViewShell>
  )
}

// ── Цели: Objectives (desired state) + срез Business State (World Model) ──────
function GoalsTab() {
  const [objectives, setObjectives] = useState<any[]>([])
  const [world, setWorld] = useState<any>(null)
  const [gaps, setGaps] = useState<any[]>([])
  const [title, setTitle] = useState("")
  const [desired, setDesired] = useState("")
  const [measuredBy, setMeasuredBy] = useState("")
  // Раньше "Заявки с сайта в неделю" (десяток по умолчанию — objectives.py::
  // ensure_leads_objective) можно было только архивировать целиком, поменять
  // "10" на своё число было нельзя нигде в интерфейсе — реальная жалоба клиента
  // после прогона (лог 2026-07-09): "откуда взялось 10 и нет способа поменять".
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState("")

  const load = () => {
    api.objectives().then(d => setObjectives(d.objectives || []))
    api.world().then(w => w && setWorld(w))
    api.gap().then(d => setGaps(d.gaps || []))
  }
  useEffect(load, [])

  async function addObjective() {
    const t = title.trim(); if (!t) return
    await api.addObjective(t, desired.trim(), measuredBy.trim())
    setTitle(""); setDesired(""); setMeasuredBy("")
    load()
  }
  async function archive(id: string) {
    await api.updateObjective(id, { status: "archived" })
    load()
  }
  function startEdit(o: any) {
    setEditingId(o.id); setEditValue(o.desired || "")
  }
  async function saveEdit(id: string) {
    const v = editValue.trim()
    setEditingId(null)
    if (!v) return
    await api.updateObjective(id, { desired: v })
    load()
  }

  const bs = world?.business_state
  const active = objectives.filter((o: any) => o.status === "active")

  return (
    <ViewBody style={{ maxWidth: 680 }}>
      {bs && (
        <>
          <SectionLabel>Где компания сейчас</SectionLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10, marginBottom: 20 }}>
            <StatCard label="План" value={`${bs.plan?.done ?? 0}/${bs.plan?.total ?? 0}`} sub={`${bs.plan?.percent ?? 0}%`} />
            <StatCard label="Лиды" value={String(bs.leads_count ?? 0)} sub={`сайтов: ${(bs.sites || []).length}`} />
            <StatCard label="Расход" value={`$${(bs.spend_usd ?? 0).toFixed(2)}`}
              sub={bs.budget_limit_usd ? `лимит $${bs.budget_limit_usd}` : "без лимита"} />
            <StatCard label="Команда" value={String(bs.team_size ?? 0)}
              sub={(bs.open_departments || []).join(", ") || "отделы закрыты"} />
          </div>
          {(bs.blockers || []).length > 0 && (
            <Card style={{ marginBottom: 20, borderColor: "rgba(224,138,138,0.35)" }}>
              <div style={{ fontSize: 12, color: "var(--danger-soft)", lineHeight: 1.5 }}>
                ⛔ {(bs.blockers || []).map((b: any) => b.summary).join(" · ")}
              </div>
            </Card>
          )}

          {(world.metrics || []).length > 0 && (
            <>
              <SectionLabel>Метрики (Measurement)</SectionLabel>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginBottom: 20 }}>
                {world.metrics.map((m: any, i: number) => (
                  <Card key={m.metric_id || i} style={{ padding: "12px 14px" }}>
                    <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
                      {m.label || m.metric_id}
                    </div>
                    <div className="mono" style={{ fontSize: 18, color: "var(--text)", marginBottom: 2 }}>{String(m.value ?? "—")}</div>
                    <Pill color={m.source === "fact" ? "var(--success)" : "var(--warning)"}>
                      {m.source === "fact" ? "факт" : "оценка"}
                    </Pill>
                  </Card>
                ))}
              </div>
            </>
          )}

          {(world.projects || []).length > 0 && (
            <>
              <SectionLabel>Проекты (что оставили после себя)</SectionLabel>
              <div style={{ display: "grid", gap: 8, marginBottom: 20 }}>
                {world.projects.map((p: any) => (
                  <Card key={p.id} style={{ padding: "12px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                      <div style={{ fontSize: 13, color: "var(--text)" }}>{p.title}</div>
                      <Pill color={p.status === "active" ? "var(--success)" : undefined}>{p.status}</Pill>
                    </div>
                    {p.left_behind && Object.keys(p.left_behind).length > 0 && (
                      <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 6 }}>
                        {Object.entries(p.left_behind).map(([k, v]) => `${k}: ${v}`).join(" · ")}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </>
          )}

          {bs.open_questions > 0 && (
            <div style={{ fontSize: 11.5, color: "var(--warning)", marginBottom: 20 }}>
              ❓ Открытых вопросов клиенту: {bs.open_questions}
            </div>
          )}
        </>
      )}

      <SectionLabel>Цели компании — к чему движемся</SectionLabel>
      <Card style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 18 }}>
        {active.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--muted)" }}>
            Целей пока нет. Добавьте измеримую цель — офис будет сверять с ней работу.
          </div>
        )}
        <ShowMore items={active} initial={4} moreLabel={n => `Показать ещё ${n} цел${n === 1 ? "ь" : n < 5 ? "и" : "ей"}`}
          render={(o: any) => {
          const g = gaps.find((x: any) => x.objective_id === o.id)
          return (
            <div key={o.id} style={{ display: "flex", alignItems: "flex-start", gap: 10, fontSize: 12.5,
              color: "var(--text-dim)", paddingBottom: 10, borderBottom: "1px solid var(--hairline)" }}>
              <span style={{ color: "var(--mercury-a)", marginTop: 1 }}>◎</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: "var(--text)", marginBottom: 3, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <span>{o.title}</span>
                  {editingId === o.id ? (
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <input autoFocus value={editValue} onChange={e => setEditValue(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter") saveEdit(o.id); if (e.key === "Escape") setEditingId(null) }}
                        style={{ ...inputStyle, padding: "3px 8px", fontSize: 12, width: 110 }} />
                      <button onClick={() => saveEdit(o.id)} title="Сохранить"
                        style={{ background: "none", border: "none", color: "var(--success)", cursor: "pointer", fontSize: 13 }}>✓</button>
                    </span>
                  ) : (
                    <span onClick={() => startEdit(o)} title="Изменить целевое значение"
                      style={{ color: "var(--mercury-a)", cursor: "pointer", borderBottom: "1px dashed var(--mercury-a)" }}>
                      {o.desired ? `→ ${o.desired}` : "→ задать значение"} ✎
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: o.measured_by ? "var(--success-dim)" : "var(--warning)" }}>
                  {o.measured_by ? `📏 ${o.measured_by}` : "⚠ пока не измерима — офис сначала создаст измеримость"}
                  {o.source === "company" && (
                    <span style={{ color: "var(--faint)", marginLeft: 6 }} title="Офис поставил эту цель сам при первой публикации сайта — значение можно поменять кликом выше">
                      · поставлена офисом автоматически
                    </span>
                  )}
                </div>
                {g && (
                  <div style={{ fontSize: 11, marginTop: 3, color: g.met ? "var(--success-dim)" : "var(--mercury-a)" }}>
                    {g.met
                      ? `✅ достигнута: ${g.current} из ${g.desired}`
                      : `📊 разрыв ${g.gap} — сейчас ${g.current} из ${g.desired}`}
                  </div>
                )}
              </div>
              <button onClick={() => archive(o.id)} title="Архивировать"
                style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer", fontSize: 14 }}>×</button>
            </div>
          )
        }} />
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
          <input value={title} onChange={e => setTitle(e.target.value)}
            placeholder="Цель — например: заявки с сайта каждую неделю"
            style={inputStyle} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <input value={desired} onChange={e => setDesired(e.target.value)}
              placeholder="Целевое значение (10/нед)" style={{ ...inputStyle, flex: "1 1 160px", minWidth: 0 }} />
            <input value={measuredBy} onChange={e => setMeasuredBy(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addObjective()}
              placeholder="Как измеряем (лиды за 7 дней)" style={{ ...inputStyle, flex: "1 1 160px", minWidth: 0 }} />
            <button onClick={addObjective}
              style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-md)", padding: "0 16px",
                background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13, flex: "1 1 auto",
                minHeight: 36 }}>Добавить</button>
          </div>
        </div>
      </Card>
      <div style={{ fontSize: 11, color: "var(--faint)", lineHeight: 1.5 }}>
        Цель с метрикой участвует в оценке прогресса; без метрики — офис сперва
        обеспечит измеримость (например, поставит счётчик заявок).
      </div>
    </ViewBody>
  )
}

const inputStyle = {
  background: "var(--surface-soft)", border: "1px solid var(--hairline)",
  borderRadius: "var(--radius-md)", padding: "9px 12px", color: "var(--text)",
  fontSize: 12, outline: "none",
} as const

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card style={{ padding: "12px 14px" }}>
      <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>{label}</div>
      <div className="mono" style={{ fontSize: 18, color: "var(--text)", marginBottom: 2 }}>{value}</div>
      {sub && <div style={{ fontSize: 10.5, color: "var(--faint)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sub}</div>}
    </Card>
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
      {saved && <div style={{ fontSize: 11, color: "var(--success)", marginBottom: 10 }}>сохранено ✓</div>}
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
        <ShowMore items={cons?.custom_rules || []} initial={5}
          render={(r: string, i: number) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--text-dim)" }}>
              <span style={{ color: "var(--mercury-a)" }}>•</span>
              <span style={{ flex: 1 }}>{r}</span>
              <button onClick={() => removeRule(r)}
                style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer", fontSize: 14 }}>×</button>
            </div>
          )} />
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

// ── Интеллект: режимы качества + эксперт-режим + базовая модель ────────────────
const CAP_LABELS: Record<string, string> = {
  text: "Текст", reasoning: "Рассуждение", coding: "Код", image: "Картинки",
  video: "Видео", search: "Поиск", voice: "Голос",
}

function IntellectTab() {
  const [model, setModel] = useState("")
  const [presets, setPresets] = useState<Preset[]>([])
  const [caps, setCaps] = useState<any>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.models().then(m => { setModel(m.default || ""); setPresets(m.presets || []) })
    api.get("/api/quality-modes").then(c => c && setCaps(c))
  }, [])
  function flash() { setSaved(true); setTimeout(() => setSaved(false), 1600) }

  function pickMode(mode: string) {
    setCaps((c: any) => ({ ...c, mode }))
    api.post("/api/quality-modes", { mode }).then(c => { if (c) setCaps(c); flash() })
  }
  function setExpert(cap: string, m: string) {
    api.post("/api/quality-modes", { expert: { [cap]: m } }).then(c => { if (c) setCaps(c); flash() })
  }

  return (
    <ViewBody style={{ maxWidth: 640 }}>
      {saved && <div style={{ fontSize: 11, color: "var(--success)", marginBottom: 10 }}>сохранено ✓</div>}

      <SectionLabel>Режим качества</SectionLabel>
      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 14 }}>
        Выберите качество — система сама подберёт лучшие модели под каждый тип задачи
        (код, картинки, видео могут идти на разные модели).
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10, marginBottom: 22 }}>
        {(caps?.modes || []).map((mo: any) => {
          const on = caps?.mode === mo.id
          return (
            <button key={mo.id} onClick={() => pickMode(mo.id)}
              style={{ textAlign: "left", padding: "12px 14px", borderRadius: "var(--radius-md)", cursor: "pointer",
                border: `1px solid ${on ? "var(--mercury-a)" : "var(--hairline)"}`,
                background: on ? "rgba(255,172,46,0.08)" : "var(--surface-soft)", transition: "all 0.15s" }}>
              <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 4 }}>{mo.icon} {mo.label}</div>
              <div style={{ fontSize: 10.5, color: "var(--muted)", lineHeight: 1.4 }}>{mo.desc}</div>
            </button>
          )
        })}
      </div>

      {/* Эксперт-режим — точечный выбор модели под capability */}
      {caps?.mode === "expert" ? (
        <>
          <SectionLabel>Модели по типу задачи</SectionLabel>
          <Card style={{ marginBottom: 18, display: "flex", flexDirection: "column", gap: 12 }}>
            {(caps?.capabilities || []).map((cap: string) => (
              <div key={cap} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 12, color: "var(--text-dim)", width: 96, flexShrink: 0 }}>{CAP_LABELS[cap] || cap}</span>
                <div style={{ flex: 1 }}>
                  <ModelPicker value={caps?.expert?.[cap] || ""} presets={presets} allowDefault compact
                    onSave={m => setExpert(cap, m)} />
                </div>
              </div>
            ))}
          </Card>
        </>
      ) : (
        <>
          <SectionLabel>Что выбрано под каждый тип</SectionLabel>
          <Card style={{ marginBottom: 18, display: "flex", flexDirection: "column", gap: 7 }}>
            {Object.entries<any>(caps?.resolved || {}).map(([cap, m]) => (
              <div key={cap} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "var(--muted)" }}>{CAP_LABELS[cap] || cap}</span>
                <span className="mono" style={{ color: "var(--text-dim)" }}>{m || "базовая модель"}</span>
              </div>
            ))}
          </Card>
        </>
      )}

      <SectionLabel>🧠 Базовая модель офиса</SectionLabel>
      <Card>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 12 }}>
          Резервная модель для задач, у которых нет специализации в режиме.
        </div>
        <ModelPicker value={model} presets={presets}
          onSave={v => { setModel(v); api.setModel(v).then(flash) }} />
      </Card>
    </ViewBody>
  )
}

// ── Роли: Role Definition (read-only) ─────────────────────────────────────────
function RolesTab() {
  const [roles, setRoles] = useState<any[]>([])
  useEffect(() => { api.get("/api/roles").then(r => r?.roles && setRoles(r.roles)) }, [])
  return (
    <ViewBody style={{ maxWidth: 680 }}>
      <SectionLabel>Роли компании — описание, а не зашитый промпт</SectionLabel>
      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 16 }}>
        У каждой роли есть миссия, зона ответственности, инструменты и ограничения.
        Итоговый промпт собирается под задачу автоматически.
      </div>
      {roles.length === 0 ? <Empty text="Загрузка…" /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {roles.map((r: any) => (
            <Card key={r.role}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 14, color: "var(--text)" }}>{r.title || r.role}</span>
                {r.department && <span style={{ fontSize: 10.5, color: "var(--muted)" }}>{DEPT_RU[r.department] || r.department}</span>}
              </div>
              {r.mission && <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45, marginBottom: 8 }}>{r.mission}</div>}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {(r.responsibilities || []).map((x: string, i: number) => (
                  <span key={i} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99,
                    background: "var(--surface-soft)", border: "1px solid var(--hairline)", color: "var(--text-dim)" }}>{x}</span>
                ))}
              </div>
              {(r.constraints || []).length > 0 && (
                <div style={{ fontSize: 10.5, color: "var(--mercury-a)", marginTop: 8 }}>🚫 {(r.constraints || []).join(" · ")}</div>
              )}
            </Card>
          ))}
        </div>
      )}
    </ViewBody>
  )
}

// ── Скиллы: каталог + установка из любого источника (как npx skills) ──────────
const ROLE_RU: Record<string, string> = {
  cto: "CTO", cmo: "CMO", sales_lead: "Head of Sales", developer: "Разработчик",
  // designer как отдельная нанимаемая роль слита с developer (roles.py) — но
  // строка "designer" остаётся в roles: скиллов как алиас поиска (защищено
  // тестами test_design_skills.py), поэтому в UI просто показываем то же имя,
  // что у developer, а не сырое "designer" (было найдено при живом аудите).
  designer: "Разработчик",
  integrator: "Интегратор", marketer: "Маркетолог",
  analyst: "Аналитик", salesman: "Продажник", researcher: "Ресёрчер",
  strategist: "Стратег", architect: "Архитектор", hr: "HR",
}
const SKILL_FIELD: React.CSSProperties = {
  background: "var(--surface-soft)", border: "1px solid var(--hairline)",
  borderRadius: "var(--radius-md)", padding: "8px 11px", color: "var(--text)",
  fontSize: 12, outline: "none",
}

// Разбор вставленного SKILL.md: если есть frontmatter (--- … ---) — вытащить поля,
// вернуть тело без него. Позволяет вставить готовый скилл и заполнить поля сами.
function splitFrontmatter(text: string): { fm: Record<string, string> | null; body: string } {
  const m = text.match(/^﻿?\s*---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n?([\s\S]*)$/)
  if (!m) return { fm: null, body: text }
  const fm: Record<string, string> = {}
  for (const line of m[1].split("\n")) {
    const i = line.indexOf(":")
    if (i > 0) fm[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim()
  }
  return { fm, body: m[2].replace(/^\s+/, "") }
}

function SkillsTab() {
  const [skills, setSkills] = useState<any[]>([])
  const [mode, setMode] = useState<"markdown" | "url" | "github">("markdown")
  // Поля скилла — тело первично, параметры заполняются сами при вставке готового SKILL.md.
  const [body, setBody] = useState("")
  const [title, setTitle] = useState("")
  const [desc, setDesc] = useState("")
  const [keywords, setKeywords] = useState("")
  const [roles, setRoles] = useState("")
  const [ref, setRef] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const load = () => api.get("/api/skills").then(d => d?.skills && setSkills(d.skills))
  useEffect(() => { load() }, [])

  // Вставили тело — если это готовый SKILL.md с frontmatter, разложим по полям.
  function onBodyChange(v: string) {
    const { fm, body: b } = splitFrontmatter(v)
    if (fm) {
      if (fm.title || fm.name) setTitle(fm.title || fm.name)
      if (fm.description) setDesc(fm.description)
      if (fm.keywords) setKeywords(fm.keywords)
      if (fm.roles) setRoles(fm.roles)
      setBody(b)
    } else {
      setBody(v)
    }
  }

  function assembleMarkdown(): string {
    const fm = ["---"]
    fm.push(`title: ${title.trim() || "Новый скилл"}`)
    if (desc.trim()) fm.push(`description: ${desc.trim()}`)
    if (keywords.trim()) fm.push(`keywords: ${keywords.trim()}`)
    if (roles.trim()) fm.push(`roles: ${roles.trim()}`)
    fm.push("---")
    return `${fm.join("\n")}\n${body.trim()}`
  }

  async function install() {
    setBusy(true); setMsg(null)
    const payload: any = { source: mode }
    if (mode === "markdown") payload.content = assembleMarkdown()
    else if (mode === "url") payload.url = ref
    else payload.ref = ref
    // Прямой fetch: install отдаёт 400 с {message} при ошибке, а api.post глотает
    // тело на non-2xx — нам нужно показать пользователю причину.
    let res: any = null
    try {
      const r = await fetch("/api/skills/install", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      })
      res = await r.json().catch(() => ({ ok: false }))
    } catch { res = { ok: false, message: "Сеть недоступна" } }
    setBusy(false)
    if (res?.ok) {
      setMsg({ ok: true, text: `Установлен: ${res.title || res.id}` })
      setBody(""); setTitle(""); setDesc(""); setKeywords(""); setRoles(""); setRef(""); load()
    } else {
      setMsg({ ok: false, text: res?.message || "Не удалось установить" })
    }
  }

  async function removeSkill(id: string) {
    const res = await api.del(`/api/skills/${encodeURIComponent(id)}`)
    if (res?.ok) load()
    else setMsg({ ok: false, text: res?.message || "Не удалось удалить" })
  }

  const installed = skills.filter(s => s.source === "installed")
  const builtin = skills.filter(s => s.source !== "installed")

  return (
    <ViewBody style={{ maxWidth: 720 }}>
      <SectionLabel>Установить скилл (из любого источника)</SectionLabel>
      <Card style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 12 }}>
          Скилл — это готовый «как делать» для агентов: заголовок с описанием
          + текст инструкции. Скилл — <b style={{ color: "var(--text-dim)" }}>инструкция,
          которой агенты будут следовать</b>: ставьте из доверенных источников.
        </div>
        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          {([["markdown", "Вставить"], ["url", "По ссылке"], ["github", "GitHub"]] as const).map(([m, label]) => (
            <button key={m} onClick={() => setMode(m)}
              style={{ padding: "5px 12px", borderRadius: "var(--radius-pill)", fontSize: 12, cursor: "pointer",
                border: `1px solid ${mode === m ? "var(--mercury-a)" : "var(--hairline)"}`,
                background: mode === m ? "rgba(255,172,46,0.08)" : "transparent",
                color: mode === m ? "var(--mercury-a)" : "var(--text-dim)" }}>{label}</button>
          ))}
        </div>
        {mode === "markdown" ? (
          <>
            {/* Тело — первично: вставь сюда готовый скилл ИЛИ опиши, как делать. */}
            <textarea value={body} onChange={e => onBodyChange(e.target.value)}
              placeholder={"Вставьте готовый скилл (SKILL.md) — параметры ниже заполнятся сами.\nИли просто опишите, как делать: пошагово, приёмы, чеклист."}
              rows={8}
              style={{ width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
                borderRadius: "var(--radius-md)", padding: "10px 12px", color: "var(--text)", fontSize: 12,
                outline: "none", fontFamily: "var(--font-mono)", resize: "vertical", lineHeight: 1.5 }} />
            <div style={{ fontSize: 11, color: "var(--muted)", margin: "8px 0 4px" }}>
              Параметры (заполнятся сами, если вставили готовый SKILL.md):
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Название *"
                style={SKILL_FIELD} />
              <input value={roles} onChange={e => setRoles(e.target.value)} placeholder="Роли: developer, marketer"
                style={SKILL_FIELD} />
              <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Описание — что делает"
                style={{ ...SKILL_FIELD, gridColumn: "1 / -1" }} />
              <input value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="Ключевые слова (через запятую)"
                style={{ ...SKILL_FIELD, gridColumn: "1 / -1" }} />
            </div>
          </>
        ) : (
          <input value={ref} onChange={e => setRef(e.target.value)}
            placeholder={mode === "url" ? "https://…/SKILL.md (сырой markdown)" : "owner/repo@skill"}
            style={{ width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "10px 12px", color: "var(--text)", fontSize: 13, outline: "none" }} />
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
          <button onClick={install} disabled={busy || (mode === "markdown" ? !(body.trim() && title.trim()) : !ref.trim())}
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-pill)", padding: "9px 20px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13,
              opacity: busy ? 0.5 : 1 }}>{busy ? "Устанавливаю…" : "Установить"}</button>
          {msg && <span style={{ fontSize: 12, color: msg.ok ? "var(--success)" : "var(--danger)" }}>{msg.text}</span>}
        </div>
      </Card>

      {installed.length > 0 && (
        <>
          <SectionLabel>Установленные · {installed.length}</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
            {installed.map(s => <SkillCard key={s.id} s={s} onRemove={() => removeSkill(s.id)} />)}
          </div>
        </>
      )}

      <SectionLabel>Встроенные · {builtin.length}</SectionLabel>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {builtin.map(s => <SkillCard key={s.id} s={s} />)}
      </div>
    </ViewBody>
  )
}

function SkillCard({ s, onRemove }: { s: any; onRemove?: () => void }) {
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 13.5, color: "var(--text)", fontWeight: 500 }}>{s.title}</span>
            <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 99,
              background: onRemove ? "rgba(255,172,46,0.12)" : "var(--surface-soft)",
              color: onRemove ? "var(--mercury-a)" : "var(--faint)", border: "1px solid var(--hairline)" }}>
              {onRemove ? "установлен" : "встроенный"}
            </span>
          </div>
          {s.description && <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.45 }}>{s.description}</div>}
          {(s.roles || []).length > 0 && (
            <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 6 }}>
              роли: {Array.from(new Set((s.roles || []).map((r: string) => ROLE_RU[r] || r))).join(", ")}
            </div>
          )}
        </div>
        {onRemove && (
          <button onClick={onRemove} title="Удалить скилл"
            style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer", fontSize: 16, flexShrink: 0 }}>×</button>
        )}
      </div>
    </Card>
  )
}

// ── Лимиты: бюджет + авто-пауза ───────────────────────────────────────────────
function LimitsTab() {
  const [lim, setLim] = useState<any>(null)
  const [total, setTotal] = useState("")
  const [daily, setDaily] = useState("")
  const [saved, setSaved] = useState(false)
  const [maxActive, setMaxActive] = useState("3")
  const [activeCount, setActiveCount] = useState(0)
  const [projSaved, setProjSaved] = useState(false)

  useEffect(() => {
    api.get("/api/limits").then(l => {
      if (l) { setLim(l); setTotal(String(l.total_usd || "")); setDaily(String(l.daily_usd || "")) }
    })
    api.projects().then(d => { setMaxActive(String(d.max_active ?? 3)); setActiveCount(d.active_count ?? 0) })
  }, [])

  function saveProjectLimit() {
    const n = Math.max(1, parseInt(maxActive) || 3)
    api.setProjectLimit(n).then(r => {
      if (r) setMaxActive(String(r.max_active))
      setProjSaved(true); setTimeout(() => setProjSaved(false), 1600)
    })
  }

  function save() {
    api.post("/api/limits", { total_usd: parseFloat(total) || 0, daily_usd: parseFloat(daily) || 0 }).then(l => {
      if (l) setLim(l); setSaved(true); setTimeout(() => setSaved(false), 1600)
    })
  }

  if (!lim) return <ViewBody><Empty text="Загрузка…" /></ViewBody>
  const pct = lim.total_usd > 0 ? Math.min(100, (lim.spent / lim.total_usd) * 100) : 0

  return (
    <ViewBody style={{ maxWidth: 560 }}>
      <SectionLabel>Параллельные проекты</SectionLabel>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 14 }}>
          Сколько разовых проектов офис ведёт ОДНОВРЕМЕННО. Сверх лимита — новые встают
          в очередь и стартуют сами, когда освобождается слот. Непрерывные процессы
          (продажи, поддержка и т.п.) в этот лимит не входят — идут параллельно без ограничений.
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "var(--text-dim)", width: 100 }}>Активно сейчас</span>
          <span className="mono" style={{ fontSize: 13, color: "var(--text)" }}>{activeCount} / {maxActive}</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
          <span style={{ fontSize: 12, color: "var(--text-dim)", width: 100 }}>Лимит</span>
          <input value={maxActive} onChange={e => setMaxActive(e.target.value)} type="number" min="1" step="1"
            onKeyDown={e => e.key === "Enter" && saveProjectLimit()}
            style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "9px 12px", color: "var(--text)", fontSize: 13, outline: "none" }} />
          <button onClick={saveProjectLimit}
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-md)", padding: "0 18px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13 }}>Сохранить</button>
        </div>
        {projSaved && <div style={{ fontSize: 11, color: "var(--success)", marginTop: 8 }}>сохранено ✓</div>}
      </Card>

      <SectionLabel>Бюджетный лимит</SectionLabel>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55, marginBottom: 14 }}>
          При достижении лимита офис автоматически встаёт на паузу — деньги не списываются дальше.
          0 = без лимита.
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "var(--text-dim)", width: 56 }}>Всего $</span>
          <input value={total} onChange={e => setTotal(e.target.value)} type="number" min="0" step="0.5"
            placeholder="0" onKeyDown={e => e.key === "Enter" && save()}
            style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "9px 12px", color: "var(--text)", fontSize: 13, outline: "none" }} />
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
          <span style={{ fontSize: 12, color: "var(--text-dim)", width: 56 }}>В день $</span>
          <input value={daily} onChange={e => setDaily(e.target.value)} type="number" min="0" step="0.5"
            placeholder="0" onKeyDown={e => e.key === "Enter" && save()}
            style={{ flex: 1, background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "9px 12px", color: "var(--text)", fontSize: 13, outline: "none" }} />
          <button onClick={save}
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-md)", padding: "0 18px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13 }}>Сохранить</button>
        </div>
        {saved && <div style={{ fontSize: 11, color: "var(--success)", marginTop: 8 }}>сохранено ✓</div>}
      </Card>

      <SectionLabel>Текущий расход</SectionLabel>
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 13, color: "var(--text)" }}>Потрачено</span>
          <span className="mono" style={{ fontSize: 13, color: lim.over_limit ? "var(--danger)" : "var(--text-dim)" }}>
            ${lim.spent.toFixed(4)}{lim.total_usd > 0 ? ` / $${lim.total_usd}` : ""}
          </span>
        </div>
        {lim.total_usd > 0 && (
          <div style={{ height: 4, background: "var(--hairline)", borderRadius: 2, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${pct}%`, transition: "width 0.5s",
              background: pct >= 100 ? "var(--danger)" : pct >= 75 ? "var(--mercury-a)" : "var(--success)" }} />
          </div>
        )}
        {typeof lim.spent_today === "number" && (
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10 }}>
            <span style={{ fontSize: 13, color: "var(--text)" }}>Сегодня</span>
            <span className="mono" style={{ fontSize: 13, color: "var(--text-dim)" }}>
              ${lim.spent_today.toFixed(4)}{lim.daily_usd > 0 ? ` / $${lim.daily_usd}` : ""}
            </span>
          </div>
        )}
        {lim.over_limit && <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 8 }}>⛔ Лимит достигнут — офис на паузе</div>}
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
