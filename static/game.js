// ============================================================
// AI OFFICE — Pixel Game Engine
// ============================================================

const TILE = 32;          // размер тайла в пикселях
const COLS = 20;          // ширина карты в тайлах
const ROWS = 14;          // высота карты в тайлах
const SCALE = 2;          // масштаб пикселей (pixel art)
const P = TILE * SCALE;   // размер тайла на экране

// Цвета ролей
const ROLE_COLORS = {
  researcher: "#4fc3f7",
  strategist: "#81c784",
  hr:         "#ffb74d",
  salesman:   "#f06292",
  developer:  "#ce93d8",
  marketer:   "#80cbc4",
  analyst:    "#fff176",
};

// Иконки ролей (emoji -> рисуем текстом)
const ROLE_ICONS = {
  researcher: "🔍", strategist: "📋", hr: "👔",
  salesman: "💰", developer: "💻", marketer: "📢", analyst: "📊",
};

// ---- Карта офиса (0=пол, 1=стена, 2=стол, 3=окно, 4=растение) ---
const MAP = [
  [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [1,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3,1],
  [1,0,2,2,0,0,2,2,0,0,2,2,0,0,2,2,0,0,0,1],
  [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
  [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,1],
  [1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,1],
  [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
  [1,0,2,2,0,0,2,2,0,0,2,2,0,0,2,2,0,0,0,1],
  [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,1],
  [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
  [1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,1],
  [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
  [1,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3,1],
  [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
];

// Позиции столов (тайловые координаты персонажа перед столом)
const DESK_POSITIONS = [
  {tx:2, ty:3},  // desk 0
  {tx:6, ty:3},  // desk 1
  {tx:10,ty:3},  // desk 2
  {tx:14,ty:3},  // desk 3
  {tx:2, ty:8},  // desk 4
  {tx:6, ty:8},  // desk 5
  {tx:10,ty:8},  // desk 6
  {tx:14,ty:8},  // desk 7
];

// ---- Состояние игры ----
const agents = {};        // agent_id -> {role, desk, x, y, tx, ty, bubble, color, status}
const bubbles = [];       // активные речевые пузыри
let logEntries = [];

// ---- Canvas setup ----
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

function resize() {
  const wrap = document.getElementById("game-wrap");
  canvas.width = wrap.clientWidth;
  canvas.height = wrap.clientHeight;
}
window.addEventListener("resize", resize);
resize();

// ---- Draw helpers ----
function drawPixelRect(x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, h);
}

function drawText(text, x, y, size=11, color="#fff", align="left") {
  ctx.font = `${size}px "Courier New", monospace`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.fillText(text, x, y);
}

// ---- Map drawing ----
const TILE_COLORS = {
  0: "#1a1a2a",   // пол
  1: "#2d1b4e",   // стена
  2: "#2a1a3a",   // стол
  3: "#1a2a3a",   // окно
  4: "#1a2a1a",   // растение
};

function drawMap(offsetX, offsetY) {
  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      const tile = MAP[row][col];
      const px = offsetX + col * P;
      const py = offsetY + row * P;

      // Пол
      drawPixelRect(px, py, P, P, TILE_COLORS[tile]);

      // Детали тайлов
      if (tile === 1) {
        // Стена — паттерн кирпичей
        ctx.fillStyle = "#3d2b5e";
        for (let by = 0; by < P; by += 8) {
          const offset = (Math.floor(by/8) % 2) * 16;
          for (let bx = offset; bx < P; bx += 32) {
            ctx.fillRect(px + bx, py + by, 28, 6);
          }
        }
        ctx.fillStyle = "#1a0a2e";
        for (let by = 0; by < P; by += 8) ctx.fillRect(px, py + by, P, 1);
      }

      if (tile === 2) {
        // Стол — деревянная столешница
        ctx.fillStyle = "#3d2200";
        ctx.fillRect(px+2, py+2, P-4, P/2);
        ctx.fillStyle = "#5a3300";
        ctx.fillRect(px+4, py+4, P-8, P/2-4);
        // Монитор
        ctx.fillStyle = "#111";
        ctx.fillRect(px+P/2-6, py+4, 12, 9);
        ctx.fillStyle = "#4fc3f7";
        ctx.fillRect(px+P/2-5, py+5, 10, 7);
        // Ножки
        ctx.fillStyle = "#2a1500";
        ctx.fillRect(px+4, py+P/2+2, 4, P/2-4);
        ctx.fillRect(px+P-8, py+P/2+2, 4, P/2-4);
      }

      if (tile === 3) {
        // Окно
        ctx.fillStyle = "#0a2040";
        ctx.fillRect(px+4, py+4, P-8, P-8);
        ctx.fillStyle = "#1a4060";
        ctx.fillRect(px+6, py+6, P-12, P-12);
        // Рама
        ctx.fillStyle = "#5a4020";
        ctx.fillRect(px+P/2-1, py+4, 2, P-8);
        ctx.fillRect(px+4, py+P/2-1, P-8, 2);
        // Блики
        ctx.fillStyle = "rgba(100,200,255,0.2)";
        ctx.fillRect(px+7, py+7, 8, 5);
      }

      if (tile === 4) {
        // Растение
        ctx.fillStyle = "#1a3a00";
        ctx.fillRect(px+P/2-4, py+P/2, 8, P/2-4);
        ctx.fillStyle = "#2a5a00";
        for (let i = 0; i < 5; i++) {
          const angle = (i / 5) * Math.PI * 2;
          const rx = Math.cos(angle) * 12 + px + P/2;
          const ry = Math.sin(angle) * 8 + py + P/2 - 4;
          ctx.fillRect(rx-4, ry-4, 8, 8);
        }
        ctx.fillStyle = "#3a7a00";
        ctx.fillRect(px+P/2-6, py+P/2-10, 12, 10);
      }
    }
  }

  // Подписи столов
  DESK_POSITIONS.forEach((d, i) => {
    const px = offsetX + d.tx * P + P/2;
    const py = offsetY + (d.ty - 1) * P + P - 6;
    drawText(`#${i}`, px, py, 9, "#555", "center");
  });
}

// ---- Pixel character drawing ----
function drawCharacter(x, y, color, role, status) {
  const S = 4; // размер 1 пикселя в спрайте
  const ox = Math.floor(x) - 8;
  const oy = Math.floor(y) - 20;

  // Тело (туловище)
  ctx.fillStyle = color;
  ctx.fillRect(ox+2*S, oy+4*S, 4*S, 4*S);

  // Голова
  ctx.fillStyle = "#f5c5a3";
  ctx.fillRect(ox+2*S, oy+1*S, 4*S, 3*S);
  // Глаза
  ctx.fillStyle = "#222";
  ctx.fillRect(ox+3*S, oy+2*S, S, S);
  ctx.fillRect(ox+5*S, oy+2*S, S, S);

  // Ноги (анимация ходьбы)
  const legPhase = (Date.now() / 200) % 2 < 1;
  ctx.fillStyle = "#333";
  if (status === "thinking") {
    // стоит на месте
    ctx.fillRect(ox+2*S, oy+8*S, 2*S, 2*S);
    ctx.fillRect(ox+4*S, oy+8*S, 2*S, 2*S);
  } else if (legPhase) {
    ctx.fillRect(ox+2*S, oy+8*S, 2*S, 3*S);
    ctx.fillRect(ox+4*S, oy+8*S+S, 2*S, 2*S);
  } else {
    ctx.fillRect(ox+2*S, oy+8*S+S, 2*S, 2*S);
    ctx.fillRect(ox+4*S, oy+8*S, 2*S, 3*S);
  }

  // Руки
  ctx.fillStyle = color;
  ctx.fillRect(ox+S, oy+4*S, S, 3*S);
  ctx.fillRect(ox+6*S, oy+4*S, S, 3*S);

  // Иконка роли над головой
  ctx.font = "12px serif";
  ctx.textAlign = "center";
  ctx.fillText(ROLE_ICONS[role] || "🤖", ox + 4*S, oy);

  // Статус-индикатор
  if (status === "thinking") {
    ctx.fillStyle = "#ffff00";
    ctx.fillRect(ox + 7*S, oy + S, 2, 2);
    ctx.fillRect(ox + 7*S + 3, oy + S - 1, 2, 2);
    ctx.fillRect(ox + 7*S + 1, oy, 2, 2);
  }
}

// ---- Bubble drawing ----
function drawBubble(text, x, y, alpha) {
  const maxW = 160;
  ctx.font = "10px Courier New";
  const words = text.split(" ");
  const lines = [];
  let line = "";
  for (const w of words) {
    const test = line + (line ? " " : "") + w;
    if (ctx.measureText(test).width > maxW - 10) {
      if (line) lines.push(line);
      line = w;
    } else line = test;
  }
  if (line) lines.push(line);

  const bw = maxW;
  const bh = lines.length * 13 + 10;
  const bx = x - bw / 2;
  const by = y - bh - 30;

  ctx.globalAlpha = alpha;
  ctx.fillStyle = "rgba(10, 10, 20, 0.95)";
  ctx.strokeStyle = "rgba(100, 200, 255, 0.6)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(bx, by, bw, bh, 4);
  ctx.fill();
  ctx.stroke();

  // Хвостик пузыря
  ctx.fillStyle = "rgba(10, 10, 20, 0.95)";
  ctx.beginPath();
  ctx.moveTo(x - 5, by + bh);
  ctx.lineTo(x + 5, by + bh);
  ctx.lineTo(x, by + bh + 6);
  ctx.fill();

  ctx.fillStyle = "#e0e0e0";
  ctx.font = "10px Courier New";
  ctx.textAlign = "left";
  lines.forEach((l, i) => ctx.fillText(l, bx + 5, by + 14 + i * 13));
  ctx.globalAlpha = 1;
}

// ---- Layout ----
function getMapOffset() {
  const wrap = document.getElementById("game-wrap");
  const mapW = COLS * P;
  const mapH = ROWS * P;
  const ox = Math.max(0, (wrap.clientWidth - mapW) / 2);
  const oy = Math.max(0, (wrap.clientHeight - mapH) / 2);
  return {ox, oy};
}

// ---- SSE ----
function connectSSE() {
  const statusBar = document.getElementById("status-bar");
  const es = new EventSource("/events");

  es.onopen = () => {
    statusBar.textContent = "● онлайн";
    statusBar.style.color = "#4fc3f7";
  };

  es.onerror = () => {
    statusBar.textContent = "● подключение...";
    statusBar.style.color = "#f06292";
  };

  es.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleEvent(event);
  };
}

function handleEvent(event) {
  if (event.type === "hired") {
    spawnAgent(event.agent_id, event.role, event.desk, event.task || "");
    addLog(event.agent_id, `принят на работу как ${event.role}`, event.role);
  }
  else if (event.type === "speech") {
    addBubble(event.agent_id, event.text);
    addLog(event.agent_id, event.text, getRole(event.agent_id));
    updateAgentStatus(event.agent_id, "thinking", event.text);
  }
  else if (event.type === "thinking") {
    addBubble(event.agent_id, event.text);
    updateAgentStatus(event.agent_id, "thinking", event.text);
  }
  else if (event.type === "task_done") {
    addLog(event.agent_id, "✓ " + (event.summary||"задача выполнена").slice(0,100), getRole(event.agent_id));
    updateAgentStatus(event.agent_id, "done", (event.summary||"").slice(0,80));
    loadDeliverables();  // обновляем счётчик и рендерим результаты
  }
  else if (event.type === "progress") {
    updateProgressBar(event);
  }
  else if (event.type === "system") {
    addLog("офис", event.text, "system");
  }
  else if (event.type === "error") {
    addLog(event.agent_id, "⚠ " + event.text, getRole(event.agent_id));
  }
  else if (event.type === "question") {
    addQuestionCard(event);
    switchView("questions");
  }
  else if (event.type === "question_answered") {
    removeQuestionCard(event.question_id);
  }
}

async function loadQuestions() {
  try {
    const r = await fetch("/api/questions");
    const d = await r.json();
    const qs = d.questions || [];
    const badge = document.getElementById("badge-questions");
    badge.textContent = qs.length || "";

    // Add only new cards — don't wipe existing ones (preserves typed text)
    for (const q of qs) addQuestionCard(q, false);

    // Remove cards that are no longer pending
    const wrap = document.getElementById("questions-wrap");
    const activeIds = new Set(qs.map(q => q.question_id));
    wrap.querySelectorAll(".q-card").forEach(card => {
      const qid = card.id.replace("qcard-", "");
      if (!activeIds.has(qid)) card.remove();
    });

    if (!wrap.querySelectorAll(".q-card").length) {
      if (!document.getElementById("no-questions")) {
        const note = document.createElement("div");
        note.className = "empty-note"; note.id = "no-questions";
        note.textContent = "Нет ожидающих вопросов";
        wrap.appendChild(note);
      }
    }
  } catch (e) { console.error("loadQuestions:", e); }
}

function addQuestionCard(event, updateBadge = true) {
  const wrap = document.getElementById("questions-wrap");
  const noQ = document.getElementById("no-questions");
  if (noQ) noQ.remove();

  if (document.getElementById("qcard-" + event.question_id)) return;

  const role = event.agent_id ? getRole(event.agent_id) : "агент";
  const card = document.createElement("div");
  card.className = "q-card";
  card.id = "qcard-" + event.question_id;
  card.innerHTML = `
    <div class="qc-head">
      <span class="qc-role">${ROLE_ICONS[role] || "❓"} ${role}</span>
      <span class="qc-id">${event.agent_id || ""}</span>
    </div>
    <div class="qc-text">${event.text}</div>
    <textarea rows="3" placeholder="Введите ответ... (Ctrl+Enter для отправки)"></textarea>
    <div class="qc-actions">
      <button class="q-skip-btn">Пропустить</button>
      <button class="q-submit-btn">Отправить ответ</button>
    </div>
  `;
  wrap.prepend(card);

  const ta = card.querySelector("textarea");
  ta.focus();

  async function submit() {
    const answer = ta.value.trim();
    if (!answer) return;
    try {
      await fetch("/api/answer", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question_id: event.question_id, answer}),
      });
      removeQuestionCard(event.question_id);
    } catch (err) { console.error("Failed to send answer:", err); }
  }

  card.querySelector(".q-submit-btn").addEventListener("click", submit);
  card.querySelector(".q-skip-btn").addEventListener("click", () => {
    fetch("/api/answer", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question_id: event.question_id, answer: ""}),
    }).catch(() => {});
    removeQuestionCard(event.question_id);
  });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.ctrlKey) submit(); });

  if (updateBadge) {
    const badge = document.getElementById("badge-questions");
    const cur = parseInt(badge.textContent || "0");
    badge.textContent = cur + 1;
  }
}

function removeQuestionCard(qid) {
  const card = document.getElementById("qcard-" + qid);
  if (card) card.remove();
  const wrap = document.getElementById("questions-wrap");
  const remaining = wrap.querySelectorAll(".q-card").length;
  const badge = document.getElementById("badge-questions");
  badge.textContent = remaining || "";
  if (!remaining) {
    const note = document.createElement("div");
    note.className = "empty-note";
    note.id = "no-questions";
    note.textContent = "Нет ожидающих вопросов";
    wrap.appendChild(note);
  }
}

function getRole(agent_id) {
  return agents[agent_id]?.role || "unknown";
}

function spawnAgent(agent_id, role, desk, task) {
  if (agents[agent_id]) return;
  const dp = DESK_POSITIONS[desk] || DESK_POSITIONS[0];
  const {ox, oy} = getMapOffset();
  const startX = ox + COLS/2 * P;
  const startY = oy + ROWS/2 * P;
  const targetX = ox + dp.tx * P + P/2;
  const targetY = oy + dp.ty * P + P/2;

  agents[agent_id] = {
    role, desk, task,
    x: startX, y: startY,
    tx: targetX, ty: targetY,
    color: ROLE_COLORS[role] || "#aaaaaa",
    status: "idle",
    bubble: null,
  };

  updateSidebar();
}

function addBubble(agent_id, text) {
  const agent = agents[agent_id];
  if (!agent) return;
  // Удаляем старый пузырь этого агента
  const idx = bubbles.findIndex(b => b.agent_id === agent_id);
  if (idx >= 0) bubbles.splice(idx, 1);

  bubbles.push({
    agent_id,
    text: text.slice(0, 100),
    born: Date.now(),
    duration: 5000,
  });
}

function updateAgentStatus(agent_id, status, message) {
  if (agents[agent_id]) {
    agents[agent_id].status = status;
    agents[agent_id].lastMsg = message;
    updateSidebar();
  }
}

function addLog(who, text, role) {
  const color = ROLE_COLORS[role] || "#556";
  const time = new Date().toLocaleTimeString("ru", {hour:"2-digit",minute:"2-digit"});
  const logWrap = document.getElementById("log-wrap");
  const div = document.createElement("div");
  div.className = "log-entry";
  div.innerHTML = `<span class="lt">${time}</span><span class="lw" style="color:${color}">${who}</span>: ${escapeHtml(text.slice(0,160))}`;
  logWrap.prepend(div);
  if (logWrap.children.length > 150) logWrap.removeChild(logWrap.lastChild);
}

function updateSidebar() {
  const list = document.getElementById("agents-grid");
  const noEl = document.getElementById("no-agents");
  const keys = Object.keys(agents);
  if (noEl) noEl.style.display = keys.length ? "none" : "block";
  // Update or create cards
  for (const [id, a] of Object.entries(agents)) {
    let card = list.querySelector(`[data-agent="${id}"]`);
    if (!card) {
      card = document.createElement("div");
      card.className = "agent-card";
      card.dataset.agent = id;
      card.style.borderLeftColor = a.color;
      card.addEventListener("click", () => openAgentDrawer(id));
      list.appendChild(card);
    }
    const dotClass = a.status === "thinking" ? "thinking" : a.status === "done" ? "done" : "idle";
    const dotIcon = a.status === "thinking" ? "⟳" : a.status === "done" ? "✓" : "○";
    card.innerHTML = `
      <div class="ac-name">
        <span class="status-dot ${dotClass}">${dotIcon}</span>
        <span style="color:${a.color}">${ROLE_ICONS[a.role]||""} ${a.role}</span>
      </div>
      <div class="ac-status">${escapeHtml((a.lastMsg || a.task || id).slice(0,120))}</div>
    `;
  }
  // Nav badge: number of agents
  const badge = document.getElementById("badge-team");
  if (badge) {
    badge.textContent = keys.length ? String(keys.length) : "";
    badge.style.display = keys.length ? "block" : "none";
  }
}

// ============================================================
// AGENT DETAIL DRAWER
// ============================================================
let drawerAgentId = null;

async function openAgentDrawer(agentId) {
  drawerAgentId = agentId;
  const a = agents[agentId];
  const drawer = document.getElementById("agent-drawer");
  const roleEl = document.getElementById("ad-role");
  const curEl = document.getElementById("ad-current");
  const delivWrap = document.getElementById("ad-deliverables");

  const localColor = (a && a.color) || "#4fc3f7";
  const localRole = (a && a.role) || roleFromId(agentId);
  roleEl.textContent = `${ROLE_ICONS[localRole] || "🤖"} ${localRole}`;
  roleEl.style.color = localColor;
  curEl.textContent = "Загрузка...";
  delivWrap.innerHTML = "";
  drawer.classList.add("open");

  let data = null;
  try {
    const r = await fetch(`/api/agent/${encodeURIComponent(agentId)}`);
    data = await r.json();
  } catch {}

  const status = (data && (data.status || (a && a.status))) || "idle";
  const current = (data && (data.current || data.task)) || (a && (a.lastMsg || a.task)) || "—";
  const statusWord = status === "thinking" ? "⟳ работает" : status === "done" ? "✓ готово" : "○ ожидает";
  curEl.innerHTML = `<b style="color:${localColor}">${escapeHtml(statusWord)}</b><br>Сейчас делает: ${escapeHtml(current)}`;

  const done = (data && data.done) || [];
  if (!done.length) {
    delivWrap.innerHTML = `<div style="color:#556;font-size:12px;padding:8px 0;">Пока ничего не сдал.</div>`;
  } else {
    done.forEach((d) => {
      const div = document.createElement("div");
      div.className = "ad-deliv";
      div.innerHTML = `
        <div class="add-task">${escapeHtml((d.task||"задача").slice(0,90))}</div>
        <div class="add-time">${escapeHtml(d.time||"")}</div>
        <div class="add-preview">${escapeHtml((d.content||"").slice(0,260))}</div>
        <div class="add-actions">
          <button class="dc-btn ad-open">↗ открыть полностью</button>
          <button class="dc-btn ad-copy">⧉ Копировать</button>
        </div>
      `;
      div.querySelector(".ad-open").addEventListener("click", () =>
        openFullTextRaw(localRole, d.task||"", d.time||"", d.content||"", localColor));
      div.querySelector(".ad-copy").addEventListener("click", async (e) => {
        try { await navigator.clipboard.writeText(d.content||""); e.target.textContent="✓ Скопировано"; setTimeout(()=>e.target.textContent="⧉ Копировать",1500); } catch {}
      });
      delivWrap.appendChild(div);
    });
  }
}

function closeAgentDrawer() {
  document.getElementById("agent-drawer").classList.remove("open");
  drawerAgentId = null;
}

// ---- Game loop ----
function update() {
  const speed = 1.5;
  for (const a of Object.values(agents)) {
    const dx = a.tx - a.x;
    const dy = a.ty - a.y;
    const dist = Math.sqrt(dx*dx + dy*dy);
    if (dist > 2) {
      a.x += (dx / dist) * speed;
      a.y += (dy / dist) * speed;
    }
  }
}

function render() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Фон
  ctx.fillStyle = "#0a0a0f";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const {ox, oy} = getMapOffset();

  // Карта
  drawMap(ox, oy);

  // Агенты
  const now = Date.now();
  for (const [id, a] of Object.entries(agents)) {
    // Подсветка выбранного агента
    if (id === selectedAgentId) {
      ctx.beginPath();
      ctx.arc(a.x, a.y - 8, 22, 0, Math.PI * 2);
      ctx.strokeStyle = a.color;
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.5 + 0.3 * Math.sin(now / 300);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    drawCharacter(a.x, a.y, a.color, a.role, a.status);
  }

  // Пузыри
  for (let i = bubbles.length - 1; i >= 0; i--) {
    const b = bubbles[i];
    const age = now - b.born;
    if (age > b.duration) { bubbles.splice(i, 1); continue; }
    const agent = agents[b.agent_id];
    if (!agent) { bubbles.splice(i, 1); continue; }
    const alpha = age < b.duration - 800 ? 1 : (b.duration - age) / 800;
    drawBubble(b.text, agent.x, agent.y, alpha);
  }

  // Заголовок
  ctx.font = "bold 11px Courier New";
  ctx.fillStyle = "#222";
  ctx.textAlign = "left";
  ctx.fillText("AI OFFICE — автономный бизнес-офис", ox + 4, oy + 14);

  // Время
  ctx.textAlign = "right";
  ctx.fillStyle = "#333";
  ctx.fillText(new Date().toLocaleString("ru"), ox + COLS*P - 4, oy + 14);
}

function gameLoop() {
  update();
  render();
  requestAnimationFrame(gameLoop);
}

// ============================================================
// ИНТЕРАКТИВ: клик по агенту → чат
// ============================================================
let selectedAgentId = null;

function findAgentAt(px, py) {
  let best = null, bestDist = 30; // радиус клика
  for (const [id, a] of Object.entries(agents)) {
    const dx = a.x - px;
    const dy = (a.y - 8) - py;
    const d = Math.sqrt(dx*dx + dy*dy);
    if (d < bestDist) { bestDist = d; best = id; }
  }
  return best;
}

function setupClickHandler() {
  canvas.addEventListener("click", (e) => {
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const id = findAgentAt(px, py);
    if (id) openChat(id);
  });
}

// ---- Чат-окно ----
const chatWindow = document.getElementById("chat-window");
const chatTitle = document.getElementById("chat-title");
const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");
const chatClose = document.getElementById("chat-close");

// Истории чатов на клиенте: agent_id -> [{role, text}]
const chatHistories = {};

function openChat(agentId) {
  selectedAgentId = agentId;
  const a = agents[agentId];
  if (!a) return;

  chatTitle.textContent = `${ROLE_ICONS[a.role] || "🤖"} ${a.role}`;
  chatTitle.style.color = a.color;
  chatWindow.classList.remove("hidden");

  // Восстанавливаем историю
  renderChatHistory(agentId);
  chatInput.focus();

  // Прячем подсказку
  const hint = document.getElementById("hint");
  if (hint) hint.style.opacity = "0";
}

function closeChat() {
  chatWindow.classList.add("hidden");
  selectedAgentId = null;
}

function renderChatHistory(agentId) {
  chatMessages.innerHTML = "";
  const hist = chatHistories[agentId] || [];
  if (hist.length === 0) {
    const a = agents[agentId];
    addChatMessage("agent", `Привет! Я ${a.role}. ${a.task ? "Сейчас работаю над: " + a.task : ""} Чем помочь?`, false);
  } else {
    for (const m of hist) addChatMessage(m.role, m.text, false);
  }
}

function addChatMessage(role, text, save = true) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  if (save && selectedAgentId) {
    (chatHistories[selectedAgentId] = chatHistories[selectedAgentId] || []).push({role, text});
  }
  return div;
}

async function sendChat() {
  const message = chatInput.value.trim();
  if (!message || !selectedAgentId) return;
  const agentId = selectedAgentId;

  addChatMessage("user", message);
  chatInput.value = "";
  chatSend.disabled = true;

  // Индикатор "печатает"
  const typing = document.createElement("div");
  typing.className = "msg typing";
  typing.textContent = "печатает...";
  chatMessages.appendChild(typing);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({agent_id: agentId, message}),
    });
    const data = await resp.json();
    typing.remove();
    if (data.error) {
      addChatMessage("agent", "⚠ Ошибка: " + data.error, false);
    } else {
      addChatMessage("agent", data.reply);
    }
  } catch (err) {
    typing.remove();
    addChatMessage("agent", "⚠ Не удалось связаться с агентом: " + err.message, false);
  } finally {
    chatSend.disabled = false;
    chatInput.focus();
  }
}

chatSend.addEventListener("click", sendChat);
chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
chatClose.addEventListener("click", closeChat);

// ============================================================
// ОНБОРДИНГ: клиент описывает задачу → офис запускается под него
// ============================================================
const intake = document.getElementById("intake");
const intakeStep1 = document.getElementById("intake-step1");
const intakeStep2 = document.getElementById("intake-step2");
const intakeLoading = document.getElementById("intake-loading");
const intakeLoadingText = document.getElementById("intake-loading-text");
const intakeInput = document.getElementById("intake-input");
const intakeNext = document.getElementById("intake-next");
const intakeStart = document.getElementById("intake-start");
const intakeQuestions = document.getElementById("intake-questions");

let intakeClientInput = "";
let intakeQuestionList = [];

async function checkBriefStatus() {
  try {
    const r = await fetch("/api/brief/status");
    const d = await r.json();
    // Если демо или бриф уже есть — пропускаем онбординг
    if (d.demo || d.ready) {
      intake.classList.add("hidden");
      showMission(d.brief);  // показываем задачу офиса — никаких пустот
    } else {
      intake.classList.remove("hidden");
    }
  } catch {
    intake.classList.remove("hidden");
  }
}

function showIntakeLoading(text) {
  intakeStep1.classList.add("hidden");
  intakeStep2.classList.add("hidden");
  intakeLoading.classList.remove("hidden");
  intakeLoadingText.textContent = text;
}

async function intakeGetQuestions() {
  intakeClientInput = intakeInput.value.trim();
  if (!intakeClientInput) { intakeInput.focus(); return; }

  showIntakeLoading("Изучаю ваш запрос, готовлю вопросы...");
  try {
    const r = await fetch("/api/brief/questions", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({input: intakeClientInput}),
    });
    const d = await r.json();
    intakeQuestionList = d.questions || [];
    renderIntakeQuestions();
    intakeLoading.classList.add("hidden");
    intakeStep2.classList.remove("hidden");
  } catch (e) {
    intakeLoading.classList.add("hidden");
    intakeStep1.classList.remove("hidden");
    alert("Ошибка: " + e.message);
  }
}

function renderIntakeQuestions() {
  intakeQuestions.innerHTML = "";
  intakeQuestionList.forEach((q, i) => {
    const div = document.createElement("div");
    div.className = "intake-q";
    div.innerHTML = `<label>${q}</label><input type="text" data-i="${i}" autocomplete="off">`;
    intakeQuestions.appendChild(div);
  });
}

async function intakeStartOffice() {
  const answers = intakeQuestionList.map((q, i) => {
    const inp = intakeQuestions.querySelector(`input[data-i="${i}"]`);
    return {q, a: inp ? inp.value.trim() : ""};
  });

  showIntakeLoading("Формирую бриф и запускаю офис... Это займёт минуту.");
  try {
    const r = await fetch("/api/brief/start", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({input: intakeClientInput, answers}),
    });
    const d = await r.json();
    if (d.ok) {
      intake.classList.add("hidden");  // офис стартовал, события пойдут по SSE
    } else {
      throw new Error(d.error || "неизвестная ошибка");
    }
  } catch (e) {
    intakeLoading.classList.add("hidden");
    intakeStep2.classList.remove("hidden");
    alert("Ошибка запуска: " + e.message);
  }
}

intakeNext.addEventListener("click", intakeGetQuestions);
intakeStart.addEventListener("click", intakeStartOffice);

function escapeHtml(s) {
  return (s || "").replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
}

// ---- Views ----
function switchView(name) {
  document.querySelectorAll(".nav-item").forEach(t => t.classList.toggle("active", t.dataset.view === name));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + name));
  if (name === "office") {
    resize();
    const {ox, oy} = getMapOffset();
    for (const a of Object.values(agents)) {
      const dp = DESK_POSITIONS[a.desk] || DESK_POSITIONS[0];
      a.tx = ox + dp.tx * P + P/2;
      a.ty = oy + dp.ty * P + P/2;
    }
  }
  if (name === "questions") {
    loadQuestions();
  }
}

// ============================================================
// PROGRESS BAR (top stepper)
// ============================================================
const DEFAULT_STAGES = ["Бриф","Исследование","Стратегия","Команда","Развитие","Результаты","Масштаб"];
let progressStages = DEFAULT_STAGES.slice();

function buildProgressSteps(stages) {
  progressStages = (stages && stages.length) ? stages : progressStages;
  const cont = document.getElementById("progress-steps");
  // remove existing steps (keep track + fill)
  cont.querySelectorAll(".pstep").forEach(e => e.remove());
  progressStages.forEach((label) => {
    const div = document.createElement("div");
    div.className = "pstep";
    div.innerHTML = `<div class="pdot">●</div><div class="plabel">${escapeHtml(label)}</div>`;
    cont.appendChild(div);
  });
}

function updateProgressBar(p) {
  if (p.stages && p.stages.length) buildProgressSteps(p.stages);
  const steps = document.querySelectorAll(".pstep");
  const stage = typeof p.stage === "number" ? p.stage : 0;
  steps.forEach((el, i) => {
    el.classList.toggle("done", i < stage);
    el.classList.toggle("current", i === stage);
  });
  const fill = document.getElementById("progress-fill");
  const pct = typeof p.percent === "number" ? p.percent : (progressStages.length>1 ? (stage/(progressStages.length-1))*100 : 0);
  // track spans 9%..91% (82% wide)
  fill.style.width = (Math.max(0, Math.min(100, pct)) * 0.82) + "%";
  const note = document.getElementById("progress-note");
  if (note) note.textContent = p.note || (p.label ? "Этап: " + p.label : "");
}

async function loadProgress() {
  try {
    const r = await fetch("/api/progress");
    const d = await r.json();
    updateProgressBar(d);
  } catch {}
}

// ============================================================
// CONNECTIONS
// ============================================================
let connectionsCache = [];

async function loadConnections() {
  try {
    const r = await fetch("/api/connections");
    const d = await r.json();
    connectionsCache = d.connections || [];
  } catch { connectionsCache = []; }
  renderConnections();
}

function renderConnections() {
  const list = document.getElementById("conn-list");
  const noEl = document.getElementById("no-conns");
  list.querySelectorAll(".conn-card").forEach(c => c.remove());
  if (noEl) noEl.style.display = connectionsCache.length ? "none" : "block";
  connectionsCache.forEach((c) => {
    const card = document.createElement("div");
    card.className = "conn-card";
    const fields = c.fields || {};
    const fieldsHtml = Object.entries(fields).map(([k,v]) =>
      `<div><span class="cf-k">${escapeHtml(k)}:</span> <span class="cf-v">${escapeHtml(String(v))}</span></div>`
    ).join("") || `<div style="color:#556">нет полей</div>`;
    card.innerHTML = `
      <div class="cc-head">
        <span class="cc-name">${escapeHtml(c.name||"Без названия")}</span>
        <span class="cc-badge">${escapeHtml(connTypeLabel(c.type))}</span>
      </div>
      <div class="cc-fields">${fieldsHtml}</div>
      ${c.note ? `<div class="cc-note">${escapeHtml(c.note)}</div>` : ""}
      <div class="cc-actions">
        <button class="dc-btn conn-edit">✎ Изменить</button>
        <button class="dc-btn conn-del">🗑 Удалить</button>
      </div>
    `;
    card.querySelector(".conn-edit").addEventListener("click", () => openConnForm(c));
    card.querySelector(".conn-del").addEventListener("click", () => deleteConnection(c.id));
    list.appendChild(card);
  });
}

function connTypeLabel(t) {
  return ({api:"API ключ", login:"Логин-пароль", token:"Токен", other:"Другое"})[t] || (t || "Другое");
}

function addFieldRow(k, v) {
  const wrap = document.getElementById("cf-fields");
  const row = document.createElement("div");
  row.className = "cf-kv";
  row.innerHTML = `
    <input type="text" class="cf-k-in" placeholder="ключ" value="${escapeAttr(k||"")}">
    <input type="text" class="cf-v-in" placeholder="значение" value="${escapeAttr(v||"")}">
    <button class="cf-kv-del" type="button">✕</button>
  `;
  row.querySelector(".cf-kv-del").addEventListener("click", () => row.remove());
  wrap.appendChild(row);
}

function escapeAttr(s) { return (s||"").replace(/"/g,"&quot;").replace(/</g,"&lt;"); }

function openConnForm(conn) {
  document.getElementById("conn-box-title").textContent = conn ? "Изменить подключение" : "Новое подключение";
  document.getElementById("cf-id").value = conn ? (conn.id||"") : "";
  document.getElementById("cf-name").value = conn ? (conn.name||"") : "";
  document.getElementById("cf-type").value = conn ? (conn.type||"api") : "api";
  document.getElementById("cf-note").value = conn ? (conn.note||"") : "";
  const fieldsWrap = document.getElementById("cf-fields");
  fieldsWrap.innerHTML = "";
  const fields = (conn && conn.fields) || {};
  const entries = Object.entries(fields);
  if (entries.length) entries.forEach(([k,v]) => addFieldRow(k, v));
  else addFieldRow("", "");
  document.getElementById("conn-overlay").classList.remove("hidden");
}

function closeConnForm() {
  document.getElementById("conn-overlay").classList.add("hidden");
}

async function saveConnection() {
  const id = document.getElementById("cf-id").value.trim();
  const name = document.getElementById("cf-name").value.trim();
  const type = document.getElementById("cf-type").value;
  const note = document.getElementById("cf-note").value.trim();
  const fields = {};
  document.querySelectorAll("#cf-fields .cf-kv").forEach(row => {
    const k = row.querySelector(".cf-k-in").value.trim();
    const v = row.querySelector(".cf-v-in").value.trim();
    if (k) fields[k] = v;
  });
  if (!name) { alert("Укажите название"); return; }
  const body = {name, type, fields, note};
  if (id) body.id = id;
  try {
    await fetch("/api/connections", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    closeConnForm();
    loadConnections();
  } catch (e) { alert("Ошибка сохранения: " + e.message); }
}

async function deleteConnection(id) {
  if (!id) return;
  if (!confirm("Удалить это подключение?")) return;
  try {
    await fetch(`/api/connections/${encodeURIComponent(id)}`, {method: "DELETE"});
    loadConnections();
  } catch (e) { alert("Ошибка: " + e.message); }
}

function setupConnections() {
  document.getElementById("btn-add-conn").addEventListener("click", () => openConnForm(null));
  document.getElementById("cf-add-field").addEventListener("click", () => addFieldRow("", ""));
  document.getElementById("conn-box-save").addEventListener("click", saveConnection);
  document.getElementById("conn-box-close").addEventListener("click", closeConnForm);
  document.getElementById("conn-box-cancel").addEventListener("click", closeConnForm);
  document.getElementById("conn-overlay").addEventListener("click", (e) => {
    if (e.target.id === "conn-overlay") closeConnForm();
  });
}

// ---- Результаты (deliverables) ----
let deliverablesCache = [];
let ftCurrentIdx = -1;

async function loadDeliverables() {
  try {
    const r = await fetch("/api/deliverables");
    const d = await r.json();
    deliverablesCache = d.deliverables || [];
    const badge = document.getElementById("badge-results");
    if (badge) {
      badge.textContent = deliverablesCache.length ? String(deliverablesCache.length) : "";
      badge.style.display = deliverablesCache.length ? "block" : "none";
    }
    renderResultsPane();
  } catch {}
}

function renderResultsPane() {
  const wrap = document.getElementById("results-wrap");
  const noEl = document.getElementById("no-results");
  if (!deliverablesCache.length) {
    if (noEl) noEl.style.display = "block";
    return;
  }
  if (noEl) noEl.style.display = "none";
  // Remove old cards, keep #no-results
  wrap.querySelectorAll(".deliv-card").forEach(c => c.remove());
  deliverablesCache.forEach((d, i) => {
    const color = ROLE_COLORS[d.role] || "#888";
    const card = document.createElement("div");
    card.className = "deliv-card";
    card.innerHTML = `
      <div class="dc-head">
        <span class="dc-who" style="color:${color}">${ROLE_ICONS[d.role]||""} ${escapeHtml(d.role)}</span>
        <span class="dc-time">${d.time||""}</span>
      </div>
      <div class="dc-task">${escapeHtml((d.task||"").slice(0,80))}</div>
      <div class="dc-preview">${escapeHtml((d.content||"").slice(0,200))}</div>
      <div class="dc-actions">
        <button class="dc-btn expand-btn" data-i="${i}">↗ Открыть полностью</button>
        <button class="dc-btn copy-btn" data-i="${i}">⧉ Копировать</button>
      </div>
    `;
    wrap.appendChild(card);
  });
  wrap.querySelectorAll(".expand-btn").forEach(btn => {
    btn.addEventListener("click", () => openFullText(+btn.dataset.i));
  });
  wrap.querySelectorAll(".copy-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const d = deliverablesCache[+btn.dataset.i];
      try { await navigator.clipboard.writeText(d.content||""); btn.textContent="✓ Скопировано"; setTimeout(()=>btn.textContent="⧉ Копировать",1500); }
      catch { btn.textContent="ошибка"; }
    });
  });
}

function openFullText(i) {
  ftCurrentIdx = i;
  const d = deliverablesCache[i];
  if (!d) return;
  ftRawContent = d.content || "";
  const color = ROLE_COLORS[d.role] || "#888";
  document.getElementById("ft-who").innerHTML = `<span style="color:${color}">${ROLE_ICONS[d.role]||""} ${escapeHtml(d.role)}</span> — ${escapeHtml(d.task||"")} <span style="color:#444;font-size:10px">${d.time||""}</span>`;
  document.getElementById("fulltext-body").textContent = d.content || "";
  document.getElementById("fulltext-overlay").classList.remove("hidden");
}

// Open fulltext modal for arbitrary content (used by agent drawer)
function openFullTextRaw(role, task, time, content, color) {
  ftCurrentIdx = -1;
  ftRawContent = content || "";
  color = color || ROLE_COLORS[role] || "#888";
  document.getElementById("ft-who").innerHTML = `<span style="color:${color}">${ROLE_ICONS[role]||""} ${escapeHtml(role)}</span> — ${escapeHtml(task||"")} <span style="color:#444;font-size:10px">${time||""}</span>`;
  document.getElementById("fulltext-body").textContent = content || "";
  document.getElementById("fulltext-overlay").classList.remove("hidden");
}
let ftRawContent = "";

function exportDeliverables() {
  if (!deliverablesCache.length) return;
  const md = deliverablesCache.map(d =>
    `# ${d.role} — ${d.task||""} (${d.time||""})\n\n${d.content||""}\n`
  ).join("\n---\n\n");
  downloadText(md, "ai-office-results.md");
}

function downloadText(text, filename) {
  const blob = new Blob([text], {type:"text/markdown;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

async function resetOffice() {
  if (!confirm("Сбросить офис и начать с нового клиента?\nВся история будет удалена.")) return;
  await fetch("/api/brief/reset", {method: "POST"}).catch(()=>{});
  location.reload();
}

function roleFromId(id) { return (id || "").replace(/_\d+$/, ""); }

function logOnly(event) {
  const role = roleFromId(event.agent_id);
  if (event.type === "hired") addLog(event.agent_id, `принят как ${event.role}`, event.role);
  else if (event.type === "speech") addLog(event.agent_id, event.text, role);
  else if (event.type === "task_done") addLog(event.agent_id, "✓ " + (event.summary||"задача выполнена"), role);
  else if (event.type === "system") addLog("офис", event.text, "system");
  else if (event.type === "error") addLog(event.agent_id, "⚠ " + event.text, role);
}

async function replayHistory() {
  try {
    const r = await fetch("/api/history");
    const d = await r.json();
    const events = d.events || [];
    if (!events.length) return;
    for (const ev of events) logOnly(ev);
    addLog("офис", `↺ История восстановлена (${events.length} событий)`, "system");
  } catch {}
}

function showMission(brief) {
  const m = document.getElementById("team-mission");
  if (!m || !brief) return;
  const text = brief.goal || brief.summary || "";
  m.textContent = text ? "🎯 " + text : "";
}

// ---- Init ----
window.addEventListener("load", () => {
  resize();
  connectSSE();
  setupClickHandler();
  checkBriefStatus();
  replayHistory();
  loadDeliverables();
  gameLoop();

  // Reset
  document.getElementById("btn-reset").addEventListener("click", resetOffice);

  // Export all
  document.getElementById("btn-export-all").addEventListener("click", exportDeliverables);

  // Full-text modal
  document.getElementById("ft-close").addEventListener("click", () =>
    document.getElementById("fulltext-overlay").classList.add("hidden"));
  document.getElementById("fulltext-overlay").addEventListener("click", (e) => {
    if (e.target.id === "fulltext-overlay") e.target.classList.add("hidden");
  });
  document.getElementById("ft-copy").addEventListener("click", async () => {
    const content = ftCurrentIdx >= 0 ? (deliverablesCache[ftCurrentIdx]||{}).content : ftRawContent;
    try { await navigator.clipboard.writeText(content||""); document.getElementById("ft-copy").textContent="✓ Скопировано"; setTimeout(()=>document.getElementById("ft-copy").textContent="⧉ Копировать",1500); }
    catch {}
  });
  document.getElementById("ft-export").addEventListener("click", () => {
    if (ftCurrentIdx >= 0) {
      const d = deliverablesCache[ftCurrentIdx];
      if (d) downloadText(d.content||"", `${d.role}-${(d.task||"result").slice(0,30)}.md`);
    } else if (ftRawContent) {
      downloadText(ftRawContent, "result.md");
    }
  });

  // Nav switching
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => switchView(item.dataset.view));
  });

  // Agent drawer
  document.getElementById("ad-close").addEventListener("click", closeAgentDrawer);
  document.getElementById("ad-chat-btn").addEventListener("click", () => {
    if (drawerAgentId) { openChat(drawerAgentId); closeAgentDrawer(); switchView("office"); }
  });

  // Progress bar
  buildProgressSteps();
  loadProgress();

  // Connections
  setupConnections();
  loadConnections();

  // Questions
  loadQuestions();

  // Model switcher
  setupModelSwitcher();
});

// ============================================================
// MODEL SWITCHER
// ============================================================
async function setupModelSwitcher() {
  try {
    const r = await fetch("/api/model");
    const d = await r.json();
    document.getElementById("model-input").value = d.model || "";
  } catch (e) {}

  async function saveModel() {
    const model = (document.getElementById("model-input").value || "").trim();
    if (!model) return;
    try {
      const r = await fetch("/api/model", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({model}),
      });
      const d = await r.json();
      if (d.ok) {
        const btn = document.getElementById("model-save");
        btn.textContent = "✓";
        btn.style.color = "#4fc3f7";
        setTimeout(() => { btn.textContent = "✓"; btn.style.color = "#4a8"; }, 1500);
      }
    } catch (e) { console.error("model save:", e); }
  }

  document.getElementById("model-save").addEventListener("click", saveModel);
  document.getElementById("model-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveModel();
  });
}

window.addEventListener("resize", () => {
  resize();
  // Обновляем целевые позиции агентов при ресайзе
  const {ox, oy} = getMapOffset();
  for (const [id, a] of Object.entries(agents)) {
    const dp = DESK_POSITIONS[a.desk] || DESK_POSITIONS[0];
    a.tx = ox + dp.tx * P + P/2;
    a.ty = oy + dp.ty * P + P/2;
  }
});
