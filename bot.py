"""
Do'kon bot: PDF kitoblar, yopiq kanal va konsultatsiya sotuvi.
To'lov: karta orqali, mijoz skrinshot yuboradi, admin tasdiqlaydi,
bot mahsulotni avtomatik yetkazadi.
"""
import asyncio
import html
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---------------- Sozlamalar (Railway'da Variables orqali beriladi) -------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "atadjanov_jasur").lstrip("@").lower()
CARD_NUMBER = os.getenv("CARD_NUMBER", "5614 6819 1902 5738")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Atadjanov Jasur")
DB_PATH = os.getenv("DB_PATH", "data/shop.db")

logging.basicConfig(level=logging.INFO)
router = Router()

TYPES = {
    "pdf": "📘 PDF kitob",
    "channel": "🔒 Yopiq kanal",
    "consult": "💬 Konsultatsiya",
}


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
        """)


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


def money(n):
    return f"{n:,}".replace(",", " ") + " so'm"


# ---------------- Klaviaturalar ----------------
def catalog_kb():
    b = InlineKeyboardBuilder()
    with db() as c:
        rows = c.execute("SELECT * FROM products WHERE active=1 ORDER BY type, id").fetchall()
    for p in rows:
        icon = TYPES[p["type"]].split()[0]
        b.button(text=f"{icon} {p['title']} — {money(p['price'])}", callback_data=f"p:{p['id']}")
    b.adjust(1)
    return b.as_markup(), len(rows)


def admin_kb():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Mahsulot qo'shish", callback_data="a:add")
    b.button(text="📋 Mahsulotlar", callback_data="a:list")
    b.button(text="📊 Statistika", callback_data="a:stats")
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


# ---------------- Mijoz qismi ----------------
@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    with db() as c:
        c.execute("INSERT OR IGNORE INTO users VALUES(?,?)", (m.from_user.id, datetime.now().isoformat()))

    # Admin birinchi /start bosganda avtomatik taniladi
    if admin_id() is None and (m.from_user.username or "").lower() == ADMIN_USERNAME:
        set_setting("admin_id", m.from_user.id)
        await m.answer("✅ Siz admin sifatida ro'yxatga olindingiz.\nBoshqaruv paneli: /admin")

    kb, count = catalog_kb()
    if count == 0:
        await m.answer(f"Assalomu alaykum, {m.from_user.first_name}! 👋\n\n"
                       "Mahsulotlar tez orada qo'shiladi. Kuzatishda qoling!")
        return
    await m.answer(f"Assalomu alaykum, {m.from_user.first_name}! 👋\n\n"
                   "Quyidagi mahsulotlardan birini tanlang:", reply_markup=kb)


@router.callback_query(F.data == "catalog")
async def back_catalog(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    kb, _ = catalog_kb()
    await cq.message.edit_text("Mahsulotni tanlang:", reply_markup=kb)


@router.callback_query(F.data.startswith("p:"))
async def show_product(cq: CallbackQuery):
    pid = int(cq.data[2:])
    with db() as c:
        p = c.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    if not p:
        await cq.answer("Bu mahsulot endi mavjud emas", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    b.button(text="🛒 Sotib olish", callback_data=f"buy:{pid}")
    b.button(text="⬅️ Orqaga", callback_data="catalog")
    b.adjust(1)
    await cq.message.edit_text(
        f"<b>{p['title']}</b>\n{TYPES[p['type']]}\n\n{p['description']}\n\n💰 Narxi: <b>{money(p['price'])}</b>",
        reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("buy:"))
async def buy(cq: CallbackQuery, state: FSMContext):
    pid = int(cq.data[4:])
    with db() as c:
        p = c.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    if not p:
        await cq.answer("Bu mahsulot endi mavjud emas", show_alert=True)
        return
    await state.set_state(Buy.waiting_screenshot)
    await state.update_data(product_id=pid)
    b = InlineKeyboardBuilder()
    b.button(text="❌ Bekor qilish", callback_data="catalog")
    await cq.message.edit_text(
        f"<b>{p['title']}</b> — {money(p['price'])}\n\n"
        f"💳 Quyidagi kartaga to'lov qiling:\n<code>{CARD_NUMBER}</code>\n{CARD_HOLDER}\n\n"
        "To'lovdan so'ng <b>chek skrinshotini</b> shu yerga yuboring. "
        "Tekshirilgach mahsulot avtomatik yuboriladi.",
        reply_markup=b.as_markup())


@router.message(Buy.waiting_screenshot, F.photo | F.document)
async def got_screenshot(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    pid = data["product_id"]
    with db() as c:
        p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        cur = c.execute(
            "INSERT INTO orders(user_id,username,full_name,product_id,status,created) VALUES(?,?,?,?,?,?)",
            (m.from_user.id, m.from_user.username, m.from_user.full_name, pid, "pending",
             datetime.now().isoformat()))
        oid = cur.lastrowid
    await state.clear()
    await m.answer("✅ Chek qabul qilindi! Tekshirilmoqda, odatda bir necha daqiqa vaqt oladi.")

    aid = admin_id()
    if not aid:
        logging.warning("Admin hali /start bosmagan, buyurtma #%s kutmoqda", oid)
        return
    who = f"@{m.from_user.username}" if m.from_user.username else f'<a href="tg://user?id={m.from_user.id}">{html.escape(m.from_user.full_name)}</a>'
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ok:{oid}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"no:{oid}"),
    ]])
    caption = (f"🆕 Buyurtma #{oid}\n👤 {who}\n📦 {p['title']}\n💰 {money(p['price'])}\n\n"
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
        await bot.send_message(uid, "🎉 To'lov tasdiqlandi! Mana sizning kitobingiz:")
        await bot.send_document(uid, product["file_id"], caption=product["title"])
    elif t == "channel":
        link = await bot.create_chat_invite_link(product["channel_id"], member_limit=1,
                                                 name=f"order-{order['id']}")
        await bot.send_message(uid, "🎉 To'lov tasdiqlandi! Yopiq kanalga kirish havolasi "
                                    f"(faqat siz uchun, bir martalik):\n{link.invite_link}")
    elif t == "consult":
        await bot.send_message(uid, "🎉 To'lov tasdiqlandi! Konsultatsiya vaqtini kelishish uchun "
                                    f"tez orada siz bilan bog'lanaman.\nSavollar bo'lsa: @{ADMIN_USERNAME}")


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
            name = html.escape(o["full_name"] or "Mijoz")
            uid = o["user_id"]
            who = f"@{o['username']}" if o["username"] else f'<a href="tg://user?id={uid}">{name}</a>'
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


@router.callback_query(F.data == "a:stats")
async def stats(cq: CallbackQuery):
    if not is_admin(cq.from_user):
        return
    with db() as c:
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        r = c.execute("""SELECT COUNT(*), COALESCE(SUM(p.price),0) FROM orders o
                         JOIN products p ON p.id=o.product_id WHERE o.status='approved'""").fetchone()
        pend = c.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
    await cq.message.answer(f"📊 Statistika\n\n👥 Foydalanuvchilar: {users}\n"
                            f"✅ Sotuvlar: {r[0]}\n💰 Tushum: {money(r[1])}\n⏳ Kutilayotgan: {pend}")
    await cq.answer()


@router.callback_query(F.data == "a:list")
async def list_products(cq: CallbackQuery):
    if not is_admin(cq.from_user):
        return
    with db() as c:
        rows = c.execute("SELECT * FROM products WHERE active=1").fetchall()
    if not rows:
        await cq.answer("Hozircha mahsulot yo'q", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    for p in rows:
        b.button(text=f"🗑 {p['title']} ({money(p['price'])})", callback_data=f"del:{p['id']}")
    b.adjust(1)
    await cq.message.answer("O'chirish uchun mahsulotni bosing:", reply_markup=b.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("del:"))
async def del_product(cq: CallbackQuery):
    if not is_admin(cq.from_user):
        return
    with db() as c:
        c.execute("UPDATE products SET active=0 WHERE id=?", (int(cq.data[4:]),))
    await cq.message.edit_text("🗑 Mahsulot o'chirildi.")


# ---------------- Admin: mahsulot qo'shish ----------------
@router.callback_query(F.data == "a:add")
async def add_start(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user):
        return
    b = InlineKeyboardBuilder()
    for k, v in TYPES.items():
        b.button(text=v, callback_data=f"t:{k}")
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
    await m.answer("Narxini so'mda yozing (faqat raqam, masalan 49000):")


@router.message(Add.price, F.text)
async def add_price(m: Message, state: FSMContext):
    digits = "".join(ch for ch in m.text if ch.isdigit())
    if not digits:
        await m.answer("Faqat raqam yozing, masalan 49000")
        return
    await state.update_data(price=int(digits))
    t = (await state.get_data())["type"]
    if t == "pdf":
        await state.set_state(Add.payload)
        await m.answer("Endi PDF faylni shu yerga yuboring:")
    elif t == "channel":
        await state.set_state(Add.payload)
        await m.answer("1) Botni yopiq kanalga <b>admin</b> qiling (\"Foydalanuvchilarni taklif qilish\" huquqi bilan).\n"
                       "2) Kanaldan istalgan bitta postni shu yerga <b>forward</b> qiling.")
    else:
        await save_product(m, state)


@router.message(Add.payload, F.document)
async def add_pdf(m: Message, state: FSMContext):
    if (await state.get_data())["type"] != "pdf":
        return
    await state.update_data(file_id=m.document.file_id)
    await save_product(m, state)


@router.message(Add.payload, F.forward_origin)
async def add_channel(m: Message, state: FSMContext, bot: Bot):
    if (await state.get_data())["type"] != "channel":
        return
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
async def add_payload_wrong(m: Message, state: FSMContext):
    t = (await state.get_data())["type"]
    await m.answer("PDF faylni yuboring." if t == "pdf" else "Kanaldan postni forward qiling.")


async def save_product(m: Message, state: FSMContext):
    d = await state.get_data()
    with db() as c:
        c.execute("INSERT INTO products(type,title,description,price,file_id,channel_id) VALUES(?,?,?,?,?,?)",
                  (d["type"], d["title"], d["description"], d["price"], d.get("file_id"), d.get("channel_id")))
    await state.clear()
    await m.answer(f"✅ Qo'shildi: <b>{d['title']}</b> — {money(d['price'])}", reply_markup=admin_kb())


async def main():
    init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
