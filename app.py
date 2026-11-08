import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ["TOKEN"]
SECRET = os.environ.get("SECRET", "")

PAGE = 10  # bir sahifada nechta MFY tugmasi chiqadi

DATA = json.loads((Path(__file__).parent / "regions.json").read_text(encoding="utf-8"))

REGIONS = {r["id"]: r["name"] for r in DATA["regions"]}
DISTRICTS = {d["id"]: d for d in DATA["districts"]}
QUARTERS = {q["id"]: q for q in DATA["quarters"]}

BY_DISTRICT = defaultdict(list)
for q in DATA["quarters"]:
    BY_DISTRICT[q["district_id"]].append(q)

region_count = Counter()
for d in DATA["districts"]:
    region_count[d["region_id"]] += len(BY_DISTRICT[d["id"]])

JAMI = len(DATA["quarters"])


def btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)


def home_markup():
    items = list(REGIONS.items())
    rows = []
    for i in range(0, len(items), 2):
        rows.append([btn(nom, f"r:{rid}") for rid, nom in items[i:i + 2]])
    return InlineKeyboardMarkup(rows)


def region_markup(rid):
    ds = [d for d in DATA["districts"] if d["region_id"] == rid]
    rows = []
    for i in range(0, len(ds), 2):
        rows.append([btn(d["name"], f"d:{d['id']}") for d in ds[i:i + 2]])
    rows.append([btn("⬅️ Viloyatlarga qaytish", "home")])
    return InlineKeyboardMarkup(rows)


def district_view(did, page):
    d = DISTRICTS[did]
    items = BY_DISTRICT[did]
    jami = len(items)
    pages = max(1, (jami + PAGE - 1) // PAGE)
    page = max(0, min(page, pages - 1))
    chunk = items[page * PAGE:(page + 1) * PAGE]

    rows = [[btn(q["name"], f"q:{q['id']}:{page}")] for q in chunk]
    nav = []
    if page > 0:
        nav.append(btn("◀️ Oldingi", f"p:{did}:{page - 1}"))
    if page < pages - 1:
        nav.append(btn("Keyingi ▶️", f"p:{did}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([btn("⬅️ Orqaga", f"r:{d['region_id']}")])
    rows.append([btn("🏠 Viloyatlar", "home")])

    matn = (f"📍 {REGIONS[d['region_id']]}\n"
            f"🏘 {d['name']}\n\n"
            f"MFY soni: {jami} ta\n")
    if jami:
        matn += f"Sahifa: {page + 1}/{pages}\n\nMFYni tanlang:"
    else:
        matn += "\nBu tuman uchun MFY ma'lumoti topilmadi."
    return matn, InlineKeyboardMarkup(rows)


HOME_TEXT = (f"Salom! Men viloyat va tumanlardagi MFY sonini va nomlarini ko'rsataman.\n"
             f"O'zbekiston bo'yicha jami: {JAMI} ta.\n\nViloyatni tanlang:")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HOME_TEXT, reply_markup=home_markup())


async def tugma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "home":
        await q.edit_message_text(HOME_TEXT, reply_markup=home_markup())

    elif data.startswith("r:"):
        rid = int(data[2:])
        matn = (f"📍 {REGIONS[rid]}\n\n"
                f"Jami MFY: {region_count[rid]} ta\n\n"
                f"Tuman yoki shaharni tanlang:")
        await q.edit_message_text(matn, reply_markup=region_markup(rid))

    elif data.startswith("d:"):
        matn, markup = district_view(int(data[2:]), 0)
        await q.edit_message_text(matn, reply_markup=markup)

    elif data.startswith("p:"):
        _, did, page = data.split(":")
        matn, markup = district_view(int(did), int(page))
        await q.edit_message_text(matn, reply_markup=markup)

    elif data.startswith("q:"):
        _, qid, page = data.split(":")
        mfy = QUARTERS[int(qid)]
        d = DISTRICTS[mfy["district_id"]]
        matn = (f"🏠 {mfy['name']}\n\n"
                f"🏘 Tuman: {d['name']}\n"
                f"📍 Viloyat: {REGIONS[d['region_id']]}")
        markup = InlineKeyboardMarkup([
            [btn("⬅️ Ro'yxatga qaytish", f"p:{d['id']}:{page}")],
            [btn("🏠 Viloyatlar", "home")],
        ])
        await q.edit_message_text(matn, reply_markup=markup)


# --- Webhook qismi (Vercel uchun) ---
ptb = Application.builder().token(TOKEN).updater(None).build()
ptb.add_handler(CommandHandler("start", start))
ptb.add_handler(CallbackQueryHandler(tugma))

app = FastAPI()


@app.get("/")
async def root():
    return {"holat": "Bot ishlayapti"}


@app.post("/webhook")
async def webhook(request: Request):
    if SECRET and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
        return Response(status_code=403)
    data = await request.json()
    async with ptb:
        update = Update.de_json(data, ptb.bot)
        await ptb.process_update(update)
    return Response(status_code=200)
