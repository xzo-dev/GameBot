# O'yin modullari va protokol

Platforma modul asosida qurilgan: yangi o'yin qo'shish uchun mavjud o'yinlarga
tegish shart emas. Server modulni papkadan avtomatik topadi, klient modulni
dinamik import qiladi.

```
backend/app/games/
  base.py        # GameModule kontrakti, Player, GameError
  registry.py    # avtomatik topish, enable/disable
  shared/        # umumiy yordamchilar (bot, vaqt, matematika)
  chess/         # module.py + MODULE
  fighting/
  football/
  uno/
  jumanji/
frontend/games/
  chess.js       # mount / update / destroy
  fighting.js
  football.js
  uno.js
  jumanji.js
```

## 1. Server moduli kontrakti

Har bir o'yin `backend/app/games/<id>/module.py` faylida `GameModule`dan meros
oluvchi sinf yaratadi va modul oxirida `MODULE = Sinf()` qo'yadi.

```python
from __future__ import annotations
from typing import Any

from ..base import GameError, GameModule, Player


class MyGame(GameModule):
    id = "mygame"                 # unikal, fayl nomi bilan bir xil bo'lsin
    title = "Mening o'yinim"
    description = "Qisqa tavsif"
    icon = "🎲"
    min_players = 2
    max_players = 4
    realtime = False              # True bo'lsa hub on_tick chaqiradi
    tick_hz = 0                   # realtime bo'lsa 20 tavsiya etiladi
    turn_timeout = 45             # navbatli o'yin uchun soniya
    supports_bot = True
    modes = ("quick", "room", "bot")
    rules_text = "Qoidalar bir jumlada."

    def create_state(self, players: list[Player], settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "slots": [p.public() for p in players],
            "turn": 0,
            "finished": False,
            "winners": [],
            "reason": "",
            "log": [],
        }

    def on_action(self, state, slot, action):
        if state["finished"]:
            raise GameError("O'yin tugagan")
        if slot != state["turn"]:
            raise GameError("Hozir sizning navbatingiz emas")
        if action.get("type") != "do":
            raise GameError("Noma'lum amal")
        # ... holatni o'zgartirish, tekshiruvlar ...
        return [{"type": "did", "by": slot}]   # klientga yuboriladigan eventlar

    def on_timeout(self, state):
        # navbat vaqti tugadi
        return []

    def on_tick(self, state, dt: float):
        # faqat realtime o'yinlar uchun; dt — haqiqiy soniya
        return []

    def bot_move(self, state):
        # faqat navbatli o'yinlar uchun; hub o'zi chaqiradi
        return None

    def view(self, state, slot: int | None):
        # klientga ko'rinadigan qism. Maxfiy ma'lumotni (masalan, boshqa
        # o'yinchining qo'li) bu yerga chiqarmang.
        return {
            "your_slot": slot,
            "turn": state["turn"],
            "finished": state["finished"],
            "slots": state["slots"],
            "log": state["log"][-6:],
        }

    def finished(self, state) -> bool:
        return bool(state.get("finished"))

    def result(self, state) -> dict:
        return {
            "draw": bool(state.get("draw")),
            "winners": state.get("winners", []),
            "scores": state.get("scores", {}),
            "reason": state.get("reason", ""),
        }


MODULE = MyGame()
```

### Metodlar semantikasi

| Metod | Qachon | Nima qiladi |
|---|---|---|
| `create_state(players, settings)` | xona boshlanganda | boshlang'ich holat dict'i |
| `on_action(state, slot, action)` | o'yinchidan `{type:"action"}` kelganda | amalni **serverda** tekshiradi, holatni o'zgartiradi, eventlar qaytaradi |
| `on_timeout(state)` | navbat vaqti tugaganda | avtomatik harakat yoki pass |
| `on_tick(state, dt)` | har tick (realtime) | fizika/AI; `dt` haqiqiy vaqt |
| `bot_move(state)` | navbatli o'yinda bot navbati | bot harakati yoki `None` |
| `finished(state)` | har amaldan keyin | o'yin tugadimi |
| `result(state)` | tugaganda | g'olib, hisob, sabab |
| `view(state, slot)` | har broadcast'da | o'sha slot uchun ko'rinish |

Muhim qoidalar:

- Holat **faqat serverda** yashaydi; klient hech qachon `state`ni to'g'ridan-to'g'ri
  o'zgartirmaydi.
- Noto'g'ri amalda `GameError("o'zbekcha xabar")` tashlang — hub uni `error`
  xabari sifatida qaytaradi.
- `view`da boshqa o'yinchining yashirin ma'lumotini chiqarmang (UNO qo'li kabi).
- Realtime o'yinlarda bot AI **`on_tick` ichida** yozilishi kerak: hub `bot_move`ni
  faqat navbatli rejimda chaqiradi. Jang va futbol shunday ishlaydi.
- `players` ro'yxatidagi `slot` — 0 dan boshlanadigan indeks; `bot=True` bo'lsa
  o'yinchi bot.
- Holat dict'i JSON-serializable bo'lsin (faqat oddiy tiplar).

### Ro'yxatga olish

`registry.discover()` `backend/app/games/` ichidagi har bir papkani skanlaydi va
`module.py`dagi `MODULE`ni topadi. `shared/`, `_` bilan boshlanadigan papkalar va
`MODULE` yo'q modullar o'tkazib yuboriladi. Qo'shimcha ro'yxat yo'q.

Admin panelda o'yinni vaqtincha o'chirish mumkin (`registry.set_enabled`).
O'chirilgan o'yin katalogda `enabled: false` bilan chiqadi va xona yaratishga
ruxsat bermaydi.

---

## 2. WebSocket protokoli

Ulanish:

```
wss://<backend>/api/ws?token=<sessiya-tokeni>
```

Token `/api/auth/telegram` yoki dev rejimda `/api/auth/dev` orqali olinadi.
Token yo'q/eskirgan bo'lsa ulanish `4401` bilan yopiladi.

### Klient → server

| `type` | Payload | Ma'nosi |
|---|---|---|
| `ping` | — | `pong` qaytadi |
| `create_room` | `{game_id, capacity, mode, difficulty, public, settings}` | xona yaratish; `mode:"bot"` bo'lsa darhol boshlanadi |
| `join_room` | `{code}` | kod bo'yicha qo'shilish yoki qayta ulanish |
| `quick_match` | `{game_id, settings}` | rating oynasi bilan navbat |
| `cancel_match` | — | navbatdan chiqish |
| `start` | — | xona egasi boshlaydi (to'la bo'lsa avtomatik) |
| `leave` | — | xonadan chiqish |
| **`action`** | `{action:{type:"..."}}` | **o'yin harakati — doim ichma-ich** |
| `chat` | `{text}` | xabar (300 belgi, rate-limit) |
| `rooms` | `{game_id?}` | ommaviy xonalar ro'yxati |
| `report` | `{target_id, reason}` | shikoyat |
| `mute` | `{target_id, mute}` | o'zingiz uchun mute |
| `sync` | — | profilni qayta olish |

**Eng ko'p uchraydigan xato:** harakatni `{type:"move", ...}` qilib yuborish.
Hub uni "Noma'lum buyruq" deb rad etadi. To'g'risi:

```js
ctx.send({ type: "action", action: { type: "move", uci: "e2e4" } });
```

### Server → klient

| `type` | Payload | Ma'nosi |
|---|---|---|
| `game_state` | `{state, events, game_id, code}` | holat + shu amaldagi eventlar |
| `room_state` | `{room, chat}` | xona ma'lumoti va chat tarixi |
| `room_created` | `{code}` | xona kodi |
| `queue` | `{status, game_id, position}` | matchmaking holati |
| `match_found` | `{code, game_id}` | raqib topildi |
| `match_result` | `{result, rewards, profile}` | yakuniy natija, achko/XP |
| `room_status` | `{status}` | `waiting` / `playing` / `finished` |
| `chat` | `{text, user_id, name, ts, system?}` | chat xabari |
| `left` | — | xonadan chiqdingiz |
| `room_closed` | `{reason}` | xona yopildi |
| `toast` | `{message}` | qisqa bildirishnoma |
| `error` | `{message}` | o'zbekcha xato |
| `rooms` | `{rooms, queues}` | ro'yxat |
| `muted`, `session_replaced`, `pong`, `profile` | — | yordamchi |

Realtime o'yinda holat 10 Hz, fizika 20 Hz yangilanadi. Klient faqat oxirgi
`state`ni chizadi; input yuborish tezligi serverda cheklangan.

### Mavjud o'yinlardagi amallar

| O'yin | Amallar |
|---|---|
| `chess` | `move {uci}`, `resign`, `offer_draw`, `accept_draw`, `decline_draw` |
| `fighting` | `move {x,y}`, `attack`, `block`, `dodge`, `resign` |
| `football` | `move {x,y,sprint}`, `kick {kind:"pass"\|"shoot"}`, `switch` |
| `uno` | `play {index, color?}` (joker uchun rang), `draw`, `pass` |
| `jumanji` | `roll {energy?}` |

Futbol `state.control` — `{slot: entity_id}` obyekti (skalar emas). Boshqarilayotgan
o'yinchi: `state.control[String(state.your_slot)]`.

---

## 3. Klient moduli

`frontend/games/<id>.js` quyidagi shaklda `default` eksport qiladi:

```js
import { esc } from "../js/ui.js";

let ctx = null;
let state = null;

export default {
  mount(root, context) {
    // context = { send, code, you }
    ctx = context;
    root.innerHTML = `<div id="mg-status"></div><button id="mg-do">Bajar</button>`;
    root.querySelector("#mg-do").addEventListener("click", () => {
      ctx.send({ type: "action", action: { type: "do" } });
    });
  },

  update(newState, events) {
    state = newState;
    // holatni chizish; events — shu yangilanishdagi eventlar
  },

  destroy() {
    ctx = null;
    state = null;
    // timer, listener va audio tozalash
  },
};
```

Qoidalar:

- `ctx.send(...)` orqali faqat yuqoridagi protokol xabarlari yuboriladi.
- O'yin harakati **doim** `{type:"action", action:{...}}` ichida.
- Ism va foydalanuvchi matnini `esc()` bilan ekranlash (XSS oldini olish).
- `destroy()`da `setInterval`/`requestAnimationFrame`/audio to'xtatilsin.
- Klientda hisob-kitob qilmang: HP, ball, navbat, coin — hammasi serverdan.
- `update(state, events)` har `game_state`da chaqiriladi. Birinchi chaqiruv
  `mount`dan keyin darhol bo'ladi.

Frontend `app.js` modulni shunday yuklaydi:

```js
const module = await import(`${GAMES_BASE}${gameId}.js`);
module.default.mount(root, { send, code, you });
module.default.update(state, []);
```

Shuning uchun yangi o'yin uchun ro'yxatga yozish shart emas — fayl nomi `id` bilan
bir xil bo'lsa yetarli. Klient fayli bo'lmasa, foydalanuvchiga "modulni yuklab
bo'lmadi" ko'rsatiladi (server baribir ishlaydi).

---

## 4. Yangi o'yin qo'shish — qadamlar

1. **Server:** `backend/app/games/mygame/__init__.py` (bo'sh) va `module.py`
   yarating, `GameModule`ni implement qiling, `MODULE = MyGame()` qo'ying.
2. **Test:** `tests/test_games.py`ga qo'shing:

```python
from app.games.base import GameError, Player
from app.games.mygame.module import MODULE as MYGAME

def test_mygame_flow():
    state = MYGAME.create_state(
        [Player(slot=0, id=1, name="A"), Player(slot=1, id=2, name="B")], {}
    )
    events = MYGAME.on_action(state, 0, {"type": "do"})
    assert events
    assert MYGAME.view(state, 0)["your_slot"] == 0
```

3. **Klient:** `frontend/games/mygame.js` yarating (`mount`/`update`/`destroy`).
4. **Bot (ixtiyoriy):** navbatli bo'lsa `bot_move`, realtime bo'lsa `on_tick`
   ichida AI. Qiyinlik `settings["difficulty"]` (`easy`/`normal`/`hard`).
5. **Serverni qayta ishga tushiring** — registry yangi papkani o'zi topadi.
6. Admin panelda o'yin katalogda ko'rinishini tekshiring, xona yarating, ikki
   brauzerda sinang.

### Rasm/audio aktivlar

Faqat o'zingiz yaratgan yoki litsenziyasi aniq bo'lgan aktivlardan foydalaning.
DLS/PES/FIFA kabi o'yinlarning logotipi, formasi, musiqasi yoki boshqa aktivlarini
nusxalamang. Ichki treklar `frontend/assets/music/`da.

---

## 5. Xavfsizlik talablari (modul muallifi uchun)

- Har bir amalda `slot` haqiqatan shu o'yinchiga tegishli ekanini tekshiring
  (navbat, faol o'yinchi, tirikligi).
- Harakat parametrlarini (koordinata, indeks, UCI, rang) chegaralang va
  validatsiya qiling; `float("nan")`, cheksiz qiymat va noto'g'ri tipni rad eting.
- Tasodifiylikni serverda qiling (`random`), klientdan kelgan zarba/dice natijasiga
  ishonmang.
- Iqtisod modulda emas: coin/achko faqat `services/economy.py`dagi atomik
  funksiyalar orqali, o'yin tugagach `finalize_match` bilan beriladi.
- Yuklangan fayl yoki JSON ichidagi kodni **hech qachon bajarmang**.
- Boshqa o'yinchining maxfiy holatini `view`da chiqarmang.
- Rate-limit va chat cheklovlari hub'da; ularni chetlab o'tadigan yangi yo'l
  yaratmang.

---

## 6. Sinov

```bash
python -m pytest -q                 # unit testlar
python tests/smoke_ws.py            # WS: hello, navbat, chat, football
python tests/smoke_social.py        # 2 user: xona, mute, reconnect, quick match
```

Qo'lda tekshiruv:

1. Bot bilan xona (`mode:"bot"`) — bot navbati ishlayaptimi?
2. Ikki qurilmada xona — harakatlar sinxronmi?
3. Ulanish uzilsa 45 soniya ichida qayta ulanish — holat tiklanadimi?
4. O'yin tugagach `match_result` va reyting yangilanishi.
