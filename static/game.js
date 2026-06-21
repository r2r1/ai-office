// ============================================================
// AI OFFICE — Pixel Game Engine
// ============================================================

// ---- Общий fetch с обработкой 401 ----
function showLoginGate() {
  document.getElementById("login-gate")?.classList.remove("hidden");
}

async function apiFetch(url, opts = {}) {
  try {
    const r = await fetch(url, opts);
    if (r.status === 401) { showLoginGate(); return null; }
    return r;
  } catch { return null; }
}

const COLS = 20;   // ширина карты в тайлах
const ROWS = 14;   // высота карты в тайлах
const ISO_W = 52;  // ширина изометрического тайла (пикс при scale=1)
const ISO_H = 26;  // высота изометрического тайла (ISO_W/2)
const WALL_H = 36; // высота стен в пикселях
const DESK_H = 16; // высота столов
let isoScale = 1.0;

// Auto-fit scale so the entire map fits the game-wrap div
function updateScale() {
  const wrap = document.getElementById("game-wrap");
  if (!wrap) return;
  const mapW = (COLS + ROWS) * ISO_W / 2;
  const mapH = (COLS + ROWS) * ISO_H / 2 + WALL_H + 60;
  const s = Math.min(wrap.clientWidth / mapW, wrap.clientHeight / mapH) * 0.90;
  isoScale = Math.max(0.5, Math.min(s, 1.8));
}

// Convert tile (col, row) to screen (x, y) — center of tile's top diamond
function tileToScreen(col, row) {
  const wrap = document.getElementById("game-wrap");
  if (!wrap) return { x: 400, y: 200 };
  const tw = ISO_W * isoScale / 2;
  const th = ISO_H * isoScale / 2;
  // Центр изометрической сетки: смещаем так, чтобы вся карта была по центру.
  const midDX = (COLS - ROWS) / 2;       // середина диапазона (col - row)
  const midSum = (COLS - 1 + ROWS - 1) / 2; // середина диапазона (col + row)
  const ox = wrap.clientWidth / 2 - midDX * tw + camX;
  // чуть выше центра — стены тянутся вверх, оставляем им место
  const oy = wrap.clientHeight / 2 - midSum * th + WALL_H * isoScale * 0.5 + camY;
  return {
    x: ox + (col - row) * tw,
    y: oy + (col + row) * th,
  };
}

// Цвета ролей
const ROLE_COLORS = {
  orchestrator: "#ffd54f",
  researcher: "#4fc3f7",
  strategist: "#81c784",
  architect:  "#b39ddb",
  hr:         "#ffb74d",
  salesman:   "#f06292",
  developer:  "#ce93d8",
  marketer:   "#80cbc4",
  analyst:    "#fff176",
  integrator: "#4dd0e1",
};

// Иконки ролей (emoji -> рисуем текстом)
const ROLE_ICONS = {
  orchestrator: "🧭", researcher: "🔍", strategist: "📋", architect: "🏗️", hr: "👔",
  salesman: "💰", developer: "💻", marketer: "📢", analyst: "📊", integrator: "🔌",
};

// Человекочитаемые названия ролей
const ROLE_NAMES = {
  orchestrator: "Директор", researcher: "Ресёрчер", strategist: "Стратег", architect: "Архитектор", hr: "HR",
  salesman: "Продажник", developer: "Разработчик", marketer: "Маркетолог", analyst: "Аналитик", integrator: "Интегратор",
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
resize();

// ---- Isometric drawing primitives ----
function isoFloor(cx, cy, fillColor, strokeColor) {
  const tw = ISO_W * isoScale / 2, th = ISO_H * isoScale / 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy - th);
  ctx.lineTo(cx + tw, cy);
  ctx.lineTo(cx, cy + th);
  ctx.lineTo(cx - tw, cy);
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();
  if (strokeColor) { ctx.strokeStyle = strokeColor; ctx.lineWidth = 0.5; ctx.stroke(); }
}

function isoBox(cx, cy, sh, topC, leftC, rightC, outlineC) {
  const tw = ISO_W * isoScale / 2, th = ISO_H * isoScale / 2;
  // Left face
  ctx.beginPath();
  ctx.moveTo(cx - tw, cy); ctx.lineTo(cx, cy + th);
  ctx.lineTo(cx, cy + th - sh); ctx.lineTo(cx - tw, cy - sh);
  ctx.closePath(); ctx.fillStyle = leftC; ctx.fill();
  // Right face
  ctx.beginPath();
  ctx.moveTo(cx + tw, cy); ctx.lineTo(cx, cy + th);
  ctx.lineTo(cx, cy + th - sh); ctx.lineTo(cx + tw, cy - sh);
  ctx.closePath(); ctx.fillStyle = rightC; ctx.fill();
  // Top face (diamond shifted up)
  ctx.beginPath();
  ctx.moveTo(cx, cy - th - sh); ctx.lineTo(cx + tw, cy - sh);
  ctx.lineTo(cx, cy + th - sh); ctx.lineTo(cx - tw, cy - sh);
  ctx.closePath(); ctx.fillStyle = topC; ctx.fill();
  if (outlineC) {
    ctx.strokeStyle = outlineC; ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(cx, cy - th - sh); ctx.lineTo(cx + tw, cy - sh);
    ctx.lineTo(cx, cy + th - sh); ctx.lineTo(cx - tw, cy - sh);
    ctx.closePath(); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx - tw, cy); ctx.lineTo(cx - tw, cy - sh);
    ctx.moveTo(cx + tw, cy); ctx.lineTo(cx + tw, cy - sh);
    ctx.moveTo(cx, cy + th); ctx.lineTo(cx, cy + th - sh);
    ctx.stroke();
  }
}

function drawIsoTile(col, row) {
  const tile = MAP[row][col];
  const { x: cx, y: cy } = tileToScreen(col, row);
  const tw = ISO_W * isoScale / 2, th = ISO_H * isoScale / 2;
  const isAlt = (col + row) % 2 === 0;
  const sh_wall = WALL_H * isoScale, sh_desk = DESK_H * isoScale;

  if (tile === 0) {
    // Floor with subtle checkerboard
    isoFloor(cx, cy, isAlt ? '#1c1a2c' : '#201e34', 'rgba(56,44,88,0.25)');
  }
  else if (tile === 1) {
    // Wall — 3D block with brick hints
    isoFloor(cx, cy, '#161424');
    isoBox(cx, cy, sh_wall, '#3d2660', '#28184a', '#1c1038', '#4e3270');
    // Subtle light stripe on top
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.beginPath();
    ctx.moveTo(cx - tw * 0.4, cy - sh_wall - th * 0.2);
    ctx.lineTo(cx + tw * 0.4, cy - sh_wall - th * 0.2);
    ctx.lineTo(cx + tw * 0.1, cy - sh_wall + th * 0.2);
    ctx.lineTo(cx - tw * 0.7, cy - sh_wall + th * 0.2);
    ctx.closePath(); ctx.fill();
  }
  else if (tile === 2) {
    // Desk — 3D wooden box with glowing monitor
    isoFloor(cx, cy, '#1c1a2c', null);
    isoBox(cx, cy, sh_desk, '#6e3e1c', '#422410', '#2c180a', '#8a5020');
    // Monitor screen on desk top
    const mx = cx + tw * 0.12, my = cy - sh_desk - th * 0.55;
    const ms = isoScale * 0.72;
    isoBox(mx, my, 9 * ms, '#141420', '#0e0e18', '#090914', null);
    // Screen glow (cyan)
    ctx.shadowColor = '#4fc3f7'; ctx.shadowBlur = 5 * isoScale;
    ctx.fillStyle = 'rgba(79,195,247,0.65)';
    const sw = ISO_W * ms / 2 * 0.7, sh2 = ISO_H * ms / 2 * 0.7;
    ctx.beginPath();
    ctx.moveTo(mx, my - sh2 - 9 * ms); ctx.lineTo(mx + sw, my - 9 * ms);
    ctx.lineTo(mx, my + sh2 - 9 * ms); ctx.lineTo(mx - sw, my - 9 * ms);
    ctx.closePath(); ctx.fill();
    ctx.shadowBlur = 0; ctx.shadowColor = 'transparent';
  }
  else if (tile === 3) {
    // Window — tall glass block
    isoFloor(cx, cy, '#161424');
    isoBox(cx, cy, sh_wall, '#183858', '#0e2440', '#081828', null);
    // Glass shimmer
    ctx.fillStyle = 'rgba(79,195,247,0.22)';
    ctx.beginPath();
    ctx.moveTo(cx - tw * 0.6, cy - sh_wall * 0.4);
    ctx.lineTo(cx - tw * 0.1, cy - sh_wall * 0.7);
    ctx.lineTo(cx + tw * 0.1, cy - sh_wall * 0.6);
    ctx.lineTo(cx - tw * 0.4, cy - sh_wall * 0.3);
    ctx.closePath(); ctx.fill();
    // Reflection stripe
    ctx.fillStyle = 'rgba(180,230,255,0.08)';
    ctx.beginPath();
    ctx.moveTo(cx - tw * 0.2, cy - sh_wall * 0.9);
    ctx.lineTo(cx + tw * 0.1, cy - sh_wall * 0.75);
    ctx.lineTo(cx, cy - sh_wall * 0.65);
    ctx.lineTo(cx - tw * 0.3, cy - sh_wall * 0.8);
    ctx.closePath(); ctx.fill();
  }
  else if (tile === 4) {
    // Plant
    isoFloor(cx, cy, '#1c1a2c');
    isoBox(cx, cy, 8 * isoScale, '#3c2010', '#241408', '#180e06', null);
    const leafY = cy - 26 * isoScale, r = 7 * isoScale;
    const lc = ['#1e5810', '#2a7018', '#358a20', '#1a6212', '#2c7a18'];
    for (let i = 0; i < 5; i++) {
      const a = (i / 5) * Math.PI * 2 + 0.4;
      ctx.fillStyle = lc[i];
      ctx.beginPath();
      ctx.ellipse(cx + Math.cos(a) * r * 1.1, leafY + Math.sin(a) * r * 0.55, r, r * 0.65, a, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = '#38941e';
    ctx.beginPath(); ctx.arc(cx, leafY - 3 * isoScale, 6 * isoScale, 0, Math.PI * 2); ctx.fill();
  }

  // Desk labels (numbers)
  const di = DESK_POSITIONS.findIndex(d => d.tx === col && d.ty === row);
  if (di >= 0) {
    ctx.font = `${8 * isoScale}px Inter, system-ui, sans-serif`;
    ctx.fillStyle = 'rgba(150,130,200,0.5)';
    ctx.textAlign = 'center';
    ctx.fillText(`#${di}`, cx, cy - sh_desk - th - 3 * isoScale);
  }
}

function drawIsoMap() {
  updateScale();
  // Diagonal strip rendering — back to front
  for (let d = 0; d < COLS + ROWS - 1; d++) {
    for (let col = Math.max(0, d - ROWS + 1); col <= Math.min(d, COLS - 1); col++) {
      const row = d - col;
      if (row < 0 || row >= ROWS) continue;
      drawIsoTile(col, row);
    }
  }
}

// ---- Colors/helpers for characters ----
const HAIR_COLORS = {
  orchestrator: "#8a6d00", researcher: "#1a4a6a", strategist: "#2a5a3a", hr: "#7a4a10",
  salesman: "#7a2a4a", developer: "#5a2a6a", marketer: "#2a5a55", analyst: "#6a6a10",
  architect: "#4a3a6a", integrator: "#0a5a6a",
};

function drawIsoCharacter(cx, cy, color, role, status, agent = null) {
  const now = Date.now();
  const sc = isoScale;
  const tw = ISO_W * sc / 2, th = ISO_H * sc / 2;
  const bodyH = 30 * sc, bodyW = 13 * sc;
  const bx = cx - bodyW / 2, by = cy - bodyH;

  // Thinking desk glow
  if (status === 'thinking') {
    const glowAlpha = 0.15 + 0.1 * Math.sin(Date.now() / 400);
    ctx.save();
    ctx.globalAlpha = glowAlpha;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 40 * sc);
    grad.addColorStop(0, '#ffd54f');
    grad.addColorStop(1, 'transparent');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(cx, cy, 40 * sc, 20 * sc, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  // Floor shadow (ellipse)
  ctx.fillStyle = 'rgba(0,0,0,0.28)';
  ctx.beginPath();
  ctx.ellipse(cx, cy, 11 * sc, 5 * sc, 0, 0, Math.PI * 2);
  ctx.fill();

  // Legs
  ctx.fillStyle = '#1e1e32';
  ctx.fillRect(bx + bodyW * 0.15, by + bodyH * 0.62, bodyW * 0.28, bodyH * 0.38);
  ctx.fillRect(bx + bodyW * 0.57, by + bodyH * 0.62, bodyW * 0.28, bodyH * 0.38);
  // Shoes
  ctx.fillStyle = '#0e0e1c';
  ctx.fillRect(bx + bodyW * 0.12, by + bodyH * 0.90, bodyW * 0.32, bodyH * 0.10);
  ctx.fillRect(bx + bodyW * 0.54, by + bodyH * 0.90, bodyW * 0.32, bodyH * 0.10);

  // Body / shirt
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(bx + bodyW * 0.08, by + bodyH * 0.34, bodyW * 0.84, bodyH * 0.30, 3 * sc);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.12)'; // light reflection
  ctx.fillRect(bx + bodyW * 0.12, by + bodyH * 0.36, bodyW * 0.76, bodyH * 0.06);
  ctx.fillStyle = 'rgba(0,0,0,0.18)'; // bottom shadow
  ctx.fillRect(bx + bodyW * 0.08, by + bodyH * 0.58, bodyW * 0.84, bodyH * 0.06);

  // Arms
  ctx.fillStyle = color;
  ctx.fillRect(bx - bodyW * 0.02, by + bodyH * 0.34, bodyW * 0.12, bodyH * 0.22);
  ctx.fillRect(bx + bodyW * 0.90, by + bodyH * 0.34, bodyW * 0.12, bodyH * 0.22);
  // Hands
  ctx.fillStyle = '#f0c090';
  ctx.fillRect(bx - bodyW * 0.02, by + bodyH * 0.54, bodyW * 0.12, bodyH * 0.09);
  ctx.fillRect(bx + bodyW * 0.90, by + bodyH * 0.54, bodyW * 0.12, bodyH * 0.09);

  // Neck
  ctx.fillStyle = '#f0c090';
  ctx.fillRect(bx + bodyW * 0.38, by + bodyH * 0.26, bodyW * 0.24, bodyH * 0.10);

  // Head
  ctx.fillStyle = '#f5c9a0';
  ctx.beginPath();
  ctx.roundRect(bx + bodyW * 0.14, by + bodyH * 0.03, bodyW * 0.72, bodyH * 0.26, 4 * sc);
  ctx.fill();
  // Hair
  ctx.fillStyle = HAIR_COLORS[role] || '#3a2a1a';
  ctx.fillRect(bx + bodyW * 0.14, by + bodyH * 0.03, bodyW * 0.72, bodyH * 0.10);
  ctx.fillRect(bx + bodyW * 0.14, by + bodyH * 0.03, bodyW * 0.10, bodyH * 0.20);
  ctx.fillRect(bx + bodyW * 0.76, by + bodyH * 0.03, bodyW * 0.10, bodyH * 0.20);
  // Eyes (whites + pupils)
  ctx.fillStyle = '#fff';
  ctx.fillRect(bx + bodyW * 0.28, by + bodyH * 0.12, bodyW * 0.16, bodyH * 0.08);
  ctx.fillRect(bx + bodyW * 0.57, by + bodyH * 0.12, bodyW * 0.16, bodyH * 0.08);
  ctx.fillStyle = '#222';
  ctx.fillRect(bx + bodyW * 0.33, by + bodyH * 0.14, bodyW * 0.08, bodyH * 0.05);
  ctx.fillRect(bx + bodyW * 0.62, by + bodyH * 0.14, bodyW * 0.08, bodyH * 0.05);

  // Role icon
  ctx.font = `${11 * sc}px Inter, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText(ROLE_ICONS[role] || '🤖', cx, by - 2 * sc);

  // Name tag
  const nameStr = ROLE_NAMES[role] || role;
  ctx.font = `bold ${9 * sc}px Inter, system-ui, sans-serif`;
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.fillText(nameStr, cx, by - 16 * sc);

  // Task hint for thinking agents
  if (status === 'thinking' && agent && agent.task) {
    const taskShort = (agent.task || '').replace(/^\[Скилл:[^\]]+\]\s*/, '').slice(0, 28);
    if (taskShort) {
      ctx.font = `${8 * sc}px Inter, system-ui, sans-serif`;
      ctx.fillStyle = 'rgba(255,213,79,0.7)';
      ctx.fillText(taskShort + (agent.task.length > 28 ? '…' : ''), cx, by - 26 * sc);
    }
  }

  // Status pulsing dot
  const dotColor = status === 'thinking' ? '#ffd54f' : status === 'done' ? '#81c784' : '#4a4a68';
  const pulse = status === 'thinking' ? 0.5 + 0.5 * Math.sin(now / 280) : 1;
  ctx.globalAlpha = pulse;
  ctx.fillStyle = dotColor;
  if (status === 'thinking') { ctx.shadowColor = dotColor; ctx.shadowBlur = 4 * sc; }
  ctx.beginPath();
  ctx.arc(bx + bodyW * 0.92 + 2 * sc, by + bodyH * 0.08, 3 * sc, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0; ctx.shadowColor = 'transparent';
  ctx.globalAlpha = 1;
}

// ---- Bubble drawing ----
function drawBubble(text, x, y, alpha) {
  const maxW = 190;
  ctx.font = "10px Inter, system-ui, sans-serif";
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
  ctx.font = "10px Inter, system-ui, sans-serif";
  ctx.textAlign = "left";
  lines.forEach((l, i) => ctx.fillText(l, bx + 8, by + 15 + i * 14));
  ctx.globalAlpha = 1;
}

// ---- Layout ----
function getMapOffset() {
  // Isometric mode: use tileToScreen() for all positioning.
  // This stub is kept for any legacy reference.
  return { ox: 0, oy: 0 };
}

// ---- Office feed panel ----
const _feedItems = [];
const _MAX_FEED = 40;

function addFeedItem(icon, who, text, type = '') {
  _feedItems.unshift({ icon, who, text, type, id: Date.now() + Math.random() });
  if (_feedItems.length > _MAX_FEED) _feedItems.pop();
  renderFeedList();
}

function renderFeedList() {
  const list = document.getElementById('office-feed-list');
  if (!list) return;
  list.innerHTML = _feedItems.slice(0, 25).map((item, i) => `
    <div class="feed-item type-${item.type}${i === 0 ? ' new' : ''}">
      <span class="fi-icon">${item.icon}</span>
      <div class="fi-body">
        ${item.who ? `<div class="fi-who">${escapeHtml(item.who)}</div>` : ''}
        <div class="fi-text">${escapeHtml(item.text)}</div>
      </div>
    </div>
  `).join('');
}

function setupFeedPanel() {
  const toggle = document.getElementById('office-feed-toggle');
  const panel = document.getElementById('office-feed-panel');
  if (toggle && panel) {
    toggle.addEventListener('click', () => panel.classList.toggle('collapsed'));
  }
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
    spawnAgent(event.agent_id, event.role, event.desk, event.task || "", event.skill || "");
    if (!hist) {
      addLog(event.agent_id, `принят на работу как ${event.role}`, event.role);
      const roleName = ROLE_NAMES[event.role] || event.role;
      addFeedItem('👋', '', `${roleName} нанят`, 'system');
    }
    // Восстанавливаем реальный статус агента из снапшота
    if (event.status && event.status !== "idle") {
      updateAgentStatus(event.agent_id, event.status, event.last_message || "");
    }
  }
  else if (event.type === "speech") {
    if (!hist) addBubble(event.agent_id, event.text);
    addLog(event.agent_id, event.text, getRole(event.agent_id), hist);
    onOfficeMessage({from: event.agent_id, role: getRole(event.agent_id), text: event.text}, hist);
    if (!hist) {
      updateAgentStatus(event.agent_id, "thinking", event.text);
      const role = getRole(event.agent_id);
      addFeedItem(ROLE_ICONS[role] || '🤖', agentDisplayName(event.agent_id), event.text, '');
    }
  }
  else if (event.type === "office_chat") {
    onOfficeMessage({from: event.from, role: event.role, text: event.text}, hist);
  }
  else if (event.type === "agent_message") {
    if (!hist) onAgentMessage(event);
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
      loadCosts();
      addFeedItem('✅', agentDisplayName(event.agent_id), event.summary || 'задача выполнена', 'done');
    }
  }
  else if (event.type === "progress") {
    if (!hist) updateProgressBar(event);
  }
  else if (event.type === "system") {
    addLog("офис", event.text, "system", hist);
    if (!hist) addFeedItem('🏢', '', event.text, 'system');
  }
  else if (event.type === "error") {
    addLog(event.agent_id, "⚠ " + event.text, getRole(event.agent_id), hist);
    if (!hist) addFeedItem('⚠️', agentDisplayName(event.agent_id) || '', event.text, 'error');
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
  else if (event.type === "integration_used") {
    if (!hist) {
      showToast(event.text || "⚙️ Действие во внешнем сервисе", "ok");
      addFeedItem('🔌', '', event.text || 'Внешний сервис', 'system');
      if (event.integration === "website") loadLeads();  // опубликован/обновлён лендинг
    }
  }
  else if (event.type === "file_written") {
    if (!hist) {
      loadFiles();
      addFeedItem('💻', '', `Файл записан: ${event.path || ''}`, 'system');
      if (_currentView !== "code") {
        const badge = document.getElementById("badge-code");
        if (badge) { badge.classList.add("badge-pulse"); setTimeout(() => badge.classList.remove("badge-pulse"), 2000); }
      }
    }
  }
  else if (event.type === "lead_captured") {
    if (!hist) {
      showToast(event.text || "🎯 Новая заявка", "ok");
      addFeedItem('🎯', '', event.text || 'Новая заявка', 'done');
      loadLeads();
      if (_currentView !== "leads") {
        const badge = document.getElementById("badge-leads");
        if (badge) { badge.classList.add("badge-pulse"); setTimeout(() => badge.classList.remove("badge-pulse"), 2000); }
      }
    }
  }
  else if (event.type === "question_answered") {
    // Вопрос закрыт (ответили в чате или таймаут) — обновим открытый тред
    if (!hist && activeThread === event.agent_id && _currentView === "chat") {
      loadAgentThread(event.agent_id);
    }
  }
}

function getRole(agent_id) {
  return agents[agent_id]?.role || "unknown";
}

function agentDisplayName(id) {
  const a = agents[id];
  if (!a) return ROLE_NAMES[roleFromId(id)] || id;
  const base = ROLE_NAMES[a.role] || a.role;
  // Если в офисе несколько агентов одной роли — добавляем номер, чтобы различать
  const sameRole = Object.values(agents).filter(x => x.role === a.role).length;
  if (sameRole > 1) {
    const m = id.match(/_(\d+)$/);
    return base + (m ? " " + m[1] : "");
  }
  return base;
}

function spawnAgent(agent_id, role, desk, task, skill = "") {
  if (agents[agent_id]) return;
  // При восстановлении скилл приходит внутри задачи: "[Скилл: ...] ..."
  if (!skill && task) {
    const m = task.match(/^\[Скилл:\s*([^\]]+)\]/);
    if (m) skill = m[1].trim();
  }
  const dp = getDeskPosition(desk);
  const center = tileToScreen(Math.floor(COLS / 2), Math.floor(ROWS / 2));
  const target = tileToScreen(dp.tx, dp.ty);

  agents[agent_id] = {
    role, desk, task, skill,
    x: center.x, y: center.y,
    tx: target.x, ty: target.y,
    color: ROLE_COLORS[role] || "#aaaaaa",
    status: "idle",
    bubble: null,
  };

  updateSidebar();
  if (_currentView === "chat") renderThreadList();
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
  t.className = `toast ${type}`;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity 0.4s"; setTimeout(() => t.remove(), 400); }, 3500);
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
        <span style="color:${a.color}">${ROLE_ICONS[a.role]||""} ${escapeHtml(agentDisplayName(id))}</span>
      </div>
      <div class="ac-status">${escapeHtml((a.skill || a.lastMsg || a.task || id).slice(0,120))}</div>
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
  roleEl.textContent = `${ROLE_ICONS[localRole] || "🤖"} ${agentDisplayName(agentId)}`;
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
  const c = (data && data.cost) || {};
  const costLine = (c.calls)
    ? `<br><span style="color:#6ee7a8;font-size:11px">💸 ${fmtCost(c.cost)} · ${fmtTokens((c.in_tokens||0)+(c.out_tokens||0))} токенов · ${c.calls} вызовов</span>`
    : "";
  curEl.innerHTML = `<b style="color:${localColor}">${escapeHtml(statusWord)}</b><br>Сейчас делает: ${escapeHtml(current)}${costLine}`;

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

  // Background gradient
  const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
  grad.addColorStop(0, '#0c0a18');
  grad.addColorStop(1, '#080610');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Isometric map
  drawIsoMap();

  // Agents (draw all chars after map so they appear on top)
  const now = Date.now();
  for (const [id, a] of Object.entries(agents)) {
    // Selection ring
    if (id === selectedAgentId) {
      ctx.beginPath();
      ctx.ellipse(a.x, a.y, 14 * isoScale, 7 * isoScale, 0, 0, Math.PI * 2);
      ctx.strokeStyle = a.color;
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.5 + 0.3 * Math.sin(now / 300);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    drawIsoCharacter(a.x, a.y, a.color, a.role, a.status, a);
  }

  // Speech bubbles
  for (let i = bubbles.length - 1; i >= 0; i--) {
    const b = bubbles[i];
    const age = now - b.born;
    if (age > b.duration) { bubbles.splice(i, 1); continue; }
    const agent = agents[b.agent_id];
    if (!agent) { bubbles.splice(i, 1); continue; }
    const alpha = age < b.duration - 800 ? 1 : (b.duration - age) / 800;
    // bubbles appear above head
    const bodyH = 30 * isoScale;
    drawBubble(b.text, agent.x, agent.y - bodyH - 10, alpha);
  }
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

  // ---- Zoom with mouse wheel (zoom toward cursor) ----
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const wrap = document.getElementById("game-wrap");
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const oldScale = isoScale;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    isoScale = Math.max(0.25, Math.min(3.5, isoScale * factor));

    // The base origin (camX=0, camY=0) maps tile midpoint to canvas center.
    // When scale changes, we shift camX/camY so the world-point under the
    // cursor stays fixed on screen.
    // Screen position of any world-tile = f(scale, camX, camY).
    // We need: f(newScale, newCam) = f(oldScale, oldCam) for the cursor tile.
    // Simplification: the screen coords scale linearly around the base origin.
    // base_x = W/2 - midDX * tw;  screen_x = base_x + camX + col*tw - row*tw
    // After scale change, base_x changes by (newScale-oldScale)*(-midDX*ISO_W/2 + (col-row)*ISO_W/2)
    // Easier: just keep the pixel under cursor fixed by noting:
    //   screenX(tile) = baseX(scale) + camX + (col-row)*tw
    // We want screenX unchanged ⟹ camX_new = camX + (baseX(old) - baseX(new))
    // baseX = W/2 - midDX * scale * ISO_W/2
    const midDX = (COLS - ROWS) / 2;
    const midSum = (COLS - 1 + ROWS - 1) / 2;
    const W = wrap.clientWidth, H = wrap.clientHeight;
    const baseXOld = W / 2 - midDX * (oldScale * ISO_W / 2);
    const baseYOld = H / 2 - midSum * (oldScale * ISO_H / 2) + WALL_H * oldScale * 0.5;
    const baseXNew = W / 2 - midDX * (isoScale * ISO_W / 2);
    const baseYNew = H / 2 - midSum * (isoScale * ISO_H / 2) + WALL_H * isoScale * 0.5;
    // Point under cursor in old coords: (mx - baseXOld - camX) = (col-row)*tw_old → world_x
    // We want: baseXNew + camXNew + world_x * (isoScale/oldScale) * ... hmm, let's use ratio:
    // Equivalent simple approach: camX adjusts so point mx stays fixed:
    //   mx = baseXOld + camX + world_x_offset   →  world_x_offset = mx - baseXOld - camX
    //   mx = baseXNew + camXNew + world_x_offset * (isoScale/oldScale)
    const wxOffset = mx - baseXOld - camX;
    const wyOffset = my - baseYOld - camY;
    camX = mx - baseXNew - wxOffset * (isoScale / oldScale);
    camY = my - baseYNew - wyOffset * (isoScale / oldScale);
    syncAgentTargets();
  }, { passive: false });

  // ---- Pan ----
  canvas.addEventListener("mousedown", (e) => {
    _panActive = true;
    moved = false;
    _panStartX = e.clientX; _panStartY = e.clientY;
    _panStartCamX = camX; _panStartCamY = camY;
    downX = e.clientX; downY = e.clientY;
  });

  // ---- Hover cursor ----
  canvas.addEventListener("mousemove", (e) => {
    if (_panActive) {
      const dx = e.clientX - _panStartX;
      const dy = e.clientY - _panStartY;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved = true;
      camX = _panStartCamX + dx;
      camY = _panStartCamY + dy;
      syncAgentTargets();
      canvas.style.cursor = "grabbing";
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    canvas.style.cursor = findAgentAt(px, py) ? "pointer" : "grab";
  });

  window.addEventListener("mouseup", (e) => {
    const wasPanning = _panActive;
    _panActive = false;
    // Реагируем на клик по агенту ТОЛЬКО если кликнули по самому канвасу.
    // Иначе клики по оверлеям/полям ввода (онбординг, формы) крали бы фокус.
    if (e.target !== canvas) return;
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    canvas.style.cursor = findAgentAt(px, py) ? "pointer" : "grab";
    if (!moved && !wasPanning) {
      const id = findAgentAt(px, py);
      if (id) openChat(id);
    }
  });
}

function syncAgentTargets() {
  for (const a of Object.values(agents)) {
    const dp = getDeskPosition(a.desk);
    const t = tileToScreen(dp.tx, dp.ty);
    a.tx = t.x; a.ty = t.y;
  }
}

// ============================================================
// ЧАТЫ: общий канал офиса + личные чаты с агентами (вкладка «Чаты»)
// ============================================================
let activeThread = null;          // "office" | agent_id | null
const threadUnread = {};          // id -> число непрочитанных
let threadMeta = {};              // agent_id -> {last_text, last_ts, unanswered}

// Клик по агенту на карте → открыть вкладку «Чаты» с этим агентом
function openChat(agentId) {
  selectedAgentId = agentId;
  switchView("chat");
  selectThread(agentId);
}

async function loadThreadList() {
  try {
    const r = await fetch("/api/threads");
    const d = await r.json();
    threadMeta = d.threads || {};
  } catch { threadMeta = {}; }
  // Засеваем непрочитанные открытыми вопросами (на случай перезагрузки)
  for (const [id, m] of Object.entries(threadMeta)) {
    if (!(id in threadUnread)) threadUnread[id] = m.unanswered || 0;
  }
  renderThreadList();
  updateChatBadge();
}

function renderThreadList() {
  const sb = document.getElementById("chats-sidebar");
  if (!sb) return;
  sb.innerHTML = "";
  sb.appendChild(buildChatItem("office", "🏢", "Общий чат офиса", "Все агенты и вы", "#8fd3ff"));
  Object.keys(agents).sort().forEach((id) => {
    const a = agents[id];
    const meta = threadMeta[id] || {};
    const subtitle = meta.last_text || (a.skill ? "спец.: " + a.skill : "");
    sb.appendChild(buildChatItem(
      id, ROLE_ICONS[a.role] || "🤖", agentDisplayName(id),
      subtitle, a.color));
  });
}

function buildChatItem(id, icon, name, last, color) {
  const item = document.createElement("div");
  item.className = "chat-item" + (activeThread === id ? " active" : "");
  const unread = threadUnread[id] || 0;
  item.innerHTML = `
    <div class="ci-avatar" style="color:${color||"#cfd"}">${icon}</div>
    <div class="ci-body">
      <div class="ci-name">${escapeHtml(name)}</div>
      <div class="ci-last">${escapeHtml((last || "").slice(0, 42))}</div>
    </div>
    ${unread ? `<div class="ci-badge">${unread}</div>` : ""}
  `;
  item.addEventListener("click", () => selectThread(id));
  return item;
}

async function selectThread(id) {
  activeThread = id;
  threadUnread[id] = 0;
  selectedAgentId = id === "office" ? null : id;
  const input = document.getElementById("chat-compose-input");
  const send = document.getElementById("chat-compose-send");
  const head = document.getElementById("cth-title");
  input.disabled = false; send.disabled = false;
  if (id === "office") {
    head.textContent = "🏢 Общий чат офиса";
    input.placeholder = "Написать всем агентам...";
    await loadOfficeFeed();
  } else {
    const a = agents[id];
    head.textContent = `${ROLE_ICONS[a?.role] || "🤖"} ${agentDisplayName(id)}` + (a?.skill ? ` · ${a.skill}` : "");
    input.placeholder = "Сообщение агенту...";
    await loadAgentThread(id);
  }
  renderThreadList();
  updateChatBadge();
  input.focus();
}

function _feedEl() { return document.getElementById("chat-feed"); }

function renderBubble({icon, who, text, cls, question, answered}) {
  const feed = _feedEl();
  const no = feed.querySelector(".empty-note");
  if (no) no.remove();
  const wrap = document.createElement("div");
  wrap.className = "cf-msg" + (cls || "");
  const hint = (question && !answered)
    ? `<div class="cf-question-hint">⏳ агент ждёт вашего ответа — напишите ниже</div>` : "";
  wrap.innerHTML = `
    <div class="cf-avatar">${icon}</div>
    <div class="cf-body">
      <div class="cf-who">${escapeHtml(who)}</div>
      <div class="cf-text${question ? " is-question" : ""}">${escapeHtml(text || "")}</div>
      ${hint}
    </div>`;
  feed.appendChild(wrap);
  feed.scrollTop = feed.scrollHeight;
}

function renderOfficeMsg(msg) {
  const from = msg.from || "agent";
  const role = msg.role || roleFromId(from);
  const isUser = from === "user" || role === "user";
  const isSystem = from === "system" || role === "system";
  renderBubble({
    icon: isUser ? "🧑" : isSystem ? "🏢" : (ROLE_ICONS[role] || "🤖"),
    who: isUser ? "Вы" : isSystem ? "Офис" : (agents[from] ? agentDisplayName(from) : (ROLE_NAMES[role] || role)),
    text: msg.text,
    cls: isUser ? " user-msg" : isSystem ? " system-msg" : "",
  });
}

function renderThreadMsg(id, m) {
  const a = agents[id];
  const isUser = m.from === "user";
  const isSystem = m.from === "system";
  renderBubble({
    icon: isUser ? "🧑" : isSystem ? "🏢" : (ROLE_ICONS[a?.role] || "🤖"),
    who: isUser ? "Вы" : isSystem ? "Офис" : agentDisplayName(id),
    text: m.text,
    cls: isUser ? " user-msg" : isSystem ? " system-msg" : "",
    question: m.kind === "question",
    answered: m.answered,
  });
}

async function loadOfficeFeed() {
  const feed = _feedEl();
  feed.innerHTML = "";
  try {
    const r = await fetch("/api/chat");
    const d = await r.json();
    const msgs = d.messages || [];
    if (!msgs.length) { feed.innerHTML = `<div class="empty-note">Пока нет сообщений</div>`; return; }
    msgs.forEach(m => renderOfficeMsg(m));
  } catch {}
}

async function loadAgentThread(id) {
  const feed = _feedEl();
  feed.innerHTML = "";
  try {
    const r = await fetch(`/api/thread/${encodeURIComponent(id)}`);
    const d = await r.json();
    const msgs = d.messages || [];
    if (!msgs.length) {
      const a = agents[id];
      feed.innerHTML = `<div class="empty-note">Чат с агентом «${escapeHtml(ROLE_NAMES[a?.role] || id)}» пуст. Напишите — он ответит.</div>`;
      return;
    }
    msgs.forEach(m => renderThreadMsg(id, m));
  } catch {}
}

// Входящее сообщение в общий канал (speech агентов или office_chat)
function onOfficeMessage(msg, historical = false) {
  if (activeThread === "office" && _currentView === "chat") {
    renderOfficeMsg(msg);
  } else if (!historical) {
    const isUser = (msg.from === "user") || (msg.role === "user");
    if (!isUser) bumpUnread("office");
  }
}

// Входящее сообщение в личный чат с агентом (вопрос или реплика)
function onAgentMessage(event) {
  const id = event.agent_id;
  const isQuestion = event.kind === "question";
  if (activeThread === id && _currentView === "chat") {
    renderThreadMsg(id, {from: event.from, text: event.text,
                         kind: event.kind, answered: false});
  } else if (event.from !== "user") {
    bumpUnread(id);
    if (isQuestion) {
      const a = agents[id];
      const who = ROLE_NAMES[a?.role] || id;
      showToast(`❓ ${who} спрашивает — откройте «Чаты»`, "ok");
      const badge = document.getElementById("badge-chat");
      if (badge) { badge.classList.add("badge-pulse"); setTimeout(() => badge.classList.remove("badge-pulse"), 2000); }
    }
  }
  // обновим превью в списке тредов
  if (event.from !== "user") {
    threadMeta[id] = threadMeta[id] || {};
    threadMeta[id].last_text = event.text;
  }
  if (_currentView === "chat") renderThreadList();
}

function bumpUnread(id) {
  if (activeThread === id && _currentView === "chat") return;
  threadUnread[id] = (threadUnread[id] || 0) + 1;
  updateChatBadge();
  if (_currentView === "chat") renderThreadList();
}

function updateChatBadge() {
  const total = Object.values(threadUnread).reduce((s, n) => s + (n || 0), 0);
  const badge = document.getElementById("badge-chat");
  if (!badge) return;
  badge.textContent = total || "";
  badge.style.display = total ? "block" : "none";
}

async function sendActiveMessage() {
  const input = document.getElementById("chat-compose-input");
  const send = document.getElementById("chat-compose-send");
  const text = (input.value || "").trim();
  if (!text || !activeThread) return;
  input.value = "";

  // Сообщения отрисовываются по событиям SSE (единый источник) — локально не дублируем
  if (activeThread === "office") {
    try {
      await fetch("/api/chat", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text}),
      });
    } catch { showToast("❌ Не удалось отправить", "err"); }
    return;
  }

  const agentId = activeThread;
  send.disabled = true;
  const feed = _feedEl();
  const typing = document.createElement("div");
  typing.className = "cf-msg"; typing.id = "thread-typing";
  typing.innerHTML = `<div class="cf-avatar">🤖</div><div class="cf-body"><div class="cf-text">печатает…</div></div>`;
  feed.appendChild(typing); feed.scrollTop = feed.scrollHeight;
  try {
    const r = await fetch("/api/ask", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({agent_id: agentId, message: text}),
    });
    const d = await r.json();
    typing.remove();
    if (d.error) renderThreadMsg(agentId, {from: "agent", text: "⚠ " + d.error});
    else if (d.answered) renderThreadMsg(agentId, {from: "system", text: "✓ Ответ отправлен агенту"});
    // d.reply приходит через SSE agent_message — отдельно не рендерим
  } catch (e) {
    typing.remove();
    renderThreadMsg(agentId, {from: "agent", text: "⚠ Не удалось связаться: " + e.message});
  } finally {
    send.disabled = false;
    document.getElementById("chat-compose-input").focus();
  }
}

function setupChat() {
  const sendBtn = document.getElementById("chat-compose-send");
  const inp = document.getElementById("chat-compose-input");
  if (sendBtn) sendBtn.addEventListener("click", sendActiveMessage);
  if (inp) inp.addEventListener("keydown", (e) => { if (e.key === "Enter") sendActiveMessage(); });
}

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

// ---- Аутентификация (Phase 0) ----
let _githubAvailable = false;

async function checkAuth() {
  let d;
  try { d = await (await fetch("/api/me")).json(); }
  catch { d = { authenticated: false, github_available: false, dev_login: true }; }
  const gate = document.getElementById("login-gate");
  if (!d.authenticated) {
    _githubAvailable = !!d.github_available;
    gate.classList.remove("hidden");
    // Кнопка «Войти через GitHub» — основной способ, показываем всегда
    document.getElementById("btn-github-login").classList.remove("hidden");
    document.getElementById("github-missing").classList.toggle("hidden", d.github_available);
    document.getElementById("dev-login-block").classList.toggle("hidden", !d.dev_login);
    return false;
  }
  gate.classList.add("hidden");
  renderUserChip(d.user);
  return true;
}

function renderUserChip(user) {
  const chip = document.getElementById("user-chip");
  if (!chip || !user) return;
  chip.classList.remove("hidden");
  chip.style.display = "flex";
  const tbAv = document.getElementById("tb-avatar");
  const tbName = document.getElementById("tb-username");
  if (tbAv) tbAv.innerHTML = user.avatar ? `<img src="${user.avatar}" style="width:100%;height:100%;border-radius:50%;object-fit:cover">` : '👤';
  if (tbName) tbName.textContent = user.name || user.github_login || user.email || '';
}

// ---- Device Flow ----
let _deviceCode = "";
let _devicePollTimer = null;

function _showDeviceStep(name) {
  ["code","wait","ok","err"].forEach(s =>
    document.getElementById(`device-step-${s}`).classList.toggle("hidden", s !== name));
}

async function startDeviceFlow() {
  document.getElementById("device-modal").classList.remove("hidden");
  _showDeviceStep("code");
  document.getElementById("dv-code").textContent = "…";

  let data;
  try {
    const r = await fetch("/auth/github/device/start", { method: "POST" });
    data = await r.json();
    if (data.error) throw new Error(data.error);
  } catch (e) {
    _showDeviceStep("err");
    document.getElementById("dv-err-text").textContent = e.message;
    return;
  }

  _deviceCode = data.device_code;
  document.getElementById("dv-code").textContent = data.user_code || "------";
  document.getElementById("dv-link").href = data.verification_uri || "https://github.com/login/device";
  document.getElementById("dv-copy").onclick = () => {
    navigator.clipboard.writeText(data.user_code || "").catch(() => {});
    showToast("Код скопирован", "ok");
  };
}

async function pollDeviceFlow() {
  if (!_deviceCode) return;
  _showDeviceStep("wait");
  clearInterval(_devicePollTimer);

  const tryPoll = async () => {
    try {
      const r = await fetch("/auth/github/device/poll", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_code: _deviceCode }),
      });
      const d = await r.json();
      if (d.ok) {
        clearInterval(_devicePollTimer);
        _showDeviceStep("ok");
        setTimeout(() => location.reload(), 1200);
        return;
      }
      const err = d.error || "";
      if (err === "expired_token" || err === "access_denied") {
        clearInterval(_devicePollTimer);
        _showDeviceStep("err");
        document.getElementById("dv-err-text").textContent =
          err === "expired_token" ? "Код истёк — попробуйте снова." : "Доступ отклонён.";
      }
    } catch { /* сетевая ошибка — продолжаем */ }
  };

  await tryPoll();
  _devicePollTimer = setInterval(tryPoll, 5000);
}

function setupLogin() {
  const gh = document.getElementById("btn-github-login");
  if (gh) gh.addEventListener("click", (e) => {
    e.preventDefault();
    if (!_githubAvailable) {
      document.getElementById("github-missing").classList.remove("hidden");
      return;
    }
    startDeviceFlow();
  });

  document.getElementById("dv-confirm")?.addEventListener("click", pollDeviceFlow);
  document.getElementById("dv-cancel")?.addEventListener("click", () => {
    clearInterval(_devicePollTimer);
    document.getElementById("device-modal").classList.add("hidden");
  });
  document.getElementById("dv-retry")?.addEventListener("click", startDeviceFlow);

  const dev = document.getElementById("btn-dev-login");
  if (dev) dev.addEventListener("click", async () => {
    const email = (document.getElementById("dev-email").value || "").trim();
    try {
      await fetch("/auth/dev-login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      location.reload();
    } catch { showToast("❌ Не удалось войти", "err"); }
  });
}

// ---- Живой лендинг: parallax-наклон сцены + scroll-reveal ----
function setupLanding() {
  const scene = document.getElementById("scene3d");
  const hero = document.querySelector(".ld-hero-right");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (scene && hero && !reduce) {
    hero.addEventListener("mousemove", (e) => {
      const r = hero.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;   // -0.5..0.5
      const py = (e.clientY - r.top) / r.height - 0.5;
      scene.style.transform = `rotateY(${px * 14}deg) rotateX(${-py * 10}deg)`;
    });
    hero.addEventListener("mouseleave", () => { scene.style.transform = ""; });
  }

  // Scroll-reveal карточек «как это работает» (детерминированно, без IO)
  const reveals = [...document.querySelectorAll("#intake .reveal")];
  const scroller = document.getElementById("landing-scroll");
  if (reveals.length) {
    if (reduce) {
      reveals.forEach((el) => el.classList.add("in"));
    } else {
      const checkReveal = () => {
        const vh = window.innerHeight;
        reveals.forEach((el) => {
          if (el.classList.contains("in")) return;
          const r = el.getBoundingClientRect();
          // показываем, когда верх карточки заходит в нижние 85% экрана (или уже выше)
          if (r.top < vh * 0.85) el.classList.add("in");
        });
      };
      checkReveal();
      scroller?.addEventListener("scroll", checkReveal, { passive: true });
      window.addEventListener("resize", checkReveal, { passive: true });
    }
  }
}

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
    syncAgentTargets();
  }
  if (name === "progress") {
    loadProgress();
  }
  if (name === "leads") {
    loadLeads();
  }
  if (name === "code") {
    loadFiles();
  }
  if (name === "chat") {
    loadThreadList();
    if (!activeThread) selectThread("office");
    else selectThread(activeThread);
  }
  if (name === "account") {
    loadAccount();
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
// ЛИДЫ И ЛЕНДИНГИ
// ============================================================
let sitesCache = [];
let leadsCache = [];

async function loadLeads() {
  try {
    const [rs, rl] = await Promise.all([fetch("/api/sites"), fetch("/api/leads")]);
    sitesCache = (await rs.json()).sites || [];
    leadsCache = (await rl.json()).leads || [];
  } catch { sitesCache = []; leadsCache = []; }
  renderSites();
  renderLeads();
  updateLeadsBadge();
}

function renderSites() {
  const list = document.getElementById("sites-list");
  if (!list) return;
  const no = document.getElementById("no-sites");
  list.querySelectorAll(".site-card").forEach(c => c.remove());
  if (no) no.style.display = sitesCache.length ? "none" : "block";
  sitesCache.forEach((s) => {
    const card = document.createElement("div");
    card.className = "site-card";
    const url = s.url || `/site/${s.slug}`;
    card.innerHTML = `
      <div class="sc-body">
        <div class="sc-title">🌐 ${escapeHtml(s.title || s.slug)}</div>
        <div class="sc-url"><a href="${url}" target="_blank" rel="noopener">${location.origin}${url} ↗</a></div>
      </div>
      <span class="sc-count">${s.leads || 0} заявок</span>
    `;
    list.appendChild(card);
  });
}

function renderLeads() {
  const list = document.getElementById("leads-list");
  if (!list) return;
  const no = document.getElementById("no-leads");
  list.querySelectorAll(".lead-card").forEach(c => c.remove());
  if (no) no.style.display = leadsCache.length ? "none" : "block";
  leadsCache.forEach((l) => {
    const card = document.createElement("div");
    card.className = "lead-card";
    const t = l.ts ? new Date(l.ts * 1000).toLocaleString("ru", {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}) : "";
    const site = sitesCache.find(s => s.slug === l.slug);
    card.innerHTML = `
      <div class="lc-top">
        <span class="lc-name">${escapeHtml(l.name || "Без имени")}</span>
        <span class="lc-time">${t}</span>
      </div>
      <div class="lc-contact">${escapeHtml(l.contact || "")}</div>
      ${l.message ? `<div class="lc-msg">${escapeHtml(l.message)}</div>` : ""}
      <div class="lc-src">с лендинга: ${escapeHtml(site ? (site.title || l.slug) : l.slug)}</div>
    `;
    list.appendChild(card);
  });
}

function updateLeadsBadge() {
  const badge = document.getElementById("badge-leads");
  if (!badge) return;
  badge.textContent = leadsCache.length ? String(leadsCache.length) : "";
  badge.style.display = leadsCache.length ? "block" : "none";
}

// ============================================================
// КОД ПРОЕКТА (рабочая папка агентов)
// ============================================================
let filesCache = [];

async function loadFiles() {
  try {
    const r = await fetch("/api/files");
    filesCache = (await r.json()).files || [];
  } catch { filesCache = []; }
  renderFiles();
  const badge = document.getElementById("badge-code");
  if (badge) { badge.textContent = filesCache.length || ""; badge.style.display = filesCache.length ? "block" : "none"; }
}

function renderFiles() {
  const list = document.getElementById("code-files");
  if (!list) return;
  const no = document.getElementById("no-files");
  list.querySelectorAll(".file-row").forEach(c => c.remove());
  if (no) no.style.display = filesCache.length ? "none" : "block";
  filesCache.forEach((f) => {
    const row = document.createElement("div");
    row.className = "file-row";
    row.innerHTML = `<span class="fr-path">📄 ${escapeHtml(f.path)}</span><span class="fr-size">${f.size} б</span>`;
    row.addEventListener("click", () => openFile(f.path));
    list.appendChild(row);
  });
}

async function openFile(path) {
  try {
    const r = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
    const content = await r.text();
    ftCurrentIdx = -1;
    ftRawContent = content;
    document.getElementById("ft-who").innerHTML = `💻 <b>${escapeHtml(path)}</b>`;
    document.getElementById("fulltext-body").textContent = content;
    document.getElementById("fulltext-overlay").classList.remove("hidden");
  } catch (e) { showToast("❌ Не удалось открыть файл", "err"); }
}

// ============================================================
// УЧЁТ ТОКЕНОВ И СТОИМОСТИ (ROI)
// ============================================================
function fmtCost(c) {
  c = c || 0;
  if (c === 0) return "$0.0000";
  return c >= 0.01 ? "$" + c.toFixed(4) : "$" + c.toFixed(5);
}

function fmtTokens(n) {
  n = n || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}

async function loadCosts() {
  try {
    const r = await fetch("/api/costs");
    const d = await r.json();
    const t = d.total || {};
    const el = document.getElementById("cost-meter");
    if (el) {
      el.textContent = `💸 ${fmtCost(t.cost)}`;
      const tok = (t.in_tokens || 0) + (t.out_tokens || 0);
      el.title = `Токенов: ${fmtTokens(tok)} (вход ${fmtTokens(t.in_tokens)} / выход ${fmtTokens(t.out_tokens)}), вызовов: ${t.calls||0}`;
    }
  } catch {}
}

// ============================================================
// ПЕРСОНАЛЬНЫЙ КЛЮЧ К AI (per-tenant)
// ============================================================
async function loadLlmSettings() {
  let d;
  try { d = await (await fetch("/api/llm-settings")).json(); }
  catch { return; }
  const st = document.getElementById("lk-status");
  const base = document.getElementById("lk-base");
  const key = document.getElementById("lk-key");
  if (base && !base.value) base.value = d.base_url || "";
  if (st) {
    if (d.has_own_key) {
      st.className = "lk-status own";
      st.textContent = `✅ Используется ваш ключ (${d.key_mask})`;
    } else {
      st.className = "lk-status shared";
      st.textContent = "⚠ Сейчас используется общий ключ оператора. Укажите свой — расход пойдёт с вашего счёта.";
    }
  }
  if (key) key.placeholder = d.has_own_key ? "•••• (задан, введите новый для замены)" : "sk-...";
}

function setupLlmSettings() {
  const save = document.getElementById("lk-save");
  const clear = document.getElementById("lk-clear");
  if (save) save.addEventListener("click", async () => {
    const base_url = document.getElementById("lk-base").value.trim();
    const api_key = document.getElementById("lk-key").value.trim();
    try {
      await fetch("/api/llm-settings", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url, api_key }),
      });
      document.getElementById("lk-key").value = "";
      showToast("✅ Ключ сохранён", "ok");
      loadLlmSettings();
    } catch { showToast("❌ Не удалось сохранить", "err"); }
  });
  if (clear) clear.addEventListener("click", async () => {
    if (!confirm("Удалить свой ключ и вернуться на общий ключ оператора?")) return;
    await fetch("/api/llm-settings/clear", { method: "POST" }).catch(() => {});
    loadLlmSettings();
  });
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
  loadIntegrations();  // статусы интеграций зависят от подключений
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

// ---- Каталог готовых интеграций ----
let integrationsCache = [];

async function loadIntegrations() {
  try {
    const r = await fetch("/api/integrations");
    const d = await r.json();
    integrationsCache = d.integrations || [];
  } catch { integrationsCache = []; }
  renderIntegrations();
}

function renderIntegrations() {
  const wrap = document.getElementById("integrations-catalog");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (!integrationsCache.length) {
    wrap.innerHTML = `<div class="empty-note">Нет доступных интеграций</div>`;
    return;
  }
  integrationsCache.forEach((it) => {
    const card = document.createElement("div");
    card.className = "integ-card";
    const acts = (it.actions || []).map(a => a.name).join(", ") || "—";
    const statusCls = it.connected ? "on" : "off";
    const statusTxt = it.connected ? "✅ подключено" : "⚪ не подключено";
    card.innerHTML = `
      <div class="ic-head">
        <span class="ic-icon">${escapeHtml(it.icon||"⚙️")}</span>
        <span class="ic-name">${escapeHtml(it.title||it.name)}</span>
        <span class="ic-status ${statusCls}">${statusTxt}</span>
      </div>
      <div class="ic-desc">${escapeHtml(it.description||"")}</div>
      <div class="ic-actions-list">Действия: ${escapeHtml(acts)}</div>
      ${it.connected ? "" : `<div class="ic-howto">${escapeHtml(it.how_to||"")}</div>`}
      <div class="ic-btns">
        <button class="dc-btn integ-connect">${
          it.connected ? "✎ Изменить доступ"
          : it.oauth_url ? `🔗 Подключить через ${escapeHtml(it.title)}`
          : "🔌 Подключить"}</button>
        ${it.connected ? `<button class="dc-btn integ-test">🧪 Проверить</button>` : ""}
      </div>
    `;
    card.querySelector(".integ-connect").addEventListener("click", () => {
      if (it.oauth_url && !it.connected) { window.location.href = it.oauth_url; return; }
      connectIntegration(it);
    });
    const testBtn = card.querySelector(".integ-test");
    if (testBtn) testBtn.addEventListener("click", () => testIntegration(it));
    wrap.appendChild(card);
  });
}

function connectIntegration(it) {
  // Ищем уже существующее подключение с таким именем — тогда редактируем его
  const existing = connectionsCache.find(c =>
    (c.name||"").toLowerCase() === (it.title||"").toLowerCase() ||
    (c.name||"").toLowerCase() === (it.name||"").toLowerCase());
  if (existing) { openConnForm(existing); return; }
  const fields = {};
  (it.cred_fields || []).forEach(f => { fields[f.key] = ""; });
  openConnForm({ name: it.title || it.name, type: "api", fields,
                 note: `Интеграция: ${it.name}` });
}

async function testIntegration(it) {
  showToast(`🧪 Проверяю ${it.title}...`, "ok");
  try {
    const r = await fetch(`/api/integrations/${encodeURIComponent(it.name)}/test`, {method: "POST"});
    const d = await r.json();
    if (d.ok) showToast(`✅ ${it.title}: ${(d.result||"работает").slice(0,80)}`, "ok");
    else showToast(`❌ ${it.title}: ${(d.error||"ошибка").slice(0,80)}`, "err");
  } catch (e) { showToast(`❌ Ошибка проверки: ${e.message}`, "err"); }
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
  document.getElementById("conn-box-title").textContent = (conn && conn.id) ? "Изменить подключение" : "Новое подключение";
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

// ============================================================
// ACCOUNT TAB
// ============================================================
async function loadAccount() {
  const r = await apiFetch("/api/me");
  if (!r) return;
  const d = await r.json();
  if (!d.authenticated) return;

  const u = d.user || {};
  const ws = d.workspace || {};

  const av = document.getElementById("acc-avatar");
  if (av) av.innerHTML = u.avatar ? `<img src="${u.avatar}" alt="">` : "👤";
  const nm = document.getElementById("acc-name");
  if (nm) nm.textContent = u.name || u.github_login || u.email || "—";
  const em = document.getElementById("acc-email");
  if (em) em.textContent = [u.email, u.github_login ? `@${u.github_login}` : ""].filter(Boolean).join(" · ") || "—";

  const planEl = document.getElementById("acc-plan");
  if (planEl) {
    const plan = (ws.plan || "free").toLowerCase();
    planEl.textContent = plan.charAt(0).toUpperCase() + plan.slice(1);
    planEl.className = `acc-plan-badge ${plan === "pro" ? "pro" : "free"}`;
  }

  const wsName = document.getElementById("acc-ws-name");
  if (wsName && ws.name) wsName.value = ws.name;
}

function setupAccount() {
  document.getElementById("acc-upgrade-btn")?.addEventListener("click", () =>
    showToast("Биллинг скоро появится", "ok")
  );

  document.getElementById("acc-ws-save")?.addEventListener("click", async () => {
    const name = (document.getElementById("acc-ws-name")?.value || "").trim();
    if (!name) return;
    const r = await apiFetch("/api/workspace/name", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (r) { showToast("✅ Название сохранено", "ok"); }
  });

  document.getElementById("acc-reset-btn")?.addEventListener("click", async () => {
    if (!confirm("Сбросить офис? Все данные текущего клиента будут удалены.")) return;
    await apiFetch("/api/brief/reset", { method: "POST" });
    showToast("Офис сброшен", "ok");
    setTimeout(() => location.reload(), 800);
  });

  document.getElementById("acc-logout-btn")?.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST" }).catch(() => {});
    location.reload();
  });
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
  setupLogin();
  setupLanding();
  // Сначала проверяем вход: онбординг показываем только авторизованным
  checkAuth().then((ok) => { if (ok) checkBriefStatus(); });
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
    if (drawerAgentId) { const id = drawerAgentId; closeAgentDrawer(); openChat(id); }
  });

  // Progress bar
  buildProgressSteps();
  loadProgress();

  // Connections
  setupConnections();
  loadConnections();
  setupLlmSettings();
  loadLlmSettings();

  // Activity feed panel
  setupFeedPanel();

  // Account tab
  setupAccount();

  // Чаты (общий + личные с агентами)
  setupChat();
  loadThreadList();

  // Лиды и лендинги
  loadLeads();

  // Расход токенов/стоимость
  loadCosts();
  setInterval(loadCosts, 20000);

  // Код проекта
  loadFiles();

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
  updateScale();
  syncAgentTargets();
});
