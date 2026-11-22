const explicit = window.GAMEHUB_API || "";
export const API_BASE = explicit
  ? explicit.replace(/\/+$/, "")
  : location.protocol === "file:"
    ? "http://127.0.0.1:8000"
    : location.origin;

export const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws";
export const GAMES_BASE = new URL("../games/", import.meta.url).href;

export const tg = window.Telegram?.WebApp || null;
