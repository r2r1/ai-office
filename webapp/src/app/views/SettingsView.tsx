// IA-пересборка (вариант C, живой дизайн-аудит): бывшая "Компания" —
// 10 под-вкладок вперемешку (кто мы / кто работает / внешние подключения).
// Роли и Скиллы переехали в «Команду» (рядом с живыми агентами, не отдельно
// от них), Хранилище/Доступы/Приложения/MCP — в новый «Ресурсы». Здесь
// остаётся то, что реально про "кто мы и куда идём" + аккаунт.
import { useEffect, useState } from "react"
import { api } from "../../data/api"
import { useOffice } from "../../data/OfficeProvider"
import { ViewShell, ViewHead, ViewBody, SubTabs, useSubTab, Card, SectionLabel, Empty, ShowMore, Pill, Button, TextInput } from "./ui"
import { ModelPicker, type Preset } from "../components/ModelPicker"

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
  { id: "goals", label: "Цели" },
  { id: "intellect", label: "Интеллект" },
  { id: "limits", label: "Лимиты" },
  { id: "account", label: "Аккаунт" },
]

export function SettingsView({ initialTab, onInitialTabHandled }: { initialTab?: string; onInitialTabHandled?: () => void } = {}) {
  const { active, setActive } = useSubTab(TABS, initialTab)
  // Открытие «Настроек» из внешнего deep-link'а (например, баннер «недостаточно
  // средств» ведёт прямо на вкладку «Лимиты») — initialTab меняется, но useSubTab
  // фиксирует активную вкладку только при МОНТИРОВАНИИ, поэтому переключаем явно.
  useEffect(() => {
    if (initialTab) { setActive(initialTab); onInitialTabHandled?.() }
  }, [initialTab]) // eslint-disable-line
  return (
    <ViewShell>
      <ViewHead title="Настройки" sub="Кто мы, куда идём и как работает интеллект офиса" />
      <SubTabs tabs={TABS} active={active} onChange={setActive} />
      {active === "profile" && <ProfileTab />}
      {active === "goals" && <GoalsTab />}
      {active === "intellect" && <IntellectTab />}
      {active === "limits" && <LimitsTab />}
      {active === "account" && <AccountTab />}
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
                      <TextInput autoFocus compact value={editValue} onChange={e => setEditValue(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter") saveEdit(o.id); if (e.key === "Escape") setEditingId(null) }}
                        style={{ padding: "3px 8px", fontSize: 12, width: 110 }} />
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
          <TextInput value={title} onChange={e => setTitle(e.target.value)}
            placeholder="Цель — например: заявки с сайта каждую неделю" />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <TextInput value={desired} onChange={e => setDesired(e.target.value)}
              placeholder="Целевое значение (10/нед)" style={{ flex: "1 1 160px", minWidth: 0 }} />
            <TextInput value={measuredBy} onChange={e => setMeasuredBy(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addObjective()}
              placeholder="Как измеряем (лиды за 7 дней)" style={{ flex: "1 1 160px", minWidth: 0 }} />
            <Button variant="secondary" onClick={addObjective} style={{ flex: "1 1 auto" }}>Добавить</Button>
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

// ── Аккаунт (перенесено из отдельного пункта меню — рабочее пространство,
// тариф и сессия логически тоже "настройки", не самостоятельный раздел) ───────
function AccountTab() {
  const { state } = useOffice()
  const [businessName, setBusinessName] = useState<string>("")
  const [confirmingReset, setConfirmingReset] = useState(false)
  const [resetting, setResetting] = useState(false)
  useEffect(() => { api.briefStatus().then(d => setBusinessName(d?.brief?.niche || "")) }, [])

  async function doReset() {
    setResetting(true)
    await api.briefReset()
    window.location.reload()
  }

  return (
    <ViewBody style={{ maxWidth: 560 }}>
      <Card style={{ marginBottom: 16 }}>
        <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 12 }}>Рабочее пространство</div>
        <Field label="ID" value={state.workspace?.id || "—"} />
        <Field label="Название" value={businessName || state.workspace?.name || "—"} />
        <Field label="Статус офиса" value={state.ready ? "работает" : "ожидает бриф"} accent={!!state.ready} />
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 12 }}>Тариф и платежи</div>
        <Field label="Текущий тариф" value={state.workspace?.plan || "Базовый"} />
        <Field label="Расход за сессию" value={`$${state.cost.toFixed(4)}`} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 12 }}>
          <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>
            Лимиты расхода — во вкладке «Лимиты» рядом.
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

      {/* Первое расследование компании (docs/first-investigation-plan-2026-07-16.md,
          Фаза 5): новый филиал/направление — НЕ повод удалять то, что офис уже узнал.
          Отдельного механизма "повторное расследование" не заводим — CEO и так ведёт
          живой диалог (office/investigation.py, _steer_from_chat) в любой момент;
          здесь просто явно указываем, где эта возможность живёт, чтобы её не искали
          там же, где полный сброс (ниже). */}
      <Card style={{ marginTop: 16, marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: "var(--text)" }}>Новый филиал или направление?</div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
          Не нужно ничего сбрасывать — просто напишите об этом CEO в «Чатах» обычным
          сообщением. Он впишет новое направление в текущую работу — прошлые данные
          о компании никуда не денутся.
        </div>
      </Card>

      <Card style={{ borderColor: confirmingReset ? "rgba(207,102,121,0.4)" : undefined }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--text)" }}>Начать заново с другим бизнесом</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              Полный сброс: бриф, код, стратегия, команда и вся история этого рабочего
              пространства удаляются безвозвратно — офис запускается с чистого листа.
            </div>
          </div>
          {!confirmingReset ? (
            <button onClick={() => setConfirmingReset(true)}
              style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-pill)", padding: "9px 18px",
                background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13, whiteSpace: "nowrap" }}>
              Начать заново
            </button>
          ) : (
            <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
              <button onClick={() => setConfirmingReset(false)} disabled={resetting}
                style={{ border: "1px solid var(--hairline)", borderRadius: "var(--radius-pill)", padding: "9px 14px",
                  background: "transparent", color: "var(--muted)", cursor: "pointer", fontSize: 13 }}>
                Отмена
              </button>
              <button onClick={doReset} disabled={resetting}
                style={{ border: "none", borderRadius: "var(--radius-pill)", padding: "9px 14px",
                  background: "#cf6679", color: "#1a0a0a", cursor: resetting ? "default" : "pointer",
                  fontSize: 13, fontWeight: 600, opacity: resetting ? 0.6 : 1, whiteSpace: "nowrap" }}>
                {resetting ? "Стираю…" : "Да, удалить всё"}
              </button>
            </div>
          )}
        </div>
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

// ── Мелкие поля ───────────────────────────────────────────────────────────────
function TextField({ label, value, onSave, placeholder }: { label: string; value: string; onSave: (v: string) => void; placeholder?: string }) {
  const [v, setV] = useState(value || "")
  useEffect(() => setV(value || ""), [value])
  return (
    <div>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 5 }}>{label}</div>
      <TextInput value={v} onChange={e => setV(e.target.value)} onBlur={() => v !== value && onSave(v)}
        onKeyDown={e => e.key === "Enter" && v !== value && onSave(v)} placeholder={placeholder} style={{ fontSize: 13 }} />
    </div>
  )
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: { id: string; label: string }[]; onChange: (v: string) => void }) {
  return (
    <div>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 5 }}>{label}</div>
      <select value={value} onChange={e => onChange(e.target.value)} className="input" style={{ fontSize: 13, cursor: "pointer" }}>
        {options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
      </select>
    </div>
  )
}
