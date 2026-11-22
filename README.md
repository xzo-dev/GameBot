# GameHub

Telegram Mini App + bot + real vaqtli multiplayer o'yin platformasi.
Backend: **FastAPI + WebSocket + SQLAlchemy (SQLite lokal / Supabase PostgreSQL prod)**.
Frontend: **sof HTML/CSS/JS**, GitHub Pages'da ishlaydi. Barcha interfeys matnlari o'zbek tilida.

## Nima bor

| Bo'lim | Holat |
|---|---|
| Telegram `initData` tekshiruvi, HMAC sessiya, WS token auth | ✅ test qilingan |
| Xonalar: kod, ommaviy/shaxsiy, capacity, qayta ulanish | ✅ |
| Tezkor o'yin (rating oynasi bilan matchmaking) | ✅ |
| Bot rejimi: Oson / O'rta / Qiyin | ✅ |
| Xona chati: tarix, tizim xabarlari, mute, shikoyat, rate-limit | ✅ |
| Shaxmat (python-chess, soat, mat/durang, minimax bot) | ✅ |
| Jang (real vaqt, HP, 3 raund, blok/dodj, bot AI) | ✅ |
| Futbol (real vaqt 5v5, dribling, pas, zarba, sprint, almashtirish, bot AI) | ✅ |
| UNO (2–4, +2/+4, skip/reverse, bot) | ✅ |
| Jumanji sarguzashti (30 katak, zar, sinovlar, hamkorlik) | ✅ |
| Achko / coin / XP, atomik tranzaksiya, kunlik bonus, ayirboshlash | ✅ |
| Coin do'koni, inventar, kiyim/almashtirish, xarid tarixi | ✅ |
| Musiqa pleeri: 3 ta ichki trek, yuklash, pleylist/loop/volume, o'yin paytida | ✅ |
| Profil: statistika, reytinglar, qo'lda skill, yutuqlar, o'yinlar tarixi | ✅ |
| Admin panel: statistika, userlar, o'yin toggle, do'kon, shikoyatlar, loglar, sozlamalar | ✅ |
| Backup: ZIP + SHA256, preview, tasdiqlash, xavfsizlik backupi, rollback | ✅ (Telegram yuborish token bilan sinovdan o'tmagan) |
| `/health` (UptimeRobot) | ✅ |

To'lov tizimi ataylab qo'shilmagan: premium faqat kosmetik va kelajakda rasmiy provayder orqali ulanadi.
Qimor / stavka / pul chiqarish mexanikasi yo'q.

## Tuzilma

```
backend/
  app/
    main.py            # FastAPI, /health, /api/health, static /app
    config.py          # .env sozlamalari
    models.py          # SQLAlchemy modellari
    api/               # auth, profile, music, admin, ws
    games/             # base.py (kontrakt), registry.py, <game>/module.py
    games/shared/      # umumiy o'yin yordamchilari
    websocket/hub.py   # xonalar, chat, tick, reconnect, forfeit
    matchmaking/       # tezkor o'yin navbati
    services/          # economy, matches, profile
    backup/service.py  # backup / restore
    bot/runner.py      # aiogram emas, python-telegram-bot: /start /play /profile /top /admin /backup
frontend/
  index.html
  css/app.css
  js/app.js            # Mini App shell, barcha ekranlar
  js/admin.js          # admin panel
  js/ws.js             # WS menejer (backoff reconnect)
  js/music.js          # global pleer
  games/*.js           # har bir o'yin uchun klient moduli
  assets/music/*.wav   # litsenziyalangan ichki treklar (o'zimiz yaratgan)
tests/
  test_games.py        # 9 unit test
  smoke_ws.py          # WS: hello, chess bot, UNO, chat, football
  smoke_social.py      # 2 user: xona, chat, mute, report, move, reconnect, quick match
  smoke_backup.py      # backup -> download -> preview -> restore, skill, transactions
render.yaml
.github/workflows/pages.yml
```

## Lokal ishga tushirish

```bash
cp .env.example .env          # qiymatlarni to'ldiring
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Brauzer: `http://127.0.0.1:8000/app/`.
`DEV_MODE=true` bo'lsa, kirish ekranida sinov hisobi paydo bo'ladi (faqat lokal).
Telegramsiz ham test qilish mumkin, lekin **productionda `DEV_MODE=false`**.

Testlar:

```bash
python -m pytest -q              # 9 passed
python tests/smoke_ws.py         # SMOKE OK
python tests/smoke_social.py     # SOCIAL OK
python tests/smoke_backup.py     # BACKUP OK
```

## Muhit o'zgaruvchilari

| Kalit | Ma'nosi |
|---|---|
| `BOT_TOKEN` | BotFather tokeni. Bo'sh bo'lsa bot ishga tushmaydi, API ishlaydi. |
| `OWNER_ID` | Bosh admin Telegram ID. |
| `ADMIN_IDS` | Qo'shimcha adminlar, vergul bilan. |
| `BACKUP_CHANNEL_ID` | Shaxsiy kanal ID (backup fayllar shu yerga yuboriladi). |
| `DATABASE_URL` | Lokal: `sqlite+aiosqlite:///./gamehub.db`. Prod: Supabase `postgresql+asyncpg://...` |
| `FRONTEND_URL` | Mini App manzili (GitHub Pages yoki Render `/app/`). |
| `PUBLIC_BASE_URL` | Render URL; bo'sh bo'lsa bot polling rejimida ishlaydi. |
| `WEBHOOK_SECRET` | Telegram webhook yo'li uchun maxfiy qism. |
| `SECRET_KEY` | Sessiya imzosi uchun. Bo'sh bo'lsa `BOT_TOKEN`dan hosil qilinadi. |
| `DEV_MODE` | `true` faqat lokal test uchun. Productionda `false`. |

Hech qachon `.env`, token yoki `SECRET_KEY`ni GitHub'ga yubormang. `.gitignore` buni bloklaydi.

## Deploy (qisqa)

1. **BotFather**: `/newbot` → token. `/newapp` → Mini App URL = GitHub Pages manzili.
2. **Supabase**: yangi loyiha → Connection string (Session pooler, port `5432`; `asyncpg` uchun `?ssl=require`).
3. **Render**: repo'ni ulang; `render.yaml` bo'yicha `gamehub-backend` servisi yaratiladi.
   `PYTHON_VERSION=3.12.7`, `DATABASE_URL`, `BOT_TOKEN`, `SECRET_KEY`, `PUBLIC_BASE_URL`, `FRONTEND_URL` kiriting.
   Health check: `/health`.
4. **GitHub Pages**: Settings → Pages → Source **GitHub Actions**; repo variable `GAMEHUB_API=https://<render-url>` qo'shing.
   Workflow `frontend/env.js` ni yaratadi va `frontend/` ni deploy qiladi.
5. **UptimeRobot**: `https://<render-url>/health` ni har 5 daqiqada ping qiling (free tier uxlab qolmasin).
6. **Backup kanal**: botni kanalga admin qiling, `BACKUP_CHANNEL_ID` ni kiriting (`getUpdates` orqali aniqlanadi).

Batafsil: [docs/DEPLOY.md](docs/DEPLOY.md).

## Yangi o'yin qo'shish

1. `backend/app/games/<yangi>/module.py` yarating va `MODULE = SizningModul()` qo'ying.
2. `GameModule` kontraktini implement qiling: `create_state`, `on_action`, `on_timeout`, `on_tick` (real vaqt bo'lsa), `bot_move` (navbatli bo'lsa), `view`.
3. Frontend: `frontend/games/<yangi>.js` — `export default { mount(root, { send, code, you }), update(state, events), destroy() }`.
4. Hech qanday ro'yxatga yozish shart emas: registry papkalarni avtomatik skanlaydi, `app.js` klientni dinamik import qiladi.
5. O'yin ichidagi barcha amallar serverda tekshirilishi shart. Klient faqat `{type:"action", action:{...}}` yuboradi.

Batafsil: [docs/GAMES.md](docs/GAMES.md).

## Backup / restore

- `POST /api/admin/backup {kind: full|db|config}` → ZIP (`backup.json` + `meta.json`), SHA256, `BackupLog`.
- Telegram kanal sozlangan bo'lsa `sendDocument` orqali yuboriladi va `file_id` saqlanadi.
- Restore: fayl yuklash → schema/versiya tekshiruvi → **preview** (jadvallar soni, ogohlantirishlar, 15 daqiqalik HMAC token) → tasdiqlash.
- Tasdiqlanganda avval xavfsizlik backupi olinadi, keyin bitta tranzaksiyada tiklanadi; xato bo'lsa rollback.
- Backup ichida tokenlar/parollar **yo'q**.

## Xavfsizlik

- Telegram `initData` serverda HMAC-SHA256 bilan tekshiriladi; klient yuborgan Telegram ID'ga ishonilmaydi.
- WS ulanish token bilan autentifikatsiya qilinadi; xona amallari faqat o'sha xona a'zolariga.
- O'yin holati to'liq serverda; harakatlar va tranzaksiyalar serverda validatsiya qilinadi.
- Pul/coin faqat `UPDATE ... RETURNING` va idempotent tranzaksiyalar orqali.
- Chat: 300 belgi, 10 xabar/10 soniya, 0.7 s interval, mute/report.
- Yuklangan fayl: faqat audio MIME, 5 MB limit; hech qanday kod bajarilmaydi.
- Admin amallari `is_admin` tekshiruvi bilan.

## Ma'lum cheklovlar

- Telegram ichida haqiqiy `initData` bilan kirish va kanalga backup yuborish real token talab qiladi — kod yozilgan, lekin bu muhitda sinalmagan.
- Render free tier 15 daqiqa harakatsizlikdan uxlaydi; UptimeRobot bilan ochiq turing.
- SQLite bir vaqtda ko'p yozuvga mo'ljallanmagan; productionda Supabase ishlating.
- Musiqa yuklamalari (Track) backup'ga kirmaydi (faqat baza/config).

## Bosqichlar holati

1. Reja va repo skeleti — bajarildi
2. Backend yadro, auth, DB — bajarildi va test qilindi
3. O'yin modullari + registry — bajarildi va test qilindi
4. Xonalar, matchmaking, chat — bajarildi va test qilindi
5. Iqtisod, do'kon, musiqa, profil — bajarildi va test qilindi
6. Mini App frontend (barcha ekranlar + 5 o'yin klienti) — bajarildi, brauzerda sinaldi
7. Bot, admin, backup, deploy hujjatlari — bajarildi (Telegram token talab qiladigan qismlar hujjatlashtirildi)
