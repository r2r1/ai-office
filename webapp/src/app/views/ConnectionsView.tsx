import { useEffect, useState } from "react"
import type { CSSProperties } from "react"
import { useOffice } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewBody, Card, Empty, SectionLabel } from "./ui"
import { Modal, ModalSection } from "../components/Modal"
import { useThrottled } from "../hooks"

/* Иконки Google-сервисов отдельно — не эмодзи */
const GOOGLE_ICON = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
  </svg>
)

const GOOGLE_SERVICES = new Set(["google_sheets", "gmail", "google_calendar"])

/** Модалка входа в личный Telegram-аккаунт — интерактивный флоу (телефон → код
 * → опционально 2FA-пароль), НЕ обычная форма одного ключа: см. how_to интеграции
 * и office/telegram_login.py на бэкенде. */
function TelegramPersonalLoginModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [step, setStep] = useState<"phone" | "code" | "password">("phone")
  const [hasDefaultCreds, setHasDefaultCreds] = useState<boolean | null>(null)
  const [apiId, setApiId] = useState("")
  const [apiHash, setApiHash] = useState("")
  const [phone, setPhone] = useState("")
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  // Оператор мог задать TELEGRAM_API_ID/TELEGRAM_API_HASH один раз в .env (ключи
  // приложения, не пользователя) — тогда поля api_id/api_hash в форме не нужны:
  // обычный пользователь не должен идти на my.telegram.org сам.
  useEffect(() => {
    if (open) api.tgConfig().then(c => setHasDefaultCreds(c.has_default_creds))
  }, [open])

  function reset() {
    setStep("phone"); setApiId(""); setApiHash(""); setPhone(""); setCode(""); setPassword(""); setError("")
  }

  async function submitPhone() {
    if (!phone.trim()) { setError("Введите номер телефона"); return }
    if (!hasDefaultCreds && (!apiId.trim() || !apiHash.trim())) { setError("Заполните все поля"); return }
    setBusy(true); setError("")
    const r = await api.tgLoginStart(phone.trim(), apiId.trim(), apiHash.trim())
    setBusy(false)
    if (!r?.ok) { setError(r?.error || "Не удалось запросить код"); return }
    setStep("code")
  }

  async function submitCode() {
    if (!code.trim()) { setError("Введите код из Telegram"); return }
    setBusy(true); setError("")
    const r = await api.tgLoginConfirm(code.trim())
    setBusy(false)
    if (r?.need_password) { setStep("password"); setError(""); return }
    if (!r?.ok) { setError(r?.error || "Код не подошёл"); return }
    reset(); onDone(); onClose()
  }

  async function submitPassword() {
    if (!password.trim()) { setError("Введите пароль двухфакторной защиты"); return }
    setBusy(true); setError("")
    const r = await api.tgLoginConfirm("", password.trim())
    setBusy(false)
    if (!r?.ok) { setError(r?.error || "Пароль не подошёл"); return }
    reset(); onDone(); onClose()
  }

  async function close() {
    if (step !== "phone") await api.tgLoginCancel()
    reset(); onClose()
  }

  const inputStyle: CSSProperties = {
    width: "100%", padding: "9px 12px", borderRadius: "var(--radius-md)",
    border: "1px solid var(--hairline-strong)", background: "var(--surface)",
    color: "var(--text)", fontSize: 13,
  }
  const btnStyle: CSSProperties = {
    padding: "9px 16px", borderRadius: "var(--radius-pill)", border: "none",
    background: "var(--mercury-a, #ffac2e)", color: "#0a0a0a", fontWeight: 600,
    fontSize: 12.5, cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1,
  }

  return (
    <Modal open={open} onClose={close} title="Вход в личный Telegram"
      subtitle="Нужен, чтобы писать в ЛС первым — бот так не умеет">
      {step === "phone" && (
        <>
          {hasDefaultCreds === false && (
            <ModalSection label="api_id и api_hash (my.telegram.org → API development tools)">
              <div style={{ fontSize: 11, color: "var(--faint)", marginBottom: 8, lineHeight: 1.5 }}>
                Оператор не задал ключи приложения — введите свои разработческие
                (обычно это делает один раз оператор сервиса, не каждый пользователь).
              </div>
              <div style={{ display: "grid", gap: 8 }}>
                <input style={inputStyle} placeholder="api_id" value={apiId} onChange={e => setApiId(e.target.value)} />
                <input style={inputStyle} placeholder="api_hash" value={apiHash} onChange={e => setApiHash(e.target.value)} />
              </div>
            </ModalSection>
          )}
          <ModalSection label="Номер телефона">
            <input style={inputStyle} placeholder="+79991234567" value={phone} onChange={e => setPhone(e.target.value)}
              disabled={hasDefaultCreds === null} autoFocus />
          </ModalSection>
        </>
      )}
      {step === "code" && (
        <ModalSection label={`Код из Telegram (отправлен на ${phone})`}>
          <input style={inputStyle} placeholder="12345" value={code} onChange={e => setCode(e.target.value)} autoFocus />
        </ModalSection>
      )}
      {step === "password" && (
        <ModalSection label="Пароль двухфакторной защиты">
          <input style={inputStyle} type="password" value={password} onChange={e => setPassword(e.target.value)} autoFocus />
        </ModalSection>
      )}
      {error && <div style={{ fontSize: 12, color: "#ff6b6b", marginTop: -8, marginBottom: 14 }}>{error}</div>}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button disabled={busy}
          onClick={step === "phone" ? submitPhone : step === "code" ? submitCode : submitPassword}
          style={btnStyle}>
          {step === "phone" ? "Получить код" : step === "code" ? "Подтвердить" : "Войти"}
        </button>
      </div>
    </Modal>
  )
}

function IntegCard({ integ, onRefresh }: { integ: any; onRefresh: () => void }) {
  const isOAuth   = Boolean(integ.oauth_url)
  const isGoogle  = GOOGLE_SERVICES.has(integ.name)
  const isTgPersonal = integ.name === "telegram_personal"
  const connected = integ.connected
  const [loginOpen, setLoginOpen] = useState(false)

  const handleConnect = () => {
    if (isOAuth) {
      // OAuth: редирект на страницу согласия
      window.location.href = integ.oauth_url
    } else if (isTgPersonal) {
      setLoginOpen(true)
    }
  }

  return (
    <Card style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Шапка */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 22, lineHeight: 1, flexShrink: 0 }}>
          {isGoogle ? GOOGLE_ICON : (integ.icon || "🔌")}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 600, lineHeight: 1.2 }}>
            {integ.title || integ.name}
          </div>
          <div style={{ fontSize: 10.5, marginTop: 3, display: "flex", alignItems: "center", gap: 5 }}>
            {connected ? (
              <span style={{ color: "#a0e0ab", fontWeight: 500 }}>✓ Подключено</span>
            ) : (
              <span style={{ color: "var(--faint)" }}>Не подключено</span>
            )}
            {isOAuth && <span style={{
              fontSize: 9, padding: "1px 5px", borderRadius: 4,
              background: "rgba(66,133,244,0.12)", color: "#4285F4", fontWeight: 600,
              border: "1px solid rgba(66,133,244,0.25)",
            }}>OAuth 2.0</span>}
          </div>
        </div>
      </div>

      {/* Описание */}
      {integ.description && (
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.55 }}>
          {integ.description}
        </div>
      )}

      {/* Кнопка подключения (только для OAuth и непривязанных) */}
      {isOAuth && !connected && (
        <button
          onClick={handleConnect}
          style={{
            marginTop: 2,
            padding: "8px 14px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid rgba(66,133,244,0.45)",
            background: "rgba(66,133,244,0.10)",
            color: "#4285F4",
            fontSize: 12, fontWeight: 600, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
            transition: "background 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "rgba(66,133,244,0.18)")}
          onMouseLeave={e => (e.currentTarget.style.background = "rgba(66,133,244,0.10)")}
        >
          {GOOGLE_ICON}
          Войти через Google
        </button>
      )}

      {/* Для подключённых Google — кнопка отключить */}
      {isGoogle && connected && (
        <button
          onClick={async () => {
            await fetch("/auth/google/disconnect", { method: "POST" })
            onRefresh()
          }}
          style={{
            marginTop: 2, padding: "6px 12px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--hairline)", background: "transparent",
            color: "var(--muted)", fontSize: 11, cursor: "pointer",
            transition: "color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--text)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--muted)")}
        >
          Отключить
        </button>
      )}

      {/* Личный Telegram — интерактивный вход, не форма ключа */}
      {isTgPersonal && !connected && (
        <button onClick={handleConnect}
          style={{
            marginTop: 2, padding: "8px 14px", borderRadius: "var(--radius-sm)",
            border: "1px solid var(--hairline-strong)", background: "var(--surface-soft)",
            color: "var(--text)", fontSize: 12, fontWeight: 600, cursor: "pointer",
          }}>
          Войти в Telegram
        </button>
      )}

      {/* Инструкция для обычных ключей */}
      {!isOAuth && !isTgPersonal && integ.how_to && !connected && (
        <div style={{
          fontSize: 10.5, color: "var(--faint)", lineHeight: 1.4,
          borderTop: "1px solid var(--hairline-soft)", paddingTop: 8, whiteSpace: "pre-line",
        }}>
          {integ.how_to}
        </div>
      )}
      {isTgPersonal && (
        <TelegramPersonalLoginModal open={loginOpen} onClose={() => setLoginOpen(false)} onDone={onRefresh} />
      )}
    </Card>
  )
}

const DI_CATEGORY_LABEL: Record<string, string> = {
  crm: "CRM", analytics: "Аналитика", social: "Соцсети",
}

// Порядок и подписи категорий каталога интеграций — новая интеграция без
// категории попадёт в "other" автоматически, каталог не расползётся плоским
// списком по мере роста (сейчас 7 интеграций, дальше будет больше).
const INTEG_CATEGORY_ORDER = ["communication", "publishing", "productivity", "dev", "other"]
const INTEG_CATEGORY_LABEL: Record<string, string> = {
  communication: "Коммуникации", publishing: "Публикация",
  productivity: "Продуктивность", dev: "Разработка", other: "Другое",
}

/** Карточка источника Digital Infrastructure (уровень 2 Instant Learning) —
 * то, что НЕ является интеграцией платформы, но офис увидел на сайте клиента
 * (соцсети/аналитика/CRM-виджет). Действие — не «подключить» (интеграции нет),
 * а попросить офис обратить на это внимание. */
function DiCard({ src }: { src: any }) {
  const [asked, setAsked] = useState(false)
  const detected = src.status === "detected_external"
  return (
    <Card style={{ padding: "13px 16px", display: "flex", alignItems: "center", gap: 12 }}>
      <span style={{ fontSize: 18, flexShrink: 0 }}>{src.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, color: "var(--text)", fontWeight: 600 }}>{src.label}</div>
        <div style={{ fontSize: 10.5, marginTop: 2 }}>
          {detected
            ? <span style={{ color: "#a0e0ab", fontWeight: 500 }}>✓ Видим на сайте</span>
            : <span style={{ color: "var(--faint)" }}>Не найдено</span>}
        </div>
      </div>
      {detected && (
        <button
          disabled={asked}
          onClick={async () => {
            await api.ask("orchestrator_1",
              `Заметил на сайте ${src.label} — учти это в работе (проанализируй/используй, если уместно).`)
            setAsked(true)
          }}
          style={{
            padding: "6px 12px", borderRadius: "var(--radius-sm)",
            border: "1px solid var(--hairline-strong)", background: asked ? "transparent" : "var(--surface-soft)",
            color: asked ? "var(--faint)" : "var(--text-dim)", fontSize: 11, cursor: asked ? "default" : "pointer",
            whiteSpace: "nowrap",
          }}>
          {asked ? "Передано" : "Сказать офису"}
        </button>
      )}
    </Card>
  )
}

/** Тело раздела «Доступы» без обёртки ViewShell — переиспользуется во вкладке
 *  «Компания → Доступы». */
export function ConnectionsBody() {
  const { state } = useOffice()
  const [connections, setConnections]   = useState<any[]>([])
  const [integrations, setIntegrations] = useState<any[]>([])
  const [diSources, setDiSources]       = useState<any[]>([])

  const refresh = () => {
    api.connections().then(d => setConnections(d.connections || []))
    api.integrations().then(d => setIntegrations(d.integrations || []))
    api.digitalInfrastructure().then(d => setDiSources(d.sources || []))
  }

  const tick = useThrottled(state.feed.length, 2500)
  useEffect(refresh, [tick])

  // Если вернулись с OAuth (?connected=google) — обновляем список
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    if (p.get("connected") === "google") {
      refresh()
      window.history.replaceState({}, "", window.location.pathname)
    }
  }, [])

  const diByCategory = ["crm", "analytics", "social"].map(cat => ({
    cat, items: diSources.filter(s => s.category === cat),
  })).filter(g => g.items.length > 0)

  const integByCategory = INTEG_CATEGORY_ORDER.map(cat => ({
    cat, items: integrations.filter((integ: any) => (integ.category || "other") === cat),
  })).filter(g => g.items.length > 0)

  return (
      <ViewBody>
        {/* Digital Infrastructure — что офис видит о компании за пределами
            своих интеграций (CRM-виджеты/аналитика/соцсети на сайте клиента) */}
        {diByCategory.length > 0 && (
          <>
            <SectionLabel style={{ marginBottom: 14 }}>
              Цифровая инфраструктура компании
            </SectionLabel>
            {diByCategory.map(({ cat, items }) => (
              <div key={cat} style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8, fontWeight: 600 }}>
                  {DI_CATEGORY_LABEL[cat] || cat}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 }}>
                  {items.map((src: any, i: number) => <DiCard key={i} src={src} />)}
                </div>
              </div>
            ))}
          </>
        )}

        {/* Каталог интеграций */}
        <SectionLabel style={{ marginBottom: 14 }}>
          Каталог интеграций · {integrations.length}
        </SectionLabel>
        {integrations.length === 0 ? (
          <Empty icon="🔌" text="Каталог не загружен" hint="Убедитесь, что сервер запущен" />
        ) : (
          <div style={{ marginBottom: 32 }}>
            {integByCategory.map(({ cat, items }) => (
              <div key={cat} style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8, fontWeight: 600 }}>
                  {INTEG_CATEGORY_LABEL[cat] || cat}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
                  {items.map((integ: any, i: number) => (
                    <IntegCard key={i} integ={integ} onRefresh={refresh} />
                  ))}
                </div>
              </div>
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
              <div key={i} className="card"
                style={{ borderRadius: "var(--radius-md)", padding: "13px 18px",
                  display: "flex", alignItems: "center", gap: 14 }}>
                <span style={{ fontSize: 20 }}>
                  {c.name === "google" ? GOOGLE_ICON : "🔌"}
                </span>
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
  )
}
