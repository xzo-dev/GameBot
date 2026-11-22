import { api } from "./api.js";
import { API_BASE } from "./config.js";
import { esc, toast } from "./ui.js";

class MusicPlayer {
  constructor() {
    this.audio = new Audio();
    this.audio.preload = "none";
    this.tracks = [];
    this.index = -1;
    this.loop = localStorage.getItem("gh_loop") !== "0";
    this.audio.loop = false;
    this.volume = Number(localStorage.getItem("gh_vol") || "0.7");
    this.audio.volume = this.volume;
    this.loaded = false;
    this.audio.addEventListener("ended", () => this.next());
    this.audio.addEventListener("play", () => this.render());
    this.audio.addEventListener("pause", () => this.render());
  }

  resolve(url) {
    if (/^https?:\/\//.test(url)) return url;
    return API_BASE + url;
  }

  async load(force = false) {
    if (this.loaded && !force) return this.tracks;
    const data = await api.tracks();
    this.tracks = data.tracks || [];
    this.loaded = true;
    return this.tracks;
  }

  render() {
    const bar = document.getElementById("player-bar");
    const title = document.getElementById("pb-title");
    const sub = document.getElementById("pb-sub");
    const toggle = document.getElementById("pb-toggle");
    if (!bar) return;
    const track = this.tracks[this.index];
    if (!track) {
      bar.classList.add("hidden");
      return;
    }
    bar.classList.remove("hidden");
    title.textContent = track.title;
    sub.textContent = track.artist + (this.audio.paused ? " · to'xtatilgan" : " · ijro etilmoqda");
    toggle.textContent = this.audio.paused ? "▶" : "❚❚";
  }

  async playIndex(index) {
    const tracks = await this.load();
    if (!tracks.length) { toast("Musiqa ro'yxati bo'sh", "error"); return; }
    this.index = ((index % tracks.length) + tracks.length) % tracks.length;
    const track = tracks[this.index];
    this.audio.src = this.resolve(track.url);
    try {
      await this.audio.play();
    } catch {
      toast("Brauzer avtoijroni blokladi. Yana bosing.", "error");
    }
    localStorage.setItem("gh_track", String(track.id));
    this.render();
  }

  async toggle() {
    if (!this.audio.src) {
      const saved = Number(localStorage.getItem("gh_track") || "0");
      const tracks = await this.load();
      const idx = Math.max(0, tracks.findIndex((t) => t.id === saved));
      await this.playIndex(idx);
      return;
    }
    if (this.audio.paused) {
      try { await this.audio.play(); } catch { toast("Ijro etib bo'lmadi", "error"); }
    } else {
      this.audio.pause();
    }
  }

  next() {
    if (!this.tracks.length) return;
    if (!this.loop && this.index >= this.tracks.length - 1) {
      this.audio.pause();
      return;
    }
    this.playIndex(this.index + 1);
  }

  prev() { this.playIndex(this.index - 1); }

  stop() {
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.index = -1;
    this.render();
  }

  setVolume(value) {
    this.volume = Math.max(0, Math.min(1, value));
    this.audio.volume = this.volume;
    localStorage.setItem("gh_vol", String(this.volume));
  }

  setLoop(value) {
    this.loop = value;
    localStorage.setItem("gh_loop", value ? "1" : "0");
  }

  async playById(id) {
    const tracks = await this.load();
    const idx = tracks.findIndex((t) => t.id === Number(id));
    if (idx >= 0) await this.playIndex(idx);
  }

  trackListHtml(currentId) {
    if (!this.tracks.length) return `<div class="muted small center" style="padding:20px">Musiqa yo'q</div>`;
    return this.tracks.map((t) => `
      <div class="list-row" data-track="${t.id}">
        <span class="list-row" style="width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:rgba(139,92,246,.16);padding:0">${t.id === currentId ? "❚❚" : "▶"}</span>
        <div class="list-main"><div class="list-title">${esc(t.title)}</div><div class="list-sub">${esc(t.artist)}${t.builtin ? "" : " · sizning audiongiz"}</div></div>
        ${t.builtin ? "" : `<button class="icon-btn" data-del-track="${t.id}" title="O'chirish">🗑</button>`}
      </div>`).join("");
  }
}

export const music = new MusicPlayer();
