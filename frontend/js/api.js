import { API_BASE } from "./config.js";

const TOKEN_KEY = "gamehub_token";

export const auth = {
  get token() { return localStorage.getItem(TOKEN_KEY) || ""; },
  set token(value) {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  },
  clear() { localStorage.removeItem(TOKEN_KEY); },
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body, form, auth: needAuth = true } = {}) {
  const headers = {};
  if (needAuth && auth.token) headers.Authorization = `Bearer ${auth.token}`;
  let payload = undefined;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(API_BASE + path, { method, headers, body: payload });
  } catch {
    throw new ApiError("Server bilan aloqa yo'q. Internetni tekshiring.", 0);
  }
  let data = null;
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    data = await response.json().catch(() => null);
  }
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? "Ma'lumot noto'g'ri" : "Xatolik yuz berdi";
    if (response.status === 401 && needAuth) auth.clear();
    throw new ApiError(message, response.status);
  }
  return data;
}

export const api = {
  base: API_BASE,
  telegramLogin: (initData) => request("/api/auth/telegram", { method: "POST", body: { init_data: initData }, auth: false }),
  devLogin: (user_id, name) => request("/api/auth/dev", { method: "POST", body: { user_id, name }, auth: false }),
  me: () => request("/api/me"),
  status: () => request("/api/status", { auth: false }),
  games: () => request("/api/games", { auth: false }),
  leaderboard: (gameId) => request(`/api/leaderboard${gameId ? `?game_id=${encodeURIComponent(gameId)}` : ""}`, { auth: false }),
  shop: () => request("/api/shop"),
  buy: (item_id) => request("/api/shop/buy", { method: "POST", body: { item_id } }),
  equip: (item_id) => request("/api/shop/equip", { method: "POST", body: { item_id } }),
  exchange: (achko) => request("/api/exchange", { method: "POST", body: { achko } }),
  setSkill: (game_id, rating) => request("/api/skill", { method: "POST", body: { game_id, rating } }),
  daily: () => request("/api/daily", { method: "POST" }),
  tracks: () => request("/api/music"),
  deleteTrack: (id) => request(`/api/music/${id}`, { method: "DELETE" }),
  uploadTrack: (file, title, artist) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title || "");
    form.append("artist", artist || "");
    return request("/api/music/upload", { method: "POST", form });
  },
  featured: () => request("/api/featured", { auth: false }),
  matches: () => request("/api/matches"),
  transactions: () => request("/api/transactions"),
  adminStats: () => request("/api/admin/stats"),
  adminUsers: (q) => request(`/api/admin/users?q=${encodeURIComponent(q || "")}`),
  adminBalance: (id, currency, amount) => request(`/api/admin/users/${id}/balance`, { method: "POST", body: { currency, amount } }),
  adminFlags: (id, flags) => request(`/api/admin/users/${id}/flags`, { method: "POST", body: flags }),
  adminToggleGame: (id, enabled) => request(`/api/admin/games/${id}/toggle`, { method: "POST", body: { enabled } }),
  adminShop: () => request("/api/admin/shop"),
  adminShopCreate: (item) => request("/api/admin/shop", { method: "POST", body: item }),
  adminShopUpdate: (id, patch) => request(`/api/admin/shop/${id}`, { method: "PATCH", body: patch }),
  adminReports: () => request("/api/admin/reports"),
  adminResolve: (id) => request(`/api/admin/reports/${id}/resolve`, { method: "POST" }),
  adminMatches: () => request("/api/admin/matches"),
  adminTransactions: () => request("/api/admin/transactions"),
  adminSettings: () => request("/api/admin/settings"),
  adminPatchSettings: (patch) => request("/api/admin/settings", { method: "PATCH", body: patch }),
  adminRooms: () => request("/api/admin/rooms"),
  adminBackup: (kind) => request("/api/admin/backup", { method: "POST", body: { kind } }),
  adminBackups: () => request("/api/admin/backups"),
  adminBackupPreview: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/admin/backup/preview", { method: "POST", form });
  },
  adminBackupRestore: (token) => request("/api/admin/backup/restore", { method: "POST", body: { token, confirm: true } }),
  adminErrors: () => request("/api/admin/errors"),
};
