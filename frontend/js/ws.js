import { WS_URL } from "./config.js";
import { auth } from "./api.js";

export class GameSocket {
  constructor() {
    this.ws = null;
    this.handlers = new Map();
    this.connected = false;
    this.stopped = false;
    this.attempts = 0;
    this.pending = [];
    this.hb = null;
  }

  on(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type).add(fn);
    return () => this.handlers.get(type)?.delete(fn);
  }

  emit(type, data) {
    for (const fn of this.handlers.get(type) || []) {
      try { fn(data); } catch (err) { console.error(err); }
    }
  }

  connect() {
    this.stopped = false;
    if (!auth.token) return;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
    const socket = new WebSocket(`${WS_URL}?token=${encodeURIComponent(auth.token)}`);
    this.ws = socket;
    socket.onopen = () => {
      this.connected = true;
      this.attempts = 0;
      this.emit("open");
      this.flush();
      clearInterval(this.hb);
      this.hb = setInterval(() => this.send({ type: "ping" }), 22000);
    };
    socket.onmessage = (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch { return; }
      this.emit(data.type, data);
      this.emit("*", data);
    };
    socket.onclose = (event) => {
      this.connected = false;
      clearInterval(this.hb);
      this.emit("close", event);
      if (this.stopped) return;
      if (event.code === 4401) {
        this.emit("unauthorized");
        return;
      }
      this.attempts += 1;
      const delay = Math.min(8000, 600 * 2 ** Math.min(this.attempts, 4));
      setTimeout(() => this.connect(), delay);
    };
    socket.onerror = () => {};
  }

  send(payload) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
      return true;
    }
    this.pending.push(payload);
    return false;
  }

  flush() {
    while (this.pending.length && this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(this.pending.shift()));
    }
  }

  reset() {
    this.pending = [];
  }

  close() {
    this.stopped = true;
    clearInterval(this.hb);
    try { this.ws?.close(); } catch {}
    this.ws = null;
    this.connected = false;
  }
}

export const socket = new GameSocket();
