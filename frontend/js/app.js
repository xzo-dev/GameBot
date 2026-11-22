import { api, auth, ApiError } from "./api.js";
import { socket } from "./ws.js";
import { music } from "./music.js";
import {
  esc, num, initials, toast, modal, confirmModal, timeShort, dateShort,
  difficultyLabel, loading, empty,
} from "./ui.js";
import { tg, GAMES_BASE } from "./config.js";

const S = {
  profile: null,
  games: [],
  status: null,
  tab: "home",
  gameId: null,
  room: null,
  client: null,
  clientGameId: "",
  clientCode: "",
  searching: false,
  waitingRooms: [],
  roomsGameId: null,
  resultCode: "",
  leaveTarget: "lobby",
  lastChat: [],
  unread: 0,
  ratingGame: "",
  wired: false,
  sawRoom: false,
  reconnectTimer: 0,
};

const THEME_ACCENTS = { th_void: "#7c3aed", th_royal: "#a855f7", th_aurora: "#22d3ee" };
const FRAME_COLORS = { fr_purple: "#8b5cf6", fr_gold: "#eab308", fr_ice: "#67e8f9" };
const SHOP_LABELS = {
  avatar: "Avatarlar", frame: "Ramkalar", theme: "Mavzular",
  board: "Shaxmat taxtalari", cards: "Karta dizaynlari", victory: "G'alaba effektlari",
};
const SHOP_ICONS = { avatar: "🎭", frame: "🖼", theme: "🎨", board: "♟", cards: "🃏", victory: "✨" };
const OUTCOME_LABELS = { win: "G'alaba", loss: "Mag'lubiyat", draw: "Durang" };
const REASONS = {
  checkmate: "Shoh va mat", timeout: "Vaqt tugadi", resign: "Taslim bo'lish",
  draw: "Durang", draw_agreed: "Kelishilgan durang", goals: "Gollar hisobi",
  forfeit: "O'yindan chiqish", knockout: "Nokaut", reached: "Marraga yetish",
  all_finished: "Barcha o'yinchilar marrada", game_over: "O'yin tugadi",
};

const $ = (selector, root = document) => root.querySelector(selector);
const view = () => document.getElementById("view");

function markTab(tab) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
}

function showTabbar() {
  document.getElementById("tabbar").classList.remove("hidden");
}

function hideTabbar() {
  document.getElementById("tabbar").classList.add("hidden");
}

function cancelSearch(silent = false) {
  if (!S.searching) return;
  S.searching = false;
  socket.send({ type: "cancel_match" });
  if (!silent) toast("Qidiruv bekor qilindi");
}

function goTab(tab) {
  if (S.room) return;
  cancelSearch(true);
  S.tab = tab;
  S.gameId = null;
  markTab(tab);
  showTabbar();
  if (tab === "home") renderHome();
  else if (tab === "games") renderGames();
  else if (tab === "shop") renderShop();
  else if (tab === "music") renderMusic();
  else if (tab === "rating") renderRating();
  else if (tab === "profile") renderProfile();
}

function equipped(categoryPrefix) {
  const inv = S.profile?.inventory || [];
  return inv.find((item) => item.equipped && item.item_id.startsWith(categoryPrefix));
}

function frameColor() {
  const frame = equipped("fr_");
  return frame ? FRAME_COLORS[frame.item_id] || "#a855f7" : "";
}

function applyTheme() {
  const theme = equipped("th_");
  const accent = theme ? THEME_ACCENTS[theme.item_id] || "" : "";
  if (accent) document.documentElement.style.setProperty("--violet", accent);
  else document.documentElement.style.removeProperty("--violet");
}

function gameTitle(id) {
  return S.games.find((g) => g.id === id)?.title || id;
}

function gameIcon(id) {
  return S.games.find((g) => g.id === id)?.icon || "🎮";
}

function gameRating(id) {
  return (S.profile?.games || []).find((g) => g.game_id === id)?.rating || 1000;
}

function renderTopbar() {
  const p = S.profile;
  if (!p) return;
  const av = document.getElementById("top-avatar");
  av.innerHTML = p.avatar ? `<img src="${esc(p.avatar)}" alt="">` : initials(p.name);
  const color = frameColor();
  av.style.borderColor = color || "";
  document.getElementById("top-name").textContent = p.name || "GameHub";
  document.getElementById("top-level").textContent = `${p.level}-daraja${p.premium ? " · Premium" : ""}`;
  document.getElementById("top-achko").textContent = num(p.achko);
  document.getElementById("top-coins").textContent = num(p.coins);
}

function updateProfile(next) {
  if (!next) return;
  S.profile = { ...S.profile, ...next };
  applyTheme();
  renderTopbar();
}

function avatarHtml(p, cls = "hero-avatar") {
  const style = frameColor() ? ` style="border-color:${frameColor()}"` : "";
  return `<div class="${cls}"${style}>${p.avatar ? `<img src="${esc(p.avatar)}" alt="">` : initials(p.name)}</div>`;
}

/* ---------------- boot & auth ---------------- */

async function boot() {
  tg?.ready?.();
  tg?.expand?.();
  tg?.setHeaderColor?.("#07040f");
  tg?.setBackgroundColor?.("#07040f");
  tg?.disableVerticalSwipes?.();
  setupChrome();
  try {
    S.status = await api.status();
  } catch {
    S.status = null;
  }
  if (auth.token) {
    try {
      const data = await api.me();
      finishLogin(data.profile, data.games);
      return;
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 401) {
        showAuth(err.message || "Server bilan aloqa yo'q");
        return;
      }
      auth.clear();
    }
  }
  if (tg?.initData) {
    try {
      const data = await api.telegramLogin(tg.initData);
      auth.token = data.token;
      finishLogin(data.profile, data.games);
    } catch (err) {
      showAuth(err.message || "Telegram orqali kirishda xatolik");
    }
    return;
  }
  showAuth();
}

function finishLogin(profile, games) {
  S.profile = profile;
  S.games = (games || []).filter((g) => g.enabled);
  applyTheme();
  renderTopbar();
  if (S.status?.maintenance && !profile.is_admin) {
    renderMaintenance();
    return;
  }
  wireSocket();
  socket.connect();
  music.load().catch(() => {});
  goTab("home");
}

function showAuth(message = "") {
  hideTabbar();
  const dev = S.status?.dev;
  view().innerHTML = `
    <div class="auth-screen">
      <div class="auth-card card glow center">
        <div style="font-size:46px;line-height:1">🎮</div>
        <h1 class="mt-sm">GameHub</h1>
        <p class="muted small">Premium Telegram o'yin platformasi</p>
        ${message ? `<div class="card mt" style="border-color:rgba(251,113,133,.4);padding:10px"><span class="small" style="color:#fecdd3">${esc(message)}</span></div>` : ""}
        <p class="small mt">Ilovaga kirish uchun Telegram orqali oching.</p>
        <button class="btn primary block mt" id="auth-retry">Telegram orqali ochish</button>
        ${dev ? `
          <div class="card mt" style="text-align:left">
            <div class="tiny muted">Sinov rejimi (DEV_MODE)</div>
            <div class="field"><label>Ism</label><input class="input" id="dev-name" value="Sinov o'yinchisi"></div>
            <div class="field"><label>Telegram ID (ixtiyoriy)</label><input class="input" id="dev-id" inputmode="numeric" placeholder="700000001"></div>
            <button class="btn ghost block mt-sm" id="dev-login">Sinov hisobi bilan kirish</button>
          </div>` : ""}
      </div>
    </div>`;
  $("#auth-retry")?.addEventListener("click", () => {
    if (tg?.initData) location.reload();
    else toast("GameHub botini Telegramda oching", "error");
  });
  $("#dev-login")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    const name = $("#dev-name")?.value.trim() || "Sinov o'yinchisi";
    const rawId = $("#dev-id")?.value.trim();
    try {
      const data = await api.devLogin(rawId ? Number(rawId) : Math.floor(700000000 + Math.random() * 999999), name);
      auth.token = data.token;
      S.status = S.status || {};
      finishLogin(data.profile, data.games);
      toast("Sinov hisobiga kirdingiz", "ok");
    } catch (err) {
      toast(err.message || "Kirish amalga oshmadi", "error");
      button.disabled = false;
    }
  });
}

function renderMaintenance() {
  hideTabbar();
  view().innerHTML = `
    <div class="auth-screen">
      <div class="auth-card card glow center">
        <div style="font-size:44px">🛠</div>
        <h2 class="mt-sm">Texnik xizmat</h2>
        <p class="muted small">Platforma yangilanmoqda. Iltimos, birozdan so'ng qayta urinib ko'ring.</p>
        <button class="btn ghost block mt" id="maint-retry">Qayta tekshirish</button>
      </div>
    </div>`;
  $("#maint-retry")?.addEventListener("click", async () => {
    S.status = await api.status().catch(() => S.status);
    if (!S.status?.maintenance || S.profile?.is_admin) goTab("home");
    else toast("Hali texnik xizmat davom etmoqda", "error");
  });
}

/* ---------------- socket ---------------- */

function wireSocket() {
  if (S.wired) return;
  S.wired = true;

  socket.on("open", () => {
    socket.send({ type: "sync" });
    S.sawRoom = !S.room;
    clearTimeout(S.reconnectTimer);
    if (S.room) {
      S.reconnectTimer = setTimeout(() => {
        if (!S.sawRoom) {
          toast("O'yin sessiyasi tugadi. Qaytadan boshlang.", "error");
          cleanupRoom();
          if (S.gameId) openGame(S.gameId);
          else goTab("games");
        }
      }, 3500);
    }
  });

  socket.on("profile", (data) => updateProfile(data.user));

  socket.on("room_state", (data) => {
    S.room = data.room;
    S.sawRoom = true;
    clearTimeout(S.reconnectTimer);
    if (data.chat) {
      S.lastChat = data.chat;
      renderChatHistory(data.chat);
    }
    if (data.room.status === "waiting") {
      renderWaitRoom(data.room);
    } else if (data.room.status === "playing") {
      ensureGameShell(data.room);
    }
  });

  socket.on("room_created", (data) => {
    if (S.room?.mode !== "bot") toast(`Xona yaratildi: ${data.code}`, "ok");
  });

  socket.on("game_state", async (payload) => {
    const { state, events, game_id: gameId, code } = payload;
    if (!gameId || !state) return;
    S.sawRoom = true;
    clearTimeout(S.reconnectTimer);
    if (!S.client || S.clientGameId !== gameId || S.clientCode !== code) {
      await mountGame(gameId, code, state);
    }
    try {
      S.client?.update(state, events || []);
    } catch (err) {
      console.error(err);
    }
    updateGameStatus();
  });

  socket.on("queue", (data) => {
    S.searching = data.status === "searching";
    renderQueueBox(data);
  });

  socket.on("queue_left", () => {
    S.searching = false;
    renderQueueBox(null);
  });

  socket.on("match_found", () => {
    S.searching = false;
    renderQueueBox(null);
    toast("Raqib topildi! O'yin boshlanmoqda...", "ok");
  });

  socket.on("rooms", (data) => {
    S.waitingRooms = data.rooms || [];
    S.roomsGameId = S.gameId;
    renderPublicRooms();
  });

  socket.on("chat", (message) => {
    S.lastChat.push(message);
    appendChatMessage(message);
  });

  socket.on("match_result", (payload) => {
    const before = { ...(S.profile || {}) };
    if (payload.profile) updateProfile(payload.profile);
    const code = S.room?.code || "";
    if (code && S.resultCode === code) return;
    S.resultCode = code;
    showResult(payload, before);
  });

  socket.on("room_status", (data) => {
    if (data.status !== "finished") return;
    const status = $("#game-status");
    if (status) status.textContent = "O'yin tugadi — natija hisoblanmoqda...";
  });

  socket.on("left", () => {
    destroyClient();
    S.room = null;
    S.lastChat = [];
    S.unread = 0;
    closeChat();
    const target = S.leaveTarget;
    S.leaveTarget = "lobby";
    if (target === "home" || !S.gameId) goTab("home");
    else openGame(S.gameId);
  });

  socket.on("room_closed", (data) => {
    toast(data.reason === "timeout" ? "Xona vaqti tugadi" : "Xona yopildi", "error");
    destroyClient();
    S.room = null;
    if (S.gameId) openGame(S.gameId);
    else goTab("games");
  });

  socket.on("toast", (data) => toast(data.message));

  socket.on("muted", (data) => toast(data.mute ? "Foydalanuvchi ovozsiz qilindi" : "Ovoz qaytarildi"));

  socket.on("error", (data) => {
    toast(data.message || "Xatolik", "error");
    if (S.searching) {
      S.searching = false;
      renderQueueBox(null);
    }
  });

  socket.on("unauthorized", () => {
    toast("Sessiya tugadi. Qaytadan kiring.", "error");
    logout(false);
  });

  socket.on("session_replaced", () => {
    socket.close();
    auth.clear();
    toast("Hisob boshqa qurilmada ochildi", "error");
    setTimeout(() => location.reload(), 900);
  });
}

/* ---------------- home ---------------- */

function renderHome() {
  if (!S.profile) return;
  showTabbar();
  markTab("home");
  const p = S.profile;
  const pct = p.xp_need ? Math.min(100, Math.round((p.xp_in / p.xp_need) * 100)) : 0;
  const featuredIds = S.status?.featured?.length ? S.status.featured : S.games.slice(0, 3).map((g) => g.id);
  const featured = featuredIds.map((id) => S.games.find((g) => g.id === id)).filter(Boolean).slice(0, 4);
  const recent = (p.history || []).slice(0, 3);
  const invCount = (p.inventory || []).length;

  view().innerHTML = `
    <div class="hero">
      <div class="hero-name">
        ${avatarHtml(p)}
        <div class="grow">
          <div class="row" style="gap:7px">
            <b style="font-size:17px">${esc(p.name)}</b>
            ${p.premium ? `<span class="badge">Premium</span>` : ""}
            ${p.is_admin ? `<span class="pill gold">Admin</span>` : ""}
          </div>
          <div class="small muted">${p.username ? "@" + esc(p.username) : "GameHub o'yinchisi"} · ${p.level}-daraja</div>
        </div>
        <button class="icon-btn" id="home-profile" title="Profil">👤</button>
      </div>
      <div class="xpbar"><i style="width:${pct}%"></i></div>
      <div class="row spread tiny muted" style="margin-top:5px">
        <span>${num(p.xp_in)} / ${num(p.xp_need)} XP</span>
        <span>${p.level + 1}-darajaga</span>
      </div>
      <div class="balance-row">
        <div class="balance"><div class="label">Achko</div><div class="value">${num(p.achko)}</div></div>
        <div class="balance"><div class="label">Coin</div><div class="value">${num(p.coins)}</div></div>
        <div class="balance"><div class="label">Kollektsiya</div><div class="value">${invCount}</div></div>
      </div>
    </div>

    <div class="card mt ${p.can_daily ? "glow" : ""}">
      <div class="row spread">
        <div class="row" style="gap:10px">
          <span style="font-size:24px">🎁</span>
          <div>
            <div class="card-title">Kunlik bonus</div>
            <div class="small muted">Har kuni +50 achko va +10 XP</div>
          </div>
        </div>
        <button class="btn gold sm" id="daily-btn" ${p.can_daily ? "" : "disabled"}>${p.can_daily ? "Olish" : "Olingan"}</button>
      </div>
    </div>

    ${S.status?.maintenance ? `<div class="card mt" style="border-color:rgba(251,113,133,.4)"><b>🛠 Texnik xizmat</b><div class="small muted">Ba'zi funksiyalar vaqtincha cheklangan.</div></div>` : ""}

    <div class="section">
      <div class="section-head"><h2>Tanlangan o'yinlar</h2><button class="link" id="all-games">Barchasi →</button></div>
      <div class="games-grid">
        ${featured.map((game) => gameCard(game)).join("") || empty("O'yinlar topilmadi")}
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h2>Musiqa</h2><button class="link" id="home-music">Ochish →</button></div>
      <div class="card">
        <div class="row spread">
          <div class="row" style="gap:10px">
            <span style="font-size:24px">🎵</span>
            <div><div class="card-title" id="home-track">GameHub musiqasi</div><div class="small muted">O'yin paytida ham tinglang</div></div>
          </div>
          <button class="icon-btn" id="home-play">▶</button>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h2>So'nggi o'yinlar</h2><button class="link" id="home-history">Profil →</button></div>
      ${recent.length ? `<div class="list">${recent.map(historyRow).join("")}</div>` : `<div class="card">${empty("Hali o'yin o'ynamagansiz. O'yinlardan birini tanlang.")}</div>`}
    </div>`;

  $("#home-profile")?.addEventListener("click", () => goTab("profile"));
  $("#all-games")?.addEventListener("click", () => goTab("games"));
  $("#home-music")?.addEventListener("click", () => goTab("music"));
  $("#home-history")?.addEventListener("click", () => goTab("profile"));
  $("#home-play")?.addEventListener("click", async () => {
    await music.toggle();
    $("#home-play").textContent = music.audio.paused ? "▶" : "❚❚";
  });
  $("#daily-btn")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const data = await api.daily();
      updateProfile(data.profile);
      toast("Kunlik bonus olindi: +50 achko", "ok");
      renderHome();
    } catch (err) {
      toast(err.message, "error");
      button.disabled = false;
    }
  });
  wireGameCards(view());
}

function gameCard(game) {
  const players = game.min_players === game.max_players ? `${game.min_players}` : `${game.min_players}–${game.max_players}`;
  const rating = gameRating(game.id);
  return `
    <button class="game-card" data-game="${esc(game.id)}">
      <div class="game-icon">${esc(game.icon)}</div>
      <div class="card-title" style="margin-top:6px">${esc(game.title)}</div>
      <div class="small muted" style="margin-top:3px;min-height:32px">${esc(game.description)}</div>
      <div class="game-meta">
        <span class="game-badge">${players} o'yinchi</span>
        ${game.realtime ? `<span class="game-badge">Real vaqt</span>` : ""}
        ${game.supports_bot ? `<span class="pill">Bot</span>` : ""}
      </div>
      <div class="row spread" style="margin-top:8px">
        <span class="tiny muted">Reyting: ${rating}</span>
        <span class="tiny" style="color:var(--violet-2)">O'ynash →</span>
      </div>
    </button>`;
}

function historyRow(match) {
  const r = match.result || {};
  const outcome = outcomeFor(match);
  const color = outcome === "win" ? "var(--green)" : outcome === "loss" ? "var(--red)" : "var(--muted)";
  const scores = scoreText(match.scores);
  return `
    <div class="list-row">
      <span class="avatar-sm">${esc(gameIcon(match.game_id))}</span>
      <div class="list-main">
        <div class="list-title">${esc(gameTitle(match.game_id))} ${scores ? `<span class="muted">${esc(scores)}</span>` : ""}</div>
        <div class="list-sub">${match.ended_at ? dateShort(match.ended_at) + " · " : ""}${esc(modeLabel(match.mode))}${REASONS[r.reason] ? " · " + esc(REASONS[r.reason]) : ""}</div>
      </div>
      ${outcome ? `<span class="pill" style="color:${color}">${OUTCOME_LABELS[outcome]}</span>` : `<span class="pill">O'yin</span>`}
    </div>`;
}

function outcomeFor(match) {
  const result = match.result || {};
  if (!S.profile) return "";
  const players = match.players || [];
  const me = players.find((p) => p.id === S.profile.id);
  if (me && Array.isArray(result.winners)) return result.winners.includes(me.slot) ? "win" : result.draw ? "draw" : "loss";
  return result.draw ? "draw" : "";
}

function scoreText(scores) {
  if (!scores || typeof scores !== "object") return "";
  const keys = Object.keys(scores);
  if (!keys.length) return "";
  return keys.map((key) => scores[key]).join(" : ");
}

function modeLabel(mode) {
  return { quick: "Tezkor", bot: "Bot", room: "Xona", private: "Shaxsiy" }[mode] || mode || "";
}

function wireGameCards(root) {
  root.querySelectorAll("[data-game]").forEach((card) => {
    card.addEventListener("click", () => openGame(card.dataset.game));
  });
}

/* ---------------- games & lobby ---------------- */

function renderGames() {
  showTabbar();
  markTab("games");
  view().innerHTML = `
    <div class="row spread">
      <div><h1>O'yinlar</h1><div class="small muted">Real raqiblar yoki botlar bilan</div></div>
      <button class="icon-btn" id="games-refresh" title="Yangilash">⟳</button>
    </div>
    <div class="games-grid mt">
      ${S.games.map((game) => gameCard(game)).join("") || empty("O'yinlar topilmadi")}
    </div>`;
  wireGameCards(view());
  $("#games-refresh")?.addEventListener("click", async () => {
    const data = await api.games().catch(() => null);
    if (data?.games) S.games = data.games.filter((g) => g.enabled);
    renderGames();
  });
}

function openGame(gameId) {
  const game = S.games.find((g) => g.id === gameId);
  if (!game) {
    toast("O'yin topilmadi", "error");
    return;
  }
  S.gameId = gameId;
  if (S.room) {
    socket.send({ type: "leave" });
    S.room = null;
    destroyClient();
  }
  markTab("games");
  showTabbar();
  renderLobby(game);
}

function capacityOptions(game) {
  if (game.id === "football") return [2, 4];
  if (game.max_players > 2) return [2, 3, 4].filter((n) => n >= game.min_players && n <= game.max_players);
  return [game.min_players];
}

function settingsFields(game) {
  if (game.id === "chess") {
    return `<div class="field"><label>Vaqt nazorati</label>
      <select class="input" id="set-time">
        <option value="3">3 daqiqa</option><option value="5" selected>5 daqiqa</option><option value="10">10 daqiqa</option>
      </select></div>`;
  }
  if (game.id === "football") {
    return `<div class="field"><label>O'yin davomiyligi</label>
      <select class="input" id="set-minutes">
        <option value="2">2 daqiqa</option><option value="3" selected>3 daqiqa</option><option value="5">5 daqiqa</option>
      </select></div>`;
  }
  if (game.id === "jumanji") {
    return `<div class="field"><label>Rejim</label>
      <select class="input" id="set-mode">
        <option value="competitive" selected>Raqobat</option><option value="coop">Kooperativ</option>
      </select></div>`;
  }
  return "";
}

function collectSettings() {
  const settings = {};
  const time = $("#set-time");
  if (time) settings.time_minutes = Number(time.value);
  const minutes = $("#set-minutes");
  if (minutes) settings.seconds = Number(minutes.value) * 60;
  const mode = $("#set-mode");
  if (mode) settings.mode = mode.value;
  return settings;
}

function renderLobby(game) {
  const rating = gameRating(game.id);
  const caps = capacityOptions(game);
  const capOptions = caps.map((n) => `<option value="${n}"${n === game.min_players ? " selected" : ""}>${n} o'yinchi</option>`).join("");
  const ratingLabel = rating < 900 ? "Boshlang'ich" : rating < 1200 ? "O'rta" : rating < 1500 ? "Ilg'or" : "Ekspert";

  view().innerHTML = `
    <div class="game-top">
      <button class="icon-btn" id="lobby-back">←</button>
      <div class="grow">
        <div class="game-title">${esc(game.icon)} ${esc(game.title)}</div>
        <div class="game-status">${esc(game.description)}</div>
      </div>
    </div>

    <div class="card mt">
      <div class="row spread">
        <div>
          <div class="tiny muted">Sizning reytingingiz</div>
          <div style="font-size:20px;font-weight:800">${rating} <span class="small muted">${ratingLabel}</span></div>
        </div>
        <button class="btn ghost sm" id="skill-btn">O'zgartirish</button>
      </div>
      <div class="small muted mt-sm">${esc(game.rules || "")}</div>
    </div>

    <div class="card mt">
      <div class="card-title">⚡ Tezkor o'yin</div>
      <div class="small muted">Reytingingizga mos raqib avtomatik topiladi.</div>
      <button class="btn primary block mt-sm" id="quick-btn">Raqib qidirish</button>
      <div id="queue-box" class="mt-sm"></div>
    </div>

    <div class="card mt">
      <div class="card-title">🤖 Bot bilan o'ynash</div>
      <div class="grid-2 mt-sm">
        <div class="field" style="margin:0"><label>Daraja</label>
          <select class="input" id="bot-diff">
            <option value="easy">Oson</option><option value="normal" selected>O'rta</option><option value="hard">Qiyin</option>
          </select>
        </div>
        ${caps.length > 1 ? `<div class="field" style="margin:0"><label>Jamoa</label><select class="input" id="bot-size">${capOptions}</select></div>` : ""}
      </div>
      <button class="btn block mt-sm" id="bot-btn">Botga qarshi boshlash</button>
    </div>

    <div class="card mt">
      <div class="card-title">🏠 Xona yaratish</div>
      <div class="grid-2 mt-sm">
        <div class="field" style="margin:0"><label>O'yinchilar</label><select class="input" id="room-size">${capOptions}</select></div>
        <div class="field" style="margin:0"><label>Ko'rinish</label>
          <select class="input" id="room-public"><option value="1" selected>Ommaviy</option><option value="0">Shaxsiy</option></select>
        </div>
      </div>
      ${settingsFields(game)}
      <button class="btn block mt-sm" id="create-btn">Xona yaratish</button>
    </div>

    <div class="card mt">
      <div class="card-title">🔑 Kod bilan kirish</div>
      <div class="input-row mt-sm">
        <input class="input" id="join-code" maxlength="5" placeholder="KOL7B" autocapitalize="characters" autocomplete="off" style="text-transform:uppercase;letter-spacing:.2em;font-weight:700">
        <button class="btn" id="join-btn">Kirish</button>
      </div>
    </div>

    <div class="card mt">
      <div class="section-head" style="margin-bottom:6px"><div class="card-title">🌐 Ommaviy xonalar</div><button class="link" id="rooms-refresh">Yangilash</button></div>
      <div id="public-rooms">${loading("Xonalar yuklanmoqda...")}</div>
    </div>`;

  $("#lobby-back")?.addEventListener("click", () => { S.gameId = null; goTab("games"); });
  $("#quick-btn")?.addEventListener("click", () => {
    S.searching = true;
    socket.send({ type: "quick_match", game_id: game.id });
    renderQueueBox({ status: "searching", position: 1 });
  });
  $("#bot-btn")?.addEventListener("click", () => {
    const difficulty = $("#bot-diff")?.value || "normal";
    const capacity = Number($("#bot-size")?.value || caps[0]);
    requestRoom(game.id, { mode: "bot", public: false, capacity, difficulty, settings: collectSettings() });
  });
  $("#create-btn")?.addEventListener("click", () => {
    const difficulty = $("#bot-diff")?.value || "normal";
    const capacity = Number($("#room-size")?.value || caps[0]);
    const isPublic = $("#room-public")?.value !== "0";
    requestRoom(game.id, { mode: "room", public: isPublic, capacity, difficulty, settings: collectSettings() });
  });
  $("#join-btn")?.addEventListener("click", joinByCode);
  $("#join-code")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") joinByCode();
  });
  $("#rooms-refresh")?.addEventListener("click", () => socket.send({ type: "rooms", game_id: game.id }));
  $("#skill-btn")?.addEventListener("click", () => openSkill(game));
  socket.send({ type: "rooms", game_id: game.id });
  if (S.searching) renderQueueBox({ status: "searching" });
}

function requestRoom(gameId, options) {
  socket.send({
    type: "create_room",
    game_id: gameId,
    mode: options.mode,
    public: options.public,
    capacity: options.capacity,
    difficulty: options.difficulty,
    settings: options.settings || {},
  });
}

function joinByCode() {
  const code = ($("#join-code")?.value || "").trim().toUpperCase();
  if (code.length < 4) {
    toast("Xona kodini kiriting", "error");
    return;
  }
  socket.send({ type: "join_room", code });
}

function renderQueueBox(data) {
  const box = $("#queue-box");
  if (!box) return;
  if (!data || data.status !== "searching") {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = `
    <div class="card" style="padding:12px">
      <div class="row" style="gap:10px">
        <div class="spinner"></div>
        <div class="grow">
          <div class="small"><b>Raqib qidirilmoqda...</b></div>
          <div class="tiny muted">Reytingingizga mos o'yinchi tanlanmoqda</div>
        </div>
        <button class="btn ghost sm" id="queue-cancel">Bekor</button>
      </div>
    </div>`;
  $("#queue-cancel")?.addEventListener("click", () => cancelSearch());
}

function openSkill(game) {
  const current = gameRating(game.id);
  const presets = [[800, "Boshlang'ich"], [1000, "O'rta"], [1300, "Ilg'or"], [1600, "Ekspert"]];
  modal(
    `<h3>Ko'nikma darajasi</h3>
     <p class="small muted">${esc(game.title)} bo'yicha reyting. Mos raqiblar shu asosda topiladi.</p>
     <div class="grid-2 mt" style="grid-template-columns:repeat(2,1fr)">
       ${presets.map(([value, label]) => `<button class="btn sm ${current === value ? "primary" : "ghost"}" data-skill="${value}">${label}<br><span class="tiny muted">${value}</span></button>`).join("")}
     </div>
     <div class="field mt"><label>Qo'lda kiritish (400–2400)</label><input class="input" id="skill-custom" inputmode="numeric" value="${current}"></div>
     <div class="actions"><button class="btn ghost" data-close>Bekor</button><button class="btn primary" id="skill-save">Saqlash</button></div>`,
    {
      onMount(el, close) {
        el.querySelectorAll("[data-skill]").forEach((button) => {
          button.addEventListener("click", () => {
            el.querySelector("#skill-custom").value = button.dataset.skill;
          });
        });
        el.querySelector("#skill-save").addEventListener("click", async () => {
          const rating = Number(el.querySelector("#skill-custom").value);
          if (!Number.isFinite(rating) || rating < 400 || rating > 2400) {
            toast("Reyting 400–2400 oralig'ida bo'lsin", "error");
            return;
          }
          try {
            await api.setSkill(game.id, rating);
            const data = await api.me();
            S.profile = data.profile;
            renderTopbar();
            close();
            toast("Reyting yangilandi", "ok");
            if (S.gameId === game.id) renderLobby(game);
          } catch (err) {
            toast(err.message, "error");
          }
        });
      },
    }
  );
}

function renderPublicRooms() {
  const box = $("#public-rooms");
  if (!box || S.roomsGameId !== S.gameId) return;
  if (!S.waitingRooms.length) {
    box.innerHTML = `<div class="muted small center" style="padding:8px">Hozircha ochiq xonalar yo'q. O'zingiz yarating.</div>`;
    return;
  }
  box.innerHTML = S.waitingRooms.map((room) => `
    <div class="list-row">
      <span class="avatar-sm">${esc(gameIcon(room.game_id))}</span>
      <div class="list-main">
        <div class="list-title">${esc(room.code)} <span class="muted">· ${room.players.length}/${room.capacity}</span></div>
        <div class="list-sub">${room.players.map((p) => esc(p.name)).join(", ") || "Bo'sh"}</div>
      </div>
      <button class="btn sm" data-join="${esc(room.code)}">Kirish</button>
    </div>`).join("");
  box.querySelectorAll("[data-join]").forEach((button) => {
    button.addEventListener("click", () => socket.send({ type: "join_room", code: button.dataset.join }));
  });
}

/* ---------------- waiting room ---------------- */

function renderWaitRoom(room) {
  if (S.client) destroyClient();
  hideTabbar();
  const host = room.host_id === S.profile.id;
  const game = S.games.find((g) => g.id === room.game_id);
  const minPlayers = game?.min_players || 2;
  const canStart = host && room.players.length >= minPlayers;
  const players = room.players.map((p) => `
    <div class="list-row">
      <span class="avatar-sm">${p.avatar ? `<img src="${esc(p.avatar)}" alt="">` : initials(p.name)}</span>
      <div class="list-main"><div class="list-title">${esc(p.name)}${p.id === S.profile.id ? " (siz)" : ""}</div><div class="list-sub">${p.id === room.host_id ? "Xona egasi" : "O'yinchi"}</div></div>
      ${p.id === room.host_id ? `<span class="pill gold">Egasi</span>` : ""}
    </div>`).join("");

  view().innerHTML = `
    <div class="game-top">
      <button class="icon-btn" id="room-back">←</button>
      <div class="grow"><div class="game-title">${esc(game?.icon || "🎮")} ${esc(game?.title || room.game_id)}</div><div class="game-status">Xona kutish rejimida</div></div>
      <button class="icon-btn" id="room-chat">💬</button>
    </div>

    <div class="card glow center mt">
      <div class="tiny muted">Xona kodi</div>
      <div style="font-size:36px;font-weight:800;letter-spacing:.18em;color:var(--violet-2)">${esc(room.code)}</div>
      <div class="row mt-sm" style="justify-content:center;gap:8px">
        <button class="btn sm ghost" id="copy-code">Nusxalash</button>
        <button class="btn sm ghost" id="open-chat">Chat</button>
      </div>
      <div class="tiny muted mt-sm">${room.public ? "Ommaviy xona" : "Shaxsiy xona"} · ${room.players.length}/${room.capacity}</div>
    </div>

    <div class="card mt">
      <div class="section-head" style="margin-bottom:8px"><div class="card-title">O'yinchilar</div><span class="tiny muted">${room.players.length}/${room.capacity}</span></div>
      <div class="list">${players}</div>
    </div>

    <div class="card mt">
      ${host
        ? `<button class="btn primary block" id="start-room" ${canStart ? "" : "disabled"}>O'yinni boshlash</button>
           ${canStart ? "" : `<div class="tiny muted center mt-sm">Kamida ${minPlayers} o'yinchi kerak</div>`}`
        : `<div class="small muted center">Xona egasi o'yinni boshlashini kuting...</div>`}
      <button class="btn ghost block mt-sm" id="leave-room">Xonadan chiqish</button>
    </div>`;

  $("#room-back")?.addEventListener("click", leaveWithConfirm);
  $("#room-chat")?.addEventListener("click", openChat);
  $("#open-chat")?.addEventListener("click", openChat);
  $("#copy-code")?.addEventListener("click", () => copyCode(room.code));
  $("#start-room")?.addEventListener("click", () => socket.send({ type: "start" }));
  $("#leave-room")?.addEventListener("click", leaveWithConfirm);
}

function copyCode(code) {
  const done = () => toast("Kod nusxalandi: " + code, "ok");
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(code).then(done).catch(() => toast("Kod: " + code));
  } else {
    toast("Kod: " + code);
  }
}

function leaveWithConfirm() {
  const playing = S.room?.status === "playing";
  confirmModal(
    playing ? "O'yindan chiqish" : "Xonadan chiqish",
    playing ? "O'yin davom etayotgan bo'lsa, taslim bo'lgan hisoblanasiz." : "Xonani tark etasizmi?",
    "Chiqish"
  ).then((ok) => {
    if (!ok) return;
    S.leaveTarget = "lobby";
    socket.send({ type: "leave" });
  });
}

/* ---------------- game screen ---------------- */

function ensureGameShell(room) {
  if (S.client && S.clientCode === room.code) return;
  if ($("#game-mount") && S.clientCode === room.code) return;
  const game = S.games.find((g) => g.id === room.game_id) || { id: room.game_id, title: room.game_id, icon: "🎮" };
  showGameShell(game, room.code);
}

function showGameShell(game, code) {
  hideTabbar();
  const v = view();
  v.innerHTML = `
    <div class="game-screen">
      <div class="game-top">
        <button class="icon-btn" id="game-back" title="Chiqish">←</button>
        <div class="grow">
          <div class="game-title">${esc(game.icon)} ${esc(game.title)}</div>
          <div class="game-status" id="game-status">Xona ${esc(code)}</div>
        </div>
        <button class="icon-btn" id="game-chat" title="Chat">💬</button>
      </div>
      <div id="game-mount"></div>
    </div>`;
  $("#game-back")?.addEventListener("click", leaveWithConfirm);
  $("#game-chat")?.addEventListener("click", openChat);
  S.unread = 0;
  updateChatBadge();
}

function updateGameStatus() {
  const el = $("#game-status");
  if (!el || !S.room) return;
  const others = S.room.players.filter((p) => p.id !== S.profile.id).map((p) => p.name);
  el.textContent = `Xona ${S.room.code}${others.length ? " · " + others.join(", ") : ""}`;
}

async function mountGame(gameId, code, state) {
  destroyClient();
  const game = S.games.find((g) => g.id === gameId) || { id: gameId, title: gameId, icon: "🎮" };
  if (!document.getElementById("game-mount") || S.clientCode !== code) showGameShell(game, code);
  const mount = document.getElementById("game-mount");
  mount.innerHTML = loading("O'yin yuklanmoqda...");
  try {
    const module = await import(`${GAMES_BASE}${gameId}.js`);
    S.client = module.default;
    S.clientGameId = gameId;
    S.clientCode = code;
    mount.innerHTML = "";
    S.client.mount(mount, {
      send: (payload) => socket.send(payload),
      code,
      you: S.profile?.id,
    });
    S.client.update(state, []);
    updateGameStatus();
  } catch (err) {
    console.error(err);
    mount.innerHTML = `<div class="card center">O'yin modulini yuklab bo'lmadi.<div class="small muted mt-sm">${esc(err.message)}</div></div>`;
  }
}

function destroyClient() {
  try {
    S.client?.destroy?.();
  } catch (err) {
    console.error(err);
  }
  S.client = null;
  S.clientGameId = "";
  S.clientCode = "";
}

function cleanupRoom() {
  destroyClient();
  S.room = null;
  S.lastChat = [];
  closeChat();
}

function showResult(payload, before) {
  const rewards = payload.rewards || {};
  const result = payload.result || {};
  const outcome = rewards.outcome || "";
  const profile = payload.profile || S.profile;
  const achkoDelta = profile && before ? profile.achko - before.achko : 0;
  const xpDelta = profile && before ? profile.xp - before.xp : 0;
  const scores = scoreText(result.scores);
  const gameId = S.clientGameId || S.room?.game_id || "";
  const titles = {};
  (profile?.achievements || []).forEach((a) => { titles[a.id] = a.title; });
  const unlocked = (rewards.achievements || []).map((id) => titles[id] || id);
  const color = outcome === "win" ? "var(--green)" : outcome === "loss" ? "var(--red)" : "var(--violet-2)";
  const ratingDelta = rewards.rating_delta || 0;

  modal(
    `<div class="center">
      <div style="font-size:40px">${outcome === "win" ? "🏆" : outcome === "loss" ? "💫" : "🤝"}</div>
      <h2 class="mt-sm" style="color:${color}">${esc(OUTCOME_LABELS[outcome] || "O'yin tugadi")}</h2>
      <div class="small muted">${esc(gameTitle(gameId))}${scores ? " · " + esc(scores) : ""}${result.reason && REASONS[result.reason] ? " · " + esc(REASONS[result.reason]) : ""}</div>
    </div>
    <div class="card mt" style="background:rgba(255,255,255,.03)">
      <div class="row spread"><span class="small muted">Achko</span><b style="color:var(--violet-2)">${achkoDelta >= 0 ? "+" : ""}${achkoDelta}</b></div>
      <div class="row spread mt-sm"><span class="small muted">Tajriba</span><b style="color:var(--cyan)">${xpDelta >= 0 ? "+" : ""}${xpDelta} XP</b></div>
      ${ratingDelta ? `<div class="row spread mt-sm"><span class="small muted">Reyting</span><b style="color:${ratingDelta > 0 ? "var(--green)" : "var(--red)"}">${ratingDelta > 0 ? "+" : ""}${ratingDelta} → ${rewards.rating}</b></div>` : ""}
      ${unlocked.length ? `<div class="mt-sm"><div class="tiny muted">Yangi yutuqlar</div>${unlocked.map((t) => `<div class="small">🏅 ${esc(t)}</div>`).join("")}</div>` : ""}
    </div>
    <div class="actions">
      <button class="btn ghost" id="res-home">Bosh sahifa</button>
      <button class="btn primary" id="res-again">Yana o'ynash</button>
    </div>`,
    {
      onMount(el, close) {
        el.querySelector("#res-home").addEventListener("click", () => {
          close();
          S.leaveTarget = "home";
          socket.send({ type: "leave" });
        });
        el.querySelector("#res-again").addEventListener("click", () => {
          close();
          S.leaveTarget = "lobby";
          socket.send({ type: "leave" });
        });
      },
    }
  );
}

/* ---------------- chat ---------------- */

function setupChrome() {
  document.getElementById("top-avatar")?.addEventListener("click", () => {
    if (S.profile && !S.room) goTab("profile");
  });
  document.querySelectorAll("#tabbar .tab").forEach((button) => {
    button.addEventListener("click", () => {
      if (S.room) {
        toast("Avval xonadan chiqing", "error");
        return;
      }
      goTab(button.dataset.tab);
    });
  });
  document.getElementById("pb-toggle")?.addEventListener("click", () => music.toggle());
  document.getElementById("pb-next")?.addEventListener("click", () => music.next());
  document.getElementById("chat-close")?.addEventListener("click", closeChat);
  document.getElementById("chat-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    sendChat();
  });
}

function openChat() {
  if (!S.room) {
    toast("Chat uchun xonaga kiring", "error");
    return;
  }
  document.getElementById("chat-drawer").classList.remove("hidden");
  S.unread = 0;
  updateChatBadge();
  const box = document.getElementById("chat-messages");
  if (box) box.scrollTop = box.scrollHeight;
}

function closeChat() {
  document.getElementById("chat-drawer")?.classList.add("hidden");
}

function updateChatBadge() {
  const button = $("#game-chat") || $("#room-chat");
  if (button) button.textContent = S.unread ? "💬•" : "💬";
}

function sendChat() {
  if (!S.room) {
    toast("Chat uchun xonaga kiring", "error");
    return;
  }
  const input = document.getElementById("chat-input");
  const text = (input?.value || "").trim();
  if (!text) return;
  socket.send({ type: "chat", text });
  input.value = "";
}

function renderChatHistory(chat) {
  const box = document.getElementById("chat-messages");
  if (!box) return;
  box.innerHTML = "";
  (chat || []).forEach((message) => appendChatMessage(message, false));
  box.scrollTop = box.scrollHeight;
}

function appendChatMessage(message, live = true) {
  const box = document.getElementById("chat-messages");
  if (!box) return;
  const el = document.createElement("div");
  if (message.system) {
    el.className = "chat-msg system";
    el.innerHTML = `<div class="bubble">${esc(message.text)}</div>`;
  } else {
    const mine = message.user_id === S.profile?.id;
    el.className = `chat-msg${mine ? " mine" : ""}`;
    const more = mine ? "" : `<button class="chat-more" data-uid="${message.user_id}" data-name="${esc(message.name || "")}" title="Amallar">⋯</button>`;
    el.innerHTML = `<div class="meta"><span>${esc(message.name || "O'yinchi")}</span><span>${esc(timeShort(message.ts))}</span>${more}</div>
      <div class="bubble">${esc(message.text)}</div>`;
    el.querySelector(".chat-more")?.addEventListener("click", (event) => {
      event.stopPropagation();
      chatMenu(Number(event.currentTarget.dataset.uid), event.currentTarget.dataset.name);
    });
  }
  box.appendChild(el);
  const drawer = document.getElementById("chat-drawer");
  const open = drawer && !drawer.classList.contains("hidden");
  if (open) box.scrollTop = box.scrollHeight;
  else if (!message.system && message.user_id !== S.profile?.id && live) {
    S.unread += 1;
    updateChatBadge();
  }
}

function chatMenu(userId, name) {
  modal(
    `<h3>${esc(name || "O'yinchi")}</h3>
     <p class="small muted">Xabar muallifi bilan amallar</p>
     <div class="actions" style="flex-direction:column">
       <button class="btn ghost" id="chat-mute">Ovozsiz qilish</button>
       <button class="btn danger" id="chat-report">Shikoyat qilish</button>
       <button class="btn ghost" data-close>Yopish</button>
     </div>`,
    {
      onMount(el, close) {
        el.querySelector("#chat-mute").addEventListener("click", () => {
          socket.send({ type: "mute", target_id: userId, mute: true });
          close();
        });
        el.querySelector("#chat-report").addEventListener("click", () => {
          socket.send({ type: "report", target_id: userId, reason: "Chatdagi nomaqbul xabar" });
          close();
        });
      },
    }
  );
}

/* ---------------- shop ---------------- */

async function renderShop() {
  showTabbar();
  markTab("shop");
  view().innerHTML = `
    <div class="row spread"><div><h1>Coin do'koni</h1><div class="small muted">Faqat kosmetik buyumlar</div></div>
      <span class="chip"><span class="dot dot-coin"></span><b>${num(S.profile?.coins || 0)}</b></span></div>
    <div id="shop-body" class="mt">${loading()}</div>`;
  try {
    const data = await api.shop();
    if (S.profile) S.profile.coins = data.coins;
    renderTopbar();
    renderShopBody(data.items || []);
  } catch (err) {
    $("#shop-body").innerHTML = `<div class="card">${empty(err.message)}</div>`;
  }
}

function renderShopBody(items) {
  const categories = [...new Set(items.map((i) => i.category))];
  const active = S.shopCat && categories.includes(S.shopCat) ? S.shopCat : categories[0] || "avatar";
  const filtered = items.filter((i) => i.category === active);
  $("#shop-body").innerHTML = `
    <div class="cat-tabs">${categories.map((c) => `<button class="cat-tab ${c === active ? "active" : ""}" data-cat="${esc(c)}">${esc(SHOP_LABELS[c] || c)}</button>`).join("")}</div>
    <div class="shop-grid mt">
      ${filtered.map((item) => shopItemHtml(item)).join("") || empty("Buyumlar yo'q")}
    </div>
    <div class="card mt">
      <div class="card-title">Achko → Coin</div>
      <div class="small muted">5 achko = 1 coin. O'yinlarda yutgan achkolar bilan kosmetik buyumlar oling.</div>
      <div class="input-row mt-sm">
        <input class="input" id="ex-amount" inputmode="numeric" value="50" min="5" step="5">
        <button class="btn gold" id="ex-btn">Ayirboshlash</button>
      </div>
      <div class="tiny muted mt-sm">Balans: ${num(S.profile?.achko || 0)} achko · ${num(S.profile?.coins || 0)} coin</div>
    </div>
    <div class="card mt">
      <div class="section-head" style="margin-bottom:6px"><div class="card-title">Xaridlar tarixi</div></div>
      <div id="purchase-history" class="small muted">Yuklanmoqda...</div>
    </div>`;
  $("#shop-body").querySelectorAll("[data-cat]").forEach((button) => {
    button.addEventListener("click", () => {
      S.shopCat = button.dataset.cat;
      renderShopBody(items);
    });
  });
  $("#shop-body").querySelectorAll("[data-buy]").forEach((button) => {
    button.addEventListener("click", () => buyItem(button.dataset.buy, items));
  });
  $("#shop-body").querySelectorAll("[data-equip]").forEach((button) => {
    button.addEventListener("click", () => equipItem(button.dataset.equip, items));
  });
  $("#ex-btn")?.addEventListener("click", exchangeAchko);
  loadPurchaseHistory();
}

function shopItemHtml(item) {
  const asset = item.asset || {};
  const icon = asset.emoji || SHOP_ICONS[item.category] || "✨";
  const bg = asset.color || asset.accent || "rgba(139,92,246,.28)";
  let action = `<button class="btn primary" data-buy="${esc(item.id)}">${num(item.price)} coin</button>`;
  if (item.owned) {
    action = item.equipped
      ? `<button class="btn ghost" disabled>O'rnatilgan</button>`
      : `<button class="btn ghost" data-equip="${esc(item.id)}">O'rnatish</button>`;
  } else if (item.premium_only && !S.profile?.premium) {
    action = `<button class="btn ghost" disabled>Premium</button>`;
  }
  return `
    <div class="shop-item">
      <div class="shop-preview" style="background:radial-gradient(circle at 30% 20%, ${esc(bg)}, rgba(8,4,18,.2))">${esc(icon)}</div>
      <div class="shop-name">${esc(item.name)}</div>
      <div class="shop-price">${item.owned ? "Sizda bor" : `${num(item.price)} coin`}${item.premium_only ? " · Premium" : ""}</div>
      ${action}
    </div>`;
}

async function buyItem(itemId, items) {
  const item = items.find((i) => i.id === itemId);
  if (!item) return;
  const ok = await confirmModal("Xaridni tasdiqlash", `${item.name} — ${item.price} coin. Xarid qilinadi?`, "Sotib olish");
  if (!ok) return;
  try {
    const data = await api.buy(itemId);
    updateProfile(data.profile);
    toast("Xarid amalga oshirildi", "ok");
    await renderShop();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function equipItem(itemId, items) {
  try {
    await api.equip(itemId);
    const data = await api.me();
    S.profile = data.profile;
    applyTheme();
    renderTopbar();
    toast("Buyum o'rnatildi", "ok");
    renderShopBody(items);
  } catch (err) {
    toast(err.message, "error");
  }
}

async function exchangeAchko() {
  const button = $("#ex-btn");
  const amount = Number($("#ex-amount")?.value || 0);
  if (!Number.isInteger(amount) || amount < 5 || amount % 5 !== 0) {
    toast("Miqdor 5 ga karrali bo'lsin", "error");
    return;
  }
  button.disabled = true;
  try {
    const data = await api.exchange(amount);
    updateProfile(data.profile);
    toast(`${amount} achko → ${amount / 5} coin`, "ok");
    await renderShop();
  } catch (err) {
    toast(err.message, "error");
    button.disabled = false;
  }
}

async function loadPurchaseHistory() {
  const box = $("#purchase-history");
  if (!box) return;
  try {
    const data = await api.transactions();
    const rows = (data.transactions || []).filter((t) => ["shop", "exchange", "purchase"].includes(t.reason));
    box.innerHTML = rows.length
      ? rows.slice(0, 8).map((t) => `<div class="row spread" style="padding:5px 0"><span>${esc(t.reason === "exchange" ? "Achko ayirboshlash" : "Xarid")} · ${dateShort(t.created_at)}</span><b style="color:${t.amount >= 0 ? "var(--green)" : "var(--red)"}">${t.amount > 0 ? "+" : ""}${t.amount} ${esc(t.currency)}</b></div>`).join("")
      : `<span class="muted">Hali xarid qilinmagan</span>`;
  } catch {
    box.innerHTML = `<span class="muted">Tarix yuklanmadi</span>`;
  }
}

/* ---------------- music ---------------- */

async function renderMusic() {
  showTabbar();
  markTab("music");
  view().innerHTML = `
    <div><h1>Musiqa</h1><div class="small muted">O'yin paytida ham tinglang</div></div>
    <div class="card mt" id="music-now">
      <div class="card-title">Hozir ijro etilmoqda</div>
      <div class="small muted" id="music-now-title">Tanlanmagan</div>
    </div>
    <div class="card mt">
      <div class="row wrap" style="gap:8px">
        <button class="btn sm" id="m-play">▶ Ijro</button>
        <button class="btn sm ghost" id="m-prev">⏮ Oldingi</button>
        <button class="btn sm ghost" id="m-next">Keyingi ⏭</button>
        <button class="btn sm ghost" id="m-stop">To'xtatish</button>
        <button class="btn sm ghost" id="m-loop">🔁 Takror</button>
      </div>
      <div class="field mt-sm"><label>Ovoz balandligi</label><input type="range" id="m-vol" min="0" max="100" value="${Math.round(music.volume * 100)}" style="width:100%"></div>
    </div>
    <div class="card mt">
      <div class="card-title">Kutubxona</div>
      <div id="track-list" class="mt-sm">${loading()}</div>
    </div>
    <div class="card mt">
      <div class="card-title">Audio yuklash</div>
      <div class="small muted">mp3, m4a, ogg yoki wav · 5 MB gacha</div>
      <div class="field"><label>Fayl</label><input class="input" type="file" id="up-file" accept="audio/*"></div>
      <div class="grid-2">
        <div class="field"><label>Nomi</label><input class="input" id="up-title" placeholder="Musiqa nomi"></div>
        <div class="field"><label>Ijrochi</label><input class="input" id="up-artist" placeholder="Ijrochi"></div>
      </div>
      <button class="btn block mt-sm" id="up-btn">Yuklash</button>
      <div class="tiny muted mt-sm">Faqat ruxsatga ega audiolarni yuklang.</div>
    </div>`;
  wireMusicControls();
  await loadTrackList();
}

function wireMusicControls() {
  $("#m-play")?.addEventListener("click", async () => {
    await music.toggle();
    refreshMusicNow();
  });
  $("#m-prev")?.addEventListener("click", () => { music.prev(); refreshMusicNow(); });
  $("#m-next")?.addEventListener("click", () => { music.next(); refreshMusicNow(); });
  $("#m-stop")?.addEventListener("click", () => { music.stop(); refreshMusicNow(); refreshTrackList(); });
  $("#m-loop")?.addEventListener("click", (event) => {
    music.setLoop(!music.loop);
    event.currentTarget.classList.toggle("primary", music.loop);
    toast(music.loop ? "Takror yoqildi" : "Takror o'chirildi");
  });
  $("#m-loop")?.classList.toggle("primary", music.loop);
  $("#m-vol")?.addEventListener("input", (event) => music.setVolume(Number(event.target.value) / 100));
  $("#up-btn")?.addEventListener("click", uploadTrack);
  refreshMusicNow();
}

async function loadTrackList() {
  const box = $("#track-list");
  if (!box) return;
  try {
    await music.load(true);
    box.innerHTML = music.trackListHtml(music.tracks[music.index]?.id);
    box.querySelectorAll("[data-track]").forEach((row) => {
      row.addEventListener("click", async () => {
        await music.playById(row.dataset.track);
        refreshMusicNow();
        refreshTrackList();
      });
    });
    box.querySelectorAll("[data-del-track]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        try {
          await api.deleteTrack(button.dataset.delTrack);
          if (music.tracks[music.index]?.id === Number(button.dataset.delTrack)) music.stop();
          toast("Audio o'chirildi", "ok");
          await loadTrackList();
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
  } catch (err) {
    box.innerHTML = empty(err.message);
  }
}

function refreshTrackList() {
  const box = $("#track-list");
  if (!box) return;
  box.innerHTML = music.trackListHtml(music.tracks[music.index]?.id);
  box.querySelectorAll("[data-track]").forEach((row) => {
    row.addEventListener("click", async () => {
      await music.playById(row.dataset.track);
      refreshMusicNow();
      refreshTrackList();
    });
  });
  box.querySelectorAll("[data-del-track]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      try {
        await api.deleteTrack(button.dataset.delTrack);
        await loadTrackList();
      } catch (err) {
        toast(err.message, "error");
      }
    });
  });
}

function refreshMusicNow() {
  const title = $("#music-now-title");
  if (!title) return;
  const track = music.tracks[music.index];
  title.textContent = track ? `${track.title} — ${track.artist}${music.audio.paused ? " (to'xtatilgan)" : ""}` : "Tanlanmagan";
  const play = $("#m-play");
  if (play) play.textContent = music.audio.paused ? "▶ Ijro" : "❚❚ Pauza";
}

async function uploadTrack() {
  const file = $("#up-file")?.files?.[0];
  if (!file) {
    toast("Audio faylni tanlang", "error");
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    toast("Fayl 5 MB dan oshmasin", "error");
    return;
  }
  const button = $("#up-btn");
  button.disabled = true;
  try {
    await api.uploadTrack(file, $("#up-title")?.value.trim(), $("#up-artist")?.value.trim());
    toast("Audio yuklandi", "ok");
    $("#up-file").value = "";
    $("#up-title").value = "";
    $("#up-artist").value = "";
    await loadTrackList();
  } catch (err) {
    toast(err.message, "error");
  }
  button.disabled = false;
}

/* ---------------- rating ---------------- */

async function renderRating() {
  showTabbar();
  markTab("rating");
  const filters = [{ id: "", title: "Umumiy" }, ...S.games.map((g) => ({ id: g.id, title: g.title }))];
  const active = S.ratingGame || "";
  view().innerHTML = `
    <div><h1>Reyting</h1><div class="small muted">Har bir o'yin uchun alohida reyting</div></div>
    <div class="cat-tabs mt">${filters.map((f) => `<button class="cat-tab ${f.id === active ? "active" : ""}" data-rating="${esc(f.id)}">${esc(f.title)}</button>`).join("")}</div>
    <div id="rating-list" class="list mt">${loading()}</div>`;
  view().querySelectorAll("[data-rating]").forEach((button) => {
    button.addEventListener("click", () => {
      S.ratingGame = button.dataset.rating;
      renderRating();
    });
  });
  try {
    const data = await api.leaderboard(active);
    const box = $("#rating-list");
    if (!box) return;
    const entries = data.entries || [];
    box.innerHTML = entries.length
      ? entries.map((e) => `
        <div class="rank-row ${e.rank <= 3 ? "top" : ""}">
          <span class="rank-num">${e.rank}</span>
          <span class="avatar-sm">${e.avatar ? `<img src="${esc(e.avatar)}" alt="">` : initials(e.name)}</span>
          <div class="list-main">
            <div class="list-title">${esc(e.name)}</div>
            <div class="list-sub">${esc(gameTitle(e.game_id))} · ${e.wins}W / ${e.losses}L</div>
          </div>
          <b style="color:var(--violet-2)">${e.rating}</b>
        </div>`).join("")
      : `<div class="card">${empty("Hali reyting shakllanmagan")}</div>`;
  } catch (err) {
    $("#rating-list").innerHTML = `<div class="card">${empty(err.message)}</div>`;
  }
}

/* ---------------- profile ---------------- */

async function renderProfile() {
  showTabbar();
  markTab("profile");
  view().innerHTML = loading();
  try {
    const data = await api.me();
    S.profile = data.profile;
    S.games = (data.games || []).filter((g) => g.enabled);
    applyTheme();
    renderTopbar();
  } catch (err) {
    view().innerHTML = `<div class="card">${empty(err.message)}</div>`;
    return;
  }
  const p = S.profile;
  const stats = (p.games || []).reduce((acc, g) => {
    acc.matches += g.matches; acc.wins += g.wins; acc.losses += g.losses; acc.draws += g.draws;
    return acc;
  }, { matches: 0, wins: 0, losses: 0, draws: 0 });
  const pct = p.xp_need ? Math.min(100, Math.round((p.xp_in / p.xp_need) * 100)) : 0;
  const achievements = p.achievements || [];
  const unlockedCount = achievements.filter((a) => a.unlocked).length;
  const inventory = p.inventory || [];
  const history = p.history || [];

  view().innerHTML = `
    <div class="hero">
      <div class="hero-name">
        ${avatarHtml(p)}
        <div class="grow">
          <div class="row" style="gap:6px"><b style="font-size:17px">${esc(p.name)}</b>
            ${p.premium ? `<span class="badge">Premium</span>` : ""}
            ${p.is_admin ? `<span class="pill gold">Admin</span>` : ""}
          </div>
          <div class="small muted">${p.username ? "@" + esc(p.username) : "ID: " + p.id}</div>
        </div>
        <button class="icon-btn" id="prof-refresh">⟳</button>
      </div>
      <div class="xpbar"><i style="width:${pct}%"></i></div>
      <div class="row spread tiny muted" style="margin-top:5px"><span>${num(p.xp_in)} / ${num(p.xp_need)} XP</span><span>${p.level}-daraja</span></div>
      <div class="balance-row">
        <div class="balance"><div class="label">Achko</div><div class="value">${num(p.achko)}</div></div>
        <div class="balance"><div class="label">Coin</div><div class="value">${num(p.coins)}</div></div>
      </div>
    </div>

    <div class="stat-grid mt">
      <div class="stat"><div class="k">O'yinlar</div><div class="v">${stats.matches}</div></div>
      <div class="stat"><div class="k">G'alabalar</div><div class="v" style="color:var(--green)">${stats.wins}</div></div>
      <div class="stat"><div class="k">Mag'lubiyatlar</div><div class="v" style="color:var(--red)">${stats.losses}</div></div>
      <div class="stat"><div class="k">Yutuqlar</div><div class="v">${unlockedCount}/${achievements.length}</div></div>
    </div>

    <div class="section">
      <div class="section-head"><h2>O'yin reytinglari</h2></div>
      <div class="list">
        ${(p.games || []).length ? p.games.map((g) => `
          <div class="list-row">
            <span class="avatar-sm">${esc(gameIcon(g.game_id))}</span>
            <div class="list-main"><div class="list-title">${esc(gameTitle(g.game_id))}</div><div class="list-sub">${g.wins}W · ${g.losses}L · ${g.draws}D</div></div>
            <b style="color:var(--violet-2)">${g.rating}</b>
          </div>`).join("") : `<div class="card small muted">Hali o'yin reytingi yo'q</div>`}
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h2>Yutuqlar</h2><span class="tiny muted">${unlockedCount}/${achievements.length}</span></div>
      <div class="grid-2">
        ${achievements.map((a) => `
          <div class="card" style="padding:12px;${a.unlocked ? "" : "opacity:.55"}">
            <div class="row" style="gap:8px"><span style="font-size:22px">${esc(a.icon || "🏅")}</span>
              <div class="list-main"><div class="list-title">${esc(a.title)}</div><div class="list-sub">${a.unlocked ? "Ochilgan" : "Yopiq"}</div></div></div>
            <div class="tiny muted mt-sm">${esc(a.description)}</div>
          </div>`).join("")}
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h2>Inventar</h2><button class="link" id="prof-shop">Do'kon →</button></div>
      ${inventory.length ? `<div class="list">${inventory.map((item) => `
        <div class="list-row">
          <span class="avatar-sm">🎁</span>
          <div class="list-main"><div class="list-title">${esc(item.name)}</div><div class="list-sub">${item.equipped ? "O'rnatilgan" : "O'rnatilmagan"}</div></div>
          ${item.equipped ? `<span class="pill on">Faol</span>` : `<button class="btn sm ghost" data-inv-equip="${esc(item.item_id)}">O'rnatish</button>`}
        </div>`).join("")}</div>` : `<div class="card small muted">Inventar bo'sh. Do'kondan kosmetik buyumlar oling.</div>`}
    </div>

    <div class="section">
      <div class="section-head"><h2>O'yinlar tarixi</h2></div>
      ${history.length ? `<div class="list">${history.map(historyRow).join("")}</div>` : `<div class="card small muted">Hali o'yin o'ynamagansiz</div>`}
    </div>

    <div class="section">
      <div class="card">
        ${p.is_admin ? `<button class="btn primary block" id="open-admin">🛠 Admin panel</button>` : ""}
        <button class="btn ghost block ${p.is_admin ? "mt-sm" : ""}" id="logout-btn">Chiqish</button>
        <div class="tiny muted center mt-sm">GameHub ${esc(S.status?.version || "")} · ${num(S.status?.users || 0)} foydalanuvchi</div>
      </div>
    </div>`;

  $("#prof-refresh")?.addEventListener("click", renderProfile);
  $("#prof-shop")?.addEventListener("click", () => goTab("shop"));
  view().querySelectorAll("[data-inv-equip]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api.equip(button.dataset.invEquip);
        toast("Buyum o'rnatildi", "ok");
        renderProfile();
      } catch (err) {
        toast(err.message, "error");
      }
    });
  });
  $("#logout-btn")?.addEventListener("click", () => logout(true));
  $("#open-admin")?.addEventListener("click", openAdmin);
}

function logout(confirmFirst) {
  const go = () => {
    socket.close();
    auth.clear();
    S.profile = null;
    S.room = null;
    S.wired = false;
    location.reload();
  };
  if (!confirmFirst) return go();
  confirmModal("Chiqish", "Hisobdan chiqasizmi?", "Chiqish").then((ok) => { if (ok) go(); });
}

async function openAdmin() {
  if (S.room) return;
  hideTabbar();
  markTab("profile");
  try {
    const module = await import("./admin.js");
    module.renderAdmin(view(), {
      profile: S.profile,
      games: S.games,
      goBack: () => goTab("profile"),
      refreshProfile: async () => {
        const data = await api.me();
        S.profile = data.profile;
        renderTopbar();
      },
    });
  } catch (err) {
    console.error(err);
    toast("Admin panel yuklanmadi", "error");
    goTab("profile");
  }
}

/* ---------------- start ---------------- */

boot();
