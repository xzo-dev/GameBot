import { confirmModal, esc } from "../js/ui.js";

const GLYPHS = {
  p: "♟", n: "♞", b: "♝", r: "♜", q: "♛", k: "♚",
  P: "♙", N: "♘", B: "♗", R: "♖", Q: "♕", K: "♔",
};

let ctx = null;
let state = null;
let selected = null;
let legalMap = new Map();
let els = {};

function parseFen(fen) {
  const rows = fen.split(" ")[0].split("/");
  const board = Array.from({ length: 8 }, () => Array(8).fill(null));
  rows.forEach((row, r) => {
    let c = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) c += Number(ch);
      else { board[r][c] = ch; c += 1; }
    }
  });
  return board;
}

function squareName(r, c) {
  return "abcdefgh"[c] + (8 - r);
}

function computeLegal() {
  legalMap = new Map();
  for (const uci of state.legal || []) {
    const from = uci.slice(0, 2);
    const to = uci.slice(2, 4);
    if (!legalMap.has(from)) legalMap.set(from, []);
    legalMap.get(from).push(to);
  }
}

function render() {
  if (!state) return;
  const board = parseFen(state.fen);
  const flip = state.your_slot === 1;
  const rows = flip ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];
  const cols = flip ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];
  computeLegal();

  const boardEl = els.board;
  boardEl.innerHTML = "";
  for (const r of rows) {
    for (const c of cols) {
      const sq = squareName(r, c);
      const piece = board[r][c];
      const cell = document.createElement("div");
      const light = (r + c) % 2 === 0;
      cell.className = `cell ${light ? "light" : "dark"}`;
      cell.dataset.square = sq;
      if (selected === sq) cell.classList.add("sel");
      if (state.last_move && (state.last_move.from === sq || state.last_move.to === sq)) cell.classList.add("last");
      if (selected && legalMap.get(selected)?.includes(sq)) {
        cell.classList.add("legal");
        if (piece) cell.classList.add("capture");
      }
      if (piece) {
        const span = document.createElement("span");
        span.className = `piece ${piece === piece.toUpperCase() ? "w" : "b"}`;
        span.textContent = GLYPHS[piece];
        cell.appendChild(span);
      }
      cell.addEventListener("click", () => onClick(sq, piece));
      boardEl.appendChild(cell);
    }
  }

  const yourTurn = state.turn === state.your_slot && !state.finished;
  const names = state.slots || [];
  const you = esc(names[state.your_slot]?.name || "Siz");
  const opp = esc(names[1 - state.your_slot]?.name || "Raqib");
  els.names.innerHTML = `
    <span class="player-chip ${yourTurn ? "active" : ""}">${you}<span class="grow"></span><span class="clock ${yourTurn ? "active" : ""}">${fmtClock(state.clocks?.[state.your_slot])}</span></span>
    <span class="player-chip ${!yourTurn && !state.finished ? "active" : ""}">${opp}<span class="grow"></span><span class="clock ${!yourTurn && !state.finished ? "active" : ""}">${fmtClock(state.clocks?.[1 - state.your_slot])}</span></span>`;
  els.status.textContent = state.finished
    ? "O'yin tugadi"
    : yourTurn
      ? (state.check ? "Shoh! Yurish sizdan." : "Sizning navbatingiz")
      : "Raqib yurmoqda...";
  els.moves.textContent = (state.moves || []).join("  ");

  if (state.draw_offer !== null && state.draw_offer !== state.your_slot && !state.finished) {
    els.offer.innerHTML = `<div class="card center small">Raqib durang taklif qildi
      <div class="row mt" style="justify-content:center">
        <button class="btn sm" id="accept-draw">Qabul</button>
        <button class="btn sm ghost" id="decline-draw">Rad</button>
      </div></div>`;
    els.offer.querySelector("#accept-draw")?.addEventListener("click", () => ctx.send({ type: "action", action: { type: "accept_draw" } }));
    els.offer.querySelector("#decline-draw")?.addEventListener("click", () => ctx.send({ type: "action", action: { type: "decline_draw" } }));
  } else {
    els.offer.innerHTML = "";
  }
  els.resign.disabled = state.finished;
  els.draw.disabled = state.finished;
}

function fmtClock(seconds) {
  if (seconds === undefined) return "--:--";
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function onClick(sq, piece) {
  if (!state || state.finished || state.turn !== state.your_slot) return;
  const own = piece && (state.your_slot === 0 ? piece === piece.toUpperCase() : piece === piece.toLowerCase());
  if (selected && legalMap.get(selected)?.includes(sq)) {
    ctx.send({ type: "action", action: { type: "move", uci: selected + sq } });
    selected = null;
    render();
    return;
  }
  if (own && legalMap.has(sq)) {
    selected = selected === sq ? null : sq;
  } else {
    selected = null;
  }
  render();
}

export default {
  mount(root, context) {
    ctx = context;
    root.innerHTML = `
      <div class="chess-shell">
        <div class="players-row" id="chess-names" style="width:100%"></div>
        <div class="turn-banner" id="chess-status"></div>
        <div class="chess-board" id="chess-board"></div>
        <div class="chess-moves" id="chess-moves"></div>
        <div id="chess-offer"></div>
        <div class="chess-controls">
          <button class="btn sm ghost" id="chess-draw">Durang</button>
          <button class="btn sm danger" id="chess-resign">Taslim</button>
        </div>
      </div>`;
    els = {
      board: root.querySelector("#chess-board"),
      names: root.querySelector("#chess-names"),
      status: root.querySelector("#chess-status"),
      moves: root.querySelector("#chess-moves"),
      offer: root.querySelector("#chess-offer"),
      resign: root.querySelector("#chess-resign"),
      draw: root.querySelector("#chess-draw"),
    };
    els.resign.addEventListener("click", async () => {
      if (await confirmModal("Taslim bo'lasizmi?", "Bu o'yinda mag'lubiyat hisoblanadi.", "Taslim")) {
        ctx.send({ type: "action", action: { type: "resign" } });
      }
    });
    els.draw.addEventListener("click", () => ctx.send({ type: "action", action: { type: "offer_draw" } }));
  },
  update(newState) {
    state = newState;
    if (state && state.finished) selected = null;
    render();
  },
  destroy() {
    state = null;
    selected = null;
    ctx = null;
    els = {};
  },
};
