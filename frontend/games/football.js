import { esc } from "../js/ui.js";

const TEAM_COLORS = [
  { fill: "#8b5cf6", ring: "#c4b5fd", label: "Binafsha" },
  { fill: "#fb7185", ring: "#fecdd3", label: "Qizil" },
];

let ctx = null;
let state = null;
let canvas = null;
let g = null;
let cw = 360;
let ch = 230;
let dpr = 1;
let raf = 0;
let moveTimer = 0;
let overlayTimer = 0;
let els = {};
let knob = null;
let dpad = null;
let smooth = new Map();
let ballSmooth = null;
let joy = { active: false, x: 0, y: 0, id: null };
let sprint = false;
let lastSent = 0;
let flash = 0;
const keys = new Set();

function slotTeam(slot) {
  if (!state) return 0;
  const per = state.per_team || 1;
  return slot < per ? 0 : 1;
}

function teamName(team) {
  const p = (state?.slots || []).find((s) => slotTeam(s.slot) === team);
  if (!team) return TEAM_COLORS[0].label;
  return p?.name || TEAM_COLORS[team].label;
}

function resize() {
  if (!canvas) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  cw = Math.max(260, Math.floor(rect.width));
  ch = Math.round(cw * 0.64);
  dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(cw * dpr);
  canvas.height = Math.round(ch * dpr);
  canvas.style.height = `${ch}px`;
  g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function sx(x) { return (x / 100) * cw; }
function sy(y) { return (y / 64) * ch; }

function drawPitch() {
  const grad = g.createLinearGradient(0, 0, 0, ch);
  grad.addColorStop(0, "#0c2f1f");
  grad.addColorStop(0.55, "#092518");
  grad.addColorStop(1, "#061a11");
  g.fillStyle = grad;
  g.fillRect(0, 0, cw, ch);

  const bands = 10;
  for (let i = 0; i < bands; i += 1) {
    g.fillStyle = i % 2 ? "rgba(255,255,255,.022)" : "rgba(0,0,0,.06)";
    g.fillRect((cw / bands) * i, 0, cw / bands, ch);
  }

  g.strokeStyle = "rgba(255,255,255,.22)";
  g.lineWidth = 1.5;
  const m = 5;
  g.strokeRect(m, m, cw - m * 2, ch - m * 2);

  g.beginPath();
  g.moveTo(cw / 2, m);
  g.lineTo(cw / 2, ch - m);
  g.stroke();
  g.beginPath();
  g.arc(cw / 2, ch / 2, Math.min(cw, ch) * 0.15, 0, Math.PI * 2);
  g.stroke();
  g.beginPath();
  g.arc(cw / 2, ch / 2, 2.2, 0, Math.PI * 2);
  g.fillStyle = "rgba(255,255,255,.35)";
  g.fill();

  const boxW = sx(16);
  const boxTop = sy(14);
  const boxH = sy(36);
  g.strokeRect(m, boxTop, boxW, boxH);
  g.strokeRect(cw - m - boxW, boxTop, boxW, boxH);

  const goalTop = sy(22);
  const goalH = sy(20);
  g.fillStyle = "rgba(255,255,255,.07)";
  g.fillRect(m, goalTop, sx(2.4), goalH);
  g.fillRect(cw - m - sx(2.4), goalTop, sx(2.4), goalH);
  g.strokeStyle = "rgba(255,255,255,.4)";
  g.strokeRect(m, goalTop, sx(2.4), goalH);
  g.strokeRect(cw - m - sx(2.4), goalTop, sx(2.4), goalH);

  g.strokeStyle = "rgba(255,255,255,.1)";
  g.lineWidth = 1;
  for (let i = 1; i < 4; i += 1) {
    const x = m + (sx(2.4) / 4) * i;
    g.beginPath();
    g.moveTo(x, goalTop);
    g.lineTo(x, goalTop + goalH);
    g.stroke();
    const x2 = cw - m - (sx(2.4) / 4) * i;
    g.beginPath();
    g.moveTo(x2, goalTop);
    g.lineTo(x2, goalTop + goalH);
    g.stroke();
  }
}

function drawEntity(ent, pos) {
  const x = sx(pos.x);
  const y = sy(pos.y);
  const r = Math.max(6, Math.min(cw, ch) * 0.026);
  const color = TEAM_COLORS[ent.t] || TEAM_COLORS[0];
  g.save();
  g.beginPath();
  g.ellipse(x, y + r * 0.85, r * 0.85, r * 0.32, 0, 0, Math.PI * 2);
  g.fillStyle = "rgba(0,0,0,.32)";
  g.fill();
  g.beginPath();
  g.arc(x, y, r, 0, Math.PI * 2);
  g.fillStyle = ent.gk ? "#f5c542" : color.fill;
  g.fill();
  g.lineWidth = 1.2;
  g.strokeStyle = "rgba(0,0,0,.45)";
  g.stroke();
  if (ent.human) {
    g.beginPath();
    g.arc(x, y, r + 2.6, 0, Math.PI * 2);
    g.strokeStyle = "rgba(255,255,255,.9)";
    g.lineWidth = 1.8;
    g.stroke();
  }
  if (ent.gk) {
    g.fillStyle = "rgba(0,0,0,.55)";
    g.font = `700 ${Math.round(r * 0.95)}px system-ui`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText("GK", x, y + 0.5);
  }
  const mine = state?.control?.[String(state.your_slot)] === ent.id;
  if (mine) {
    g.beginPath();
    g.moveTo(x, y - r - 4);
    g.lineTo(x - 4, y - r - 10);
    g.lineTo(x + 4, y - r - 10);
    g.closePath();
    g.fillStyle = "#f5c542";
    g.fill();
  }
  g.restore();
}

function drawBall(pos) {
  const x = sx(pos.x);
  const y = sy(pos.y);
  const r = Math.max(3.4, Math.min(cw, ch) * 0.017);
  g.beginPath();
  g.ellipse(x, y + r * 0.9, r * 0.85, r * 0.3, 0, 0, Math.PI * 2);
  g.fillStyle = "rgba(0,0,0,.35)";
  g.fill();
  const grad = g.createRadialGradient(x - r * 0.35, y - r * 0.4, r * 0.2, x, y, r);
  grad.addColorStop(0, "#ffffff");
  grad.addColorStop(1, "#cbd5e1");
  g.beginPath();
  g.arc(x, y, r, 0, Math.PI * 2);
  g.fillStyle = grad;
  g.fill();
  g.strokeStyle = "rgba(15,23,42,.55)";
  g.lineWidth = 1;
  g.stroke();
}

function lerpPoint(obj, tx, ty, factor, snapDistance) {
  if (!obj) return { x: tx, y: ty };
  const d = Math.hypot(tx - obj.x, ty - obj.y);
  if (snapDistance && d > snapDistance) {
    obj.x = tx;
    obj.y = ty;
  } else {
    obj.x += (tx - obj.x) * factor;
    obj.y += (ty - obj.y) * factor;
  }
  return obj;
}

function draw() {
  raf = requestAnimationFrame(draw);
  if (!g) return;
  if (!state) {
    g.clearRect(0, 0, cw, ch);
    return;
  }
  drawPitch();
  for (const ent of state.entities || []) {
    let pos = smooth.get(ent.id);
    if (!pos) {
      pos = { x: ent.x, y: ent.y };
      smooth.set(ent.id, pos);
    }
    lerpPoint(pos, ent.x, ent.y, 0.4, 30);
    drawEntity(ent, pos);
  }
  if (state.ball) {
    ballSmooth = lerpPoint(ballSmooth, state.ball.x, state.ball.y, 0.55, 30);
    drawBall(ballSmooth);
  }
  if (flash > 0) {
    g.fillStyle = `rgba(255,255,255,${flash * 0.25})`;
    g.fillRect(0, 0, cw, ch);
    flash = Math.max(0, flash - 0.05);
  }
}

function sendMove(force = false) {
  if (!ctx || !state || state.finished) return;
  const now = performance.now();
  if (!force && now - lastSent < 90) return;
  lastSent = now;
  let { x, y } = joy.active ? joy : keyVector();
  if (Math.hypot(x, y) > 1) {
    const len = Math.hypot(x, y);
    x /= len;
    y /= len;
  }
  ctx.send({ type: "action", action: { type: "move", x: +x.toFixed(3), y: +y.toFixed(3), sprint } });
}

function keyVector() {
  let x = 0;
  let y = 0;
  if (keys.has("arrowleft") || keys.has("a")) x -= 1;
  if (keys.has("arrowright") || keys.has("d")) x += 1;
  if (keys.has("arrowup") || keys.has("w")) y -= 1;
  if (keys.has("arrowdown") || keys.has("s")) y += 1;
  return { x, y };
}

function moveKnob(clientX, clientY) {
  const r = dpad.getBoundingClientRect();
  const dx = clientX - (r.left + r.width / 2);
  const dy = clientY - (r.top + r.height / 2);
  const max = r.width / 2 - 20;
  const len = Math.hypot(dx, dy) || 1;
  const scale = Math.min(1, len / max);
  joy.x = (dx / len) * scale;
  joy.y = (dy / len) * scale;
  knob.style.transform = `translate(${(dx / len) * max * scale}px, ${(dy / len) * max * scale}px)`;
  sendMove();
}

function joyDown(event) {
  event.preventDefault();
  joy.active = true;
  joy.id = event.pointerId;
  dpad.setPointerCapture?.(event.pointerId);
  moveKnob(event.clientX, event.clientY);
}

function joyMove(event) {
  if (!joy.active || event.pointerId !== joy.id) return;
  event.preventDefault();
  moveKnob(event.clientX, event.clientY);
}

function joyUp(event) {
  if (event.pointerId !== joy.id) return;
  joy.active = false;
  joy.x = 0;
  joy.y = 0;
  joy.id = null;
  knob.style.transform = "";
  sendMove(true);
}

function kick(kind) {
  if (!ctx) return;
  ctx.send({ type: "action", action: { type: "kick", kind } });
}

function showOverlay(text, ms = 1800) {
  if (!els.overlay) return;
  els.overlay.textContent = text;
  els.overlay.classList.remove("hidden");
  clearTimeout(overlayTimer);
  overlayTimer = setTimeout(() => els.overlay?.classList.add("hidden"), ms);
}

function onKeyDown(event) {
  const tag = event.target?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  const key = event.key.toLowerCase();
  if (["arrowleft", "arrowright", "arrowup", "arrowdown", " "].includes(key)) event.preventDefault();
  if (event.repeat) return;
  keys.add(key);
  if (key === "shift") {
    sprint = true;
    sendMove(true);
  } else if (key === " ") {
    kick("shoot");
  } else if (key === "x") {
    kick("pass");
  } else if (key === "c" && ctx) {
    ctx.send({ type: "action", action: { type: "switch" } });
  } else if (keyVector().x || keyVector().y) {
    sendMove(true);
  }
}

function onKeyUp(event) {
  const key = event.key.toLowerCase();
  keys.delete(key);
  if (key === "shift") {
    sprint = false;
    sendMove(true);
  } else if (!joy.active) {
    const v = keyVector();
    if (!v.x && !v.y) sendMove(true);
  }
}

function onVisibility() {
  if (document.hidden) {
    joy.active = false;
    joy.x = joy.y = 0;
    if (knob) knob.style.transform = "";
    sendMove(true);
  }
}

function setScore() {
  if (!state || !els.score) return;
  els.score.textContent = `${state.score?.[0] ?? 0} : ${state.score?.[1] ?? 0}`;
}

function setTime() {
  if (!state || !els.time) return;
  const t = Math.max(0, Math.ceil(state.time ?? 0));
  els.time.textContent = `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

function update(next, events = []) {
  const previous = state;
  state = next;
  if (!next) return;
  if (!previous || previous.per_team !== next.per_team) smooth.clear();
  setScore();
  setTime();
  for (const event of events || []) {
    if (event.type === "goal") {
      flash = 1;
      showOverlay(`GOL! ${esc(event.team === 0 ? teamName(0) : teamName(1))}`, 1900);
    }
  }
  if (next.finished && els.overlay) {
    showOverlay("O'yin tugadi", 6000);
  }
}

export default {
  mount(root, context) {
    ctx = context;
    state = null;
    smooth = new Map();
    ballSmooth = null;
    flash = 0;
    root.innerHTML = `
      <div class="football-shell">
        <canvas id="football-canvas"></canvas>
        <div class="football-hud"><span id="fb-score">0 : 0</span><span class="t" id="fb-time">0:00</span></div>
        <div class="football-overlay hidden" id="fb-overlay"></div>
      </div>
      <div class="football-controls">
        <div class="dpad" id="fb-dpad"><div class="dpad-knob" id="fb-knob"></div></div>
        <div class="touch-btns">
          <button class="touch-btn" id="fb-pass">PAS</button>
          <button class="touch-btn big" id="fb-shoot">ZARBA</button>
          <button class="touch-btn" id="fb-sprint">YUGUR</button>
          <button class="touch-btn" id="fb-switch">ALMASHTIRISH</button>
        </div>
      </div>`;
    canvas = root.querySelector("#football-canvas");
    dpad = root.querySelector("#fb-dpad");
    knob = root.querySelector("#fb-knob");
    els = {
      score: root.querySelector("#fb-score"),
      time: root.querySelector("#fb-time"),
      overlay: root.querySelector("#fb-overlay"),
    };
    resize();
    dpad.addEventListener("pointerdown", joyDown);
    dpad.addEventListener("pointermove", joyMove);
    dpad.addEventListener("pointerup", joyUp);
    dpad.addEventListener("pointercancel", joyUp);
    root.querySelector("#fb-pass").addEventListener("pointerdown", () => kick("pass"));
    root.querySelector("#fb-shoot").addEventListener("pointerdown", () => kick("shoot"));
    root.querySelector("#fb-switch").addEventListener("pointerdown", () => ctx.send({ type: "action", action: { type: "switch" } }));
    const sprintBtn = root.querySelector("#fb-sprint");
    const sprintOn = (event) => {
      event.preventDefault();
      sprint = true;
      sprintBtn.classList.add("active");
      sendMove(true);
    };
    const sprintOff = () => {
      sprint = false;
      sprintBtn.classList.remove("active");
      sendMove(true);
    };
    sprintBtn.addEventListener("pointerdown", sprintOn);
    sprintBtn.addEventListener("pointerup", sprintOff);
    sprintBtn.addEventListener("pointercancel", sprintOff);
    sprintBtn.addEventListener("pointerleave", sprintOff);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", onVisibility);
    moveTimer = setInterval(() => {
      if (!state || state.finished) return;
      const k = keyVector();
      if (joy.active || k.x || k.y) sendMove(true);
    }, 120);
    raf = requestAnimationFrame(draw);
  },
  update,
  destroy() {
    cancelAnimationFrame(raf);
    clearInterval(moveTimer);
    clearTimeout(overlayTimer);
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("keyup", onKeyUp);
    window.removeEventListener("resize", resize);
    document.removeEventListener("visibilitychange", onVisibility);
    keys.clear();
    sprint = false;
    joy = { active: false, x: 0, y: 0, id: null };
    smooth = new Map();
    ballSmooth = null;
    state = null;
    ctx = null;
    canvas = null;
    g = null;
    els = {};
  },
};
