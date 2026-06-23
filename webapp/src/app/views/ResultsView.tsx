import { useEffect, useState } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, SubTabs, ViewBody, Card, Empty, Pill, SectionLabel } from "./ui"

const TABS = [
  { id: "leads", label: "Лиды" },
  { id: "sites", label: "Сайты" },
  { id: "files", label: "Код" },
]

export function ResultsView() {
  const { state } = useOffice()
  const [tab, setTab] = useState("leads")
  const [files, setFiles] = useState<any[]>([])
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string>("")

  useEffect(() => {
    api.files().then(d => setFiles(d.files || []))
  }, [state.feed.length])

  async function openFile(path: string) {
    setSelectedFile(path)
    const d = await api.fileContent(path)
    setFileContent(d.content || "")
  }

  const tabsWithBadges = TABS.map(t => ({
    ...t,
    badge: t.id === "leads" ? state.leads.length
      : t.id === "sites" ? state.sites.length
      : t.id === "files" ? files.length
      : undefined,
  }))

  return (
    <ViewShell>
      <ViewHead title="Итоги" sub="Лиды, опубликованные сайты и код проекта" />
      <SubTabs tabs={tabsWithBadges} active={tab} onChange={t => { setTab(t); setSelectedFile(null) }} />

      {tab === "leads" && <LeadsTab leads={state.leads} />}
      {tab === "sites" && <SitesTab sites={state.sites} leads={state.leads} />}
      {tab === "files" && <FilesTab files={files} selected={selectedFile} content={fileContent} onOpen={openFile} />}
    </ViewShell>
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

// ── Файлы / Код ───────────────────────────────────────────────────────────────
function FilesTab({ files, selected, content, onOpen }: {
  files: any[]; selected: string | null; content: string; onOpen: (p: string) => void
}) {
  if (files.length === 0) return (
    <ViewBody>
      <Empty icon="⟨/⟩" text="Рабочая папка пуста"
        hint="Разработчик напишет код через инструмент write_file — файлы появятся здесь" />
    </ViewBody>
  )

  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
      <div style={{ width: 240, flexShrink: 0, borderRight: "1px solid var(--hairline)", overflowY: "auto", padding: "12px 0" }}>
        {files.map((f: any, i: number) => (
          <div key={i} onClick={() => onOpen(f.path)}
            style={{
              padding: "8px 18px", cursor: "pointer", fontSize: 12,
              color: selected === f.path ? "var(--text)" : "var(--text-dim)",
              background: selected === f.path ? "var(--hairline-soft)" : "transparent",
              borderLeft: `2px solid ${selected === f.path ? "var(--mercury-a)" : "transparent"}`,
              transition: "background 0.12s",
            }}
            onMouseEnter={e => { if (selected !== f.path) (e.currentTarget as HTMLElement).style.background = "var(--surface-soft)" }}
            onMouseLeave={e => { if (selected !== f.path) (e.currentTarget as HTMLElement).style.background = "transparent" }}>
            <span className="mono">{f.path}</span>
            <span style={{ float: "right", fontSize: 10, color: "var(--faint)" }}>
              {f.size ? `${f.size}b` : ""}
            </span>
          </div>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "18px 24px" }}>
        {selected ? (
          <>
            <div className="mono" style={{ fontSize: 10, color: "var(--muted)", marginBottom: 14 }}>{selected}</div>
            <pre style={{
              fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-dim)", lineHeight: 1.65,
              whiteSpace: "pre-wrap", wordBreak: "break-all", margin: 0,
            }}>
              {content || "Загрузка…"}
            </pre>
          </>
        ) : (
          <div style={{ color: "var(--faint)", fontSize: 13, paddingTop: 40, textAlign: "center" }}>
            Выберите файл слева
          </div>
        )}
      </div>
    </div>
  )
}
