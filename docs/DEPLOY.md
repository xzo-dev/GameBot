# GameHub — to'liq deploy qo'llanmasi

Bu qo'llanma GitHub, BotFather, Supabase, Render, GitHub Pages va UptimeRobot'ni
birinchi martadan boshlab sozlash uchun. Har bir qadamni tartib bilan bajaing.

Kerak bo'ladi:

- GitHub akkaunt va bo'sh repo (public yoki private — Pages uchun public osonroq);
- Telegram akkaunt;
- Supabase akkaunt (bepul);
- Render akkaunt (bepul, GitHub bilan ulanadi);
- UptimeRobot akkaunt (bepul);
- Maxfiy qiymatlarni saqlash joyi (masalan, parol menejeri).

> **Muhim:** `.env`, `BOT_TOKEN`, `SECRET_KEY`, `DATABASE_URL` hech qachon GitHub'ga
> tushmasin. Repo'dagi `.gitignore` ularni bloklaydi, lekin qiymatlarni chatga ham
> yubormang.

---

## 0. Repo'ni GitHub'ga yuklash

```bash
git init
git add .
git status          # .env, *.db, tools/, backups/ chiqmasligini tekshiring
git commit -m "GameHub"
git branch -M main
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

`frontend/env.js` ham `.gitignore`da — u GitHub Actions tomonidan avtomatik yaratiladi.

---

## 1. BotFather: bot yaratish

1. Telegram'da **@BotFather** ga yozing.
2. `/newbot` → bot nomi → username (`..._bot` bilan tugashi shart).
3. BotFather bergan **tokenni** saqlang. Bu `BOT_TOKEN`.
4. `/setdescription` va `/setabouttext` bilan o'zbekcha tavsif qo'shing.
5. `/setcommands` → quyidagilarni kiriting:

```
start - Botni ishga tushirish
play - O'yinlarni ochish
profile - Profil va statistika
top - Reyting
```

6. **Mini App'ni keyinroq** ulaymiz (4-qadamda Pages URL paydo bo'lgach):
   `/newapp` → botni tanlang → nomi `GameHub` → URL = GitHub Pages manzili
   (masalan `https://<username>.github.io/<repo>/`).
7. Menyu tugmasi uchun: `/setmenubutton` → bot → URL → tugma matni `🎮 O'ynash`.
   (Ba'zi akkauntlarda bu buyruq `/setmenubutton` emas, Bot Settings → Menu Button
   orqali ham ochiladi.)

`OWNER_ID` — sizning shaxsiy Telegram ID'ingiz. Uni **@userinfobot** orqali oling.

---

## 2. Supabase: PostgreSQL baza

1. [supabase.com](https://supabase.com) → **New project**.
2. Nom, parol (DB paroli — saqlang), region (foydalanuvchilarga yaqin).
3. Loyiha ochilgach: **Project Settings → Database → Connection string**.
4. **Session pooler** variantini tanlang (port `5432`). Render free tier IPv6
   qo'llamaydi, shuning uchun to'g'ridan-to'g'ri `db.<ref>.supabase.co` hosti
   ishlamasligi mumkin; session pooler IPv4 orqali ishlaydi va prepared
   statement'larni qo'llab-quvvatlaydi.
5. Stringni `postgresql+asyncpg://` ga o'zgartiring va SSL qo'shing:

```
postgresql+asyncpg://postgres.<ref>:<PAROL>@aws-0-<region>.pooler.supabase.com:5432/postgres?ssl=require
```

Eslatmalar:

- `asyncpg` uchun parametr `ssl=require` (u `sslmode` emas). `sslmode` yozsangiz
  ulanish `unexpected keyword argument` bilan yiqiladi.
- Parolda `@`, `/`, `#` bo'lsa URL-encode qiling (masalan `@` → `%40`).
- Transaction pooler (port `6543`) ishlatmoqchi bo'lsangiz, asyncpg prepared
  statement keshi muammo beradi — session pooler'da qoling.
- Jadvallar birinchi ishga tushishda `create_all` bilan avtomatik yaratiladi.

Bu qiymat `DATABASE_URL` bo'ladi.

---

## 3. Render: backend

Repo ildizida `render.yaml` bor. Ikki yo'l:

### A. Blueprint (tavsiya etiladi)

1. Render → **New → Blueprint** → GitHub repo'ni tanlang.
2. Render `render.yaml`ni o'qiydi: `gamehub-backend`, free plan, health check `/health`.
3. `sync: false` bilan belgilangan qiymatlarni kiriting (quyida ro'yxat).

### B. Qo'lda Web Service

- **Runtime:** Python 3
- **Build Command:** `pip install -r backend/requirements.txt`
- **Start Command:** `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/health`
- **Environment:** `PYTHON_VERSION=3.12.7` (albatta qo'lda qo'shing; standart versiya
  ba'zi paketlarda muammo beradi).

### Environment variable'lar

| Kalit | Qiymat |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `DATABASE_URL` | 2-qadamdagi Supabase URL |
| `BOT_TOKEN` | BotFather tokeni |
| `OWNER_ID` | sizning Telegram ID |
| `SECRET_KEY` | uzun tasodifiy satr (masalan 48+ belgi) |
| `FRONTEND_URL` | GitHub Pages manzili (4-qadamdan keyin) |
| `PUBLIC_BASE_URL` | `https://<servis>.onrender.com` |
| `WEBHOOK_SECRET` | tasodifiy satr (webhook yo'lini himoyalaydi) |
| `BACKUP_CHANNEL_ID` | backup kanal ID (6-qadam) |
| `ADMIN_IDS` | qo'shimcha admin ID'lari, vergul bilan (ixtiyoriy) |
| `DEV_MODE` | `false` (productionda hech qachon `true` emas) |

Deploy tugagach `https://<servis>.onrender.com/health` ni ochib tekshiring:

```json
{"status":"ok","version":"...","db":"ok","rooms":0,"online":0}
```

### Webhook yoki polling?

- `PUBLIC_BASE_URL` **va** `WEBHOOK_SECRET` ikkalasi to'ldirilgan bo'lsa, bot
  ishga tushganda Telegram'ga webhook o'rnatiladi:
  `https://<servis>.onrender.com/api/telegram/webhook/<WEBHOOK_SECRET>`.
- Aks holda bot **polling** rejimida ishlaydi. Polling ham to'g'ri ishlaydi, lekin
  Render uxlab qolganda yangilanishlar kechikadi.
- Webhook'dan polling'ga qaytish uchun `PUBLIC_BASE_URL`ni bo'shatib qayta deploy
  qiling va Telegram'da webhook'ni o'chiring:
  `https://api.telegram.org/bot<TOKEN>/deleteWebhook`.

Bot ishga tushmasa ham API va Mini App ishlayveradi — `BOT_TOKEN` bo'sh bo'lsa
bot qismi shunchaki o'chadi.

---

## 4. GitHub Pages: frontend

1. GitHub repo → **Settings → Pages** → **Source: GitHub Actions**.
2. **Settings → Secrets and variables → Actions → Variables** → **New variable**:
   - Nomi: `GAMEHUB_API`
   - Qiymati: `https://<servis>.onrender.com`
3. `main` branch'ga `frontend/` o'zgarishi push qilinsin. Workflow
   `.github/workflows/pages.yml` `frontend/env.js` faylini yaratadi va `frontend/`
   papkasini deploy qiladi.
4. Actions tugagach URL: `https://<username>.github.io/<repo>/`.
5. Shu URL'ni:
   - BotFather `/newapp` va `/setmenubutton` ga kiriting;
   - Render'dagi `FRONTEND_URL`ga kiriting (CORS va bot tugmasi uchun).

`frontend/env.js` repo'da yo'q — bu normal. Lokal ishlash uchun
`frontend/env.example.js`ni `env.js` qilib nusxalab, API manzilini yozing.

---

## 5. UptimeRobot: Render uxlab qolmasin

Render free tier ~15 daqiqa harakatsizlikdan keyin uxlaydi. Birinchi so'rov 30–60 s
kutadi.

1. UptimeRobot → **Add New Monitor**.
2. Type: **HTTP(s)**.
3. URL: `https://<servis>.onrender.com/health`.
4. Interval: **5 minutes**.
5. Alert contact: email yoki Telegram.

`/health` yengil endpoint (DB holatini ham qaytaradi), shuning uchun uni ishlatish
xavfsiz. `/api/health` ham xuddi shu javobni beradi.

---

## 6. Backup kanali

1. Telegram'da **yangi shaxsiy kanal** yarating (masalan `GameHub Backups`).
2. Botni kanalga **admin** qiling, "Post messages" huquqi bilan.
3. Kanal ID'sini oling. Eng oddiy yo'l: kanaldagi istalgan postni
   **@userinfobot** yoki **@JsonDumpBot** ga forward qiling — `forward_from_chat.id`
   `-100...` ko'rinishida bo'ladi. Shu qiymat `BACKUP_CHANNEL_ID`.
4. Render'da `BACKUP_CHANNEL_ID`ni kiriting va qayta deploy qiling.
5. Admin panel → **Backup** → backup yarating. Bot kanalga ZIP faylni yuborishi
   kerak. Yuborilmasa, sabab `Logs`da ko'rinadi (bot admin emas yoki ID xato).

Backup ichida tokenlar va parollar yo'q; faqat baza/config ma'lumotlari.

---

## 7. Deploydan keyingi tekshiruv ro'yxati

1. `https://<servis>.onrender.com/health` → `status: ok`, `db: ok`.
2. `https://<username>.github.io/<repo>/` ochiladi.
3. Botga `/start` → "O'ynash" tugmasi chiqadi va Mini App ochiladi.
4. Mini App ichida:
   - Bosh sahifa: kunlik bonus olinadi;
   - O'yinlar: shaxmatda bot bilan o'yin boshlanadi;
   - Reyting va Profil ma'lumotlari yuklanadi;
   - Coin do'koni: achko → coin ayirboshlash ishlaydi.
5. Ikki Telegram akkaunt bilan xona yarating: kod bilan qo'shilish, chat, o'yin
   sinxronligi.
6. Admin panel (`/admin` yoki bot `/admin`) → statistika, userlar, backup.
7. Render logs'da xatolik yo'qligini tekshiring.

Telegram tokenisiz lokal rejimda `DEV_MODE=true` bilan sinov hisobi orqali hammasini
tekshirish mumkin, lekin **productionda `DEV_MODE=false`**.

---

## 8. Muammolarni tuzatish

| Belgi | Sabab / yechim |
|---|---|
| `/health` 502 yoki timeout | Servis hali ko'tarilmoqda yoki uxlagan. UptimeRobot qo'shing, loglarni oching. |
| `db: error` | `DATABASE_URL` xato. `postgresql+asyncpg://`, `ssl=require`, URL-encoded parolni tekshiring. |
| `InvalidPasswordError` | Supabase paroli noto'g'ri yoki URL-encode qilinmagan. |
| Bot javob bermaydi | `BOT_TOKEN` bo'sh/xato; webhook yo'li `WEBHOOK_SECRET` bilan mos emas; Render logs'da `Bot ishga tushmadi`. |
| WS 4401 | Sessiya tokeni yo'q yoki muddati o'tgan. Mini App'ni Telegram ichida qayta oching. |
| Mini App API'ga ulanmaydi | `GAMEHUB_API` variable yo'q yoki noto'g'ri; `frontend/env.js` eski. Pages workflow'ni qayta ishga tushiring. |
| CORS xatosi | Render'dagi `FRONTEND_URL` Pages manziliga teng emas. |
| Backup kanalga bormaydi | Bot kanal admini emas yoki `BACKUP_CHANNEL_ID` noto'g'ri. |
| Lokal baza bo'sh ko'rinadi | SQLite URL nisbiy (`./gamehub.db`) — serverni repo ildizidan `--app-dir backend` bilan ishga tushiring. |

---

## 9. Xavfsizlik eslatmalari

- Productionda `DEV_MODE=false`; dev login endpoint'i o'chadi.
- `SECRET_KEY` va `WEBHOOK_SECRET`ni alohida, uzun va tasodifiy qiling.
- Telegram `initData` serverda tekshiriladi; klient yuborgan user ID'ga ishonilmaydi.
- Barcha o'yin holati va tranzaksiyalar serverda validatsiya qilinadi.
- Admin huquqi `OWNER_ID` / `ADMIN_IDS` orqali beriladi.
- To'lov tizimi ataylab yo'q; premium faqat kosmetik va kelajakda rasmiy provayder
  orqali ulanadi. Qimor/stavka/pul chiqarish yo'q.
- Yangilashdan oldin backup oling; restore avval preview va xavfsizlik backupi bilan
  ishlaydi.
