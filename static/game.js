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
    statusBar.textContent = "● подключено";
    statusBar.style.color = "#4fc3f7";
  };

  es.onerror = () => {
    statusBar.textContent = "● переподключение...";
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
    // Мигаем вкладкой Results чтобы привлечь внимание
    const badge = document.getElementById("results-badge");
    if (badge) { badge.style.background="#f06292"; setTimeout(()=>badge.style.background="",2000); }
  }
  else if (event.type === "system") {
    addLog("офис", event.text, "system");
  }
  else if (event.type === "error") {
    addLog(event.agent_id, "⚠ " + event.text, getRole(event.agent_id));
  }
  else if (event.type === "question") {
    showQuestionModal(event);
  }
}

function showQuestionModal(event) {
  // Remove any existing modal
  const existing = document.getElementById("question-modal");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = "question-modal";
  overlay.style.cssText = `
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.75); z-index: 9999;
    display: flex; align-items: center; justify-content: center;
  `;

  const role = getRole(event.agent_id);
  const color = (agents[event.agent_id] && agents[event.agent_id].color) || "#4fc3f7";

  const box = document.createElement("div");
  box.style.cssText = `
    background: #0f0f1a; border: 1px solid ${color}; border-radius: 8px;
    padding: 24px; max-width: 480px; width: 90%; font-family: 'Courier New', monospace;
    color: #e0e0e0;
  `;

  box.innerHTML = `
    <div style="color:${color}; font-weight:bold; margin-bottom:12px; font-size:13px;">
      Вопрос от агента ${role} (${event.agent_id})
    </div>
    <div style="margin-bottom:16px; font-size:13px; line-height:1.5;">${event.text}</div>
    <textarea id="q-answer" rows="3" style="
      width:100%; box-sizing:border-box; background:#1a1a2a; color:#e0e0e0;
      border:1px solid #333; border-radius:4px; padding:8px; font-family:inherit;
      font-size:12px; resize:vertical; margin-bottom:12px;
    " placeholder="Введите ответ..."></textarea>
    <div style="display:flex; gap:8px; justify-content:flex-end;">
      <button id="q-cancel" style="
        background:transparent; color:#888; border:1px solid #333;
        padding:6px 16px; cursor:pointer; border-radius:4px; font-family:inherit;
      ">Пропустить</button>
      <button id="q-submit" style="
        background:${color}22; color:${color}; border:1px solid ${color};
        padding:6px 16px; cursor:pointer; border-radius:4px; font-family:inherit;
      ">Отправить</button>
    </div>
  `;

  overlay.appendChild(box);
  document.body.appendChild(overlay);

  const answerEl = document.getElementById("q-answer");
  answerEl.focus();

  async function submit() {
    const answer = answerEl.value.trim();
    overlay.remove();
    if (!answer) return;
    try {
      await fetch("/api/answer", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question_id: event.question_id, answer}),
      });
    } catch (err) {
      console.error("Failed to send answer:", err);
    }
  }

  document.getElementById("q-submit").addEventListener("click", submit);
  document.getElementById("q-cancel").addEventListener("click", () => overlay.remove());
  answerEl.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.ctrlKey) submit(); });
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
  const list = document.getElementById("agents-list");
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
      card.addEventListener("click", () => openChat(id));
      list.appendChild(card);
    }
    const dotClass = a.status === "thinking" ? "thinking" : a.status === "done" ? "done" : "idle";
    const dotIcon = a.status === "thinking" ? "⟳" : a.status === "done" ? "✓" : "○";
    card.innerHTML = `
      <div class="ac-name">
        <span class="status-dot ${dotClass}">${dotIcon}</span>
        <span style="color:${a.color}">${ROLE_ICONS[a.role]||""} ${a.role}</span>
      </div>
      <div class="ac-status">${escapeHtml((a.lastMsg || a.task || id).slice(0,80))}</div>
    `;
  }
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

// ---- Tabs ----
function switchTab(name) {
  document.querySelectorAll(".sb-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".sb-pane").forEach(p => p.classList.toggle("active", p.id === "pane-" + name));
}

// ---- Результаты (deliverables) ----
let deliverablesCache = [];
let ftCurrentIdx = -1;

async function loadDeliverables() {
  try {
    const r = await fetch("/api/deliverables");
    const d = await r.json();
    deliverablesCache = d.deliverables || [];
    const badge = document.getElementById("results-badge");
    if (badge) {
      badge.textContent = deliverablesCache.length ? String(deliverablesCache.length) : "";
      badge.style.display = deliverablesCache.length ? "inline" : "none";
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
  const color = ROLE_COLORS[d.role] || "#888";
  document.getElementById("ft-who").innerHTML = `<span style="color:${color}">${ROLE_ICONS[d.role]||""} ${escapeHtml(d.role)}</span> — ${escapeHtml(d.task||"")} <span style="color:#444;font-size:10px">${d.time||""}</span>`;
  document.getElementById("fulltext-body").textContent = d.content || "";
  document.getElementById("fulltext-overlay").classList.remove("hidden");
}

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
  const m = document.getElementById("sb-mission");
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

  // Tabs
  document.querySelectorAll(".sb-tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

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
    const d = deliverablesCache[ftCurrentIdx];
    if (!d) return;
    try { await navigator.clipboard.writeText(d.content||""); document.getElementById("ft-copy").textContent="✓ Скопировано"; setTimeout(()=>document.getElementById("ft-copy").textContent="⧉ Копировать",1500); }
    catch {}
  });
  document.getElementById("ft-export").addEventListener("click", () => {
    const d = deliverablesCache[ftCurrentIdx];
    if (d) downloadText(d.content||"", `${d.role}-${(d.task||"result").slice(0,30)}.md`);
  });
});

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
