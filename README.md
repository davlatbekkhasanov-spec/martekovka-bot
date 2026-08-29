# martekovka-bot

Martekovka (markerovka) vaqt + miqdor boti. Natijalar `davlat-yordamchi-bot` hub orqali **Фасовка** kategoriyasiga tushadi.

## Ishlatish

1. `/start` — ro'yxatdagi xodimlar
2. **▶️ Boshlash** → **⏸ Tanaffus** / **▶️ Davom etish** → **✔️ Tugatish**
3. Pozitsiya sonini kiriting (masalan `108`)

## Railway env

```
BOT_TOKEN=
ADMIN_IDS=
DB_PATH=/data/martekovka.db
TZ=Asia/Tashkent
YORDAMCHI_HUB_URL=https://davlat-yordamchi-bot-production.up.railway.app
YORDAMCHI_HUB_SECRET=   # hub bilan bir xil
```

Volume: mount path `/data`

## Hub

- `bot_key`: `martekovka`
- Summary: `Martekovka: poz N, ish HH:MM:SS, dam HH:MM:SS`
- Ball: 1 poz = 1 ball (Фасовка)
