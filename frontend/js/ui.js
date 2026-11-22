export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function num(value) {
  const n = Number(value) || 0;
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1).replace(".0", "") + "M";
  if (Math.abs(n) >= 1e4) return (n / 1e3).toFixed(1).replace(".0", "") + "k";
  return n.toLocaleString("ru-RU").replace(",", " ");
}

export function initials(name) {
  return esc((name || "?").trim().slice(0, 1).toUpperCase());
}

export function avatar(name, url, cls = "avatar-sm") {
  return `<span class="${cls}">${url ? `<img src="${esc(url)}" alt="">` : initials(name)}</span>`;
}

export function toast(message, kind = "") {
  const box = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateY(-6px)";
    el.style.transition = "all .25s";
    setTimeout(() => el.remove(), 300);
  }, 3200);
}

export function modal(html, { onMount, onClose } = {}) {
  const root = document.getElementById("modal-root");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `<div class="modal">${html}</div>`;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    backdrop.remove();
    onClose?.();
  };
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) close();
  });
  root.appendChild(backdrop);
  backdrop.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", close));
  onMount?.(backdrop.querySelector(".modal"), close);
  return close;
}

export function confirmModal(title, text, confirmLabel = "Tasdiqlash") {
  return new Promise((resolve) => {
    let answered = false;
    modal(
      `<h3>${esc(title)}</h3><p class="muted small">${esc(text)}</p>
       <div class="actions"><button class="btn ghost" data-close>Bekor</button>
       <button class="btn primary" id="confirm-yes">${esc(confirmLabel)}</button></div>`,
      {
        onMount(el, close) {
          el.querySelector("#confirm-yes").addEventListener("click", () => {
            answered = true;
            close();
            resolve(true);
          });
        },
        onClose() {
          if (!answered) resolve(false);
        },
      }
    );
  });
}

export function timeShort(ts) {
  if (!ts) return "";
  const d = new Date(ts.length > 12 ? ts : ts * 1000);
  return d.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" });
}

export function dateShort(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("uz-UZ", { day: "2-digit", month: "short" });
  } catch {
    return "";
  }
}

export function difficultyLabel(value) {
  return { easy: "Oson", normal: "O'rta", hard: "Qiyin" }[value] || value;
}

export function loading(text = "Yuklanmoqda...") {
  return `<div class="center" style="padding:60px 0;display:flex;flex-direction:column;align-items:center;gap:12px">
    <div class="spinner"></div><span class="muted small">${esc(text)}</span></div>`;
}

export function empty(text) {
  return `<div class="center muted small" style="padding:34px 10px">${esc(text)}</div>`;
}
