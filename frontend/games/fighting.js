import { esc } from "../js/ui.js";

const COLORS = [
  { body: "#a78bfa", dark: "#5b21b6", glow: "rgba(167,139,250,.55)" },
  { body: "#fb7185", dark: "#9f1239", glow: "rgba(251,113,133,.55)" },
];

let ctx = null;
let state = null;
let canvas = null;
let g = null;
let cw = 360;
let ch = 224;
let dpr = 1;
let raf = 0;
let els = {};
let xPos = [30, 70];
let effects = [];
let shake = 0;
let flash = 0;
const keys = new Set();

function resize() {
  if (!canvas) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  cw = Math.max(260, Math.floor(rect.width));
  ch = Math.round(cw * 0.62);
  dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(cw * dpr);
  canvas.height = Math.round(ch * dpr);
  canvas.style.height = `${ch}px`;
  g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function send(action) {
  if (ctx) ctx.send({ type: "action", action });
}

function drawBackground() {
  const grad = g.createLinearGradient(0, 0, 0, ch);
  grad.addColorStop(0, "#170b2b");
  grad.addColorStop(0.6, "#0b0617");
  grad.addColorStop(1, "#150b24");
  g.fillStyle = grad;
  g.fillRect(0, 0, cw, ch);

  const floorY = ch * 0.8;
  const floor = g.createLinearGradient(0, floorY, 0, ch);
  floor.addColorStop(0, "rgba(139,92,246,.16)");
  floor.addColorStop(1, "rgba(20,10,35,.1)");
  g.fillStyle = floor;
  g.fillRect(0, floorY, cw, ch - floorY);
  g.strokeStyle = "rgba(167,139,250,.35)";
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(0, floorY);
  g.lineTo(cw, floorY);
  g.stroke();

  g.fillStyle = "rgba(167,139,250,.06)";
  for (let i = 0; i < 26; i += 1) {
    const x = (i * 71) % cw;
    const y = 18 + ((i * 37) % Math.max(10, Math.round(floorY * 0.55)));
    g.beginPath();
    g.arc(x, y, 1.4, 0, Math.PI * 2);
    g.fill();
  }

  g.strokeStyle = "rgba(255,255,255,.05)";
  for (let i = 1; i < 8; i += 1) {
    const x = (cw / 8) * i;
    g.beginPath();
    g.moveTo(cw / 2, floorY);
    g.lineTo(x, ch);
    g.stroke();
  }
}

function drawHp(fighters) {
  const barW = cw * 0.36;
  const barH = 8;
  const y = 14;
  const left = 12;
  const right = cw - 12 - barW;
  const names = state?.slots || [];

  g.font = "600 10px system-ui";
  g.textBaseline = "top";
  g.textAlign = "left";
  g.fillStyle = "rgba(255,255,255,.65)";
  g.fillText((names[0]?.name || "Siz").slice(0, 16), left, y - 11);
  g.textAlign = "right";
  g.fillText((names[1]?.name || "Raqib").slice(0, 16), cw - 12, y - 11);

  g.fillStyle = "rgba(255,255,255,.09)";
  g.fillRect(left, y, barW, barH);
  g.fillRect(right, y, barW, barH);
  const hp0 = Math.max(0, Math.min(100, fighters[0]?.hp ?? 0)) / 100;
  const hp1 = Math.max(0, Math.min(100, fighters[1]?.hp ?? 0)) / 100;
  const grad0 = g.createLinearGradient(left, 0, left + barW, 0);
  grad0.addColorStop(0, "#8b5cf6");
  grad0.addColorStop(1, "#22d3ee");
  g.fillStyle = grad0;
  g.fillRect(left, y, barW * hp0, barH);
  const grad1 = g.createLinearGradient(right, 0, right + barW, 0);
  grad1.addColorStop(0, "#fda4af");
  grad1.addColorStop(1, "#e11d48");
  g.fillStyle = grad1;
  g.fillRect(right + barW * (1 - hp1), y, barW * hp1, barH);

  g.font = "700 11px system-ui";
  g.textBaseline = "middle";
  g.fillStyle = "rgba(255,255,255,.8)";
  g.textAlign = "center";
  const t = Math.max(0, Math.ceil(state?.time ?? 0));
  g.fillText(`${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`, cw / 2, y + 4);

  for (let slot = 0; slot < 2; slot += 1) {
    const rounds = fighters[slot]?.rounds || 0;
    for (let i = 0; i < 2; i += 1) {
      const px = slot === 0 ? left + 6 + i * 14 : cw - 12 - 6 - i * 14;
      g.beginPath();
      g.arc(px, y + 18, 3.6, 0, Math.PI * 2);
      g.fillStyle = i < rounds ? COLORS[slot].body : "rgba(255,255,255,.16)";
      g.fill();
    }
  }

  g.font = "700 11px system-ui";
  g.textAlign = "center";
  g.fillStyle = "rgba(255,255,255,.55)";
  g.fillText(`RAUND ${state?.round ?? 1}`, cw / 2, y + 22);
}

function drawFighter(fighter, index, x) {
  const color = COLORS[index];
  const floorY = ch * 0.8;
  const scale = Math.min(cw, ch) / 210;
  const bodyH = 58 * scale;
  const headR = 10 * scale;
  const hipY = floorY - bodyH * 0.42;
  const shoulderY = floorY - bodyH * 0.82;
  const headY = shoulderY - headR * 1.15;
  const facing = fighter.slot === 0 ? 1 : -1;
  const dead = fighter.hp <= 0;

  g.save();
  g.globalAlpha = fighter.dodge ? 0.55 : dead ? 0.45 : 1;

  g.strokeStyle = color.body;
  g.lineWidth = 5 * scale;
  g.lineCap = "round";
  g.beginPath();
  g.moveTo(x - 6 * scale, hipY);
  g.lineTo(x - 9 * scale, floorY);
  g.moveTo(x + 6 * scale, hipY);
  g.lineTo(x + 9 * scale, floorY);
  g.stroke();

  g.fillStyle = color.body;
  g.beginPath();
  g.roundRect(x - 12 * scale, shoulderY, 24 * scale, bodyH * 0.48, 8 * scale);
  g.fill();
  g.fillStyle = color.dark;
  g.fillRect(x - 12 * scale, hipY - 3 * scale, 24 * scale, 5 * scale);

  g.beginPath();
  g.arc(x, headY, headR, 0, Math.PI * 2);
  g.fillStyle = color.body;
  g.fill();
  g.fillStyle = "rgba(20,10,32,.5)";
  g.fillRect(x - facing * headR * 0.45 - 3 * scale, headY - 1.5 * scale, 6 * scale, 2.6 * scale);

  const attacking = Boolean(fighter.attack);
  const armY = shoulderY + 12 * scale;
  g.strokeStyle = color.body;
  g.lineWidth = 5 * scale;
  g.beginPath();
  if (fighter.block) {
    g.moveTo(x - facing * 11 * scale, armY);
    g.lineTo(x + facing * 8 * scale, armY - 6 * scale);
    g.moveTo(x - facing * 11 * scale, armY + 6 * scale);
    g.lineTo(x + facing * 9 * scale, armY + 4 * scale);
  } else if (attacking) {
    const reach = (fighter.attack === "heavy" ? 30 : 23) * scale;
    g.moveTo(x + facing * 9 * scale, armY);
    g.lineTo(x + facing * reach, armY + 1);
  } else {
    g.moveTo(x + facing * 10 * scale, armY);
    g.lineTo(x + facing * 15 * scale, armY + 8 * scale);
  }
  g.stroke();

  if (attacking) {
    g.beginPath();
    g.arc(x + facing * ((fighter.attack === "heavy" ? 30 : 23) * scale), armY + 1, 4 * scale, 0, Math.PI * 2);
    g.fillStyle = "rgba(255,255,255,.75)";
    g.fill();
  }

  if (fighter.block) {
    g.beginPath();
    g.arc(x + facing * 4 * scale, armY, 17 * scale, -1.1, 1.1);
    g.strokeStyle = "rgba(34,211,238,.55)";
    g.lineWidth = 2;
    g.stroke();
  }

  if (fighter.stun) {
    g.fillStyle = "rgba(251,113,133,.85)";
    g.font = `700 ${Math.round(11 * scale)}px system-ui`;
    g.textAlign = "center";
    g.fillText("✦", x, headY - headR - 6);
  }

  g.globalAlpha = 1;
  g.font = `700 ${Math.round(10 * scale)}px system-ui`;
  g.textAlign = "center";
  g.textBaseline = "bottom";
  g.fillStyle = "rgba(255,255,255,.55)";
  g.fillText((state?.slots?.[fighter.slot]?.name || "").slice(0, 14), x, headY - headR - 10);
  g.restore();
}

function drawOverlay() {
  if (state?.finished) {
    g.fillStyle = "rgba(5,3,12,.6)";
    g.fillRect(0, 0, cw, ch);
    g.font = `800 ${Math.round(Math.min(cw, ch) * 0.085)}px system-ui`;
    g.textAlign = "center";
    g.fillStyle = "#c4b5fd";
    g.textBaseline = "middle";
    g.fillText("JANG TUGADI", cw / 2, ch / 2);
    return;
  }
  if (state?.pause > 0) {
    g.fillStyle = "rgba(5,3,12,.55)";
    g.fillRect(0, 0, cw, ch);
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.font = `800 ${Math.round(Math.min(cw, ch) * 0.09)}px system-ui`;
    g.fillStyle = "#c4b5fd";
    g.fillText(`RAUND ${state.round}`, cw / 2, ch * 0.42);
    g.font = "500 12px system-ui";
    g.fillStyle = "rgba(255,255,255,.6)";
    g.fillText("Keyingi raundga tayyorlaning", cw / 2, ch * 0.52);
  }
}

function draw() {
  raf = requestAnimationFrame(draw);
  if (!g) return;
  if (!state) {
    g.clearRect(0, 0, cw, ch);
    return;
  }
  const shakeX = shake > 0 ? (Math.random() - 0.5) * shake * 8 : 0;
  g.save();
  g.translate(shakeX, 0);
  drawBackground();
  shake = Math.max(0, shake - 0.08);
  const fighters = state.fighters || [];
  fighters.forEach((fighter, i) => {
    xPos[i] += (fighter.x - xPos[i]) * 0.4;
    if (Math.abs(fighter.x - xPos[i]) > 40) xPos[i] = fighter.x;
    drawFighter(fighter, i, (xPos[i] / 100) * cw);
  });
  effects = effects.filter((e) => {
    e.t += 1;
    const alpha = Math.max(0, 1 - e.t / 34);
    g.globalAlpha = alpha;
    g.fillStyle = e.color;
    g.font = "800 13px system-ui";
    g.textAlign = "center";
    g.fillText(e.text, e.x, e.y - e.t * 0.55);
    g.globalAlpha = 1;
    return e.t < 34;
  });
  drawHp(fighters);
  if (flash > 0) {
    g.fillStyle = `rgba(251,113,133,${flash * 0.3})`;
    g.fillRect(0, 0, cw, ch);
    flash = Math.max(0, flash - 0.08);
  }
  drawOverlay();
  g.restore();
}

function update(next, events = []) {
  state = next;
  xPos[0] = (state.fighters?.[0]?.x ?? 30);
  if (Math.abs((state.fighters?.[1]?.x ?? 70) - xPos[1]) > 40) xPos[1] = state.fighters[1].x;
  for (const event of events || []) {
    if (event.type === "hit") {
      shake = 1;
      flash = 0.7;
      const victim = state.fighters?.[1 - event.by];
      const x = ((victim?.x ?? 50) / 100) * cw;
      effects.push({
        x: x + (Math.random() - 0.5) * 18,
        y: ch * 0.5,
        text: event.blocked ? `BLOK ${event.damage}` : `-${event.damage}`,
        color: event.blocked ? "#67e8f9" : "#fda4af",
        t: 0,
      });
    } else if (event.type === "miss") {
      const victim = state.fighters?.[1 - event.by];
      effects.push({
        x: ((victim?.x ?? 50) / 100) * cw,
        y: ch * 0.45,
        text: "DODJ",
        color: "#a7f3d0",
        t: 0,
      });
    }
  }
}

function press(key, down) {
  if (down) keys.add(key);
  else keys.delete(key);
}

function move(step) {
  send({ type: "move", move: step });
}

function block(on) {
  send({ type: "block", on });
  const btn = els.block;
  if (btn) btn.classList.toggle("active", on);
}

function onKeyDown(event) {
  const tag = event.target?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  const key = event.key.toLowerCase();
  if (event.repeat) return;
  if (key === "a" || key === "arrowleft") move(-1);
  else if (key === "d" || key === "arrowright") move(1);
  else if (key === "j" || key === " ") send({ type: "attack", kind: "light" });
  else if (key === "k") send({ type: "attack", kind: "heavy" });
  else if (key === "l") send({ type: "dodge" });
  else if (key === "s" || key === "arrowdown") block(true);
  else return;
  event.preventDefault();
}

function onKeyUp(event) {
  const key = event.key.toLowerCase();
  if (key === "a" || key === "arrowleft" || key === "d" || key === "arrowright") move(0);
  else if (key === "s" || key === "arrowdown") block(false);
}

export default {
  mount(root, context) {
    ctx = context;
    state = null;
    xPos = [30, 70];
    effects = [];
    shake = 0;
    flash = 0;
    root.innerHTML = `
      <canvas id="fighting-canvas"></canvas>
      <div class="fight-controls">
        <div class="fight-move">
          <button class="touch-btn" id="fight-left">◀</button>
          <button class="touch-btn" id="fight-right">▶</button>
        </div>
        <div class="fight-atk">
          <button class="touch-btn" id="fight-block">BLOK</button>
          <button class="touch-btn" id="fight-light">YENGIL</button>
          <button class="touch-btn" id="fight-heavy">OG'IR</button>
          <button class="touch-btn" id="fight-dodge">DODJ</button>
        </div>
      </div>`;
    canvas = root.querySelector("#fighting-canvas");
    els = {
      block: root.querySelector("#fight-block"),
    };
    resize();
    const hold = (el, onPress, onRelease) => {
      el.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        el.setPointerCapture?.(event.pointerId);
        onPress();
      });
      const release = () => onRelease?.();
      el.addEventListener("pointerup", release);
      el.addEventListener("pointercancel", release);
      el.addEventListener("pointerleave", release);
    };
    hold(root.querySelector("#fight-left"), () => move(-1), () => move(0));
    hold(root.querySelector("#fight-right"), () => move(1), () => move(0));
    hold(els.block, () => block(true), () => block(false));
    root.querySelector("#fight-light").addEventListener("pointerdown", (e) => { e.preventDefault(); send({ type: "attack", kind: "light" }); });
    root.querySelector("#fight-heavy").addEventListener("pointerdown", (e) => { e.preventDefault(); send({ type: "attack", kind: "heavy" }); });
    root.querySelector("#fight-dodge").addEventListener("pointerdown", (e) => { e.preventDefault(); send({ type: "dodge" }); });
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("resize", resize);
    raf = requestAnimationFrame(draw);
  },
  update,
  destroy() {
    cancelAnimationFrame(raf);
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("keyup", onKeyUp);
    window.removeEventListener("resize", resize);
    keys.clear();
    state = null;
    ctx = null;
    canvas = null;
    g = null;
    els = {};
    effects = [];
  },
};
