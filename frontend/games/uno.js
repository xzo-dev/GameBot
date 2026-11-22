import { esc, modal } from "../js/ui.js";

let ctx = null;
let state = null;
let els = {};

const COLORS = { R: "Qizil", Y: "Sariq", G: "Yashil", B: "Ko'k" };
const LABELS = { skip: "⊘", reverse: "⇄", draw2: "+2", wild: "★", wild4: "+4" };

function cardHtml(card, { playable = false, drawn = false } = {}) {
  const label = LABELS[card.value] || card.value;
  return `<button class="uno-card ${card.color} ${playable ? "playable" : ""} ${drawn ? "drawn" : ""}"
    data-index="${card.index}" style="border-color:rgba(255,255,255,${card.color === "W" ? ".9" : ".7"})">
    <span class="big">${label}</span>
    <span class="tiny" style="opacity:.75">${card.color === "W" ? "JOKER" : esc(card.color)}</span>
  </button>`;
}

function render() {
  if (!state) return;
  const you = state.your_slot;
  const playableSet = new Set(state.legal || []);
  const top = state.top;
  const drawnIdx = state.drawn_index;
  els.table.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;gap:8px">
      <div class="uno-opponents" id="uno-opps"></div>
      <div class="uno-table" style="align-items:center;gap:16px;padding:4px 0">
        <div style="position:relative">
          <button class="uno-card back" id="uno-draw">KARTA<br>OLISH</button>
          <div class="tiny muted center" style="margin-top:4px">${state.counts?.reduce((a, b) => a + b, 0) > 0 ? state.counts.reduce((a, b) => a + b, 0) + " karta" : ""}</div>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          ${top ? `<div class="uno-card ${top.color}"><span class="big">${LABELS[top.value] || esc(top.value)}</span><span class="tiny" style="opacity:.75">${top.color === "W" ? "JOKER" : esc(top.color)}</span></div>` : ""}
          <div style="display:flex;flex-direction:column;align-items:center;gap:4px">
            <span class="tiny muted">Rang</span>
            <span class="uno-color-indicator" style="background:${colorHex(state.current_color)}"></span>
            <span class="tiny muted">${state.direction === 1 ? "↻" : "↺"}</span>
          </div>
        </div>
      </div>
    </div>`;

  const opps = els.table.querySelector("#uno-opps");
  (state.slots || []).forEach((p, i) => {
    if (i === you) return;
    const div = document.createElement("div");
    div.className = "uno-opp";
    div.innerHTML = `<span>${p.bot ? "🤖" : "👤"} ${esc(p.name)}</span><span class="mini"></span><b>${state.counts?.[i] ?? 0}</b>`;
    if (state.turn === i) div.style.color = "var(--violet-2)";
    opps.appendChild(div);
  });

  els.hand.innerHTML = "";
  (state.hand || []).forEach((card, index) => {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = cardHtml({ ...card, index }, { playable: playableSet.has(index), drawn: index === drawnIdx });
    const button = wrapper.firstElementChild;
    button.addEventListener("click", () => playCard(index, card));
    els.hand.appendChild(button);
  });

  const yourTurn = state.turn === you && !state.finished;
  els.status.textContent = state.finished
    ? "O'yin tugadi"
    : yourTurn
      ? (drawnIdx !== null ? "Yangi kartani o'ynang yoki navbatni bosing" : "Sizning navbatingiz")
      : (state.slots?.[state.turn]?.name || "Raqib") + " o'ynamoqda...";
  els.log.textContent = (state.log || []).slice(-3).join(" · ");
  els.drawBtn.disabled = !!state.finished || !yourTurn || drawnIdx !== null;
  els.passBtn.classList.toggle("hidden", drawnIdx === null || !yourTurn);
}

function colorHex(color) {
  return { R: "#f43f5e", Y: "#facc15", G: "#34d399", B: "#60a5fa" }[color] || "#a78bfa";
}

function playCard(index, card) {
  if (!state || state.finished || state.turn !== state.your_slot) return;
  if (!(state.legal || []).includes(index)) return;
  if (card.color === "W") {
    modal(
      `<h3>Rang tanlang</h3><p class="muted small">Joker kartadan keyin o'yin rangi</p>
       <div class="grid-2 mt" style="grid-template-columns:repeat(2,1fr)">
        ${["R", "Y", "G", "B"].map((c) => `<button class="btn" data-color="${c}" style="background:${colorHex(c)}22;border-color:${colorHex(c)}66">${COLORS[c]}</button>`).join("")}
       </div>`,
      {
        onMount(el, close) {
          el.querySelectorAll("[data-color]").forEach((b) => b.addEventListener("click", () => {
            ctx.send({ type: "action", action: { type: "play", index, color: b.dataset.color } });
            close();
          }));
        },
      }
    );
    return;
  }
  ctx.send({ type: "action", action: { type: "play", index } });
}

export default {
  mount(root, context) {
    ctx = context;
    root.innerHTML = `
      <div class="uno-shell">
        <div class="turn-banner" id="uno-status"></div>
        <div id="uno-table"></div>
        <div class="uno-hand" id="uno-hand"></div>
        <div class="uno-actions">
          <button class="btn sm" id="uno-draw-btn">Karta olish</button>
          <button class="btn sm ghost hidden" id="uno-pass">Navbat</button>
        </div>
        <div class="uno-log" id="uno-log"></div>
      </div>`;
    els = {
      table: root.querySelector("#uno-table"),
      hand: root.querySelector("#uno-hand"),
      status: root.querySelector("#uno-status"),
      log: root.querySelector("#uno-log"),
      drawBtn: root.querySelector("#uno-draw-btn"),
      passBtn: root.querySelector("#uno-pass"),
    };
    els.drawBtn.addEventListener("click", () => ctx.send({ type: "action", action: { type: "draw" } }));
    els.passBtn.addEventListener("click", () => ctx.send({ type: "action", action: { type: "pass" } }));
  },
  update(newState) {
    state = newState;
    render();
  },
  destroy() {
    state = null;
    els = {};
    ctx = null;
  },
};
