import { esc } from "../js/ui.js";

const CELL_META = {
  start: { icon: "🚪", label: "Bosh" },
  jungle: { icon: "🌿", label: "" },
  hazard: { icon: "🐍", label: "Xavf" },
  bonus: { icon: "💎", label: "Bonus" },
  challenge: { icon: "🐯", label: "Sinov" },
  finish: { icon: "🏆", label: "Marra" },
};
const TOKEN_COLORS = ["#a78bfa", "#fb7185", "#34d399", "#fbbf24"];

let ctx = null;
let state = null;
let els = {};
let boost = false;
let lastYourTurn = false;

function render() {
  if (!state) return;
  const you = state.your_slot;
  const yourTurn = !state.finished && state.turn === you;
  if (yourTurn && !lastYourTurn) boost = false;
  lastYourTurn = yourTurn;

  const names = state.slots || [];
  els.status.innerHTML = state.finished
    ? "O'yin tugadi"
    : `${esc(names[state.turn]?.name || "O'yinchi")} navbati${state.turn === you ? " — siz" : ""}`;
  els.status.style.color = yourTurn ? "var(--violet-2)" : "";

  const cells = state.cells || [];
  const board = els.board;
  board.innerHTML = "";
  cells.forEach((type, index) => {
    const meta = CELL_META[type] || CELL_META.jungle;
    const cell = document.createElement("div");
    cell.className = `jcell ${type}`;
    if (index === (state.positions?.[you] ?? -1)) cell.style.boxShadow = "inset 0 0 0 2px rgba(167,139,250,.75)";
    const tokens = document.createElement("div");
    tokens.className = "jtokens";
    (state.positions || []).forEach((pos, player) => {
      if (pos !== index) return;
      const token = document.createElement("span");
      token.className = "jtoken";
      token.style.background = TOKEN_COLORS[player % TOKEN_COLORS.length];
      token.style.opacity = state.done?.includes(player) ? "0.5" : "1";
      token.title = names[player]?.name || "";
      tokens.appendChild(token);
    });
    cell.innerHTML = `<span>${meta.icon}</span>${meta.label ? `<small>${meta.label}</small>` : ""}<small>${index}</small>`;
    cell.appendChild(tokens);
    if (index === state.positions?.[state.turn] && !state.finished) {
      cell.style.borderColor = TOKEN_COLORS[state.turn % TOKEN_COLORS.length];
    }
    board.appendChild(cell);
  });

  els.dice.textContent = state.dice ? state.dice : "–";
  els.mode.textContent = state.coop ? "Kooperativ" : "Raqobat";
  els.energy.textContent = `Energiya +2 (${state.energy?.[you] ?? 0})`;
  els.energy.classList.toggle("active", boost);
  els.energy.disabled = !yourTurn || state.finished || (state.energy?.[you] ?? 0) <= 0;
  els.roll.disabled = !yourTurn || state.finished;
  els.roll.textContent = yourTurn ? (boost ? "Zar + 2 tashlash" : "Zar tashlash") : "Kutilmoqda...";
  els.last.textContent = state.last ? CELL_META[state.last]?.label || "" : "";
  els.log.innerHTML = (state.log || []).slice(-6).map((line) => `<div>${esc(line)}</div>`).join("");
}

function onRoll() {
  if (!ctx || !state || state.finished || state.turn !== state.your_slot) return;
  if (boost && (state.energy?.[state.your_slot] ?? 0) <= 0) return;
  ctx.send({ type: "action", action: { type: "roll", energy: boost } });
}

export default {
  mount(root, context) {
    ctx = context;
    state = null;
    boost = false;
    lastYourTurn = false;
    root.innerHTML = `
      <div class="turn-banner" id="j-status"></div>
      <div class="jumanji-board" id="j-board"></div>
      <div class="card mt-sm">
        <div class="row" style="align-items:center;gap:14px">
          <div class="center" style="width:64px">
            <div class="tiny muted">Zar</div>
            <div id="j-dice" style="font-size:30px;font-weight:800;line-height:1.1">–</div>
          </div>
          <div class="grow">
            <div class="row spread"><span class="tiny muted" id="j-mode"></span><span class="tiny" id="j-last"></span></div>
            <div class="jumanji-actions mt-sm">
              <button class="btn primary sm" id="j-roll">Zar tashlash</button>
              <button class="btn ghost sm" id="j-energy">Energiya +2</button>
            </div>
          </div>
        </div>
      </div>
      <div class="card small" id="j-log" style="max-height:120px;overflow:auto"></div>`;
    els = {
      status: root.querySelector("#j-status"),
      board: root.querySelector("#j-board"),
      dice: root.querySelector("#j-dice"),
      mode: root.querySelector("#j-mode"),
      energy: root.querySelector("#j-energy"),
      roll: root.querySelector("#j-roll"),
      last: root.querySelector("#j-last"),
      log: root.querySelector("#j-log"),
    };
    els.roll.addEventListener("click", onRoll);
    els.energy.addEventListener("click", () => {
      if (els.energy.disabled) return;
      boost = !boost;
      render();
    });
  },
  update(next) {
    state = next;
    render();
  },
  destroy() {
    state = null;
    ctx = null;
    els = {};
  },
};
