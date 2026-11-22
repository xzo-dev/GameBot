import { api, auth } from "./api.js";
import { API_BASE } from "./config.js";
import {
  esc, num, toast, modal, confirmModal, loading, empty, timeShort, dateShort,
} from "./ui.js";

const A = {
  root: null,
  profile: null,
  games: [],
  goBack: () => {},
  refreshProfile: async () => {},
  tab: "stats",
};

const TABS = [
  ["stats", "Statistika"],
  ["users", "Foydalanuvchilar"],
  ["games", "O'yinlar"],
  ["rooms", "Xonalar"],
  ["shop", "Do'kon"],
  ["reports", "Shikoyatlar"],
  ["backups", "Backup"],
  ["logs", "Jurnal"],
  ["settings", "Sozlamalar"],
];

export function renderAdmin(root, options) {
  A.root = root;
  Object.assign(A, options);
  root.innerHTML = `
    <div class="row spread">
      <div><h1>Admin panel</h1><div class="small muted">GameHub boshqaruvi</div></div>
      <button class="icon-btn" id="adm-back">←</button>
    </div>
    <div class="tabs mt" id="adm-tabs">
      ${TABS.map(([id, title]) => `<button class="tab-sm ${id === A.tab ? "active" : ""}" data-admin-tab="${id}">${title}</button>`).join("")}
    </div>
    <div id="adm-body" class="mt">${loading()}</div>`;
  document.getElementById("adm-back").addEventListener("click", () => A.goBack());
  root.querySelectorAll("[data-admin-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      A.tab = button.dataset.adminTab;
      root.querySelectorAll("[data-admin-tab]").forEach((b) => b.classList.toggle("active", b === button));
      loadTab();
    });
  });
  loadTab();
}

function body() {
  return document.getElementById("adm-body");
}

function loadTab() {
  if (A.tab === "stats") return loadStats();
  if (A.tab === "users") return loadUsers();
  if (A.tab === "games") return loadGames();
  if (A.tab === "rooms") return loadRooms();
  if (A.tab === "shop") return loadShop();
  if (A.tab === "reports") return loadReports();
  if (A.tab === "backups") return loadBackups();
  if (A.tab === "logs") return loadLogs();
  if (A.tab === "settings") return loadSettings();
  body().innerHTML = empty("Bo'lim topilmadi");
}

async function guard(loader) {
  body().innerHTML = loading();
  try {
    await loader();
  } catch (err) {
    body().innerHTML = `<div class="card">${empty(err.message || "Xatolik")}</div>`;
  }
}

/* ---------------- stats ---------------- */

function loadStats() {
  return guard(async () => {
    const stats = await api.adminStats();
    const queue = Object.entries(stats.queue || {});
    body().innerHTML = `
      <div class="stat-grid">
        <div class="stat"><div class="k">Foydalanuvchilar</div><div class="v">${num(stats.users)}</div></div>
        <div class="stat"><div class="k">O'yinlar</div><div class="v">${num(stats.matches)}</div></div>
        <div class="stat"><div class="k">Achko (jami)</div><div class="v">${num(stats.achko_total)}</div></div>
        <div class="stat"><div class="k">Coin (jami)</div><div class="v">${num(stats.coins_total)}</div></div>
        <div class="stat"><div class="k">Onlayn</div><div class="v" style="color:var(--green)">${stats.online}</div></div>
        <div class="stat"><div class="k">Xonalar</div><div class="v">${stats.rooms}</div></div>
        <div class="stat"><div class="k">Ochiq shikoyat</div><div class="v" style="color:${stats.open_reports ? "var(--red)" : "var(--green)"}">${stats.open_reports}</div></div>
        <div class="stat"><div class="k">Versiya</div><div class="v" style="font-size:16px">${esc(stats.version)}</div></div>
      </div>
      <div class="card mt">
        <div class="card-title">Matchmaking navbati</div>
        ${queue.length ? queue.map(([game, count]) => `<div class="row spread small" style="padding:4px 0"><span>${esc(gameTitle(game))}</span><b>${count}</b></div>`).join("") : `<div class="small muted mt-sm">Navbat bo'sh</div>`}
      </div>
      <div class="card mt">
        <div class="card-title">O'yin modullari</div>
        <div class="list mt-sm">
          ${(stats.games || []).map((game) => `
            <div class="list-row">
              <span class="avatar-sm">${esc(gameIcon(game.id))}</span>
              <div class="list-main"><div class="list-title">${esc(game.title)}</div><div class="list-sub">${esc(game.id)}</div></div>
              <span class="pill ${game.enabled ? "on" : "off"}">${game.enabled ? "Yoqilgan" : "O'chirilgan"}</span>
            </div>`).join("")}
        </div>
      </div>`;
  });
}

/* ---------------- users ---------------- */

function loadUsers(query = "") {
  return guard(async () => {
    const data = await api.adminUsers(query);
    body().innerHTML = `
      <div class="input-row">
        <input class="input" id="adm-user-q" placeholder="Ism, username yoki ID" value="${esc(query)}">
        <button class="btn" id="adm-user-search">Qidirish</button>
      </div>
      <div class="list mt">${(data.users || []).map(userRow).join("") || empty("Foydalanuvchilar topilmadi")}</div>`;
    const search = () => loadUsers(document.getElementById("adm-user-q").value.trim());
    document.getElementById("adm-user-search").addEventListener("click", search);
    document.getElementById("adm-user-q").addEventListener("keydown", (event) => {
      if (event.key === "Enter") search();
    });
    body().querySelectorAll("[data-user-id]").forEach((row) => {
      const id = Number(row.dataset.userId);
      row.querySelector("[data-usr-balance]")?.addEventListener("click", () => userBalance(id, row.dataset.userName));
      row.querySelector("[data-usr-ban]")?.addEventListener("click", () => toggleFlag(id, "banned", row.dataset.banned !== "1"));
      row.querySelector("[data-usr-premium]")?.addEventListener("click", () => toggleFlag(id, "premium", row.dataset.premium !== "1"));
      row.querySelector("[data-usr-admin]")?.addEventListener("click", () => toggleFlag(id, "admin", row.dataset.admin !== "1"));
    });
  });
}

function userRow(user) {
  return `
    <div class="list-row" data-user-id="${user.id}" data-user-name="${esc(user.name)}" data-banned="${user.banned ? 1 : 0}" data-premium="${user.premium ? 1 : 0}" data-admin="${user.admin ? 1 : 0}" style="flex-wrap:wrap">
      <span class="avatar-sm">${esc((user.name || "?").slice(0, 1).toUpperCase())}</span>
      <div class="list-main">
        <div class="list-title">${esc(user.name)} ${user.banned ? `<span class="pill off">Bloklangan</span>` : ""}</div>
        <div class="list-sub">${user.username ? "@" + esc(user.username) : ""} · ID ${user.id} · ${user.level}-daraja · ${num(user.achko)} achko · ${num(user.coins)} coin</div>
      </div>
      <div class="row wrap" style="gap:5px">
        <button class="btn sm ghost" data-usr-balance>Balans</button>
        <button class="btn sm ghost" data-usr-ban>${user.banned ? "Blokdan chiqarish" : "Bloklash"}</button>
        <button class="btn sm ghost" data-usr-premium>${user.premium ? "Premium off" : "Premium"}</button>
        <button class="btn sm ghost" data-usr-admin>${user.admin ? "Admin off" : "Admin"}</button>
      </div>
    </div>`;
}

function userBalance(id, name) {
  modal(
    `<h3>${esc(name)}</h3><p class="small muted">Balansni o'zgartirish (manfiy ham mumkin)</p>
     <div class="field"><label>Valyuta</label><select class="input" id="bal-cur"><option value="achko">Achko</option><option value="coins">Coin</option><option value="xp">XP</option></select></div>
     <div class="field"><label>Miqdor</label><input class="input" id="bal-amount" inputmode="numeric" placeholder="100"></div>
     <div class="actions"><button class="btn ghost" data-close>Bekor</button><button class="btn primary" id="bal-save">Qo'llash</button></div>`,
    {
      onMount(el, close) {
        el.querySelector("#bal-save").addEventListener("click", async () => {
          const amount = Number(el.querySelector("#bal-amount").value);
          if (!Number.isInteger(amount) || amount === 0) {
            toast("Nolga teng bo'lmagan butun son kiriting", "error");
            return;
          }
          try {
            await api.adminBalance(id, el.querySelector("#bal-cur").value, amount);
            toast("Balans yangilandi", "ok");
            close();
            loadUsers(document.getElementById("adm-user-q")?.value || "");
          } catch (err) {
            toast(err.message, "error");
          }
        });
      },
    }
  );
}

async function toggleFlag(id, flag, value) {
  try {
    await api.adminFlags(id, { [flag]: value });
    toast("Yangilandi", "ok");
    loadUsers(document.getElementById("adm-user-q")?.value || "");
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------------- games ---------------- */

function loadGames() {
  return guard(async () => {
    const data = await api.adminStats();
    A.games = data.games || [];
    body().innerHTML = `
      <div class="small muted">O'yin modullarini yoqish yoki o'chirish. O'chirilgan o'yinlar foydalanuvchilarga ko'rinmaydi.</div>
      <div class="list mt">
        ${A.games.map((game) => `
          <div class="list-row">
            <span class="avatar-sm">${esc(gameIcon(game.id))}</span>
            <div class="list-main"><div class="list-title">${esc(game.title)}</div><div class="list-sub">${esc(game.id)}</div></div>
            <button class="btn sm ${game.enabled ? "danger" : "primary"}" data-toggle="${esc(game.id)}" data-on="${game.enabled ? 1 : 0}">${game.enabled ? "O'chirish" : "Yoqish"}</button>
          </div>`).join("")}
      </div>`;
    body().querySelectorAll("[data-toggle]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api.adminToggleGame(button.dataset.toggle, button.dataset.on !== "1");
          toast("O'yin holati yangilandi", "ok");
          loadGames();
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
  });
}

/* ---------------- rooms ---------------- */

function loadRooms() {
  return guard(async () => {
    const data = await api.adminRooms();
    const rooms = data.rooms || [];
    body().innerHTML = `
      <div class="row spread"><div class="small muted">Faol xonalar: ${rooms.length}</div><button class="btn sm ghost" id="adm-rooms-refresh">Yangilash</button></div>
      <div class="list mt">
        ${rooms.length ? rooms.map((room) => `
          <div class="list-row">
            <span class="avatar-sm">${esc(gameIcon(room.game_id))}</span>
            <div class="list-main">
              <div class="list-title">${esc(room.code)} · ${esc(gameTitle(room.game_id))}</div>
              <div class="list-sub">${room.players.map((p) => esc(p.name)).join(", ") || "Bo'sh"} · ${room.players_count}/${room.capacity} · ${esc(room.mode)}</div>
            </div>
            <span class="pill ${room.status === "playing" ? "on" : ""}">${esc(room.status)}</span>
            <span class="pill">${room.public ? "Ommaviy" : "Shaxsiy"}</span>
          </div>`).join("") : empty("Faol xonalar yo'q")}
      </div>`;
    document.getElementById("adm-rooms-refresh").addEventListener("click", loadRooms);
  });
}

/* ---------------- shop ---------------- */

function loadShop() {
  return guard(async () => {
    const data = await api.adminShop();
    const items = data.items || [];
    body().innerHTML = `
      <div class="card">
        <div class="card-title">Yangi buyum</div>
        <div class="grid-2 mt-sm">
          <div class="field" style="margin:0"><label>ID</label><input class="input" id="adm-item-id" placeholder="av_neon2"></div>
          <div class="field" style="margin:0"><label>Kategoriya</label>
            <select class="input" id="adm-item-cat">
              <option value="avatar">Avatar</option><option value="frame">Ramka</option><option value="theme">Mavzu</option>
              <option value="board">Shaxmat taxtasi</option><option value="cards">Kartalar</option><option value="victory">G'alaba effekti</option>
            </select>
          </div>
        </div>
        <div class="field"><label>Nomi</label><input class="input" id="adm-item-name" placeholder="Neon niqob"></div>
        <div class="field"><label>Tavsif</label><input class="input" id="adm-item-desc" placeholder="Qisqa tavsif"></div>
        <div class="grid-2">
          <div class="field"><label>Narx (coin)</label><input class="input" id="adm-item-price" inputmode="numeric" value="100"></div>
          <div class="field"><label>Emoji</label><input class="input" id="adm-item-emoji" maxlength="4" placeholder="🎭"></div>
        </div>
        <label class="row small mt-sm"><input type="checkbox" id="adm-item-premium"> Faqat Premium uchun</label>
        <button class="btn primary block mt-sm" id="adm-item-create">Yaratish</button>
      </div>
      <div class="table-wrap mt">
        <table class="mini-table">
          <thead><tr><th>ID</th><th>Kategoriya</th><th>Nomi</th><th>Narx</th><th>Holat</th><th></th></tr></thead>
          <tbody>
            ${items.map((item) => `
              <tr>
                <td>${esc(item.id)}</td>
                <td>${esc(item.category)}</td>
                <td>${esc(item.name)}${item.premium_only ? " ✦" : ""}</td>
                <td>${num(item.price)}</td>
                <td><span class="pill ${item.active ? "on" : "off"}">${item.active ? "Faol" : "O'chirilgan"}</span></td>
                <td class="row" style="gap:4px">
                  <button class="btn sm ghost" data-item-edit="${esc(item.id)}">Tahrir</button>
                  ${item.active ? `<button class="btn sm danger" data-item-off="${esc(item.id)}">O'chirish</button>` : ""}
                </td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>`;

    document.getElementById("adm-item-create").addEventListener("click", async () => {
      const id = document.getElementById("adm-item-id").value.trim();
      const name = document.getElementById("adm-item-name").value.trim();
      const category = document.getElementById("adm-item-cat").value;
      const price = Number(document.getElementById("adm-item-price").value);
      if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(id)) {
        toast("ID harflar bilan boshlanib, harf/raqam bo'lsin", "error");
        return;
      }
      if (!name) {
        toast("Nomni kiriting", "error");
        return;
      }
      try {
        await api.adminShopCreate({
          id,
          category,
          name,
          description: document.getElementById("adm-item-desc").value.trim(),
          price: Number.isFinite(price) ? price : 100,
          premium_only: document.getElementById("adm-item-premium").checked,
          asset: { emoji: document.getElementById("adm-item-emoji").value.trim() },
        });
        toast("Buyum yaratildi", "ok");
        loadShop();
      } catch (err) {
        toast(err.message, "error");
      }
    });

    body().querySelectorAll("[data-item-edit]").forEach((button) => {
      button.addEventListener("click", () => editItem(items.find((i) => i.id === button.dataset.itemEdit)));
    });
    body().querySelectorAll("[data-item-off]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api.adminShopUpdate(button.dataset.itemOff, { active: false });
          toast("Buyum o'chirildi", "ok");
          loadShop();
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
  });
}

function editItem(item) {
  if (!item) return;
  modal(
    `<h3>${esc(item.name)}</h3>
     <div class="field"><label>Nomi</label><input class="input" id="ed-name" value="${esc(item.name)}"></div>
     <div class="field"><label>Tavsif</label><input class="input" id="ed-desc" value="${esc(item.description || "")}"></div>
     <div class="field"><label>Narx</label><input class="input" id="ed-price" inputmode="numeric" value="${item.price}"></div>
     <label class="row small"><input type="checkbox" id="ed-premium" ${item.premium_only ? "checked" : ""}> Premium</label>
     <label class="row small mt-sm"><input type="checkbox" id="ed-active" ${item.active ? "checked" : ""}> Faol</label>
     <div class="actions"><button class="btn ghost" data-close>Bekor</button><button class="btn primary" id="ed-save">Saqlash</button></div>`,
    {
      onMount(el, close) {
        el.querySelector("#ed-save").addEventListener("click", async () => {
          try {
            await api.adminShopUpdate(item.id, {
              name: el.querySelector("#ed-name").value.trim(),
              description: el.querySelector("#ed-desc").value.trim(),
              price: Number(el.querySelector("#ed-price").value) || 0,
              premium_only: el.querySelector("#ed-premium").checked,
              active: el.querySelector("#ed-active").checked,
            });
            toast("Buyum yangilandi", "ok");
            close();
            loadShop();
          } catch (err) {
            toast(err.message, "error");
          }
        });
      },
    }
  );
}

/* ---------------- reports ---------------- */

function loadReports() {
  return guard(async () => {
    const data = await api.adminReports();
    const reports = data.reports || [];
    body().innerHTML = `
      <div class="small muted">Ochiq shikoyatlar. Shikoyat matni o'yinchi tomonidan yuborilgan.</div>
      <div class="list mt">
        ${reports.length ? reports.map((report) => `
          <div class="list-row" style="flex-wrap:wrap">
            <div class="list-main">
              <div class="list-title">${esc(report.reason)}</div>
              <div class="list-sub">Yuboruvchi: ${report.reporter_id} · Nomi: ${report.target_id || "—"} · Xona: ${esc(report.room || "—")} · ${dateShort(report.created_at)}</div>
            </div>
            <button class="btn sm primary" data-resolve="${report.id}">Hal qilindi</button>
          </div>`).join("") : empty("Ochiq shikoyatlar yo'q")}
      </div>`;
    body().querySelectorAll("[data-resolve]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api.adminResolve(button.dataset.resolve);
          toast("Shikoyat hal qilindi", "ok");
          loadReports();
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
  });
}

/* ---------------- backups ---------------- */

function loadBackups() {
  return guard(async () => {
    const data = await api.adminBackups();
    const backups = data.backups || [];
    body().innerHTML = `
      <div class="card">
        <div class="card-title">Backup yaratish</div>
        <div class="small muted">Backup Telegram kanalga yuboriladi (agar BACKUP_CHANNEL_ID sozlangan bo'lsa).</div>
        <div class="row wrap mt-sm">
          <button class="btn btn primary sm" data-backup="full">To'liq backup</button>
          <button class="btn sm ghost" data-backup="db">Faqat baza</button>
          <button class="btn sm ghost" data-backup="config">Faqat config</button>
        </div>
        <div class="tiny muted mt-sm">Deploydan oldin to'liq backup oling.</div>
      </div>
      <div class="card mt">
        <div class="card-title">Tiklash (restore)</div>
        <div class="small muted">Backup ZIP yoki JSON yuklang. Avval ko'rib chiqish, keyin tasdiqlash.</div>
        <div class="field"><input class="input" type="file" id="adm-restore-file" accept=".zip,.json,application/zip,application/json"></div>
        <button class="btn danger block" id="adm-restore-btn">Preview va tiklash</button>
      </div>
      <div class="table-wrap mt">
        <table class="mini-table">
          <thead><tr><th>ID</th><th>Turi</th><th>Fayl</th><th>Hajm</th><th>Telegram</th><th>Sana</th><th></th></tr></thead>
          <tbody>
            ${backups.map((b) => `
              <tr>
                <td>${b.id}</td><td>${esc(b.kind)}</td>
                <td class="small">${esc(b.file)}</td>
                <td>${Math.round((b.size || 0) / 1024)} KB</td>
                <td>${b.telegram_file_id ? `<span class="pill on">Yuborilgan</span>` : `<span class="pill">Lokal</span>`}</td>
                <td class="small">${b.created_at ? dateShort(b.created_at) : ""}</td>
                <td><button class="btn sm ghost" data-backup-dl="${b.id}" data-file="${esc(b.file)}">Yuklab olish</button></td>
              </tr>`).join("") || `<tr><td colspan="7" class="muted">Backup yo'q</td></tr>`}
          </tbody>
        </table>
      </div>`;

    body().querySelectorAll("[data-backup]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const result = await api.adminBackup(button.dataset.backup);
          toast(`Backup yaratildi: ${result.file}${result.telegram_sent ? " · Telegramga yuborildi" : " · faqat lokal"}`, "ok");
          loadBackups();
        } catch (err) {
          toast(err.message, "error");
          button.disabled = false;
        }
      });
    });

    body().querySelectorAll("[data-backup-dl]").forEach((button) => {
      button.addEventListener("click", () => downloadBackup(Number(button.dataset.backupDl), button.dataset.file));
    });

    document.getElementById("adm-restore-btn").addEventListener("click", async () => {
      const file = document.getElementById("adm-restore-file").files?.[0];
      if (!file) {
        toast("Backup faylni tanlang", "error");
        return;
      }
      try {
        const preview = await api.adminBackupPreview(file);
        showRestorePreview(preview);
      } catch (err) {
        toast(err.message, "error");
      }
    });
  });
}

async function downloadBackup(id, fileName) {
  try {
    const response = await fetch(`${API_BASE}/api/admin/backups/${id}/download`, {
      headers: { Authorization: `Bearer ${auth.token}` },
    });
    if (!response.ok) throw new Error("Faylni yuklab bo'lmadi");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName || `backup_${id}.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (err) {
    toast(err.message, "error");
  }
}

function showRestorePreview(preview) {
  const counts = Object.entries(preview.counts || {});
  const current = preview.current || {};
  modal(
    `<h3>Tiklashni ko'rib chiqish</h3>
     <div class="small muted">Versiya: ${esc(preview.version || "—")} · Turi: ${esc(preview.kind || "—")} · ${esc(preview.created_at || "")}</div>
     ${(preview.warnings || []).map((w) => `<div class="card mt-sm" style="padding:9px;border-color:rgba(245,197,66,.35)"><span class="small" style="color:var(--gold)">${esc(w)}</span></div>`).join("")}
     <div class="table-wrap mt">
       <table class="mini-table">
         <thead><tr><th>Jadval</th><th>Hozir</th><th>Backup</th></tr></thead>
         <tbody>${counts.map(([name, count]) => `<tr><td>${esc(name)}</td><td>${current[name] ?? "—"}</td><td>${count}</td></tr>`).join("")}</tbody>
       </table>
     </div>
     <div class="tiny muted mt-sm">Tiklashdan oldin avtomatik xavfsizlik backupi olinadi. Bu amal joriy ma'lumotlarni almashtiradi.</div>
     <div class="actions"><button class="btn ghost" data-close>Bekor</button><button class="btn danger" id="restore-apply">Tiklash</button></div>`,
    {
      onMount(el, close) {
        el.querySelector("#restore-apply").addEventListener("click", async () => {
          const ok = await confirmModal(
            "Tiklashni tasdiqlang",
            "Barcha joriy foydalanuvchi va o'yin ma'lumotlari backup bilan almashtiriladi.",
            "Tiklash"
          );
          if (!ok) return;
          try {
            const result = await api.adminBackupRestore(preview.token);
            close();
            toast(`Tiklandi. Xavfsizlik backupi: ${result.safety_backup}`, "ok");
            await A.refreshProfile();
            setTimeout(() => location.reload(), 1400);
          } catch (err) {
            toast(err.message, "error");
          }
        });
      },
    }
  );
}

/* ---------------- logs ---------------- */

function loadLogs(kind = "errors") {
  return guard(async () => {
    body().innerHTML = `
      <div class="tabs">
        <button class="tab-sm ${kind === "errors" ? "active" : ""}" data-log="errors">Xatolar</button>
        <button class="tab-sm ${kind === "matches" ? "active" : ""}" data-log="matches">O'yinlar</button>
        <button class="tab-sm ${kind === "transactions" ? "active" : ""}" data-log="transactions">Tranzaksiyalar</button>
      </div>
      <div id="adm-log-body" class="mt">${loading()}</div>`;
    body().querySelectorAll("[data-log]").forEach((button) => {
      button.addEventListener("click", () => loadLogs(button.dataset.log));
    });
    const box = document.getElementById("adm-log-body");
    if (kind === "errors") {
      const data = await api.adminErrors();
      box.innerHTML = (data.errors || []).length ? `<div class="list">${data.errors.map((e) => `
        <div class="list-row" style="align-items:flex-start">
          <div class="list-main"><div class="list-title" style="white-space:normal">${esc(e.message)}</div>
          <div class="list-sub">${esc(e.source)} · ${esc(e.level)} · ${timeShort(e.created_at)}</div></div>
        </div>`).join("")}</div>` : empty("Xatolar yo'q");
    } else if (kind === "matches") {
      const data = await api.adminMatches();
      box.innerHTML = (data.matches || []).length ? `<div class="table-wrap"><table class="mini-table">
        <thead><tr><th>ID</th><th>O'yin</th><th>Xona</th><th>Rejim</th><th>Natija</th><th>Sana</th></tr></thead>
        <tbody>${data.matches.map((m) => `<tr><td>${m.id}</td><td>${esc(gameTitle(m.game_id))}</td><td>${esc(m.room || "")}</td><td>${esc(m.mode)}</td><td class="small">${esc(JSON.stringify(m.result || {}))}</td><td>${timeShort(m.ended_at)}</td></tr>`).join("")}</tbody>
      </table></div>` : empty("O'yinlar yo'q");
    } else {
      const data = await api.adminTransactions();
      box.innerHTML = (data.transactions || []).length ? `<div class="table-wrap"><table class="mini-table">
        <thead><tr><th>ID</th><th>Foydalanuvchi</th><th>Valyuta</th><th>Miqdor</th><th>Balans</th><th>Sabab</th><th>Sana</th></tr></thead>
        <tbody>${data.transactions.map((t) => `<tr><td>${t.id}</td><td>${t.user_id}</td><td>${esc(t.currency)}</td><td style="color:${t.amount >= 0 ? "var(--green)" : "var(--red)"}">${t.amount}</td><td>${t.balance}</td><td>${esc(t.reason)}</td><td>${timeShort(t.created_at)}</td></tr>`).join("")}</tbody>
      </table></div>` : empty("Tranzaksiyalar yo'q");
    }
  });
}

/* ---------------- settings ---------------- */

function loadSettings() {
  return guard(async () => {
    const settings = await api.adminSettings();
    const maintenance = Boolean(settings.maintenance?.enabled);
    const featured = settings.featured?.games || [];
    const games = await api.games();
    body().innerHTML = `
      <div class="card">
        <div class="row spread">
          <div><div class="card-title">Texnik xizmat</div><div class="small muted">Yoqilganda oddiy foydalanuvchilar uchun ilova yopiladi.</div></div>
          <button class="btn sm ${maintenance ? "danger" : "ghost"}" id="adm-maint">${maintenance ? "O'chirish" : "Yoqish"}</button>
        </div>
      </div>
      <div class="card mt">
        <div class="card-title">Tanlangan o'yinlar</div>
        <div class="small muted">Bosh sahifada ko'rsatiladigan o'yinlar.</div>
        <div class="list mt-sm">
          ${(games.games || []).map((game) => `
            <label class="list-row" style="cursor:pointer">
              <span class="avatar-sm">${esc(game.icon)}</span>
              <div class="list-main"><div class="list-title">${esc(game.title)}</div><div class="list-sub">${esc(game.id)}</div></div>
              <input type="checkbox" data-featured="${esc(game.id)}" ${featured.includes(game.id) ? "checked" : ""}>
            </label>`).join("")}
        </div>
        <button class="btn primary block mt-sm" id="adm-featured-save">Saqlash</button>
      </div>`;
    document.getElementById("adm-maint").addEventListener("click", async () => {
      try {
        await api.adminPatchSettings({ maintenance: { enabled: !maintenance } });
        toast("Texnik xizmat holati yangilandi", "ok");
        loadSettings();
      } catch (err) {
        toast(err.message, "error");
      }
    });
    document.getElementById("adm-featured-save").addEventListener("click", async () => {
      const ids = [...body().querySelectorAll("[data-featured]:checked")].map((input) => input.dataset.featured);
      try {
        await api.adminPatchSettings({ featured: ids });
        toast("Tanlangan o'yinlar yangilandi", "ok");
      } catch (err) {
        toast(err.message, "error");
      }
    });
  });
}

/* ---------------- helpers ---------------- */

function gameTitle(id) {
  return A.games.find((g) => g.id === id)?.title || id;
}

function gameIcon(id) {
  return A.games.find((g) => g.id === id)?.icon || "🎮";
}
