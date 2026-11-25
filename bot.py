"""
inson.lab kitob do'koni boti.
To'lov: karta orqali, mijoz chek yuboradi, admin tasdiqlaydi, bot kitobni o'zi yuboradi.
Sotuv: rasmli katalog, bepul parchalar, aksiya narxi, to'plam, eslatmalar, test.
"""
import asyncio
import html
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from catalog import BOOKS, BUNDLE, BY_SLUG

# ---------------- Sozlamalar (Railway Variables) ----------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "atadjanov_jasur").lstrip("@").lower()
CARD_NUMBER = os.getenv("CARD_NUMBER", "5614 6819 1902 5738")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Atadjanov Jasur")
DB_PATH = os.getenv("DB_PATH", "data/shop.db")
TZ = ZoneInfo("Asia/Tashkent")
PRICE = int(os.getenv("PRICE", "49000"))
PROMO_PRICE = int(os.getenv("PROMO_PRICE", "39000"))
BUNDLE_PRICE = int(os.getenv("BUNDLE_PRICE", "149000"))
BUNDLE_PROMO = int(os.getenv("BUNDLE_PROMO", "119000"))
PROMO_UNTIL = datetime.fromisoformat(os.getenv("PROMO_UNTIL", "2026-11-30T23:59")).replace(tzinfo=TZ)
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
CHANNEL = os.getenv("CHANNEL", "@insonlab")
CHANNEL_POSTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channel_posts.json")

logging.basicConfig(level=logging.INFO)
router = Router()

TYPES = {"pdf": "📘 PDF kitob", "channel": "🔒 Yopiq kanal", "consult": "💬 Konsultatsiya", "bundle": "📚 To'plam"}
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


# ---------------- Narxlar ----------------
def now():
    return datetime.now(TZ)


def promo_on():
    return now() <= PROMO_UNTIL


def promo_date():
    return f"{PROMO_UNTIL.day}-{MONTHS[PROMO_UNTIL.month - 1]}"


def money(n):
    return f"{n:,}".replace(",", " ") + " so'm"


def slug_price(slug):
    if slug == "all":
        return BUNDLE_PROMO if promo_on() else BUNDLE_PRICE
    return PROMO_PRICE if promo_on() else PRICE


def price_line(slug):
    full = BUNDLE_PRICE if slug == "all" else PRICE
    if promo_on():
        return f"💰 <s>{money(full)}</s> → <b>{money(slug_price(slug))}</b>\n⏳ Aksiya {promo_date()}gacha"
    return f"💰 Narxi: <b>{money(full)}</b>"


def product_price(p):
    return slug_price(p["slug"]) if p["slug"] else p["price"]


# ---------------- Ma'lumotlar bazasi ----------------
def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT, title TEXT, description TEXT, price INTEGER,
            file_id TEXT, channel_id INTEGER, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, full_name TEXT,
            product_id INTEGER, status TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, joined TEXT);
        CREATE TABLE IF NOT EXISTS followups(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT,
            slug TEXT, due TEXT, done INTEGER DEFAULT 0);
        """)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(products)")}
        for col in ("sample_file_id", "bundle_ids", "slug"):
            if col not in cols:
                c.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT")
        ocols = {r["name"] for r in c.execute("PRAGMA table_info(orders)")}
        if "amount" not in ocols:
            c.execute("ALTER TABLE orders ADD COLUMN amount INTEGER")
        ucols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        for col in ("source", "username", "full_name"):
            if col not in ucols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
        # inson.lab kitoblarini katalogga qo'shish (bir marta)
        for b in BOOKS + [BUNDLE]:
            row = c.execute("SELECT id FROM products WHERE slug=?", (b["slug"],)).fetchone()
            t = "bundle" if b["slug"] == "all" else "pdf"
            if not row:
                c.execute("INSERT INTO products(type,title,description,price,slug,active) VALUES(?,?,?,?,?,1)",
                          (t, b["title"], b.get("short", ""), slug_price(b["slug"]), b["slug"]))
            else:
                c.execute("UPDATE products SET active=1, title=? WHERE slug=?", (b["title"], b["slug"]))
        # Oldin qo'lda qo'shilgan kitob bo'lsa, PDF'ini olib, eskisini yashiramiz
        for b in BOOKS:
            old = c.execute("SELECT * FROM products WHERE slug IS NULL AND type='pdf' AND file_id IS NOT NULL "
                            "AND lower(title) LIKE ?", (f"%{b['title'].lower()[:8]}%",)).fetchone()
            if old:
                c.execute("UPDATE products SET file_id=COALESCE(file_id, ?) WHERE slug=?", (old["file_id"], b["slug"]))
                c.execute("UPDATE products SET active=0 WHERE id=?", (old["id"],))


def get_setting(key):
    with db() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None


def set_setting(key, value):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))


def admin_id():
    v = get_setting("admin_id")
    return int(v) if v else None


def is_admin(user):
    aid = admin_id()
    return aid is not None and user.id == aid


def by_slug(slug):
    with db() as c:
        return c.execute("SELECT * FROM products WHERE slug=?", (slug,)).fetchone()


def get_product(pid, active_only=True):
    with db() as c:
        q = "SELECT * FROM products WHERE id=?" + (" AND active=1" if active_only else "")
        return c.execute(q, (pid,)).fetchone()


def bundle_items(p):
    if p["slug"] == "all":
        return [by_slug(b["slug"]) for b in BOOKS]
    ids = [int(x) for x in (p["bundle_ids"] or "").split(",") if x.strip().isdigit()]
    if not ids:
        return []
    with db() as c:
        return c.execute(f"SELECT * FROM products WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()


def bought(uid, slug):
    """Foydalanuvchi bu kitobni (yoki to'plamni) olganmi / chek yuborganmi."""
    with db() as c:
        rows = c.execute("SELECT p.slug FROM orders o JOIN products p ON p.id=o.product_id "
                         "WHERE o.user_id=? AND o.status IN ('pending','approved')", (uid,)).fetchall()
    have = {r["slug"] for r in rows}
    return "all" in have or slug in have


# ---------------- Rasm va fayllar (file_id keshlanadi) ----------------
async def send_asset_photo(bot, chat_id, name, caption, kb):
    key = f"img:{name}"
    fid = get_setting(key)
    if fid:
        try:
            return await bot.send_photo(chat_id, fid, caption=caption, reply_markup=kb)
        except Exception:
            logging.warning("Kesh rasm ishlamadi: %s", name)
    msg = await bot.send_photo(chat_id, FSInputFile(os.path.join(ASSETS, name)), caption=caption, reply_markup=kb)
    set_setting(key, msg.photo[-1].file_id)
    return msg


async def send_sample_doc(bot, chat_id, book, caption, kb):
    p = by_slug(book["slug"])
    if p and p["sample_file_id"]:
        try:
            return await bot.send_document(chat_id, p["sample_file_id"], caption=caption, reply_markup=kb)
        except Exception:
            logging.warning("Kesh parcha ishlamadi: %s", book["slug"])
    path = os.path.join(ASSETS, "samples", f"{book['file']}_parcha.pdf")
    msg = await bot.send_document(chat_id, FSInputFile(path), caption=caption, reply_markup=kb)
    with db() as c:
        c.execute("UPDATE products SET sample_file_id=? WHERE slug=?", (msg.document.file_id, book["slug"]))
    return msg


# ---------------- Klaviaturalar ----------------
MENU = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📚 Kitoblar"), KeyboardButton(text="🔥 5 tasi bittada")],
    [KeyboardButton(text="🎁 Bepul parcha"), KeyboardButton(text="🧭 Qaysi biri menga mos?")],
    [KeyboardButton(text="💬 Savol berish")],
], resize_keyboard=True)


def books_kb():
    b = InlineKeyboardBuilder()
    for bk in BOOKS:
        b.button(text=f"{bk['emoji']} {bk['title']} — {bk['short']}", callback_data=f"v:{bk['slug']}")
    b.button(text=f"🔥 5 tasi bittada — {money(slug_price('all'))}", callback_data="v:all")
    with db() as c:  # admin qo'shgan boshqa mahsulotlar (kanal, konsultatsiya)
        extra = c.execute("SELECT * FROM products WHERE active=1 AND slug IS NULL AND type IN ('channel','consult')").fetchall()
    for p in extra:
        b.button(text=f"{TYPES[p['type']].split()[0]} {p['title']} — {money(p['price'])}", callback_data=f"p:{p['id']}")
    b.adjust(1)
    return b.as_markup()


def book_kb(slug):
    b = InlineKeyboardBuilder()
    b.button(text=f"🛒 Sotib olish — {money(slug_price(slug))}", callback_data=f"buy:{slug}")
    b.button(text="📖 Bepul parchani o'qish", callback_data=f"smp:{slug}")
    b.button(text=f"🔥 5 tasi birga — {money(slug_price('all'))}", callback_data="v:all")
    b.button(text="⬅️ Barcha kitoblar", callback_data="books")
    b.adjust(1)
    return b.as_markup()


def admin_kb():
    b = InlineKeyboardBuilder()
    b.button(text="📚 Kitob PDF'lari holati", callback_data="a:books")
    b.button(text="📣 Hammaga xabar yuborish", callback_data="a:bc")
    b.button(text="🔗 Instagram / kanal havolalari", callback_data="a:links")
    b.button(text="📊 Statistika", callback_data="a:stats")
    b.button(text="➕ Boshqa mahsulot (kanal/konsultatsiya)", callback_data="a:add")
    b.button(text="📋 Boshqa mahsulotlar", callback_data="a:list")
    b.adjust(1)
    return b.as_markup()


# ---------------- Holatlar ----------------
class Buy(StatesGroup):
    waiting_screenshot = State()


class Add(StatesGroup):
    type = State()
    title = State()
    description = State()
    price = State()
    payload = State()


class Admin(StatesGroup):
    attach = State()
    broadcast = State()


# ---------------- Eslatmalar ----------------
def plan(uid, kind, slug, minutes):
    with db() as c:
        if c.execute("SELECT 1 FROM followups WHERE user_id=? AND kind=? AND slug=? AND done=0",
                     (uid, kind, slug)).fetchone():
            return
        c.execute("INSERT INTO followups(user_id,kind,slug,due) VALUES(?,?,?,?)",
                  (uid, kind, slug, (now() + timedelta(minutes=minutes)).isoformat()))


def cancel_plans(uid, kinds=None):
    with db() as c:
        if kinds:
            c.execute(f"UPDATE followups SET done=1 WHERE user_id=? AND kind IN ({','.join('?' * len(kinds))})",
                      (uid, *kinds))
        else:
            c.execute("UPDATE followups SET done=1 WHERE user_id=?", (uid,))


async def followup_loop(bot: Bot):
    while True:
        try:
            if get_setting("desc_promo") not in (None, str(int(promo_on()))):
                await setup_profile(bot)
            with db() as c:
                rows = c.execute("SELECT * FROM followups WHERE done=0 AND due<=?", (now().isoformat(),)).fetchall()
                for r in rows:
                    c.execute("UPDATE followups SET done=1 WHERE id=?", (r["id"],))
            for r in rows:
                try:
                    await send_followup(bot, r)
                except Exception as e:
                    logging.info("Eslatma yuborilmadi %s: %s", r["user_id"], e)
        except Exception:
            logging.exception("followup_loop")
        await asyncio.sleep(60)


async def send_followup(bot, r):
    uid, kind, slug = r["user_id"], r["kind"], r["slug"]
    if slug and bought(uid, slug):
        return
    bk = BY_SLUG.get(slug)
    b = InlineKeyboardBuilder()
    if kind == "sample1" and bk:
        b.button(text=f"🛒 To'liq kitob — {money(slug_price(slug))}", callback_data=f"buy:{slug}")
        b.button(text=f"🔥 5 tasi birga — {money(slug_price('all'))}", callback_data="v:all")
        b.adjust(1)
        promo = f"\n\n⏳ Aksiya narxi {promo_date()}gacha." if promo_on() else ""
        await bot.send_message(uid, (
            f"📖 «{bk['title']}» parchasini o'qib chiqdingizmi?\n\n"
            f"Parcha — kitobning faqat boshi. To'liq kitobda {bk['pages']} bet: barcha boblar, "
            f"mashqlar va tayyor qoidalar.\n\nYoqqan bo'lsa, davomi shu yerda 👇{promo}"),
            reply_markup=b.as_markup())
    elif kind == "sample2" and bk and promo_on():
        b.button(text=f"🛒 Hozir olish — {money(slug_price(slug))}", callback_data=f"buy:{slug}")
        b.button(text="📚 Barcha kitoblar", callback_data="books")
        b.adjust(1)
        await bot.send_message(uid, (
            f"⏳ Eslatma: aksiya {promo_date()}da tugaydi.\n\n"
            f"«{bk['title']}» hozir <s>{money(PRICE)}</s> → <b>{money(PROMO_PRICE)}</b>.\n"
            f"5 ta kitob birga: <b>{money(BUNDLE_PROMO)}</b> (bittasi ~{money(BUNDLE_PROMO // 5)})."),
            reply_markup=b.as_markup())
    elif kind == "cart":
        b.button(text="💳 To'lov ma'lumotlari", callback_data=f"buy:{slug}")
        b.button(text="💬 Admin bilan gaplashish", url=f"https://t.me/{ADMIN_USERNAME}")
        b.adjust(1)
        title = BUNDLE["title"] if slug == "all" else (bk["title"] if bk else "kitob")
        await bot.send_message(uid, (
            f"🛒 «{title}» buyurtmangiz yakunlanmay qoldi.\n\n"
            "To'lovda muammo bo'ldimi? Kartaga o'tkazib, chek rasmini shu yerga yuborsangiz kifoya. "
            "Savol bo'lsa, adminga yozing."), reply_markup=b.as_markup())
    elif kind == "welcome":
        with db() as c:
            took = c.execute("SELECT 1 FROM followups WHERE user_id=? AND kind='sample1'", (uid,)).fetchone()
        if took:
            return
        b.button(text="🎁 Bepul parcha tanlash", callback_data="free")
        b.button(text="🧭 Qaysi biri menga mos?", callback_data="quiz")
        b.adjust(1)
        await bot.send_message(uid, (
            "👋 Hali kitob tanlamadingizmi?\n\nHar bir kitobning boshini bepul o'qish mumkin, "
            "hech narsa to'lamaysiz. Yoki 1 savolga javob bering, sizga mosini tavsiya qilaman."),
            reply_markup=b.as_markup())


# ---------------- Kanalga rejalashtirilgan postlar ----------------
async def channel_loop(bot: Bot):
    """channel_posts.json dagi postlarni vaqti kelganda kanalga joylaydi (o'sha kun ichida kechiksa ham)."""
    warned = False
    while True:
        try:
            with open(CHANNEL_POSTS, encoding="utf-8") as f:
                posts = json.load(f)
            t = now()
            for p in posts:
                at = datetime.fromisoformat(p["at"]).replace(tzinfo=TZ)
                key = f"chpost:{p['id']}"
                if at > t or at.date() != t.date() or get_setting(key):
                    continue
                kb = None
                if p.get("url"):
                    b = InlineKeyboardBuilder()
                    b.button(text=p["btn"], url=p["url"])
                    kb = b.as_markup()
                try:
                    if p.get("img"):
                        await bot.send_photo(CHANNEL, FSInputFile(os.path.join(ASSETS, "channel", p["img"])),
                                             caption=p["text"], reply_markup=kb)
                    else:
                        await bot.send_message(CHANNEL, p["text"], reply_markup=kb, disable_web_page_preview=True)
                    set_setting(key, t.isoformat())
                    logging.info("Kanalga joylandi: %s", p["id"])
                except Exception as e:
                    logging.warning("Kanalga joylab bo'lmadi %s: %s", p["id"], e)
                    if not warned and admin_id():
                        warned = True
                        try:
                            await bot.send_message(admin_id(), "⚠️ Kanalga post joylab bo'lmadi. @insonlabbot'ni "
                                                   f"{CHANNEL} kanaliga admin qiling («Xabar joylash» huquqi bilan).\n\n{html.escape(str(e))}")
                        except Exception:
                            pass
                    break
        except Exception:
            logging.exception("channel_loop")
        await asyncio.sleep(60)


# ---------------- Mijoz: start va katalog ----------------
def welcome_text(name):
    lines = "\n".join(f"{b['emoji']} <b>{b['title']}</b> — {b['short']}" for b in BOOKS)
    promo = (f"\n\n🔥 <b>Ochilish aksiyasi {promo_date()}gacha:</b>\n"
             f"bitta kitob <s>{money(PRICE)}</s> → <b>{money(PROMO_PRICE)}</b>\n"
             f"5 tasi birga <s>{money(BUNDLE_PRICE)}</s> → <b>{money(BUNDLE_PROMO)}</b>") if promo_on() else ""
    return (f"Assalomu alaykum, {html.escape(name)}! 👋\n\n"
            "Bu <b>inson.lab</b> kitob do'koni. Psixologiyani mish-mishlardan emas, "
            "haqiqiy tadqiqotlardan o'rganing: har bob tajriba, raqam va hayotiy misol bilan.\n\n"
            f"{lines}\n\n📱 Barcha kitoblar <b>elektron (PDF)</b>: qog'oz kitob emas. To'lovdan keyin fayl shu botga keladi, telefonda o'qiladi.\n\n🎁 Har kitobning boshi <b>bepul</b>: avval o'qing, yoqsa oling.{promo}")


@router.message(CommandStart())
async def start(m: Message, state: FSMContext, bot: Bot):
    await state.clear()
    arg = (m.text or "").split(maxsplit=1)
    arg = arg[1] if len(arg) == 2 else ""
    with db() as c:
        new = c.execute("INSERT OR IGNORE INTO users(id,joined,source,username,full_name) VALUES(?,?,?,?,?)",
                        (m.from_user.id, now().isoformat(), arg or "direct",
                         m.from_user.username, m.from_user.full_name)).rowcount

    if admin_id() is None and (m.from_user.username or "").lower() == ADMIN_USERNAME:
        set_setting("admin_id", m.from_user.id)
        await m.answer("✅ Siz admin sifatida ro'yxatga olindingiz.\nBoshqaruv paneli: /admin")

    await m.answer("Pastdagi menyudan foydalaning 👇", reply_markup=MENU)

    # Chuqur havolalar: ?start=b1..b5, all, quiz, free, p<ID>
    if arg in BY_SLUG or arg == "all":
        await show_slug(bot, m.chat.id, arg)
        return
    if arg == "quiz":
        await send_quiz(m)
        return
    if arg == "free":
        await free_menu(m)
        return
    if arg.startswith("p") and arg[1:].isdigit():
        p = get_product(int(arg[1:]))
        if p:
            if p["slug"]:
                await show_slug(bot, m.chat.id, p["slug"])
            else:
                await m.answer(*other_view(p))
            return

    await send_asset_photo(bot, m.chat.id, "welcome.jpg", welcome_text(m.from_user.first_name), books_kb())
    if new:
        plan(m.from_user.id, "welcome", "", 120)


async def show_slug(bot, chat_id, slug):
    if slug == "all":
        lines = "\n".join(f"{b['emoji']} {b['title']} — {b['short']} ({b['pages']} bet)" for b in BOOKS)
        b = InlineKeyboardBuilder()
        b.button(text=f"🛒 5 tasini olish — {money(slug_price('all'))}", callback_data="buy:all")
        b.button(text="🎁 Avval bepul parcha", callback_data="free")
        b.button(text="⬅️ Barcha kitoblar", callback_data="books")
        b.adjust(1)
        each = slug_price("all") // 5
        cap = (f"🔥 <b>{BUNDLE['title']}</b>\n{BUNDLE['hook']}\n\n{lines}\n\n"
               f"📱 5 ta elektron kitob (PDF) · jami {sum(b['pages'] for b in BOOKS)} bet · 120+ tadqiqot\n"
               f"Alohida olinsa: <s>{money(slug_price('b1') * 5)}</s>\n"
               f"{price_line('all')}\n✅ Bitta kitob ~{money(each)} ga tushadi")
        await send_asset_photo(bot, chat_id, "bundle.jpg", cap, b.as_markup())
        return
    bk = BY_SLUG[slug]
    bullets = "\n".join(f"• {x}" for x in bk["bullets"])
    cap = (f"{bk['emoji']} <b>{bk['title']}</b> — {bk['short']}\n\n<i>{bk['hook']}</i>\n\n{bk['about']}\n\n"
           f"<b>Ichida:</b>\n{bullets}\n\n📱 Elektron kitob (PDF) · {bk['pages']} bet · telefonda o'qiladi\n{price_line(slug)}")
    await send_asset_photo(bot, chat_id, f"book0{slug[1]}.jpg", cap, book_kb(slug))


@router.callback_query(F.data.startswith("v:"))
async def view_cb(cq: CallbackQuery, bot: Bot):
    await cq.answer()
    await show_slug(bot, cq.from_user.id, cq.data[2:])


@router.callback_query(F.data == "books")
async def books_cb(cq: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    await cq.answer()
    await send_asset_photo(bot, cq.from_user.id, "welcome.jpg", "📚 <b>inson.lab kitoblari</b>\nBirini tanlang:", books_kb())


@router.message(F.text == "📚 Kitoblar")
async def books_msg(m: Message, bot: Bot, state: FSMContext):
    await state.clear()
    await send_asset_photo(bot, m.chat.id, "welcome.jpg", welcome_text(m.from_user.first_name), books_kb())


@router.message(F.text == "🔥 5 tasi bittada")
async def bundle_msg(m: Message, bot: Bot, state: FSMContext):
    await state.clear()
    await show_slug(bot, m.chat.id, "all")


@router.message(F.text == "💬 Savol berish")
async def ask_msg(m: Message):
    b = InlineKeyboardBuilder()
    b.button(text="✍️ Adminga yozish", url=f"https://t.me/{ADMIN_USERNAME}")
    await m.answer("Kitoblar, to'lov yoki boshqa savol bo'lsa, adminga yozing. Tez javob beramiz.",
                   reply_markup=b.as_markup())


# ---------------- Bepul parcha ----------------
async def free_menu(m):
    b = InlineKeyboardBuilder()
    for bk in BOOKS:
        b.button(text=f"{bk['emoji']} {bk['title']}", callback_data=f"smp:{bk['slug']}")
    b.adjust(1)
    await m.answer("🎁 Qaysi kitobning bepul parchasini o'qiysiz?\n"
                   "Parchada: kitob mundarijasi, kirish va 2 ta to'liq bob.", reply_markup=b.as_markup())


@router.message(F.text == "🎁 Bepul parcha")
async def free_msg(m: Message, state: FSMContext):
    await state.clear()
    await free_menu(m)


@router.callback_query(F.data == "free")
async def free_cb(cq: CallbackQuery):
    await cq.answer()
    await free_menu(cq.message)


@router.callback_query(F.data.startswith("smp:"))
async def sample_cb(cq: CallbackQuery, bot: Bot):
    slug = cq.data[4:]
    bk = BY_SLUG.get(slug)
    if not bk:
        await cq.answer("Topilmadi", show_alert=True)
        return
    await cq.answer("Parcha yuborilmoqda...")
    b = InlineKeyboardBuilder()
    b.button(text=f"🛒 To'liq kitob — {money(slug_price(slug))}", callback_data=f"buy:{slug}")
    await send_sample_doc(bot, cq.from_user.id, bk,
                          f"📖 «{bk['title']}» bepul parchasi.\nO'qib chiqing, yoqsa to'liq kitob shu yerda 👇",
                          b.as_markup())
    plan(cq.from_user.id, "sample1", slug, 45)
    plan(cq.from_user.id, "sample2", slug, 60 * 22)
    cancel_plans(cq.from_user.id, ["welcome"])


# ---------------- Test: qaysi kitob mos ----------------
async def send_quiz(m):
    b = InlineKeyboardBuilder()
    for bk in BOOKS:
        b.button(text=bk["pain"], callback_data=f"q:{bk['slug']}")
    b.adjust(1)
    await m.answer("🧭 Hozir sizni ko'proq nima qiynayapti?", reply_markup=b.as_markup())


@router.message(F.text == "🧭 Qaysi biri menga mos?")
async def quiz_msg(m: Message, state: FSMContext):
    await state.clear()
    await send_quiz(m)


@router.callback_query(F.data == "quiz")
async def quiz_cb(cq: CallbackQuery):
    await cq.answer()
    await send_quiz(cq.message)


@router.callback_query(F.data.startswith("q:"))
async def quiz_answer(cq: CallbackQuery, bot: Bot):
    await cq.answer()
    bk = BY_SLUG[cq.data[2:]]
    await cq.message.answer(f"Sizga <b>«{bk['title']}»</b> mos keladi 👇")
    await show_slug(bot, cq.from_user.id, bk["slug"])


# ---------------- Xarid ----------------
def pay_text(title, amount):
    return (f"🛒 <b>Buyurtma: {title}</b> (elektron PDF)\n💰 To'lov: <b>{money(amount)}</b>\n\n"
            f"<b>1.</b> Shu kartaga {money(amount)} o'tkazing (Click, Payme yoki bank ilovasi):\n"
            f"<code>{CARD_NUMBER}</code>  ← bosing, nusxa olinadi\n{CARD_HOLDER}\n\n"
            "<b>2.</b> To'lov chekining <b>rasmini</b> (skrinshot) shu chatga yuboring.\n\n"
            "<b>3.</b> Tekshirilgach PDF fayl shu chatga avtomatik keladi.\n\n"
            f"Savol bo'lsa: @{ADMIN_USERNAME}")


@router.callback_query(F.data.startswith("buy:"))
async def buy(cq: CallbackQuery, state: FSMContext):
    key = cq.data[4:]
    if key.isdigit():
        p = get_product(int(key))
    else:
        p = by_slug(key)
    if not p or not p["active"]:
        await cq.answer("Bu mahsulot endi mavjud emas", show_alert=True)
        return
    await cq.answer()
    amount = product_price(p)
    await state.set_state(Buy.waiting_screenshot)
    await state.update_data(product_id=p["id"], amount=amount)
    b = InlineKeyboardBuilder()
    if p["slug"] and p["slug"] != "all":
        extra = slug_price("all") - amount
        b.button(text=f"🔥 Yana {money(extra)} qo'shib, 5 tasini olish", callback_data="buy:all")
    b.button(text="❌ Bekor qilish", callback_data="cancel")
    b.adjust(1)
    title = BUNDLE["title"] if p["slug"] == "all" else p["title"]
    await cq.message.answer(pay_text(title, amount), reply_markup=b.as_markup())
    if p["slug"]:
        plan(cq.from_user.id, "cart", p["slug"], 40)


@router.callback_query(F.data == "cancel")
async def cancel(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.answer("Bekor qilindi")
    await cq.message.edit_reply_markup(reply_markup=None)


@router.message(Buy.waiting_screenshot, F.photo | F.document)
async def got_screenshot(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    pid = data["product_id"]
    with db() as c:
        p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        amount = data.get("amount") or product_price(p)
        oid = c.execute(
            "INSERT INTO orders(user_id,username,full_name,product_id,status,created,amount) VALUES(?,?,?,?,?,?,?)",
            (m.from_user.id, m.from_user.username, m.from_user.full_name, pid, "pending",
             now().isoformat(), amount)).lastrowid
    await state.clear()
    cancel_plans(m.from_user.id, ["cart", "sample1", "sample2", "welcome"])
    await m.answer("✅ Chek qabul qilindi! Tekshirilmoqda, odatda 5–30 daqiqa.\nTasdiqlangach kitob shu yerga keladi.")

    aid = admin_id()
    if not aid:
        logging.warning("Admin hali /start bosmagan, buyurtma #%s kutmoqda", oid)
        return
    who = (f"@{m.from_user.username}" if m.from_user.username else
           f'<a href="tg://user?id={m.from_user.id}">{html.escape(m.from_user.full_name)}</a>')
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ok:{oid}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"no:{oid}"),
    ]])
    title = BUNDLE["title"] if p["slug"] == "all" else p["title"]
    caption = (f"🆕 Buyurtma #{oid}\n👤 {who}\n📦 {title}\n💰 {money(amount)}\n\n"
               "Kartangizga pul tushganini tekshiring.")
    if m.photo:
        await bot.send_photo(aid, m.photo[-1].file_id, caption=caption, reply_markup=kb)
    else:
        await bot.send_document(aid, m.document.file_id, caption=caption, reply_markup=kb)


@router.message(Buy.waiting_screenshot)
async def need_photo(m: Message):
    await m.answer("Iltimos, to'lov chekining <b>rasmini</b> (skrinshot) yuboring.")


# ---------------- Admin: tasdiqlash ----------------
async def deliver(bot: Bot, order, product):
    uid = order["user_id"]
    t = product["type"]
    if t == "pdf":
        if not product["file_id"]:
            raise RuntimeError("Bu kitobning PDF fayli botga hali yuklanmagan (/admin → Kitob PDF'lari)")
        await bot.send_message(uid, "🎉 To'lov tasdiqlandi! Mana kitobingiz:")
        await bot.send_document(uid, product["file_id"], caption=product["title"])
    elif t == "bundle":
        items = [i for i in bundle_items(product) if i]
        missing = [i["title"] for i in items if not i["file_id"]]
        if missing:
            raise RuntimeError("PDF yuklanmagan: " + ", ".join(missing))
        await bot.send_message(uid, "🎉 To'lov tasdiqlandi! Mana kitoblaringiz:")
        for i in items:
            await bot.send_document(uid, i["file_id"], caption=i["title"])
    elif t == "channel":
        link = await bot.create_chat_invite_link(product["channel_id"], member_limit=1, name=f"order-{order['id']}")
        await bot.send_message(uid, "🎉 To'lov tasdiqlandi! Yopiq kanalga kirish havolasi "
                                    f"(faqat siz uchun, bir martalik):\n{link.invite_link}")
        return
    elif t == "consult":
        await bot.send_message(uid, "🎉 To'lov tasdiqlandi! Konsultatsiya vaqtini kelishish uchun "
                                    f"tez orada siz bilan bog'lanaman.\nSavollar bo'lsa: @{ADMIN_USERNAME}")
        return
    b = InlineKeyboardBuilder()
    b.button(text="📚 Boshqa kitoblar", callback_data="books")
    await bot.send_message(uid, "Rahmat! 🙏 O'qib chiqqach fikringizni yozib qoldirsangiz, juda xursand bo'lamiz.",
                           reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^(ok|no):\d+$"))
async def decide(cq: CallbackQuery, bot: Bot):
    if not is_admin(cq.from_user):
        await cq.answer("Ruxsat yo'q", show_alert=True)
        return
    action, oid = cq.data.split(":")
    with db() as c:
        o = c.execute("SELECT * FROM orders WHERE id=?", (int(oid),)).fetchone()
        p = c.execute("SELECT * FROM products WHERE id=?", (o["product_id"],)).fetchone() if o else None
    if not o or o["status"] != "pending":
        await cq.answer("Bu buyurtma allaqachon ko'rib chiqilgan", show_alert=True)
        return
    old = cq.message.caption or ""
    if action == "ok":
        try:
            await deliver(bot, o, p)
        except Exception as e:
            logging.exception("Yetkazishda xato")
            await cq.answer(f"Yetkazib bo'lmadi: {e}", show_alert=True)
            return
        status, mark = "approved", "✅ TASDIQLANDI va yuborildi"
        if p["type"] == "consult":
            uid = o["user_id"]
            who = f"@{o['username']}" if o["username"] else f'<a href="tg://user?id={uid}">{html.escape(o["full_name"] or "Mijoz")}</a>'
            await bot.send_message(cq.from_user.id, f"💬 Konsultatsiya mijozi: {who} — u bilan bog'laning.")
    else:
        await bot.send_message(o["user_id"], "❌ To'lov tasdiqlanmadi. Chek noto'g'ri yoki pul tushmagan.\n"
                                             f"Xato bo'lsa, murojaat qiling: @{ADMIN_USERNAME}")
        status, mark = "rejected", "❌ RAD ETILDI"
    with db() as c:
        c.execute("UPDATE orders SET status=? WHERE id=?", (status, int(oid)))
    await cq.message.edit_caption(caption=f"{old}\n\n{mark}")
    await cq.answer()


# ---------------- Admin: panel ----------------
@router.message(Command("admin"))
async def admin(m: Message, state: FSMContext):
    if not is_admin(m.from_user):
        return
    await state.clear()
    await m.answer("⚙️ Boshqaruv paneli", reply_markup=admin_kb())


def books_status():
    lines = []
    for bk in BOOKS:
        p = by_slug(bk["slug"])
        lines.append(f"{'✅' if p and p['file_id'] else '❌'} {bk['title']}  ({bk['file']}.pdf)")
    return "\n".join(lines)


@router.callback_query(F.data == "a:books")
async def a_books(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user):
        return
    await cq.answer()
    await state.set_state(Admin.attach)
    await cq.message.answer(
        "📚 To'liq PDF'lar holati:\n\n" + books_status() +
        "\n\nPDF fayllarni shu chatga yuboring (bir nechtasini birdan ham bo'ladi). "
        "Fayl nomi kitobga mos bo'lsa (masalan 01_Korinmas_iplar.pdf), bot o'zi biriktiradi.")


def match_book(fname):
    f = (fname or "").lower()
    for bk in BOOKS:
        if f.startswith(bk["file"].lower()) and "parcha" not in f:
            return bk
    return None


@router.message(F.document, F.document.file_name.func(lambda n: match_book(n) is not None))
async def attach_pdf(m: Message):
    """Admin kitob PDF'ini yuborsa — avtomatik biriktiriladi (holatdan qat'i nazar)."""
    if not is_admin(m.from_user):
        return
    bk = match_book(m.document.file_name)
    with db() as c:
        c.execute("UPDATE products SET file_id=? WHERE slug=?", (m.document.file_id, bk["slug"]))
    await m.answer(f"✅ «{bk['title']}» PDF biriktirildi.\n\n{books_status()}")


@router.callback_query(F.data == "a:bc")
async def a_bc(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user):
        return
    await cq.answer()
    await state.set_state(Admin.broadcast)
    with db() as c:
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    await cq.message.answer(f"📣 Xabarni yuboring ({n} ta foydalanuvchiga ketadi). "
                            "Matn, rasm yoki video bo'lishi mumkin. Bekor qilish: /admin")


@router.message(Admin.broadcast)
async def do_bc(m: Message, state: FSMContext, bot: Bot):
    if not is_admin(m.from_user):
        return
    await state.clear()
    with db() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM users").fetchall()]
    b = InlineKeyboardBuilder()
    b.button(text="📚 Kitoblarni ko'rish", callback_data="books")
    ok = 0
    await m.answer(f"Yuborilmoqda: {len(ids)} ta...")
    for uid in ids:
        try:
            await bot.copy_message(uid, m.chat.id, m.message_id, reply_markup=b.as_markup())
            ok += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await m.answer(f"✅ Yuborildi: {ok} / {len(ids)}", reply_markup=admin_kb())


@router.callback_query(F.data == "a:stats")
async def stats(cq: CallbackQuery):
    if not is_admin(cq.from_user):
        return
    with db() as c:
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = c.execute("SELECT COUNT(*) FROM users WHERE joined>=?", (now().date().isoformat(),)).fetchone()[0]
        r = c.execute("""SELECT COUNT(*), COALESCE(SUM(COALESCE(o.amount,p.price)),0) FROM orders o
                         JOIN products p ON p.id=o.product_id WHERE o.status='approved'""").fetchone()
        pend = c.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        samples = c.execute("SELECT COUNT(DISTINCT user_id) FROM followups WHERE kind='sample1'").fetchone()[0]
        src = c.execute("SELECT source, COUNT(*) n FROM users GROUP BY source ORDER BY n DESC LIMIT 8").fetchall()
        top = c.execute("""SELECT p.title, COUNT(*) n FROM orders o JOIN products p ON p.id=o.product_id
                           WHERE o.status='approved' GROUP BY p.id ORDER BY n DESC""").fetchall()
    s = "\n".join(f"  {x['source'] or '—'}: {x['n']}" for x in src)
    t = "\n".join(f"  {x['title']}: {x['n']}" for x in top) or "  hali yo'q"
    await cq.message.answer(f"📊 Statistika\n\n👥 Foydalanuvchilar: {users} (bugun +{today})\n"
                            f"📖 Parcha olganlar: {samples}\n✅ Sotuvlar: {r[0]}\n💰 Tushum: {money(r[1])}\n"
                            f"⏳ Kutilayotgan: {pend}\n\n🔝 Sotuvlar:\n{t}\n\n🔗 Qayerdan kelgan:\n{s}")
    await cq.answer()


@router.callback_query(F.data == "a:links")
async def links(cq: CallbackQuery, bot: Bot):
    if not is_admin(cq.from_user):
        return
    me = await bot.get_me()
    u = f"https://t.me/{me.username}"
    lines = [f"Umumiy: {u}", f"To'plam: {u}?start=all", f"Test (qaysi kitob mos): {u}?start=quiz",
             f"Bepul parchalar: {u}?start=free", ""]
    lines += [f"{b['title']}: {u}?start={b['slug']}" for b in BOOKS]
    await cq.message.answer("🔗 Havolalar (Instagram bio, stories, kanal):\n\n" + "\n".join(lines),
                            disable_web_page_preview=True)
    await cq.answer()


# ---------------- Admin: boshqa mahsulotlar (kanal / konsultatsiya) ----------------
def other_view(p):
    b = InlineKeyboardBuilder()
    b.button(text=f"🛒 Sotib olish — {money(p['price'])}", callback_data=f"buy:{p['id']}")
    b.button(text="⬅️ Barcha mahsulotlar", callback_data="books")
    b.adjust(1)
    return (f"<b>{p['title']}</b>\n{TYPES.get(p['type'], '')}\n\n{p['description']}"
            f"\n\n💰 Narxi: <b>{money(p['price'])}</b>"), b.as_markup()


@router.callback_query(F.data.startswith("p:"))
async def show_other(cq: CallbackQuery):
    p = get_product(int(cq.data[2:]))
    if not p:
        await cq.answer("Bu mahsulot endi mavjud emas", show_alert=True)
        return
    await cq.answer()
    text, kb = other_view(p)
    await cq.message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "a:list")
async def list_products(cq: CallbackQuery):
    if not is_admin(cq.from_user):
        return
    with db() as c:
        rows = c.execute("SELECT * FROM products WHERE active=1 AND slug IS NULL").fetchall()
    if not rows:
        await cq.answer("Boshqa mahsulot yo'q", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    for p in rows:
        b.button(text=f"🗑 O'chirish · {p['title']}", callback_data=f"del:{p['id']}")
    b.adjust(1)
    await cq.message.answer("Boshqa mahsulotlar:", reply_markup=b.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("del:"))
async def del_product(cq: CallbackQuery):
    if not is_admin(cq.from_user):
        return
    with db() as c:
        c.execute("UPDATE products SET active=0 WHERE id=? AND slug IS NULL", (int(cq.data[4:]),))
    await cq.message.edit_text("🗑 Mahsulot o'chirildi.")


@router.callback_query(F.data == "a:add")
async def add_start(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user):
        return
    b = InlineKeyboardBuilder()
    b.button(text=TYPES["channel"], callback_data="t:channel")
    b.button(text=TYPES["consult"], callback_data="t:consult")
    b.adjust(1)
    await state.set_state(Add.type)
    await cq.message.answer("Mahsulot turini tanlang:", reply_markup=b.as_markup())
    await cq.answer()


@router.callback_query(Add.type, F.data.startswith("t:"))
async def add_type(cq: CallbackQuery, state: FSMContext):
    await state.update_data(type=cq.data[2:])
    await state.set_state(Add.title)
    await cq.message.edit_text("Mahsulot nomini yozing:")


@router.message(Add.title, F.text)
async def add_title(m: Message, state: FSMContext):
    await state.update_data(title=html.escape(m.text.strip()))
    await state.set_state(Add.description)
    await m.answer("Qisqa tavsif yozing (mijoz ko'radi):")


@router.message(Add.description, F.text)
async def add_desc(m: Message, state: FSMContext):
    await state.update_data(description=m.html_text)
    await state.set_state(Add.price)
    await m.answer("Narxini so'mda yozing (faqat raqam, masalan 99000):")


@router.message(Add.price, F.text)
async def add_price(m: Message, state: FSMContext):
    digits = "".join(ch for ch in m.text if ch.isdigit())
    if not digits:
        await m.answer("Faqat raqam yozing, masalan 99000")
        return
    await state.update_data(price=int(digits))
    if (await state.get_data())["type"] == "channel":
        await state.set_state(Add.payload)
        await m.answer("1) Botni yopiq kanalga <b>admin</b> qiling (\"Foydalanuvchilarni taklif qilish\" huquqi bilan).\n"
                       "2) Kanaldan istalgan bitta postni shu yerga <b>forward</b> qiling.")
    else:
        await save_product(m, state)


@router.message(Add.payload, F.forward_origin)
async def add_channel(m: Message, state: FSMContext, bot: Bot):
    chat = getattr(m.forward_origin, "chat", None)
    if not chat:
        await m.answer("Bu kanal posti emas. Kanaldan postni forward qiling.")
        return
    try:
        me = await bot.get_chat_member(chat.id, bot.id)
        if me.status != "administrator" or not getattr(me, "can_invite_users", False):
            raise ValueError
    except Exception:
        await m.answer("Bot bu kanalda admin emas yoki taklif qilish huquqi yo'q. Tuzatib, qayta forward qiling.")
        return
    await state.update_data(channel_id=chat.id)
    await save_product(m, state)


@router.message(Add.payload)
async def add_payload_wrong(m: Message):
    await m.answer("Kanaldan postni forward qiling.")


async def save_product(m: Message, state: FSMContext):
    d = await state.get_data()
    with db() as c:
        c.execute("INSERT INTO products(type,title,description,price,channel_id) VALUES(?,?,?,?,?)",
                  (d["type"], d["title"], d["description"], d["price"], d.get("channel_id")))
    await state.clear()
    await m.answer(f"✅ Qo'shildi: <b>{d['title']}</b> — {money(d['price'])}", reply_markup=admin_kb())


# ---------------- Boshqa har qanday xabar ----------------
@router.message()
async def fallback(m: Message, bot: Bot):
    await send_asset_photo(bot, m.chat.id, "welcome.jpg", welcome_text(m.from_user.first_name), books_kb())


BOT_DESCRIPTION_TPL = '📚 inson.lab kitob do‘koni\n\nPsixologiyani mish-mishdan emas, haqiqiy tadqiqotlardan o‘rganing. 5 ta elektron kitob (PDF):\n\n🧵 Ko‘rinmas iplar — manipulyatsiyadan himoya\n❤️ Yurak algoritmi — sevgi ilmi\n👁 Indamas til — tana tili\n🎯 Ta’sir kodi — halol ishontirish\n💸 Pul miyasi — pul psixologiyasi\n\n🎁 Har kitobning boshi BEPUL — avval o‘qing, yoqsa oling.\n{PROMO}👇 Boshlash uchun «START» ni bosing'
BOT_SHORT = '📚 inson.lab: psixologiya bo‘yicha 5 ta elektron kitob. Boshi bepul. Bepul parcha uchun START bosing.'


async def setup_profile(bot: Bot):
    """Start bosilishidan oldin ko'rinadigan matn (description) va profil qisqa tavsifi."""
    try:
        promo = (f"🔥 Aksiya {promo_date()}gacha: {money(PROMO_PRICE)}\n\n" if promo_on() else "")
        await bot.set_my_description(BOT_DESCRIPTION_TPL.replace("{PROMO}", promo))
        set_setting("desc_promo", int(promo_on()))
        await bot.set_my_short_description(BOT_SHORT)
        from aiogram.types import BotCommand
        await bot.set_my_commands([BotCommand(command="start", description="Kitoblar va bepul parcha")])
    except Exception as e:
        logging.warning("Bot profilini sozlab bo'lmadi: %s", e)


async def main():
    init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=False)
    await setup_profile(bot)
    asyncio.create_task(followup_loop(bot))
    asyncio.create_task(channel_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
