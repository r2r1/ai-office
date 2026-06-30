import { useEffect, useState, type ReactNode } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { roleName } from "../../data/roles"
import { ViewShell, ViewHead, SubTabs, ViewBody, Card, Empty, Pill, SectionLabel } from "./ui"
import { Modal, ModalPre } from "../components/Modal"
import { useThrottled } from "../hooks"

type ModalContent = { title: ReactNode; subtitle?: ReactNode; body: ReactNode } | null

const TABS = [
  { id: "outputs", label: "Итоги" },
  { id: "sites",   label: "Сайты" },
  { id: "leads",   label: "Лиды" },
]

export function ResultsView() {
  const { state } = useOffice()
  const [tab, setTab] = useState("outputs")
  const [deliverables, setDeliverables] = useState<any[]>([])
  const [modal, setModal] = useState<ModalContent>(null)

  const tick = useThrottled(state.feed.length, 2500)
  useEffect(() => {
    api.deliverables().then(d => setDeliverables(d.deliverables || []))
  }, [tick])

  const tabsWithBadges = TABS.map(t => ({
    ...t,
    badge: t.id === "outputs" ? deliverables.length
      : t.id === "sites" ? state.sites.length
      : t.id === "leads" ? state.leads.length
      : undefined,
  }))

  return (
    <ViewShell>
      <ViewHead title="Результаты" sub="Готовые материалы, сайты и собранные заявки" />
      <SubTabs tabs={tabsWithBadges} active={tab} onChange={setTab} />

      {tab === "outputs" && <DeliverablesTab deliverables={deliverables} onOpen={setModal} />}
      {tab === "sites"   && <SitesTab sites={state.sites} leads={state.leads} />}
      {tab === "leads"   && <LeadsTab leads={state.leads} />}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.title} subtitle={modal?.subtitle}>
        {modal?.body}
      </Modal>
    </ViewShell>
  )
}

// ── Итоги (deliverables) ──────────────────────────────────────────────────────
function DeliverablesTab({ deliverables, onOpen }: { deliverables: any[]; onOpen: (c: ModalContent) => void }) {
  if (deliverables.length === 0) return (
    <ViewBody>
      <Empty icon="◎" text="Готовые материалы появятся здесь"
        hint="Результаты работы агентов — стратегия, ТЗ, тексты и другие артефакты" />
    </ViewBody>
  )
  return (
    <ViewBody>
      <SectionLabel style={{ marginBottom: 16 }}>Готовые материалы · {deliverables.length}</SectionLabel>
      <div style={{ display: "grid", gap: 12 }}>
        {deliverables.map((d: any, i: number) => {
          const full = d.content || d.result || ""
          return (
            <Card key={i} onClick={() => onOpen({ title: roleName(d.role), subtitle: d.title || d.task, body: <ModalPre>{full}</ModalPre> })}>
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }}>
                <Pill accent>{roleName(d.role)}</Pill>
                <span style={{ fontSize: 12.5, color: "var(--text)", fontWeight: 500 }}>{d.title}</span>
              </div>
              {full && (
                <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.6,
                  display: "-webkit-box", WebkitLineClamp: 5, WebkitBoxOrient: "vertical", overflow: "hidden",
                  whiteSpace: "pre-wrap", borderTop: "1px solid var(--hairline-soft)", paddingTop: 10, marginTop: 4 }}>
                  {full}
                </div>
              )}
              <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 8 }}>Нажмите, чтобы открыть полностью →</div>
            </Card>
          )
        })}
      </div>
    </ViewBody>
  )
}

// ── Лиды ──────────────────────────────────────────────────────────────────────
function LeadsTab({ leads }: { leads: any[] }) {
  if (leads.length === 0) return (
    <ViewBody>
      <Empty icon="◈" text="Заявок пока нет"
        hint="Лиды появятся, когда агент опубликует лендинг и посетители оставят контакты" />
    </ViewBody>
  )

  return (
    <ViewBody>
      <SectionLabel style={{ marginBottom: 16 }}>Всего заявок: {leads.length}</SectionLabel>
      <div style={{ display: "grid", gap: 10 }}>
        {leads.map((l: any, i: number) => (
          <Card key={i} style={{ padding: "12px 16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 500, color: "var(--text)", marginBottom: 3 }}>
                  {l.name || "Аноним"}
                </div>
                {(l.contact || l.phone || l.email) && (
                  <div style={{ fontSize: 12, color: "var(--mercury-a)", marginBottom: l.message ? 7 : 0 }}>
                    {l.contact || l.phone || l.email}
                  </div>
                )}
                {l.message && (
                  <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{l.message}</div>
                )}
              </div>
              <div className="mono" style={{ fontSize: 10, color: "var(--faint)", flexShrink: 0, paddingTop: 2 }}>
                {l.ts ? new Date(l.ts * 1000).toLocaleDateString("ru", { day: "2-digit", month: "short" }) : `#${i + 1}`}
              </div>
            </div>
            {l.site && (
              <div style={{ fontSize: 10, color: "var(--faint)", marginTop: 8,
                borderTop: "1px solid var(--hairline-soft)", paddingTop: 8 }}>
                Источник: {l.site}
              </div>
            )}
          </Card>
        ))}
      </div>
    </ViewBody>
  )
}

// ── Сайты ─────────────────────────────────────────────────────────────────────
function SitesTab({ sites, leads }: { sites: any[]; leads: any[] }) {
  if (sites.length === 0) return (
    <ViewBody>
      <Empty icon="⊟" text="Опубликованных сайтов нет"
        hint="Маркетолог опубликует лендинг — он появится здесь с ссылкой и статистикой" />
    </ViewBody>
  )

  return (
    <ViewBody>
      <SectionLabel style={{ marginBottom: 16 }}>Опубликовано: {sites.length}</SectionLabel>
      <div style={{ display: "grid", gap: 12 }}>
        {sites.map((s: any, i: number) => {
          const siteLids = leads.filter((l: any) => l.site === s.slug || l.site === s.title)
          return (
            <Card key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)", marginBottom: 5 }}>
                    {s.title || s.slug}
                  </div>
                  <a href={s.url} target="_blank" rel="noreferrer"
                    style={{ fontSize: 12, color: "var(--mercury-a)", textDecoration: "none", wordBreak: "break-all" }}
                    onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")}
                    onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}>
                    {s.url}
                  </a>
                </div>
                <Pill accent>{siteLids.length + (s.leads ?? 0)} заявок</Pill>
              </div>
              {s.description && (
                <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{s.description}</div>
              )}
            </Card>
          )
        })}
      </div>
    </ViewBody>
  )
}

