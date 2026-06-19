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
  orchestrator: "#ffd54f",
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
  orchestrator: "🧭", researcher: "🔍", strategist: "📋", hr: "👔",
  salesman: "💰", developer: "💻", marketer: "📢", analyst: "📊",
};

// Человекочитаемые названия ролей
const ROLE_NAMES = {
  orchestrator: "Директор", researcher: "Ресёрчер", strategist: "Стратег", hr: "HR",
  salesman: "Продажник", developer: "Разработчик", marketer: "Маркетолог", analyst: "Аналитик",
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
  // overflow: дополнительные позиции (агенты стоят свободнее)
  {tx:4, ty:5},
  {tx:8, ty:5},
  {tx:12,ty:5},
  {tx:16,ty:5},
  {tx:4, ty:10},
  {tx:8, ty:10},
  {tx:12,ty:10},
  {tx:16,ty:10},
];

function getDeskPosition(n) {
  return DESK_POSITIONS[n % DESK_POSITIONS.length];
}

// ---- Состояние игры ----
const agents = {};        // agent_id -> {role, desk, x, y, tx, ty, bubble, color, status}
const bubbles = [];       // активные речевые пузыри
let logEntries = [];
let camX = 0, camY = 0;
let _panActive = false, _panStartX = 0, _panStartY = 0, _panStartCamX = 0, _panStartCamY = 0;

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
// Цвет волос по роли — чтобы персонажи различались
const HAIR_COLORS = {
  orchestrator: "#8a6d00", researcher: "#1a4a6a", strategist: "#2a5a3a", hr: "#7a4a10",
  salesman: "#7a2a4a", developer: "#5a2a6a", marketer: "#2a5a55", analyst: "#6a6a10",
};

function shade(hex, amt) {
  // затемнить/осветлить hex-цвет на amt (-255..255)
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) + amt, g = ((n >> 8) & 0xff) + amt, b = (n & 0xff) + amt;
  r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); b = Math.max(0, Math.min(255, b));
  return `rgb(${r},${g},${b})`;
}

function drawCharacter(x, y, color, role, status) {
  const S = 4; // размер 1 пикселя в спрайте
  const ox = Math.floor(x) - 8;
  const oy = Math.floor(y) - 20;
  const now = Date.now();

  // Тень под персонажем
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.beginPath();
  ctx.ellipse(ox + 4*S, oy + 10*S + 2, 4*S, 1.4*S, 0, 0, Math.PI*2);
  ctx.fill();

  // Ноги
  ctx.fillStyle = "#2a2a38";
  ctx.fillRect(ox+2*S, oy+8*S, 2*S-2, 2*S);
  ctx.fillRect(ox+4*S+2, oy+8*S, 2*S-2, 2*S);

  // Тело (туловище) — с лёгким объёмом
  ctx.fillStyle = color;
  ctx.fillRect(ox+2*S, oy+4*S, 4*S, 4*S);
  ctx.fillStyle = shade(typeof color === "string" && color[0] === "#" ? color : "#aaaaaa", -40);
  ctx.fillRect(ox+2*S, oy+7*S, 4*S, S); // нижняя тень рубашки
  ctx.fillStyle = "rgba(255,255,255,0.15)";
  ctx.fillRect(ox+2*S, oy+4*S, 4*S, S); // блик сверху

  // Руки
  ctx.fillStyle = color;
  ctx.fillRect(ox+S, oy+4*S, S, 3*S);
  ctx.fillRect(ox+6*S, oy+4*S, S, 3*S);
  // Кисти
  ctx.fillStyle = "#f5c5a3";
  ctx.fillRect(ox+S, oy+7*S-2, S, S);
  ctx.fillRect(ox+6*S, oy+7*S-2, S, S);

  // Голова
  ctx.fillStyle = "#f5c5a3";
  ctx.fillRect(ox+2*S, oy+1*S, 4*S, 3*S);
  // Волосы (цвет по роли)
  ctx.fillStyle = HAIR_COLORS[role] || "#3a2a1a";
  ctx.fillRect(ox+2*S, oy+1*S-2, 4*S, S+2);
  ctx.fillRect(ox+2*S, oy+1*S, S, S);
  ctx.fillRect(ox+5*S, oy+1*S, S, S);
  // Глаза (с белками)
  ctx.fillStyle = "#fff";
  ctx.fillRect(ox+3*S-1, oy+2*S, S, S);
  ctx.fillRect(ox+5*S-1, oy+2*S, S, S);
  ctx.fillStyle = "#222";
  ctx.fillRect(ox+3*S, oy+2*S, S-2, S-1);
  ctx.fillRect(ox+5*S, oy+2*S, S-2, S-1);

  // Иконка роли над головой
  ctx.font = "12px serif";
  ctx.textAlign = "center";
  ctx.fillText(ROLE_ICONS[role] || "🤖", ox + 4*S, oy - 2);

  // Статус-точка (пульсирующая)
  const dotColor = status === "thinking" ? "#ffd54f" : status === "done" ? "#81c784" : "#5a5a78";
  const pulse = status === "thinking" ? 0.5 + 0.5*Math.sin(now/250) : 1;
  ctx.globalAlpha = pulse;
  ctx.fillStyle = dotColor;
  ctx.beginPath();
  ctx.arc(ox + 7*S, oy + 1*S, 3, 0, Math.PI*2);
  ctx.fill();
  ctx.globalAlpha = 1;
}

// ---- Bubble drawing ----
function drawBubble(text, x, y, alpha) {
  const maxW = 190;
  ctx.font = "10px Courier New";
  const words = text.split(" ");
  const lines = [];
  let line = "";
  for (const w of words) {
    const test = line + (line ? " " : "") + w;
    if (ctx.measureText(test).width > maxW - 16) {
      if (line) lines.push(line);
      line = w;
    } else line = test;
  }
  if (line) lines.push(line);

  // ширина по самой длинной строке
  let bw = 0;
  for (const l of lines) bw = Math.max(bw, ctx.measureText(l).width);
  bw = Math.min(maxW, bw + 16);
  const bh = lines.length * 14 + 12;
  let bx = x - bw / 2;
  let by = y - bh - 34;
  // удерживаем пузырь внутри канваса
  bx = Math.max(6, Math.min(canvas.width - bw - 6, bx));
  by = Math.max(6, by);

  ctx.globalAlpha = alpha;
  // тень
  ctx.shadowColor = "rgba(0,0,0,0.5)";
  ctx.shadowBlur = 8;
  ctx.shadowOffsetY = 3;
  ctx.fillStyle = "rgba(14, 16, 26, 0.97)";
  ctx.beginPath();
  ctx.roundRect(bx, by, bw, bh, 7);
  ctx.fill();
  ctx.shadowColor = "transparent";
  ctx.shadowBlur = 0;
  ctx.shadowOffsetY = 0;

  ctx.strokeStyle = "rgba(79, 195, 247, 0.5)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(bx, by, bw, bh, 7);
  ctx.stroke();

  // Хвостик пузыря (только если он указывает в пределах пузыря)
  const tailX = Math.max(bx + 8, Math.min(bx + bw - 8, x));
  ctx.fillStyle = "rgba(14, 16, 26, 0.97)";
  ctx.beginPath();
  ctx.moveTo(tailX - 5, by + bh - 1);
  ctx.lineTo(tailX + 5, by + bh - 1);
  ctx.lineTo(tailX, by + bh + 7);
  ctx.fill();

  ctx.fillStyle = "#e0e0e8";
  ctx.font = "10px Courier New";
  ctx.textAlign = "left";
  lines.forEach((l, i) => ctx.fillText(l, bx + 8, by + 15 + i * 14));
  ctx.globalAlpha = 1;
}

// ---- Layout ----
function getMapOffset() {
  const wrap = document.getElementById("game-wrap");
  const mapW = COLS * P;
  const mapH = ROWS * P;
  const ox = Math.max(0, (wrap.clientWidth - mapW) / 2) + camX;
  const oy = Math.max(0, (wrap.clientHeight - mapH) / 2) + camY;
  return {ox, oy};
}

// ---- SSE ----
function connectSSE() {
  const statusBar = document.getElementById("status-bar");
  const es = new EventSource("/events");

  es.onopen = () => {
    statusBar.textContent = "● онлайн";
    statusBar.style.color = "#4fc3f7";
    _historyDividerAdded = false;  // сбрасываем при каждом переподключении
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
  const hist = !!event.historical;  // исторические события — тихо, без переключений

  if (event.type === "hired") {
    spawnAgent(event.agent_id, event.role, event.desk, event.task || "");
    if (!hist) addLog(event.agent_id, `принят на работу как ${event.role}`, event.role);
    // Восстанавливаем реальный статус агента из снапшота
    if (event.status && event.status !== "idle") {
      updateAgentStatus(event.agent_id, event.status, event.last_message || "");
    }
  }
  else if (event.type === "speech") {
    if (!hist) addBubble(event.agent_id, event.text);
    addLog(event.agent_id, event.text, getRole(event.agent_id), hist);
    addToChatFeed({from: event.agent_id, role: getRole(event.agent_id), text: event.text}, hist);
    if (!hist) updateAgentStatus(event.agent_id, "thinking", event.text);
  }
  else if (event.type === "office_chat") {
    addToChatFeed({from: event.from, role: event.role, text: event.text}, hist);
  }
  else if (event.type === "thinking") {
    if (!hist) {
      addBubble(event.agent_id, event.text);
      updateAgentStatus(event.agent_id, "thinking", event.text);
    }
  }
  else if (event.type === "task_done") {
    addLog(event.agent_id, "✓ " + (event.summary||"задача выполнена").slice(0,100), getRole(event.agent_id), hist);
    if (!hist) {
      updateAgentStatus(event.agent_id, "done", (event.summary||"").slice(0,80));
      loadDeliverables();
    }
  }
  else if (event.type === "progress") {
    if (!hist) updateProgressBar(event);
  }
  else if (event.type === "system") {
    addLog("офис", event.text, "system", hist);
  }
  else if (event.type === "error") {
    addLog(event.agent_id, "⚠ " + event.text, getRole(event.agent_id), hist);
  }
  else if (event.type === "question") {
    if (!hist) {
      addQuestionCard(event);
      // Auto-switch only from the office canvas; elsewhere just pulse the badge
      if (_currentView === "office") {
        switchView("questions");
      } else {
        const badge = document.getElementById("badge-questions");
        badge.classList.add("badge-pulse");
        setTimeout(() => badge.classList.remove("badge-pulse"), 2000);
        showToast("❓ Агент задал вопрос — см. вкладку «Вопросы»", "ok");
      }
    }
  }
  else if (event.type === "connection_added") {
    if (!hist) {
      loadConnections();  // обновляем вкладку Доступы
      showToast(`🔌 Доступ «${event.connection && event.connection.name}» сохранён`, "ok");
    }
  }
  else if (event.type === "connection_error") {
    if (!hist) showToast(`❌ ${event.platform}: ${event.error}`, "err");
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
    badge.style.display = qs.length ? "block" : "none";

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
    badge.style.display = "block";
  }
}

function removeQuestionCard(qid) {
  const card = document.getElementById("qcard-" + qid);
  if (card) card.remove();
  const wrap = document.getElementById("questions-wrap");
  const remaining = wrap.querySelectorAll(".q-card").length;
  const badge = document.getElementById("badge-questions");
  badge.textContent = remaining || "";
  badge.style.display = remaining ? "block" : "none";
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
  const dp = getDeskPosition(desk);
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

let _historyDividerAdded = false;

function showToast(msg, type = "ok") {
  const t = document.createElement("div");
  t.textContent = msg;
  t.style.cssText = `
    position:fixed; bottom:24px; right:24px; z-index:9000;
    padding:10px 18px; border-radius:8px; font-size:12px; font-family:'Courier New',monospace;
    color:#fff; max-width:360px; box-shadow:0 4px 20px rgba(0,0,0,.5);
    background:${type==="ok" ? "#1a3a1a" : "#3a1a1a"};
    border:1px solid ${type==="ok" ? "#4a8a4a" : "#8a3a3a"};
    transition: opacity 0.4s;
  `;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 400); }, 3500);
}

function addLog(who, text, role, historical = false) {
  const color = historical ? "#333355" : (ROLE_COLORS[role] || "#556");
  const time = new Date().toLocaleTimeString("ru", {hour:"2-digit",minute:"2-digit"});
  const logWrap = document.getElementById("log-wrap");

  // Первый живой лог после исторических — добавляем разделитель
  if (!historical && !_historyDividerAdded) {
    _historyDividerAdded = true;
    const sep = document.createElement("div");
    sep.style.cssText = "padding:6px 20px; font-size:10px; color:#2a2a4a; border-bottom:1px solid #151528; text-align:center;";
    sep.textContent = "── история выше ──";
    logWrap.prepend(sep);
  }

  const div = document.createElement("div");
  div.className = "log-entry" + (historical ? " log-hist" : "");
  div.innerHTML = `<span class="lt">${time}</span><span class="lw" style="color:${color}">${who}</span>: ${escapeHtml(text.slice(0,160))}`;
  if (historical) {
    logWrap.appendChild(div);  // исторические — в конец (старые внизу)
  } else {
    logWrap.prepend(div);      // новые — наверх
  }
  if (logWrap.children.length > 300) logWrap.removeChild(logWrap.lastChild);
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

  // Модель этого агента
  setupAgentModelSelector(agentId, data && data.model, data && data.model_custom);

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
  let downX = 0, downY = 0, moved = false;

  canvas.addEventListener("mousedown", (e) => {
    _panActive = true;
    moved = false;
    _panStartX = e.clientX; _panStartY = e.clientY;
    _panStartCamX = camX; _panStartCamY = camY;
    downX = e.clientX; downY = e.clientY;
  });
  window.addEventListener("mousemove", (e) => {
    if (!_panActive) return;
    const dx = e.clientX - _panStartX;
    const dy = e.clientY - _panStartY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved = true;
    camX = _panStartCamX + dx;
    camY = _panStartCamY + dy;
    syncAgentTargets();
    canvas.style.cursor = "grabbing";
  });
  window.addEventListener("mouseup", (e) => {
    _panActive = false;
    canvas.style.cursor = "default";
    if (!moved) {
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const id = findAgentAt(px, py);
      if (id) openChat(id);
    }
  });
}

function syncAgentTargets() {
  const {ox, oy} = getMapOffset();
  for (const a of Object.values(agents)) {
    const dp = getDeskPosition(a.desk);
    a.tx = ox + dp.tx * P + P/2;
    a.ty = oy + dp.ty * P + P/2;
  }
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

  // Сохраняем выбранную на старте модель
  await saveIntakeModel();

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
let _currentView = "office";
function switchView(name) {
  _currentView = name;
  document.querySelectorAll(".nav-item").forEach(t => t.classList.toggle("active", t.dataset.view === name));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + name));
  if (name === "office") {
    resize();
    const {ox, oy} = getMapOffset();
    for (const a of Object.values(agents)) {
      const dp = getDeskPosition(a.desk);
      a.tx = ox + dp.tx * P + P/2;
      a.ty = oy + dp.ty * P + P/2;
    }
  }
  if (name === "questions") {
    loadQuestions();
  }
  if (name === "progress") {
    loadProgress();
  }
  if (name === "chat") {
    loadChatFeed();
    const badge = document.getElementById("badge-chat");
    if (badge) { badge.textContent = ""; badge.style.display = "none"; }
  }
}

// ============================================================
// PROGRESS BAR (динамические кликабельные этапы)
// ============================================================
// Этапы приходят с бэка: {stages:[{id,title,status,summary,item_count}], current, percent, note}
let _stageData = [];

function renderProgress(p) {
  _stageData = (p.stages && p.stages.length) ? p.stages : _stageData;

  // Слим-полоса в топбаре
  const fill = document.getElementById("progress-fill");
  const pct = typeof p.percent === "number" ? p.percent : 0;
  if (fill) fill.style.width = Math.max(0, Math.min(100, pct)) + "%";
  const note = document.getElementById("progress-note");
  const cur = _stageData.find(s => s.status === "active");
  if (note) {
    const noteText = (p.note !== undefined && p.note) ? p.note : (cur ? `▸ ${cur.title}` : "");
    note.textContent = noteText;
  }

  // Подробные этапы во вкладке «Этапы»
  const list = document.getElementById("progress-stages-list");
  if (!list) return;
  const noStages = document.getElementById("no-stages");
  if (noStages) noStages.style.display = _stageData.length ? "none" : "block";
  list.querySelectorAll(".ps-stage").forEach(e => e.remove());
  _stageData.forEach((s) => {
    const div = document.createElement("div");
    div.className = "ps-stage" + (s.status === "done" ? " done" : s.status === "active" ? " active" : "");
    const count = s.item_count ? `<span class="pss-count">${s.item_count}</span>` : "";
    div.innerHTML = `
      <div class="pss-head">
        <span class="pss-dot"></span>
        <span class="pss-title">${escapeHtml(s.title)}</span>
        ${count}
      </div>
      ${s.summary ? `<div class="pss-summary">${escapeHtml(s.summary.slice(0,160))}</div>` : ""}
    `;
    div.title = "Нажмите, чтобы посмотреть сводку этапа";
    div.addEventListener("click", () => openMilestone(s.id));
    list.appendChild(div);
  });
}
// обратная совместимость со старым именем
function updateProgressBar(p) { renderProgress(p); }
function buildProgressSteps() { /* этапы строятся из данных бэка */ }

async function loadProgress() {
  try {
    const r = await fetch("/api/progress");
    renderProgress(await r.json());
  } catch {}
}

async function openMilestone(stageId) {
  try {
    const r = await fetch(`/api/milestone/${encodeURIComponent(stageId)}`);
    if (!r.ok) return;
    const m = await r.json();
    ftCurrentIdx = -1;
    ftRawContent = (m.summary || "") + "\n\n" + (m.items||[]).map(it => `- ${it.text||""}`).join("\n");
    const statusWord = m.status === "done" ? "✓ завершён" : m.status === "active" ? "⟳ в работе" : "○ впереди";
    const items = (m.items || []).slice().reverse().map(it => {
      const role = ROLE_NAMES[it.role] || it.role || "";
      const icon = ROLE_ICONS[it.role] || "•";
      return `<div class="ms-item"><div class="ms-item-who">${icon} ${escapeHtml(role)}</div><div class="ms-item-text">${escapeHtml(it.text||"")}</div></div>`;
    }).join("") || `<div style="color:#667;padding:8px 0;">Пока нет записей по этому этапу.</div>`;

    document.getElementById("ft-who").innerHTML =
      `🧭 Этап: <b>${escapeHtml(m.title)}</b> <span style="color:#888;font-size:11px">(${statusWord})</span>`;
    const body = document.getElementById("fulltext-body");
    body.innerHTML =
      (m.summary ? `<div class="ms-summary"><b>Сводка:</b><br>${escapeHtml(m.summary)}</div>` : "") +
      `<div class="ms-items-head">Что сделано (${(m.items||[]).length}):</div>` + items;
    document.getElementById("fulltext-overlay").classList.remove("hidden");
  } catch (e) { console.error("openMilestone:", e); }
}

// ============================================================
// ОБЩИЙ ЧАТ ОФИСА (двусторонний)
// ============================================================
const _chatSeen = new Set();

function addToChatFeed(msg, historical = false) {
  const feed = document.getElementById("chat-feed");
  if (!feed) return;
  const no = document.getElementById("no-chat-msgs");
  if (no) no.remove();

  const from = msg.from || "agent";
  const role = msg.role || roleFromId(from);
  const isUser = from === "user" || role === "user";
  const isSystem = from === "system" || role === "system";

  const wrap = document.createElement("div");
  wrap.className = "cf-msg" + (isUser ? " user-msg" : isSystem ? " system-msg" : "");
  const icon = isUser ? "🧑" : isSystem ? "🏢" : (ROLE_ICONS[role] || "🤖");
  const who = isUser ? "Вы" : isSystem ? "Офис" : `${ROLE_NAMES[role] || role}`;
  wrap.innerHTML = `
    <div class="cf-avatar">${icon}</div>
    <div class="cf-body">
      <div class="cf-who">${escapeHtml(who)}</div>
      <div class="cf-text">${escapeHtml(msg.text || "")}</div>
    </div>
  `;
  feed.appendChild(wrap);
  feed.scrollTop = feed.scrollHeight;

  // Бейдж непрочитанного, если мы не на вкладке чата
  if (!historical && _currentView !== "chat" && !isUser) {
    const badge = document.getElementById("badge-chat");
    if (badge) {
      const cur = parseInt(badge.textContent || "0") + 1;
      badge.textContent = cur;
      badge.style.display = "block";
    }
  }
}

async function loadChatFeed() {
  try {
    const r = await fetch("/api/chat");
    const d = await r.json();
    const msgs = d.messages || [];
    const feed = document.getElementById("chat-feed");
    if (feed) feed.querySelectorAll(".cf-msg").forEach(c => c.remove());
    for (const m of msgs) addToChatFeed(m, true);
  } catch (e) { /* чат может быть недоступен */ }
}

async function sendChatBroadcast() {
  const inp = document.getElementById("chat-compose-input");
  const text = (inp.value || "").trim();
  if (!text) return;
  inp.value = "";
  addToChatFeed({from: "user", role: "user", text}, true);
  try {
    await fetch("/api/chat", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text}),
    });
  } catch (e) { showToast("❌ Не удалось отправить сообщение", "err"); }
}

function setupChat() {
  const sendBtn = document.getElementById("chat-compose-send");
  const inp = document.getElementById("chat-compose-input");
  if (sendBtn) sendBtn.addEventListener("click", sendChatBroadcast);
  if (inp) inp.addEventListener("keydown", (e) => { if (e.key === "Enter") sendChatBroadcast(); });
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

// История теперь стримится через SSE как historical-события (не нужен отдельный fetch)
async function replayHistory() {}

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

  // Скачать логи работы офиса
  document.getElementById("btn-logs").addEventListener("click", () => {
    window.location.href = "/api/logs";
    showToast("📥 Лог скачивается — можно прислать на анализ", "ok");
  });

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

  // Общий чат
  setupChat();
  loadChatFeed();

  // Model switcher (topbar global) + onboarding model picker
  setupModelSwitcher();
  setupIntakeModel();
});

// ============================================================
// MODEL MANAGEMENT — глобальная модель + индивидуальные по агентам
// ============================================================
const CUSTOM_OPT = "__custom__";
let _modelPresets = [];   // [{id,label}]
let _modelDefault = "";

async function loadModelsConfig() {
  try {
    const r = await fetch("/api/models");
    const d = await r.json();
    _modelPresets = d.presets || [];
    _modelDefault = d.default || "";
  } catch (e) { console.error("loadModelsConfig:", e); }
}

/**
 * Заполняет <select> пресетами + опцией «своя модель».
 * current — текущее значение; если его нет среди пресетов, включаем кастомное поле.
 * Возвращает выбранную модель через колбэк onPick(model).
 */
function fillModelSelect(selectEl, customEl, current) {
  selectEl.innerHTML = "";
  for (const p of _modelPresets) {
    const opt = document.createElement("option");
    opt.value = p.id; opt.textContent = p.label;
    selectEl.appendChild(opt);
  }
  const customOpt = document.createElement("option");
  customOpt.value = CUSTOM_OPT; customOpt.textContent = "✏️ Своя модель…";
  selectEl.appendChild(customOpt);

  const known = _modelPresets.some(p => p.id === current);
  if (current && !known) {
    selectEl.value = CUSTOM_OPT;
    customEl.style.display = "block";
    customEl.value = current;
  } else {
    selectEl.value = current || (_modelPresets[0] && _modelPresets[0].id) || "";
    customEl.style.display = "none";
    customEl.value = "";
  }
}

function readModelSelect(selectEl, customEl) {
  if (selectEl.value === CUSTOM_OPT) return (customEl.value || "").trim();
  return selectEl.value;
}

// ---- Топбар: глобальная модель (input) ----
async function setupModelSwitcher() {
  await loadModelsConfig();
  document.getElementById("model-input").value = _modelDefault || "";

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
        _modelDefault = model;
        const btn = document.getElementById("model-save");
        btn.textContent = "✓"; btn.style.color = "#4fc3f7";
        setTimeout(() => { btn.style.color = "#4a8"; }, 1500);
      }
    } catch (e) { console.error("model save:", e); }
  }

  document.getElementById("model-save").addEventListener("click", saveModel);
  document.getElementById("model-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveModel();
  });
}

// ---- Онбординг: выбор модели на первом запуске ----
async function setupIntakeModel() {
  await loadModelsConfig();
  const sel = document.getElementById("intake-model");
  const custom = document.getElementById("intake-model-custom");
  if (!sel) return;
  fillModelSelect(sel, custom, _modelDefault);
  sel.addEventListener("change", () => {
    custom.style.display = sel.value === CUSTOM_OPT ? "block" : "none";
    if (sel.value === CUSTOM_OPT) custom.focus();
  });
}

async function saveIntakeModel() {
  const sel = document.getElementById("intake-model");
  const custom = document.getElementById("intake-model-custom");
  if (!sel) return;
  const model = readModelSelect(sel, custom);
  if (!model) return;
  try {
    await fetch("/api/model", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({model}),
    });
    _modelDefault = model;
  } catch (e) { console.error("saveIntakeModel:", e); }
}

// ---- Карточка агента: индивидуальная модель ----
function setupAgentModelSelector(agentId, current, isCustom) {
  const sel = document.getElementById("ad-model");
  const custom = document.getElementById("ad-model-custom");
  if (!sel) return;
  if (!_modelPresets.length) {
    // на случай если конфиг ещё не загружен
    loadModelsConfig().then(() => fillModelSelect(sel, custom, current || _modelDefault));
  } else {
    fillModelSelect(sel, custom, current || _modelDefault);
  }

  async function save() {
    const model = readModelSelect(sel, custom);
    try {
      await fetch(`/api/agent/${encodeURIComponent(agentId)}/model`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({model}),
      });
      addLog("офис", `Модель агента ${agentId} → ${model}. Он войдёт в курс дела по сохранённому контексту.`, "system");
    } catch (e) { console.error("agent model save:", e); }
  }

  sel.onchange = () => {
    if (sel.value === CUSTOM_OPT) { custom.style.display = "block"; custom.focus(); }
    else { custom.style.display = "none"; save(); }
  };
  custom.onkeydown = (e) => { if (e.key === "Enter") save(); };
  custom.onblur = () => { if (custom.value.trim()) save(); };
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
