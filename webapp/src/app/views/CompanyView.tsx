import { useEffect, useState } from "react"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, SubTabs, useSubTab, Card, SectionLabel, Empty } from "./ui"
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

const TABS = [
  { id: "profile", label: "Профиль" },
  { id: "intellect", label: "Интеллект" },
  { id: "roles", label: "Роли" },
  { id: "skills", label: "Скиллы" },
  { id: "limits", label: "Лимиты" },
  { id: "storage", label: "Хранилище" },
  { id: "access", label: "Доступы" },
]

const DEPT_RU: Record<string, string> = { tech: "Технический", marketing: "Маркетинг", sales: "Продажи" }

export function CompanyView() {
  const { active, setActive } = useSubTab(TABS)
  return (
    <ViewShell>
      <ViewHead title="Компания" sub="Характер, интеллект, скиллы, лимиты и хранилище офиса" />
      <SubTabs tabs={TABS} active={active} onChange={setActive} />
      {active === "profile" && <ProfileTab />}
      {active === "intellect" && <IntellectTab />}
      {active === "roles" && <RolesTab />}
      {active === "skills" && <SkillsTab />}
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
    api.get("/api/capabilities").then(c => c && setCaps(c))
  }, [])
  function flash() { setSaved(true); setTimeout(() => setSaved(false), 1600) }

  function pickMode(mode: string) {
    setCaps((c: any) => ({ ...c, mode }))
    api.post("/api/capabilities", { mode }).then(c => { if (c) setCaps(c); flash() })
  }
  function setExpert(cap: string, m: string) {
    api.post("/api/capabilities", { expert: { [cap]: m } }).then(c => { if (c) setCaps(c); flash() })
  }

  return (
    <ViewBody style={{ maxWidth: 640 }}>
      {saved && <div style={{ fontSize: 11, color: "#a0e0ab", marginBottom: 10 }}>сохранено ✓</div>}

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
                <div style={{ fontSize: 10.5, color: "#ffac2e", marginTop: 8 }}>🚫 {(r.constraints || []).join(" · ")}</div>
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
  designer: "Дизайнер", integrator: "Интегратор", marketer: "Маркетолог",
  analyst: "Аналитик", salesman: "Продажник", researcher: "Ресёрчер",
}
const SKILL_EXAMPLE = `---
title: Название скилла
description: Что этот скилл делает
keywords: ключ1, ключ2
roles: developer, designer
---
Тело-плейбук: пошаговые инструкции, приёмы, чеклист.`

function SkillsTab() {
  const [skills, setSkills] = useState<any[]>([])
  const [mode, setMode] = useState<"markdown" | "url" | "github">("markdown")
  const [content, setContent] = useState("")
  const [ref, setRef] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const load = () => api.get("/api/skills").then(d => d?.skills && setSkills(d.skills))
  useEffect(() => { load() }, [])

  async function install() {
    setBusy(true); setMsg(null)
    const body: any = { source: mode }
    if (mode === "markdown") body.content = content
    else if (mode === "url") body.url = ref
    else body.ref = ref
    // Прямой fetch: install отдаёт 400 с {message} при ошибке, а api.post глотает
    // тело на non-2xx — нам нужно показать пользователю причину.
    let res: any = null
    try {
      const r = await fetch("/api/skills/install", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      })
      res = await r.json().catch(() => ({ ok: false }))
    } catch { res = { ok: false, message: "Сеть недоступна" } }
    setBusy(false)
    if (res?.ok) {
      setMsg({ ok: true, text: `Установлен: ${res.title || res.id}` })
      setContent(""); setRef(""); load()
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
          Скилл — это готовый «как делать» для агентов. Формат как у Claude Code
          (frontmatter + тело). Скилл — <b style={{ color: "var(--text-dim)" }}>инструкция,
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
          <textarea value={content} onChange={e => setContent(e.target.value)}
            placeholder={SKILL_EXAMPLE} rows={9}
            style={{ width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "10px 12px", color: "var(--text)", fontSize: 12,
              outline: "none", fontFamily: "var(--font-mono)", resize: "vertical", lineHeight: 1.5 }} />
        ) : (
          <input value={ref} onChange={e => setRef(e.target.value)}
            placeholder={mode === "url" ? "https://…/SKILL.md (сырой markdown)" : "owner/repo@skill"}
            style={{ width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)", padding: "10px 12px", color: "var(--text)", fontSize: 13, outline: "none" }} />
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
          <button onClick={install} disabled={busy || (mode === "markdown" ? !content.trim() : !ref.trim())}
            style={{ border: "1px solid var(--hairline-strong)", borderRadius: "var(--radius-pill)", padding: "9px 20px",
              background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 13,
              opacity: busy ? 0.5 : 1 }}>{busy ? "Устанавливаю…" : "Установить"}</button>
          {msg && <span style={{ fontSize: 12, color: msg.ok ? "#a0e0ab" : "#e05a5a" }}>{msg.text}</span>}
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
              роли: {(s.roles || []).map((r: string) => ROLE_RU[r] || r).join(", ")}
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

// ── Доступы: полный каталог интеграций + сохранённые ключи (OAuth) ────────────
function AccessTab() {
  return <ConnectionsBody />
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
