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
    addLog(event.agent_id, "✓ задача выполнена", getRole(event.agent_id));
    updateAgentStatus(event.agent_id, "done", event.summary || "");
  }
  else if (event.type === "system") {
    addLog("офис", event.text, "system");
  }
  else if (event.type === "error") {
    addLog(event.agent_id, "⚠ " + event.text, getRole(event.agent_id));
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
  const color = ROLE_COLORS[role] || "#888";
  const entry = {who, text: text.slice(0, 120), color, time: new Date().toLocaleTimeString("ru", {hour:"2-digit",minute:"2-digit"})};
  logEntries.unshift(entry);
  if (logEntries.length > 100) logEntries.pop();

  const log = document.getElementById("log");
  const div = document.createElement("div");
  div.className = "log-entry";
  div.innerHTML = `<span class="who" style="color:${color}">${entry.time} ${who}</span>: ${entry.text}`;
  log.prepend(div);
  if (log.children.length > 100) log.removeChild(log.lastChild);
}

function updateSidebar() {
  const list = document.getElementById("agents-list");
  list.innerHTML = "";
  for (const [id, a] of Object.entries(agents)) {
    const card = document.createElement("div");
    card.className = "agent-card";
    card.style.borderLeftColor = a.color;
    const statusDot = a.status === "thinking" ? "⚡" : a.status === "done" ? "✓" : "○";
    card.innerHTML = `
      <div class="name" style="color:${a.color}">${statusDot} ${ROLE_ICONS[a.role]||""} ${a.role}</div>
      <div class="task">${a.task || id}</div>
    `;
    list.appendChild(card);
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

// ---- Init ----
window.addEventListener("load", () => {
  resize();
  connectSSE();
  gameLoop();
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
