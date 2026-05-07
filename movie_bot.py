import asyncio
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote
from pyrogram import enums
from pyrogram.enums import ChatMemberStatus
from pyrogram import Client, filters, idle
from pyrogram.errors import MessageNotModified, UserNotParticipant, ChatAdminRequired
from pyrogram.errors import FloodWait
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineQueryResultArticle,
    InputTextMessageContent
)
from pymongo import MongoClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==========================================
#                  CONFIG
# ==========================================
API_ID = 38119035
API_HASH = "0f84597433eacb749fd482ad238a104e"
BOT_TOKEN = "8371879333:AAGrSXYY7LBXB8CBw5z-vJqUgnPMw-hcYX0"
MONGO_URL = "mongodb+srv://mrjavohirjon:javohir123@cluster0.gzf5ecj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

UZ_TZ = ZoneInfo("Asia/Tashkent")
SAVED_MOVIE = -1003797574060
KINO1CHRA_CHANNEL = -1003897814741
MAIN_CHANNEL = "@KinoDrift"
SAVE_SHORTS = -1003822143783
NOTIFIER_CHANNEL = "@Kinodrift_Notifier"

ALLOWED_GENRES = [
    "jangari", "detektiv", "sarguzasht", "hujjatli", "tarixiy",
    "fantastik", "multfilm", "ujas", "drama", "komediya", "triller"
]

# ==========================================
#              DATABASE SETUP
# ==========================================
mongo = MongoClient(MONGO_URL)
db = mongo.moviebot
movies_col = db.movies
users_col = db.users
fav_col = db.favorites
req_col = db.requests
ratings_col = db.ratings
settings_col = db.settings
requests_col = db.requests
history_col = db.history          # 📜 YANGI: Yuklab olish tarixi
watchlist_col = db.watchlist       # 🗓 YANGI: Ko'rmoqchiman ro'yxati
comments_col = db.comments         # 💬 YANGI: Izohlar

app = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
broadcast_wait = set()
pending_broadcasts = {}
request_wait = set()
approve_wait = {}
comment_wait = {}   # 💬 YANGI: izoh yozish holati
edit_wait = {}      # 🎬 YANGI: kino tahrirlash holati
addpart_wait = {}   # 📦 YANGI: ko'p qismli kino qo'shish holati


# ==========================================
#                SETTINGS
# ==========================================

def get_config():
    config = db.settings.find_one({"type": "bot_config"})
    if not config:
        default_data = {
            "type": "bot_config",
            "mandatory_channels": [],
            "main_admin": 5014031582,
            "admin_ids": []
        }
        db.settings.insert_one(default_data)
        return default_data
    return config

def get_bot_config():
    config = settings_col.find_one({"id": "main_config"})
    if not config:
        default_data = {
            "id": "main_config",
            "bot_token": "TOKENDINGIZNI_YORDAMCHI_SIFATIDA_YOZING",
            "admin_ids": [123456789, 987654321],
            "mandatory_channels": ["@kanal1", "@kanal2"],
        }
        settings_col.insert_one(default_data)
        return default_data
    return config

def is_admin(uid):
    conf = get_config()
    main_admin = conf.get("main_admin")
    admin_ids = conf.get("admin_ids", [])
    if isinstance(main_admin, list):
        return uid in main_admin or uid in admin_ids
    return uid == main_admin or uid in admin_ids

def is_main_admin(uid):
    conf = get_config()
    main_admin = conf.get("main_admin")
    if isinstance(main_admin, list):
        return uid in main_admin
    return uid == main_admin

config = get_bot_config()


# ==========================================
#         KOD TIZIMI: BO'SH KODLAR
# ==========================================

def get_next_movie_code():
    """
    Aqlli kod tizimi:
    - O'chirilgan kinolarning kodini topib, birinchi bo'sh kodni qaytaradi.
    - Bo'sh kod yo'q bo'lsa, eng katta koddan keyin birini beradi.
    Misol: 67-kod o'chirilgan, 100-ga yetganda → 67 beriladi.
    """
    all_codes = set(m["code"] for m in movies_col.find({}, {"code": 1}))
    if not all_codes:
        return 1
    max_code = max(all_codes)
    for i in range(1, max_code + 2):
        if i not in all_codes:
            return i


# ==========================================
#               KEYBOARDS
# ==========================================

def user_menu(user_id):
    buttons = [
        [KeyboardButton("📂 Barcha Kinolar"), KeyboardButton("🎭 Janrlar")],
        [KeyboardButton("📈 Top Kinolar"), KeyboardButton("📥 Kino so'rash")],
        [KeyboardButton("⭐ Sevimlilar"), KeyboardButton("📊 Statistika")],
        [KeyboardButton("🔗 Taklifnoma"), KeyboardButton("🏆 Leaderboard")],
        [KeyboardButton("📜 Tarixim"), KeyboardButton("🗓 Ko'rmoqchiman")],
        [KeyboardButton("📢 Reklama")]
    ]
    if is_admin(user_id):
        buttons.append([KeyboardButton("⚙️ Admin Menu")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def genres_keyboard():
    buttons = []
    for i in range(0, len(ALLOWED_GENRES), 2):
        row = [KeyboardButton(f"📁 {g.capitalize()}") for g in ALLOWED_GENRES[i:i+2]]
        buttons.append(row)
    buttons.append([KeyboardButton("⬅️ Orqaga")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def movie_extra_kb(code, is_admin_user=False, insta_link=None):
    buttons = [
        [
            InlineKeyboardButton("⭐ 1", callback_data=f"rate_{code}_1"),
            InlineKeyboardButton("⭐ 2", callback_data=f"rate_{code}_2"),
            InlineKeyboardButton("⭐ 3", callback_data=f"rate_{code}_3"),
            InlineKeyboardButton("⭐ 4", callback_data=f"rate_{code}_4"),
            InlineKeyboardButton("⭐ 5", callback_data=f"rate_{code}_5")
        ]
    ]
    if insta_link:
        buttons.append([InlineKeyboardButton("🎬 Kinodan parcha (Video)", url=insta_link)])
    buttons.append([
        InlineKeyboardButton("⭐ Sevimlilarga", callback_data=f"fav_{code}"),
        InlineKeyboardButton("🗓 Ko'rmoqchiman", callback_data=f"wl_{code}")
    ])
    buttons.append([InlineKeyboardButton("💬 Izoh qoldirish", callback_data=f"comment_{code}")])
    if is_admin_user:
        buttons.append([
            InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_{code}"),
            InlineKeyboardButton("🗑 O'chirish", callback_data=f"rm_{code}")
        ])
    return InlineKeyboardMarkup(buttons)

def admin_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Admin Panel"), KeyboardButton("📢 Xabar yuborish")],
        [KeyboardButton("👤 Admin qo'shish"), KeyboardButton("👤 Admin o'chirish")],
        [KeyboardButton("➕ Kanal qo'shish"), KeyboardButton("➖ Kanal o'chirish")],
        [KeyboardButton("🎬 Kino kanalni sozlash"), KeyboardButton("👑 Adminlikni o'tkazish")],
        [KeyboardButton("📥 Kelgan So'rovlar"), KeyboardButton("🗑 So'rovlarni tozalash")],
        [KeyboardButton("📋 Kanallar ro'yxati"), KeyboardButton("👤 User Menu ga qaytish")]
    ], resize_keyboard=True)

def cancel_menu():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Bekor qilish")]], resize_keyboard=True)

def admin_settings_menu():
    return ReplyKeyboardMarkup([
        ["➕ Kanal qo'shish", "➖ Kanal o'chirish"],
        ["📋 Kanallar ro'yxati", "👤 Admin qo'shish"],
        ["⬅️ Orqaga"]
    ], resize_keyboard=True)


# ==========================================
#                HELPERS
# ==========================================

async def check_force_join(client, msg):
    uid = msg.from_user.id
    if is_admin(uid):
        return True

    user_db_data = users_col.find_one({"user_id": uid})
    if user_db_data and user_db_data.get("is_vip", False):
        return True

    conf = get_config()
    channels = conf.get("mandatory_channels", [])

    # Kanal yo'q bo'lsa to'g'ridan o'tkazib yuborish
    if not channels:
        return True

    unsubscribed = []

    for chan in channels:
        try:
            chat_id = chan["id"]
            if isinstance(chat_id, str) and chat_id.startswith("-100"):
                chat_id = int(chat_id)

            member = await client.get_chat_member(chat_id, uid)
            if member.status in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER
            ]:
                continue
            else:
                unsubscribed.append(chan)
        except Exception as e:
            print(f"FORCE JOIN TEKSHIRISHDA XATO: {chan.get('id')} — {e}")
            unsubscribed.append(chan)

    if unsubscribed:
        buttons = []
        for index, ch in enumerate(unsubscribed, start=1):
            link = ch.get('link')
            buttons.append([InlineKeyboardButton(text=f"➕ {index}-kanal", url=link)])

        start_param = msg.command[1] if hasattr(msg, "command") and msg.command and len(msg.command) > 1 else "start"
        me = await client.get_me()
        join_url = f"https://t.me/{me.username}?start={start_param}"
        buttons.append([InlineKeyboardButton(text="✅ Tasdiqlash", url=join_url)])

        text = "<b>👋 Assalomu alaykum!</b>\n\nBotdan foydalanish uchun homiy kanallarga a'zo bo'ling:"

        if hasattr(msg, "data"):
            await msg.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await msg.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
        return False

    return True


def get_movie_list(page=1, genre=None):
    items_per_page = 10
    query = {"genres": genre} if genre else {}
    total_movies = movies_col.count_documents(query)

    if total_movies == 0:
        return "😔 Hozircha bazada kinolar yo'q.", None

    total_pages = math.ceil(total_movies / items_per_page)
    movies = list(movies_col.find(query).sort("code", -1).skip((page - 1) * items_per_page).limit(items_per_page))

    text = f"🎬 <b>Kinolar ro'yxati:</b>\n"
    if genre:
        text += f"📂 Janr: #{genre}\n"
    text += "─────────────────\n\n"

    for m in movies:
        movie_title = m.get('title', "Noma'lum film").split('\n')[0]
        movie_code = m.get('code', "Yo'q")
        downloads_count = m.get('downloads', 0)
        avg = m.get('avg_rating', 0.0)
        text += (
            f"🎬 <b>{movie_title}</b>\n"
            f"📥 <b>Yuklab olindi:</b> {downloads_count} marta | ⭐ {avg:.1f}\n"
            f"🔑 <b>FILM KODI:</b> <code>{movie_code}</code>\n\n"
        )

    buttons = []
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}_{genre or ''}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}_{genre or ''}"))
    buttons.append(nav_row)

    return text, InlineKeyboardMarkup(buttons)


async def notify_admin_new_user(client, user):
    try:
        total = users_col.count_documents({})
        username = f"@{user.username}" if user.username else "Username yo'q"
        text = (
            f"🤖 <b>Botga yangi a'zo qo'shildi!</b>\n\n"
            f"👤 Ismi: <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
            f"🔗 Username: {username}\n"
            f"🆔 ID: <code>{user.id}</code>\n\n"
            f"👥 Jami a'zolar: <b>{total} ta</b>"
        )
        await client.send_message(
            chat_id=NOTIFIER_CHANNEL,
            text=text,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Notifier kanaliga xabar yuborishda xato: {e}")


# ==========================================
#          WEEKLY MAINTENANCE
# ==========================================

async def update_weekly_vip_winners():
    print("Haftalik VIP yangilanishi boshlandi...")
    old_vips = [u["user_id"] for u in users_col.find({"is_vip": True})]
    users_col.update_many({}, {"$set": {"is_vip": False}})

    new_top_10 = list(users_col.find({"referrals": {"$gte": 5}}).sort("referrals", -1).limit(10))
    new_vip_ids = [u["user_id"] for u in new_top_10]

    for user in new_top_10:
        u_id = user["user_id"]
        users_col.update_one({"user_id": u_id}, {"$set": {"is_vip": True}})
        try:
            await app.send_message(
                u_id,
                "🎉 <b>TABRIKLAYMIZ!</b>\n\nSiz haftalik TOP 10 talikka kirdingiz va <b>VIP status</b> oldingiz! "
                "1 hafta davomida majburiy obunalarsiz botdan foydalana olasiz. 💪"
            )
        except:
            continue

    for old_id in old_vips:
        if old_id not in new_vip_ids:
            try:
                await app.send_message(
                    chat_id=old_id,
                    text="😔 <b>VIP status muddati tugadi.</b>\n\nBu hafta TOP 10 talikka kira olmadingiz. "
                         "VIP imtiyozlari to'xtatildi. Keyingi hafta yaxshiraq harakat qiling! 🚀"
                )
            except Exception as e:
                print(f"Xabar yuborishda xato (ID: {old_id}): {e}")
                continue


async def send_weekly_highlights():
    print("Haftalik tavsiyanoma yuborilmoqda...")
    top_3 = list(movies_col.find().sort([("weekly_downloads", -1), ("avg_rating", -1)]).limit(3))
    if not top_3:
        return

    text = "🌟 <b>HAFTA TAVSIYASI</b>\n______________________________________\n\n"
    text += "🔥 Ushbu haftaning eng mashhur kinolari:\n\n"
    for i, m in enumerate(top_3, 1):
        movie_title = m['title'].split('\n')[0]
        downloads_count = m.get('downloads', 0)
        movie_code = m['code']
        text += (
            f"{i}.  <b>{movie_title}</b>\n"
            f"   📥 <b>Yuklab olindi:</b> {downloads_count} marta\n"
            f"   🔑 <b>FILM KODI:</b> <code>{movie_code}</code>\n\n"
        )
    text += "🍿 <i>Kino kodini botga yuboring!</i>"

    async for user in users_col.find():
        try:
            await app.send_message(user["user_id"], text)
            await asyncio.sleep(0.05)
        except:
            continue

    movies_col.update_many({}, {"$set": {"weekly_downloads": 0}})


# ==========================================
#               SCHEDULER
# ==========================================

async def send_daily_stats_to_channel():
    now = datetime.now(UZ_TZ)
    total_u = users_col.count_documents({})
    total_m = movies_col.count_documents({})
    stats_text = f"📊 Kunlik Statistika\n\n👤 Userlar: {total_u}\n🎬 Kinolar: {total_m}\n⏰ {now.strftime('%Y-%m-%d %H:%M')}"
    try:
        await app.send_message(chat_id=SAVED_MOVIE, text=stats_text)
    except:
        pass

scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
scheduler.add_job(send_daily_stats_to_channel, "cron", hour=21, minute=0)
scheduler.add_job(update_weekly_vip_winners, "cron", day_of_week="sun", hour=20, minute=0)


# ==========================================
#        KINO YUBORISH (ASOSIY)
# ==========================================

async def handle_movie_delivery(client, user_id, movie_code):
    """
    Ko'p qismli kino bo'lsa → qism tanlash tugmalari chiqaradi.
    Bir qismli bo'lsa → to'g'ridan-to'g'ri yuboradi.
    """
    if str(movie_code).isdigit():
        movie_code = int(movie_code)

    movie = movies_col.find_one({
        "$or": [
            {"code": movie_code},
            {"code": int(movie_code) if str(movie_code).isdigit() else None}
        ]
    })

    if not movie:
        return False

    parts = movie.get("parts", [])

    # ─── KO'P QISMLI KINO: tugmalar chiqar ───
    if parts and len(parts) > 1:
        title_line = movie.get("title", "Kino").split('\n')[0]
        avg_rating = movie.get('avg_rating', 0.0)
        downloads = movie.get('downloads', 0)

        text = (
            f"🎬 <b>{title_line}</b>\n\n"
            f"📦 Bu kino <b>{len(parts)} qism</b>dan iborat.\n"
            f"📥 Yuklab olindi: {downloads} marta | ⭐ {avg_rating:.1f}\n\n"
            f"👇 <b>Qaysi qismni ko'rmoqchisiz?</b>"
        )

        buttons = []
        row = []
        for p in sorted(parts, key=lambda x: x["part"]):
            part_num = p["part"]
            label = p.get("label", f"{part_num}-qism")
            btn = InlineKeyboardButton(
                f"▶️ {label}",
                callback_data=f"part_{movie_code}_{part_num}"
            )
            row.append(btn)
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        buttons.append([
            InlineKeyboardButton(
                "📦 Barcha qismlarni olish",
                callback_data=f"allparts_{movie_code}"
            )
        ])

        await client.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return True

    # ─── BIR QISMLI KINO: to'g'ridan yuborish ───
    file_id = movie.get("file_id")
    if not file_id and parts and len(parts) == 1:
        file_id = parts[0]["file_id"]
    if not file_id:
        return False

    return await _send_movie_file(client, user_id, movie, file_id, part_label=None)


async def _send_movie_file(client, user_id, movie, file_id, part_label=None):
    """Bitta video faylni yuborish (tarix va statistika bilan)"""
    movies_col.update_one(
        {"_id": movie["_id"]},
        {"$inc": {"downloads": 1, "weekly_downloads": 1}}
    )

    # 📜 TARIX: Yuklab olishni saqlash
    history_col.update_one(
        {"user_id": user_id},
        {
            "$push": {
                "movies": {
                    "$each": [{
                        "code": movie["code"],
                        "title": movie.get("title", "").split('\n')[0],
                        "part": part_label,
                        "date": datetime.now(UZ_TZ)
                    }],
                    "$slice": -30
                }
            }
        },
        upsert=True
    )

    updated_downloads = movie.get('downloads', 0) + 1
    movie_title = movie.get('title', "Noma'lum film").split('\n')[0]
    bot_me = await client.get_me()
    avg_rating = movie.get('avg_rating', 0.0)

    kb = movie_extra_kb(
        code=movie['code'],
        is_admin_user=is_admin(user_id),
        insta_link=movie.get('insta_link')
    )

    # Izohlar
    comments = list(comments_col.find({"movie_code": movie["code"]}).sort("date", -1).limit(3))
    comment_text = ""
    if comments:
        comment_text = "\n\n💬 <b>So'nggi izohlar:</b>\n"
        for c in comments:
            comment_text += f"• {c['username']}: {c['text'][:60]}\n"

    part_text = f"\n📌 <b>Qism:</b> {part_label}" if part_label else ""

    caption_text = (
        f"🎬 <b>{movie_title}</b>"
        f"{part_text}\n"
        f"📥 <b>Yuklab olindi:</b> {updated_downloads} marta\n"
        f"⭐ <b>Reyting:</b> {avg_rating:.1f}\n"
        f"🔑 <b>Film kodi:</b> <code>{movie['code']}</code>\n"
        f"🤖 <b>Bot:</b> @{bot_me.username}"
        f"{comment_text}"
    )

    try:
        await client.send_video(
            chat_id=user_id,
            video=file_id,
            caption=caption_text,
            reply_markup=kb
        )
        return True
    except Exception as e:
        print(f"VIDEO YUBORISHDA XATO: {e}")
        return False


# ==========================================
#   📦 KO'P QISMLI KINO — CALLBACK HANDLER
# ==========================================

@app.on_callback_query(filters.regex(r"^part_(\d+)_(\d+)$"))
async def send_movie_part_cb(client, cb):
    """User qaysi qismni tanlasa o'sha qismni yuboradi"""
    _, movie_code, part_num = cb.data.split("_")
    movie_code = int(movie_code)
    part_num = int(part_num)
    user_id = cb.from_user.id

    movie = movies_col.find_one({"code": movie_code})
    if not movie:
        return await cb.answer("❌ Kino topilmadi!", show_alert=True)

    parts = movie.get("parts", [])
    target = next((p for p in parts if p["part"] == part_num), None)
    if not target:
        return await cb.answer("❌ Bu qism topilmadi!", show_alert=True)

    await cb.answer(f"⏳ {part_num}-qism yuborilmoqda...")
    label = target.get("label", f"{part_num}-qism")
    success = await _send_movie_file(client, user_id, movie, target["file_id"], part_label=label)
    if not success:
        await client.send_message(user_id, "❌ Video yuborishda xato yuz berdi.")


@app.on_callback_query(filters.regex(r"^allparts_(\d+)$"))
async def send_all_parts_cb(client, cb):
    """User 'Barcha qismlarni olish' ni bossa hammasini yuboradi"""
    movie_code = int(cb.data.split("_")[1])
    user_id = cb.from_user.id

    movie = movies_col.find_one({"code": movie_code})
    if not movie:
        return await cb.answer("❌ Kino topilmadi!", show_alert=True)

    parts = sorted(movie.get("parts", []), key=lambda x: x["part"])
    await cb.answer(f"⏳ {len(parts)} ta qism yuborilmoqda...")

    for p in parts:
        label = p.get("label", f"{p['part']}-qism")
        await _send_movie_file(client, user_id, movie, p["file_id"], part_label=label)
        await asyncio.sleep(1)


# ==========================================
#   📦 ADMIN: QISM QO'SHISH BUYRUQLARI
# ==========================================

@app.on_message(filters.command("addpart") & filters.private)
async def addpart_command(client, msg):
    """
    /addpart 47 1  →  47-kinoning 1-qismini qo'shish
    /addpart 47 2  →  47-kinoning 2-qismini qo'shish
    """
    if not is_admin(msg.from_user.id):
        return await msg.reply("🚫 Bu buyruq faqat adminlar uchun!")

    args = msg.command[1:]
    if len(args) < 2 or not args[0].isdigit() or not args[1].isdigit():
        return await msg.reply(
            "❌ Noto'g'ri format!\n\n"
            "✅ To'g'ri: <code>/addpart 47 2</code>\n"
            "<i>(47 — kino kodi, 2 — qism raqami)</i>"
        )

    code = int(args[0])
    part_num = int(args[1])

    movie = movies_col.find_one({"code": code})
    if not movie:
        return await msg.reply(f"❌ <b>{code}</b> kodli kino bazada topilmadi!")

    parts = movie.get("parts", [])
    if any(p["part"] == part_num for p in parts):
        return await msg.reply(
            f"⚠️ {code}-kinoning <b>{part_num}-qismi</b> allaqachon mavjud!\n\n"
            f"O'chirish: <code>/removepart {code} {part_num}</code>"
        )

    addpart_wait[msg.from_user.id] = {"code": code, "part": part_num}
    title_line = movie.get("title", "Kino").split('\n')[0]

    await msg.reply(
        f"🎬 <b>{title_line}</b>\n"
        f"📦 <b>{part_num}-qism</b> uchun:\n\n"
        f"⬇️ Hozir shu xabarga <b>reply qilib video yuboring</b>.",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Bekor qilish")]], resize_keyboard=True)
    )


@app.on_message(filters.command("removepart") & filters.private)
async def removepart_command(client, msg):
    """/removepart 47 2  →  47-kinoning 2-qismini o'chirish"""
    if not is_admin(msg.from_user.id):
        return await msg.reply("🚫 Bu buyruq faqat adminlar uchun!")

    args = msg.command[1:]
    if len(args) < 2 or not args[0].isdigit() or not args[1].isdigit():
        return await msg.reply("❌ Format: <code>/removepart 47 2</code>")

    code = int(args[0])
    part_num = int(args[1])
    result = movies_col.update_one({"code": code}, {"$pull": {"parts": {"part": part_num}}})

    if result.modified_count > 0:
        updated = movies_col.find_one({"code": code})
        remaining = len(updated.get("parts", []))
        await msg.reply(
            f"🗑 <b>{code}-kinoning {part_num}-qismi o'chirildi.</b>\n"
            f"📊 Qolgan qismlar: <b>{remaining} ta</b>"
        )
    else:
        await msg.reply(f"❌ {code}-kinoning {part_num}-qismi topilmadi!")


@app.on_message(filters.command("parts") & filters.private)
async def list_parts_command(client, msg):
    """/parts 47  →  47-kinoning barcha qismlarini ko'rish"""
    if not is_admin(msg.from_user.id):
        return await msg.reply("🚫 Bu buyruq faqat adminlar uchun!")

    args = msg.command[1:]
    if not args or not args[0].isdigit():
        return await msg.reply("❌ Format: <code>/parts 47</code>")

    code = int(args[0])
    movie = movies_col.find_one({"code": code})
    if not movie:
        return await msg.reply(f"❌ {code} kodli kino topilmadi!")

    parts = sorted(movie.get("parts", []), key=lambda x: x["part"])
    title_line = movie.get("title", "Kino").split('\n')[0]

    if not parts:
        return await msg.reply(
            f"🎬 <b>{title_line}</b>\n\n"
            f"📦 Bu kino hali qismlarga bo'linmagan.\n"
            f"Qism qo'shish: <code>/addpart {code} 1</code>"
        )

    text = f"🎬 <b>{title_line}</b> — Qismlar ro'yxati:\n\n"
    for p in parts:
        date = p.get("added_at")
        date_str = date.strftime("%d.%m.%Y") if date else "—"
        part_label = p.get('label') or f"{p['part']}-qism"
        text += f"📌 <b>{part_label}</b> — {date_str}\n"
    text += f"\n📊 Jami: <b>{len(parts)} ta qism</b>"
    text += f"\n➕ Keyingi qism: <code>/addpart {code} {len(parts)+1}</code>"
    await msg.reply(text)


# ==========================================
#        AUTO SAVE FROM CHANNEL
# ==========================================

@app.on_message(filters.video & filters.chat(SAVED_MOVIE))
async def save_movie_from_channel(client, msg):
    caption = msg.caption or ""
    found_genres = [word.strip("#").lower() for word in caption.split() if word.startswith("#") and word.strip("#").lower() in ALLOWED_GENRES]
    if not found_genres:
        found_genres = ["boshqa"]

    # ✅ AQLLI KOD TIZIMI: bo'sh koddan foydalanish
    new_code = get_next_movie_code()

    star_buttons = [
        InlineKeyboardButton("⭐ 1", callback_data=f"star_1_{new_code}"),
        InlineKeyboardButton("⭐ 2", callback_data=f"star_2_{new_code}"),
        InlineKeyboardButton("⭐ 3", callback_data=f"star_3_{new_code}"),
        InlineKeyboardButton("⭐ 4", callback_data=f"star_4_{new_code}"),
        InlineKeyboardButton("⭐ 5", callback_data=f"star_5_{new_code}")
    ]

    movie_buttons = InlineKeyboardMarkup([
        star_buttons,
        [
            InlineKeyboardButton("🎬 Kinodan parcha", callback_data=f"trailer_none"),
            InlineKeyboardButton("⭐ Sevimlilar", callback_data=f"fav_{new_code}")
        ]
    ])

    movies_col.insert_one({
        "code": new_code,
        "file_id": msg.video.file_id,
        "title": caption,
        "downloads": 0,
        "weekly_downloads": 0,
        "genres": found_genres,
        "rating": 0.0,
        "avg_rating": 0.0,
        "votes_count": 0,
        "total_stars": 0,
        "added_at": datetime.now(UZ_TZ)
    })

    # Boshqa o'chirilgan kodlar bor-yo'qligini ko'rsatish
    all_codes = set(m["code"] for m in movies_col.find({}, {"code": 1}))
    max_code = max(all_codes)
    gaps = [i for i in range(1, max_code) if i not in all_codes]
    gap_info = f"\n⚠️ <b>Bo'sh kodlar:</b> {gaps[:5]}" if gaps else "\n✅ Kodlar ketma-ket to'liq"

    await msg.reply(
        f"✅ <b>Bot bazasiga saqlandi!</b>\n\n"
        f"🔑 <b>FILM KODI:</b> <code>{new_code}</code>\n"
        f"🎭 <b>Janrlar:</b> #{' #'.join(found_genres)}\n"
        f"📊 <b>Reyting:</b> 0.0 (0 ta ovoz)"
        f"{gap_info}",
        reply_markup=movie_buttons
    )


@app.on_message(filters.chat(SAVED_MOVIE) & filters.reply & filters.text)
async def update_trailer_link(client, msg):
    if msg.reply_to_message.from_user.is_self and "FILM KODI:" in (msg.reply_to_message.text or ""):
        if "instagram.com" in msg.text:
            try:
                text = msg.reply_to_message.text
                movie_code = int(text.split("FILM KODI:")[1].split()[0].strip())
                link = msg.text.strip()
                movies_col.update_one({"code": movie_code}, {"$set": {"trailer": link}})
                new_markup = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("⭐ 1", callback_data=f"star_1_{movie_code}"),
                        InlineKeyboardButton("⭐ 2", callback_data=f"star_2_{movie_code}"),
                        InlineKeyboardButton("⭐ 3", callback_data=f"star_3_{movie_code}"),
                        InlineKeyboardButton("⭐ 4", callback_data=f"star_4_{movie_code}"),
                        InlineKeyboardButton("⭐ 5", callback_data=f"star_5_{movie_code}")
                    ],
                    [
                        InlineKeyboardButton("🎬 Kinodan parcha", url=link),
                        InlineKeyboardButton("⭐ Sevimlilar", callback_data=f"fav_{movie_code}")
                    ]
                ])
                await msg.reply_to_message.edit_reply_markup(reply_markup=new_markup)
                await msg.reply("✅ Kinodan parcha (link) muvaffaqiyatli bog'landi!")
                await msg.delete()
            except Exception as e:
                await msg.reply(f"❌ Xatolik: {str(e)}")


# ==========================================
#             INLINE SEARCH
# ==========================================

@app.on_inline_query()
async def inline_search(client, query):
    string = query.query.strip()
    me = await client.get_me()
    bot_username = me.username

    if not string:
        movies = list(movies_col.find().sort("downloads", -1).limit(5))
    elif string.isdigit():
        movies = list(movies_col.find({"code": int(string)}))
    else:
        movies = list(movies_col.find({"title": {"$regex": string, "$options": "i"}}).limit(5))

    results = []
    for m in movies:
        movie_title = m.get('title', "Noma'lum film").split('\n')[0]
        movie_code = m.get('code', '000')
        downloads_count = m.get('downloads', 0)
        results.append(
            InlineQueryResultArticle(
                title=f"🎬 {movie_title}",
                description=f"📥 {downloads_count} marta | 🔑 Kod: {movie_code}",
                input_message_content=InputTextMessageContent(
                    f"🎬 <b>{movie_title}</b>\n"
                    f"📥 <b>Yuklab olindi:</b> {downloads_count} marta\n"
                    f"🔑 <b>Film kodi:</b> <code>{movie_code}</code>\n\n"
                    f"🤖 <b>Botimiz:</b> @{bot_username}"
                ),
                thumb_url="https://img.icons8.com/fluency/48/movie.png",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎬 Kinoni ko'rish", url=f"https://t.me/{bot_username}?start={movie_code}")]
                ])
            )
        )

    await query.answer(results, cache_time=5)


# ==========================================
#               START HANDLER
# ==========================================

@app.on_message(filters.command("start") & filters.private)
async def start(client, msg):
    try:
        user = msg.from_user
        user_id = user.id
        print(f"START: {user_id} — {user.first_name}")

        user_data = users_col.find_one({"user_id": user_id})
        is_new_user = user_data is None

        if is_new_user:
            users_col.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "first_name": user.first_name,
                        "username": user.username,
                        "is_counted": False,
                        "referrals": 0
                    },
                    "$setOnInsert": {"joined_at": datetime.utcnow()}
                },
                upsert=True
            )
            user_data = {"is_counted": False}
            await notify_admin_new_user(client, user)

        is_subscribed = await check_force_join(client, msg)
        if not is_subscribed:
            return

        try:
            await client.delete_messages(msg.chat.id, msg.id - 1)
        except:
            pass

        # Referal tizimi
        if user_data.get("is_counted") == False and msg.command and len(msg.command) > 1:
            ref_id_str = msg.command[1]
            if ref_id_str.isdigit():
                ref_id = int(ref_id_str)
                if ref_id != user_id:
                    users_col.update_one({"user_id": ref_id}, {"$inc": {"referrals": 1}})
                    users_col.update_one({"user_id": user_id}, {"$set": {"is_counted": True}})
                    try:
                        await client.send_message(ref_id, "🎉 Do'stingiz obuna bo'ldi! +1 ball.")
                    except:
                        pass

        # Kino kodi yoki salomlashish
        if msg.command and len(msg.command) > 1:
            if await handle_movie_delivery(client, user_id, msg.command[1]):
                return

        await msg.reply(f"Assalomu alaykum {user.first_name}!", reply_markup=user_menu(user_id))

    except Exception as e:
        print(f"START HANDLERDA XATO: {e}")
        import traceback
        traceback.print_exc()


# ==========================================
#         KINO KANAL HANDLERLARI
# ==========================================

@app.on_message(filters.chat(KINO1CHRA_CHANNEL) & (filters.video | filters.document))
async def on_movie_upload(client, msg):
    await msg.reply_text(
        f"✅ <b>Kino yuklandi!</b> (ID: {msg.id})\n\n"
        "Endi ushbu xabarga <b>Reply</b> qilib, foydalanuvchi ID-sini yuboring."
    )

@app.on_message(filters.chat(KINO1CHRA_CHANNEL) & filters.reply)
async def handle_admin_id_reply(client, msg):
    if msg.text and msg.text.strip().isdigit():
        user_id = int(msg.text.strip())

        movie_id = None
        if msg.reply_to_message.reply_to_message:
            movie_id = msg.reply_to_message.reply_to_message.id
        elif msg.reply_to_message.video or msg.reply_to_message.document:
            movie_id = msg.reply_to_message.id

        if movie_id:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Topildi (Yuborish)", callback_data=f"sendv_{user_id}_{movie_id}")]
            ])
            await msg.reply_text(
                f"👤 Foydalanuvchi: <code>{user_id}</code>\n"
                f"🎬 Kino ID: <code>{movie_id}</code>\n\n"
                "Yuborish uchun pastdagi tugmani bosing:",
                reply_markup=keyboard
            )
        else:
            await msg.reply_text("❌ Xato: Kino xabarini topa olmadim.")

@app.on_callback_query(filters.regex(r"^sendv_(\d+)_(\d+)"))
async def send_movie_final(client, cb):
    data = cb.data.split("_")
    user_id = int(data[1])
    movie_id = int(data[2])

    try:
        await client.copy_message(
            chat_id=user_id,
            from_chat_id=KINO1CHRA_CHANNEL,
            message_id=movie_id
        )
        await client.send_message(
            chat_id=user_id,
            text="🎬 <b>Siz so'ragan kinoyingiz botimizga yuklandi!</b>\n\nMarhamat, tomosha qilishingiz mumkin."
        )
        await cb.message.edit_text(f"✅ Muvaffaqiyatli yuborildi!\n👤 Foydalanuvchi: {user_id}")
        await cb.answer("Yuborildi!", show_alert=True)
    except Exception as e:
        await cb.answer(f"Xatolik: {str(e)}", show_alert=True)


# ==========================================
#           CALLBACK HANDLERS
# ==========================================

@app.on_callback_query(filters.regex("^check_"))
async def check_callback(client, query):
    code = query.data.split("_")[1]
    if await check_force_join(client, query):
        await query.message.delete()
        uid = query.from_user.id
        if code != "none":
            await handle_movie_delivery(client, uid, code)
        else:
            await client.send_message(uid, "✅ Obuna tasdiqlandi! Xush kelibsiz.", reply_markup=user_menu(uid))

@app.on_callback_query(filters.regex("^rate_"))
async def rate_movie_cb(client, cb):
    _, code, stars = cb.data.split("_")
    code, stars = int(code), int(stars)
    ratings_col.update_one({"user_id": cb.from_user.id, "movie_code": code}, {"$set": {"stars": stars}}, upsert=True)
    all_r = list(ratings_col.find({"movie_code": code}))
    avg = sum(r['stars'] for r in all_r) / len(all_r)
    movies_col.update_one({"code": code}, {"$set": {"avg_rating": avg}})
    await cb.answer(f"Rahmat! {stars} yulduz qabul qilindi.", show_alert=True)

@app.on_callback_query(filters.regex("^page_"))
async def page_cb(client, cb):
    data = cb.data.split("_")
    p = int(data[1])
    g = data[2] if len(data) > 2 and data[2] != "" else None
    t, m = get_movie_list(p, g)
    try:
        await cb.message.edit_text(t, reply_markup=m)
    except MessageNotModified:
        pass

@app.on_callback_query(filters.regex(r"^found_(\d+)"))
async def movie_found_callback(client, cb):
    user_id = int(cb.data.split("_")[1])
    try:
        admin_id_msg = cb.message.reply_to_message
        movie_msg = admin_id_msg.reply_to_message
        if movie_msg:
            await movie_msg.copy(chat_id=user_id)
            await client.send_message(chat_id=user_id, text="✅ <b>Siz so'ragan kinoyingiz botimizga yuklandi!</b>")
            await cb.message.edit_text(f"✅ Kino {user_id} ga yuborildi va foydalanuvchi ogohlantirildi.")
        else:
            await cb.answer("Xato: Kino fayli topilmadi!", show_alert=True)
    except Exception as e:
        await cb.answer(f"Xatolik: {str(e)}", show_alert=True)

@app.on_callback_query(filters.regex(r"^star_(\d+)_(\d+)"))
async def handle_star_rating(client, cb):
    _, stars, code = cb.data.split("_")
    stars = int(stars)
    code = int(code)

    movie = movies_col.find_one({"code": code})
    if not movie:
        return await cb.answer("Kino topilmadi!", show_alert=True)

    new_votes = movie.get("votes_count", 0) + 1
    new_total = movie.get("total_stars", 0) + stars
    new_avg = round(new_total / new_votes, 1)

    movies_col.update_one(
        {"code": code},
        {"$set": {"votes_count": new_votes, "total_stars": new_total, "rating": new_avg, "avg_rating": new_avg}}
    )

    current_caption = cb.message.caption if cb.message.caption else cb.message.text or ""
    lines = current_caption.split('\n')
    if "📊 Reyting:" in lines[-1]:
        lines[-1] = f"📊 <b>Reyting:</b> {new_avg} ({new_votes} ta ovoz)"
    else:
        lines.append(f"📊 <b>Reyting:</b> {new_avg} ({new_votes} ta ovoz)")

    updated_text = "\n".join(lines)
    try:
        await cb.edit_message_text(updated_text, reply_markup=cb.message.reply_markup)
        await cb.answer(f"Siz {stars} yulduz berdingiz!")
    except:
        try:
            await cb.edit_message_caption(updated_text, reply_markup=cb.message.reply_markup)
            await cb.answer(f"Siz {stars} yulduz berdingiz!")
        except:
            await cb.answer("Ovozingiz saqlandi!")

@app.on_callback_query(filters.regex("^fav_"))
async def add_fav_callback(client, cb):
    code = int(cb.data.split("_")[1])
    fav_col.update_one({"user_id": cb.from_user.id}, {"$addToSet": {"movies": code}}, upsert=True)
    await cb.answer("⭐ Sevimlilar ro'yxatiga qo'shildi!")

# ==========================================
#   🗓 YANGI: KO'RMOQCHIMAN (WATCHLIST)
# ==========================================

@app.on_callback_query(filters.regex("^wl_"))
async def add_watchlist_callback(client, cb):
    code = int(cb.data.split("_")[1])
    movie = movies_col.find_one({"code": code})
    if not movie:
        return await cb.answer("Kino topilmadi!", show_alert=True)
    watchlist_col.update_one(
        {"user_id": cb.from_user.id},
        {"$addToSet": {"movies": {"code": code, "title": movie.get("title", "").split('\n')[0]}}},
        upsert=True
    )
    await cb.answer("🗓 Ko'rmoqchiman ro'yxatiga qo'shildi!")

# ==========================================
#   💬 YANGI: IZOH TIZIMI
# ==========================================

@app.on_callback_query(filters.regex("^comment_"))
async def comment_callback(client, cb):
    code = int(cb.data.split("_")[1])
    uid = cb.from_user.id
    comment_wait[uid] = code
    await cb.message.reply(
        f"✍️ <b>{code}-kino uchun izohingizni yozing:</b>\n\n<i>(Bekor qilish uchun: ❌ Bekor qilish)</i>",
        reply_markup=cancel_menu()
    )
    await cb.answer()

# ==========================================
#   ✏️ YANGI: KINO TAHRIRLASH
# ==========================================

@app.on_callback_query(filters.regex("^edit_"))
async def edit_movie_callback(client, cb):
    if not is_admin(cb.from_user.id):
        return await cb.answer("🚫 Faqat adminlar uchun!", show_alert=True)
    code = int(cb.data.split("_")[1])
    uid = cb.from_user.id
    edit_wait[uid] = {"code": code, "step": "field"}
    await cb.message.reply(
        f"✏️ <b>{code}-kinoni tahrirlash</b>\n\nNimani o'zgartirmoqchisiz?",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("📝 Nomini o'zgartirish")],
            [KeyboardButton("🎭 Janrini o'zgartirish")],
            [KeyboardButton("❌ Bekor qilish")]
        ], resize_keyboard=True)
    )
    await cb.answer()

# ==========================================
#   🗑 KINO O'CHIRISH (KODLARNI QAYTA TARTIBGA SOLISH)
# ==========================================

@app.on_callback_query(filters.regex("^rm_"))
async def rm_cb(client, cb):
    if not is_admin(cb.from_user.id):
        return await cb.answer("🚫 Bu amal faqat adminlar uchun!", show_alert=True)
    try:
        code_str = cb.data.split("_")[1]
        code = int(code_str) if code_str.isdigit() else code_str
        result = movies_col.delete_one({"code": code})
        if result.deleted_count > 0:
            # Keyingi bo'sh kod qaysi bo'lishini ko'rsatish
            next_code = get_next_movie_code()
            await cb.message.edit_text(
                f"🗑 Kino (Kod: {code}) bazadan muvaffaqiyatli o'chirildi.\n\n"
                f"ℹ️ Keyingi yangi kino kodi: <b>{next_code}</b>"
            )
        else:
            await cb.answer("❌ Bu kodli kino bazada topilmadi.", show_alert=True)
    except Exception as e:
        await cb.answer(f"❌ Xatolik yuz berdi: {e}", show_alert=True)

@app.on_callback_query(filters.regex("^approve_"))
async def approve_cb(client, cb):
    if is_admin(cb.from_user.id):
        data = cb.data.split("_")
        uid, req_name = int(data[1]), "_".join(data[2:])
        try:
            req_col.delete_one({"user_id": uid, "name": req_name})
            await cb.message.edit_text(f"✅ '{req_name}' topildi deb belgilandi va xabar yuborildi.")
        except Exception as e:
            await cb.answer(f"Xato: {e}", show_alert=True)

@app.on_callback_query(filters.regex("^notfound_"))
async def not_found_cb(client, cb):
    if is_admin(cb.from_user.id):
        data = cb.data.split("_")
        uid, req_name = int(data[1]), "_".join(data[2:])
        try:
            users_col.update_one({"user_id": uid}, {"$inc": {"referrals": 1}})
            await client.send_message(
                chat_id=uid,
                text=f"😔 <b>Uzur, siz so'ragan '{req_name}' kinosini topa olmadik.</b>\n\n"
                     f"Sizga boshqa kino so'rash uchun qaytadan imkoniyat berildi. 🚀"
            )
            req_col.delete_one({"user_id": uid, "name": req_name})
            await cb.message.edit_text(f"❌ '{req_name}' topilmadi. Limit qaytarildi.")
        except Exception as e:
            await cb.answer(f"Xato: {e}", show_alert=True)

@app.on_callback_query(filters.regex("^(confirm|cancel)_clear_requests"))
async def clear_requests_cb(client, callback_query):
    data = callback_query.data
    uid = callback_query.from_user.id
    if not is_admin(uid):
        return await callback_query.answer("Siz admin emassiz!", show_alert=True)
    if data == "confirm_clear_requests":
        requests_col.delete_many({})
        await callback_query.message.edit_text("✅ Barcha so'rovlar muvaffaqiyatli tozalandi!")
        await callback_query.answer("Tozalandi", show_alert=False)
    elif data == "cancel_clear_requests":
        await callback_query.message.edit_text("❌ Tozalash amali bekor qilindi.")
        await callback_query.answer("Bekor qilindi")

@app.on_callback_query(filters.regex("^ignore$"))
async def ignore_cb(client, cb):
    await cb.answer()


# ==========================================
#                SHORTS HANDLER
# ==========================================

@app.on_message(filters.chat(SAVE_SHORTS) & filters.reply, group=-1)
async def handle_shorts_processing(client, msg):
    if not msg.reply_to_message.video:
        return

    text = msg.text if msg.text else ""
    code_match = re.search(r"start=(\d+)", text)
    movie_code = code_match.group(1) if code_match else (text if text.isdigit() else None)

    if not movie_code:
        await msg.reply("❌ Xato: Videoga reply qilib kodni yuboring!")
        return

    movie = movies_col.find_one({
        "$or": [
            {"code": movie_code},
            {"code": int(movie_code) if movie_code.isdigit() else None}
        ]
    })

    if not movie:
        await msg.reply(f"❌ Bazada 【{movie_code}】 kodli kino topilmadi!")
        return

    bot_info = await client.get_me()
    caption = (
        f" <b>{movie['title']}</b>\n\n"
        f"ℹ️ <i>Yuqoridagi videoda ushbu kinodan parcha ko'rsatilgan.</i>\n"
        f"🔑 <b>Kino kodi:</b> <code>{movie['code']}</code>\n\n"
        f"📥 <b>Kinoni yuklab olish uchun pastdagi tugmani bosing:</b>"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Kinoni ko'rish / Yuklash", url=f"https://t.me/{bot_info.username}?start={movie['code']}")]
    ])

    try:
        await client.send_video(
            chat_id=MAIN_CHANNEL,
            video=msg.reply_to_message.video.file_id,
            caption=caption,
            reply_markup=keyboard
        )
        await msg.reply("✅ Asosiy kanalga muvaffaqiyatli yuborildi!")
    except Exception as e:
        await msg.reply(f"❌ Xatolik turi: {type(e).__name__}\nHabar: {e}")


# ==========================================
#     INSTAGRAM LINK (SAVED_MOVIE KANAL)
# ==========================================

@app.on_message(filters.text & filters.chat(SAVED_MOVIE))
async def save_insta_link(client, msg):
    if msg.reply_to_message and msg.reply_to_message.video:
        link = msg.text
        if "instagram.com" in link:
            video_file_id = msg.reply_to_message.video.file_id
            movies_col.update_one(
                {"file_id": video_file_id},
                {"$set": {"insta_link": link}}
            )
            await msg.reply("🔗 Instagram havola ushbu kinoga biriktirildi!")


def movie_found_kb(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Topildi", callback_data=f"found_{user_id}")]
    ])


# ==========================================
#          ASOSIY TEXT HANDLER
# ==========================================

@app.on_message((filters.text | filters.video | filters.photo) & filters.private)
async def handle_text(client, msg):
    if not msg.from_user:
        return

    uid = msg.from_user.id
    txt = msg.text

    # ─── 📦 QISM VIDEO QABUL QILISH (addpart_wait) ───
    if uid in addpart_wait:
        if txt == "❌ Bekor qilish":
            addpart_wait.pop(uid)
            return await msg.reply("Bekor qilindi.", reply_markup=admin_menu())
        if msg.video:
            state = addpart_wait.pop(uid)
            code = state["code"]
            part_num = state["part"]
            label = f"{part_num}-qism"
            movies_col.update_one(
                {"code": code},
                {
                    "$push": {
                        "parts": {
                            "part": part_num,
                            "file_id": msg.video.file_id,
                            "label": label,
                            "added_at": datetime.now(UZ_TZ)
                        }
                    }
                }
            )
            updated = movies_col.find_one({"code": code})
            total_parts = len(updated.get("parts", []))
            title_line = updated.get("title", "Kino").split('\n')[0]
            return await msg.reply(
                f"✅ <b>Muvaffaqiyatli saqlandi!</b>\n\n"
                f"🎬 Kino: <b>{title_line}</b>\n"
                f"🔑 Kod: <code>{code}</code>\n"
                f"📦 Qo'shildi: <b>{label}</b>\n"
                f"📊 Jami qismlar: <b>{total_parts} ta</b>\n\n"
                f"<i>Endi user {code} kodini yuborganda qism tanlash tugmalari chiqadi.</i>",
                reply_markup=admin_menu()
            )
        return  # Video yuborilmagan bo'lsa kutib turadi

    # ─── IZOH HOLATI ───
    if uid in comment_wait:
        if txt == "❌ Bekor qilish":
            comment_wait.pop(uid)
            return await msg.reply("Bekor qilindi.", reply_markup=user_menu(uid))
        movie_code = comment_wait.pop(uid)
        comments_col.insert_one({
            "user_id": uid,
            "username": msg.from_user.first_name,
            "movie_code": movie_code,
            "text": txt[:200],
            "date": datetime.now(UZ_TZ)
        })
        return await msg.reply("💬 Izohingiz saqlandi! Rahmat.", reply_markup=user_menu(uid))

    # ─── TAHRIRLASH HOLATI ───
    if uid in edit_wait:
        state = edit_wait[uid]
        if txt == "❌ Bekor qilish":
            edit_wait.pop(uid)
            return await msg.reply("Bekor qilindi.", reply_markup=admin_menu())

        if state["step"] == "field":
            if txt == "📝 Nomini o'zgartirish":
                edit_wait[uid]["step"] = "title"
                return await msg.reply("📝 Yangi nomni yuboring:", reply_markup=cancel_menu())
            elif txt == "🎭 Janrini o'zgartirish":
                edit_wait[uid]["step"] = "genre"
                genres_str = ", ".join(ALLOWED_GENRES)
                return await msg.reply(f"🎭 Yangi janrni yuboring:\n<i>({genres_str})</i>", reply_markup=cancel_menu())

        elif state["step"] == "title":
            edit_wait.pop(uid)
            movies_col.update_one({"code": state["code"]}, {"$set": {"title": txt}})
            return await msg.reply(f"✅ {state['code']}-kino nomi yangilandi!", reply_markup=admin_menu())

        elif state["step"] == "genre":
            edit_wait.pop(uid)
            new_genre = txt.strip().lower()
            if new_genre not in ALLOWED_GENRES:
                return await msg.reply(f"❌ Noto'g'ri janr! Quyidagilardan birini yozing:\n{', '.join(ALLOWED_GENRES)}")
            movies_col.update_one({"code": state["code"]}, {"$set": {"genres": [new_genre]}})
            return await msg.reply(f"✅ {state['code']}-kino janri yangilandi: #{new_genre}", reply_markup=admin_menu())

    # ─── BROADCAST HOLATI ───
    user_state = next((s for s in broadcast_wait if isinstance(s, str) and s.endswith(f"_{uid}")), None)
    if user_state:
        if txt == "❌ Bekor qilish":
            broadcast_wait.discard(user_state)
            return await msg.reply("Bekor qilindi.", reply_markup=admin_menu())

        if user_state.startswith("remadmin_"):
            broadcast_wait.discard(user_state)
            try:
                rem_id = int(txt)
                result = db.settings.update_one({"type": "bot_config"}, {"$pull": {"admin_ids": rem_id}})
                if result.modified_count > 0:
                    return await msg.reply(f"✅ {rem_id} yordamchi adminlar ro'yxatidan o'chirildi.", reply_markup=admin_menu())
                else:
                    return await msg.reply("❌ Bunday ID yordamchi adminlar ro'yxatida topilmadi.", reply_markup=admin_menu())
            except:
                return await msg.reply("❌ Xato! Faqat ID raqamini yuboring.")

        elif user_state.startswith("addchan_"):
            txt_input = txt.strip()
            ch_id = None
            link = None
            title = None
            try:
                if txt_input.startswith("-100"):
                    chat = await client.get_chat(txt_input)
                    ch_id = chat.id
                    title = chat.title
                    link = chat.invite_link or f"https://t.me/c/{str(ch_id)[4:]}/1"
                elif txt_input.startswith("@"):
                    chat = await client.get_chat(txt_input)
                    ch_id = chat.id
                    title = chat.title
                    link = f"https://t.me/{txt_input[1:]}"
                elif "t.me/" in txt_input and "+" not in txt_input and "/joinchat/" not in txt_input:
                    path = txt_input.split("t.me/")[1].split("/")[0]
                    chat = await client.get_chat(f"@{path}")
                    ch_id = chat.id
                    title = chat.title
                    link = txt_input
                elif "t.me/+" in txt_input or "joinchat" in txt_input:
                    chat = await client.get_chat(txt_input)
                    ch_id = chat.id
                    title = chat.title
                    link = txt_input
                else:
                    return await msg.reply("❌ Noto'g'ri format! ID, Username yoki Link yuboring.")
            except Exception as e:
                return await msg.reply(f"❌ Bot kanalni topa olmadi!\nXatolik: `{e}`")

            if ch_id and link:
                new_ch = {"id": str(ch_id), "link": link, "title": title or "Nomsiz kanal"}
                db.settings.update_one({"type": "bot_config"}, {"$addToSet": {"mandatory_channels": new_ch}}, upsert=True)
                broadcast_wait.discard(user_state)
                return await msg.reply(
                    f"✅ Kanal muvaffaqiyatli qo'shildi!\n\n"
                    f"📢 Nomi: {title}\n"
                    f"🆔 ID: <code>{ch_id}</code>\n"
                    f"🔗 Link: {link}",
                    reply_markup=admin_menu()
                )

        elif user_state.startswith("remchan_"):
            ch_id_input = txt.strip()
            conf = db.settings.find_one({"type": "bot_config"})
            if not conf:
                return await msg.reply("❌ Sozlamalar topilmadi!")
            channels = conf.get("mandatory_channels", [])
            target_channel = None
            for c in channels:
                if str(c.get('id')) == str(ch_id_input) or c.get('link') == ch_id_input:
                    target_channel = c
                    break
            if target_channel:
                db.settings.update_one({"type": "bot_config"}, {"$pull": {"mandatory_channels": {"id": target_channel['id']}}})
                broadcast_wait.discard(user_state)
                return await msg.reply(
                    f"🗑 Kanal muvaffaqiyatli o'chirildi!\n\n🆔 ID: <code>{target_channel['id']}</code>",
                    reply_markup=admin_menu()
                )
            else:
                available_ids = ", ".join([f"<code>{c.get('link', c.get('id'))}</code>" for c in channels])
                return await msg.reply(f"❌ Bunday kanal topilmadi!\n\nMavjudlari: {available_ids}")

        elif user_state.startswith("setmoviechan_"):
            broadcast_wait.discard(user_state)
            link = txt.strip()
            if link.startswith("-100"):
                movie_ch = int(link)
            elif link.startswith("@"):
                movie_ch = link
            elif "t.me/" in link:
                part = link.split("t.me/")[1].split("/")[0]
                movie_ch = f"@{part}" if not part.startswith("+") else link
            else:
                return await msg.reply("❌ Noto'g'ri format!")
            db.settings.update_one({"type": "bot_config"}, {"$set": {"movie_channel": movie_ch}})
            return await msg.reply(f"✅ Kino kanali yangilandi: <code>{movie_ch}</code>", reply_markup=admin_menu())

        if user_state.startswith("addadmin_"):
            broadcast_wait.discard(user_state)
            try:
                new_id = int(txt)
                db.settings.update_one({"type": "bot_config"}, {"$addToSet": {"admin_ids": new_id}})
                try:
                    await client.send_message(
                        chat_id=new_id,
                        text=(
                            "👨‍💻 <b>Siz ushbu botga yordamchi admin etib tayinlandingiz!</b>\n\n"
                            "Endi sizda quyidagi huquqlar bor:\n"
                            "• Bot statistikasini ko'rish\n"
                            "• Foydalanuvchilarga xabar yuborish\n\n"
                            "<i>Admin panelga kirish uchun /start bosing.</i>"
                        ),
                        reply_markup=admin_menu()
                    )
                except Exception as e:
                    print(f"Yordamchi adminga xabar yuborib bo'lmadi: {e}")
                return await msg.reply(f"✅ <code>{new_id}</code> yordamchi adminlar ro'yxatiga qo'shildi.", reply_markup=admin_menu())
            except ValueError:
                return await msg.reply("❌ Xato! Faqat ID raqam yuboring.")

        elif user_state.startswith("transfer_"):
            broadcast_wait.discard(user_state)
            try:
                new_main_id = int(txt)
                db.settings.update_one({"type": "bot_config"}, {"$set": {"main_admin": new_main_id}})
                db.settings.update_one({"type": "bot_config"}, {"$pull": {"admin_ids": new_main_id}})
                try:
                    await client.send_message(
                        chat_id=new_main_id,
                        text="👑 <b>Tabriklaymiz!</b>\n\nSiz ushbu botning <b>Asosiy Admini</b> etib tayinlandingiz.\n\n👉 /start tugmasini bosing.",
                        reply_markup=admin_menu()
                    )
                except:
                    pass
                await msg.reply(
                    f"✅ Egalik huquqi muvaffaqiyatli o'tkazildi!\n\nYangi admin (ID: <code>{new_main_id}</code>) xabardor qilindi.",
                    reply_markup=user_menu(uid)
                )
                return
            except ValueError:
                return await msg.reply("❌ Xato! Iltimos, faqat raqamli ID yuboring.")

    # ─── MAJBURIY OBUNA ───
    if not await check_force_join(client, msg):
        return

    # ─── LEADERBOARD ───
    if txt == "🏆 Leaderboard":
        res_text = await get_leaderboard_text()
        return await msg.reply(res_text)

    # ─── KOD ORQALI QIDIRISH ───
    if txt and txt.isdigit():
        code = int(txt)
        movie = movies_col.find_one({"code": code})
        if movie:
            await handle_movie_delivery(client, uid, code)
            return
        else:
            return await msg.reply(f"❌ <b>{code}</b> kodli kino topilmadi.")

    # ─── ADMIN APPROVE HOLATI ───
    if uid in approve_wait:
        if txt == "❌ Bekor qilish":
            approve_wait.pop(uid)
            return await msg.reply("Bekor qilindi.", reply_markup=admin_menu())
        data = approve_wait.pop(uid)
        try:
            code = int(txt)
            user_text = (
                f"✅ <b>Siz so'ragan kino {SAVED_MOVIE} kanaliga yuklandi!</b>\n\n"
                f"🍿 Kino kodi: <code>{code}</code>\n"
                f"🎬 Nomi: {data['name']}\n\n"
                f"<i>Botga kodni yuborib kinoni yuklab olishingiz mumkin.</i>"
            )
            await client.send_message(data["target"], user_text)
            req_col.delete_one({"user_id": data["target"], "name": data["name"]})
            await msg.reply("✅ Foydalanuvchiga xabar va kino kodi yuborildi.", reply_markup=admin_menu())
        except:
            await msg.reply("Xato! Faqat raqamli kod yuboring.")
        return

    # ─── STATISTIKA ───
    if txt == "📊 Statistika":
        u_dat = users_col.find_one({"user_id": uid})
        refs = u_dat.get("referrals", 0) if u_dat else 0
        vip_status = "✅ Faol" if refs >= 5 or is_admin(uid) else "❌ Faol emas"
        all_movies = list(movies_col.find({}, {"downloads": 1}))
        total_downloads = sum(m.get("downloads", 0) for m in all_movies)
        u_count = users_col.count_documents({})
        hist = history_col.find_one({"user_id": uid})
        watched = len(hist.get("movies", [])) if hist else 0
        now = datetime.now(UZ_TZ)
        res = (
            f"📊 <b>Statistika:</b>\n"
            f"______________________________________\n\n"
            f"💎 <b>VIP Status:</b> {vip_status}\n"
            f"👥 Do'stlaringiz: <code>{refs} ta</code>\n"
            f"📜 Ko'rgan kinolaringiz: <code>{watched} ta</code>\n\n"
            f"👤 Jami Userlar: {u_count}\n"
            f"📥 Jami yuklab olishlar: {total_downloads}\n"
            f"⏰ Vaqt: {now.strftime('%H:%M / %d.%m.%Y')}"
        )
        return await msg.reply(res)

    # ─── ADMIN PANEL ───
    if txt == "📊 Admin Panel" and is_admin(uid):
        all_movies = list(movies_col.find({}, {"downloads": 1}))
        total_downloads = sum(m.get("downloads", 0) for m in all_movies)
        u_count = users_col.count_documents({})
        m_count = movies_col.count_documents({})
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_u = users_col.count_documents({"joined_at": {"$gte": today_start}})
        now = datetime.now(UZ_TZ)
        # Bo'sh kodlar
        all_codes = set(m["code"] for m in movies_col.find({}, {"code": 1}))
        max_code = max(all_codes) if all_codes else 0
        gaps = [i for i in range(1, max_code) if i not in all_codes]
        gap_text = f"\n🔑 Bo'sh kodlar: {gaps[:10]}" if gaps else "\n✅ Barcha kodlar ketma-ket"
        res = (
            f"📊 <b>Admin Panel Statistika</b>\n"
            f"______________________________________\n\n"
            f"🆕 Bugun qo'shildi: {today_u}\n"
            f"👥 Jami Userlar: {u_count}\n"
            f"🎬 Jami yuklangan kinolar: {m_count}\n"
            f"📥 Jami yuklab olishlar: {total_downloads}\n"
            f"⏰ Vaqt: {now.strftime('%Y-%m-%d %H:%M')}"
            f"{gap_text}"
        )
        return await msg.reply(res, reply_markup=admin_menu())

    # ─── MENU TUGMALARI ───
    if txt == "🎭 Janrlar":
        return await msg.reply("🎭 Janrni tanlang:", reply_markup=genres_keyboard())

    if txt == "📂 Barcha Kinolar":
        t, m = get_movie_list(1)
        return await msg.reply(t, reply_markup=m)

    if txt == "📈 Top Kinolar":
        top = list(movies_col.find().sort([("avg_rating", -1), ("downloads", -1)]).limit(10))
        res = "📈 <b>Top 10 Kinolar:</b>\n\n"
        for i, x in enumerate(top, 1):
            t_line = x['title'].split('\n')[0]
            downloads_count = x.get('downloads', 0)
            avg = x.get('avg_rating', 0.0)
            movie_code = x['code']
            res += (
                f"{i}.  <b>{t_line}</b>\n"
                f"   📥 {downloads_count} marta | ⭐ {avg:.1f}\n"
                f"   🔑 <b>FILM KODI:</b> <code>{movie_code}</code>\n\n"
            )
        return await msg.reply(res)

    if txt == "⭐ Sevimlilar":
        fav = fav_col.find_one({"user_id": uid})
        if not fav or not fav.get("movies"):
            return await msg.reply("⭐ Sevimlilar ro'yxatingiz bo'sh.")
        res = "⭐ <b>Siz saqlagan kinolar:</b>\n\n"
        for c in fav["movies"]:
            m = movies_col.find_one({"code": c})
            if m:
                t_line = m['title'].split('\n')[0]
                res += f"🎬 {t_line}\n🔑 FILM KODI: <code>{m['code']}</code>\n\n"
        return await msg.reply(res)

    # ─── 📜 YANGI: TARIX ───
    if txt == "📜 Tarixim":
        hist = history_col.find_one({"user_id": uid})
        if not hist or not hist.get("movies"):
            return await msg.reply("📜 Siz hali hech qanday kino ko'rmaganingiz.")
        movies_list = list(reversed(hist.get("movies", [])))[:15]
        res = "📜 <b>Sizning ko'rgan kinolaringiz (oxirgi 30 ta):</b>\n\n"
        for i, entry in enumerate(movies_list, 1):
            date_str = entry["date"].strftime("%d.%m.%Y") if isinstance(entry.get("date"), datetime) else "—"
            nomalum = "Noma'lum"
            title = entry.get("title", nomalum)
            res += f"{i}. 🎬 {title}\n   🔑 Kod: <code>{entry['code']}</code> | 📅 {date_str}\n\n"
        return await msg.reply(res)

    # ─── 🗓 YANGI: KO'RMOQCHIMAN ───
    if txt == "🗓 Ko'rmoqchiman":
        wl = watchlist_col.find_one({"user_id": uid})
        if not wl or not wl.get("movies"):
            return await msg.reply("🗓 Ko'rmoqchiman ro'yxatingiz bo'sh.\n\nKinolarni ko'rib, <b>🗓 Ko'rmoqchiman</b> tugmasini bosing!")
        res = "🗓 <b>Ko'rmoqchiman ro'yxati:</b>\n\n"
        buttons = []
        for entry in wl.get("movies", []):
            title = entry.get("title", "Noma'lum")
            code = entry.get("code")
            res += f"🎬 {title}\n🔑 Kod: <code>{code}</code>\n\n"
            buttons.append([InlineKeyboardButton(f"▶️ {title[:25]}", callback_data=f"playwl_{code}"),
                             InlineKeyboardButton("🗑", callback_data=f"rmwl_{code}")])
        return await msg.reply(res, reply_markup=InlineKeyboardMarkup(buttons))

    if txt == "📥 Kino so'rash":
        u_dat = users_col.find_one({"user_id": uid})
        refs = u_dat.get("referrals", 0) if u_dat else 0
        if refs < 5 and not is_admin(uid):
            bot_obj = await client.get_me()
            ref_link = f"https://t.me/{bot_obj.username}?start={uid}"
            vip_text = (
                "⚠️ <b>KECHIRASIZ, SIZ VIP EMASSIZ!</b>\n"
                "______________________________________\n\n"
                "📥 <b>Kino so'rash</b> funksiyasi faqat VIP a'zolar uchun.\n"
                f"👤 Sizning takliflaringiz: <code>{refs} ta</code>\n"
                f"🚀 Yana <code>{5 - refs} ta</code> do'st qo'shishingiz kerak.\n\n"
                f"🔗 <b>Sizning havolangiz:</b>\n<code>{ref_link}</code>"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Ulashish (Share)", url=f"https://t.me/share/url?url={ref_link}")]
            ])
            return await msg.reply(vip_text, reply_markup=kb)
        request_wait.add(uid)
        return await msg.reply("✍🏻 <b>Kino nomini yozing:</b>", reply_markup=cancel_menu())

    if txt == "📢 Reklama":
        return await msg.reply("📢 Reklama xizmati bo'yicha admin bilan bog'laning: @Mr_Javohirjon")

    if txt == "⬅️ Orqaga":
        return await msg.reply("Bosh menyu:", reply_markup=user_menu(uid))

    if txt == "⚙️ Admin Menu" and is_admin(uid):
        return await msg.reply("⚙️ Admin paneliga xush kelibsiz.", reply_markup=admin_menu())

    if txt == "📋 Kanallar ro'yxati":
        conf = get_config()
        channels = conf.get("mandatory_channels", [])
        if channels:
            text = "📢 <b>Majburiy kanallar:</b>\n\n"
            for ch in channels:
                text += f"• {ch.get('title', 'Nomsiz')} — {ch.get('link', '')}\n"
        else:
            text = "Hozircha kanallar yo'q"
        return await msg.reply(text)

    if txt == "👤 User Menu ga qaytish":
        return await msg.reply("👤 Foydalanuvchi menyusi.", reply_markup=user_menu(uid))

    if txt and txt.startswith("📁 "):
        genre_name = txt.replace("📁 ", "").lower()
        t, m = get_movie_list(1, genre_name)
        return await msg.reply(t, reply_markup=m)

    # ─── KINO SO'ROVI ───
    if uid in request_wait:
        request_wait.remove(uid)
        if txt == "❌ Bekor qilish":
            return await msg.reply("Bekor qilindi.", reply_markup=user_menu(uid))
        req_col.insert_one({"name": txt, "username": msg.from_user.first_name, "user_id": uid})
        return await msg.reply("✅ So'rov yuborildi! Tez orada bazaga qo'shiladi.", reply_markup=user_menu(uid))

    # ─── BROADCAST ───
    if uid in broadcast_wait:
        broadcast_wait.discard(uid)
        if txt == "❌ Bekor qilish":
            return await msg.reply("Bekor qilindi.", reply_markup=admin_menu())
        sent = 0
        for user in users_col.find():
            try:
                await msg.copy(user["user_id"])
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        return await msg.reply(f"✅ Xabar {sent} ta foydalanuvchiga yuborildi.")

    if txt == "🔗 Taklifnoma":
        await send_referral_info(client, msg)
        return

    # ─── ADMIN TUGMALARI ───
    if is_admin(uid):
        if txt == "👤 Admin qo'shish":
            broadcast_wait.add(f"addadmin_{uid}")
            return await msg.reply("➕ Yangi admin ID raqamini yuboring:", reply_markup=cancel_menu())

        if txt == "👤 Admin o'chirish":
            conf = get_config()
            admins = conf.get("admin_ids", [])
            if not admins:
                return await msg.reply("Yordamchi adminlar mavjud emas.")
            res = "👤 <b>O'chirish uchun ID'ni yuboring:</b>\n\n"
            for a in admins:
                res += f"• <code>{a}</code>\n"
            broadcast_wait.add(f"remadmin_{uid}")
            return await msg.reply(res, reply_markup=cancel_menu())

        if txt == "➕ Kanal qo'shish":
            broadcast_wait.add(f"addchan_{uid}")
            return await msg.reply("📢 Kanal ma'lumotlarini yuboring:\n\n`@kanal_username` yoki kanal ID yoki link", reply_markup=cancel_menu())

        elif txt == "➖ Kanal o'chirish":
            conf = get_config()
            chans = conf.get("mandatory_channels", [])
            if not chans:
                return await msg.reply("❌ Hozircha majburiy kanallar yo'q.")
            res = "➖ <b>O'chirish uchun kanal linkini nusxalab yuboring:</b>\n\n"
            for index, c in enumerate(chans, start=1):
                res += f"{index}. <code>{c.get('link', c.get('id'))}</code>\n"
            broadcast_wait.add(f"remchan_{uid}")
            return await msg.reply(res, reply_markup=cancel_menu())

        if txt == "🎬 Kino kanalni sozlash":
            broadcast_wait.add(f"setmoviechan_{uid}")
            return await msg.reply("🎬 Kinolar yuboriladigan kanal ID sini yuboring (Masalan: -100...):", reply_markup=cancel_menu())

        if txt == "👑 Adminlikni o'tkazish" and is_main_admin(uid):
            broadcast_wait.add(f"transfer_{uid}")
            return await msg.reply("⚠️ Yangi Asosiy Admin ID raqamini yuboring:", reply_markup=cancel_menu())

        if txt == "📥 Kelgan So'rovlar":
            reqs = list(req_col.find().limit(5))
            if not reqs:
                return await msg.reply("Hozircha so'rovlar yo'q.")
            for r in reqs:
                tid = r.get('user_id')
                req_name = r.get('name', "Noma'lum foydalanuvchi")
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Topildi", callback_data=f"approve_{tid}_{req_name}"),
                        InlineKeyboardButton("❌ Topilmadi", callback_data=f"notfound_{tid}_{req_name}")
                    ]
                ])
                await msg.reply(f"🎬 <b>So'rov:</b> {req_name}\n👤 Kimdan: {tid}", reply_markup=kb)
            return

        if txt == "🗑 So'rovlarni tozalash":
            confirm_markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Ha, o'chirilsin", callback_data="confirm_clear_requests"),
                    InlineKeyboardButton("❌ Yo'q, bekor qilish", callback_data="cancel_clear_requests")
                ]
            ])
            return await msg.reply(
                "⚠️ <b>DIQQAT!</b>\n\nBarcha kelgan so'rovlarni o'chirib tashlamoqchimisiz?",
                reply_markup=confirm_markup
            )

        if txt == "📢 Xabar yuborish":
            broadcast_wait.add(uid)
            return await msg.reply(
                "✍️ Yuboriladigan xabarni yuboring (rasm, video yoki tekst):",
                reply_markup=cancel_menu()
            )

    # ─── MATN BO'YICHA QIDIRISH ───
    if txt and not txt.isdigit() and len(txt) > 2:
        movies = list(movies_col.find({"title": {"$regex": txt, "$options": "i"}}).limit(5))
        if movies:
            res_text = f"🔍 <b>'{txt}' bo'yicha topilgan kinolar:</b>\n\n"
            for m in movies:
                movie_title = m.get('title', "Noma'lum film").split('\n')[0]
                downloads_count = m.get('downloads', 0)
                movie_code = m.get('code', "Yo'q")
                avg = m.get('avg_rating', 0.0)
                res_text += (
                    f"🎬 <b>{movie_title}</b>\n"
                    f"   📥 {downloads_count} marta | ⭐ {avg:.1f}\n"
                    f"   🔑 <b>Kod:</b> <code>{movie_code}</code>\n\n"
                )
            return await msg.reply(res_text)


# ==========================================
#    WATCHLIST — PLAY VA O'CHIRISH
# ==========================================

@app.on_callback_query(filters.regex(r"^playwl_(\d+)"))
async def play_from_watchlist(client, cb):
    code = int(cb.data.split("_")[1])
    await cb.answer("Kino yuborilmoqda...")
    await handle_movie_delivery(client, cb.from_user.id, code)

@app.on_callback_query(filters.regex(r"^rmwl_(\d+)"))
async def remove_from_watchlist(client, cb):
    code = int(cb.data.split("_")[1])
    uid = cb.from_user.id
    watchlist_col.update_one(
        {"user_id": uid},
        {"$pull": {"movies": {"code": code}}}
    )
    await cb.answer("🗑 Ro'yxatdan o'chirildi!")
    # Ro'yxatni yangilash
    wl = watchlist_col.find_one({"user_id": uid})
    if not wl or not wl.get("movies"):
        return await cb.message.edit_text("🗓 Ko'rmoqchiman ro'yxatingiz bo'sh.")
    res = "🗓 <b>Ko'rmoqchiman ro'yxati:</b>\n\n"
    buttons = []
    for entry in wl.get("movies", []):
        title = entry.get("title", "Noma'lum")
        c = entry.get("code")
        res += f"🎬 {title}\n🔑 Kod: <code>{c}</code>\n\n"
        buttons.append([InlineKeyboardButton(f"▶️ {title[:25]}", callback_data=f"playwl_{c}"),
                         InlineKeyboardButton("🗑", callback_data=f"rmwl_{c}")])
    await cb.message.edit_text(res, reply_markup=InlineKeyboardMarkup(buttons))


# ==========================================
#               REFERAL
# ==========================================

async def send_referral_info(client, msg):
    uid = msg.from_user.id
    bot_obj = await client.get_me()
    bot_username = bot_obj.username
    user_data = users_col.find_one({"user_id": uid})
    referrals_count = user_data.get("referrals", 0) if user_data else 0
    current_limit = referrals_count // 5
    next_limit_step = 5 - (referrals_count % 5)
    ref_link = f"https://t.me/{bot_username}?start={uid}"
    text = (
        f"🎁 <b>DO'STLARINGIZNI TAKLIF QILING VA VIP BO'LING!</b>\n"
        f"______________________________________\n\n"
        f"👤 <b>Sizning holatingiz:</b>\n"
        f"┣ Do'stlar: <code>{referrals_count} ta</code>\n"
        f"┣ Kunlik limit: <b>{current_limit} ta kino</b>\n"
        f"┗ Keyingi limitga: <code>{next_limit_step} ta</code> do'st qoldi\n\n"
        f"💎 <b>VIP Tizimi qanday ishlaydi?</b>\n"
        f"• 5 ta do'st = Kuniga <b>1 ta</b> kino so'rash\n"
        f"• 10 ta do'st = Kuniga <b>2 ta</b> kino so'rash\n"
        f"• Har 5 ta do'st uchun limit <b>+1</b> ga oshadi!\n\n"
        f"🔗 <b>Sizning maxsus havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>Havolani do'stlaringizga yuboring! 🚀</i>"
    )
    share_url = f"https://t.me/share/url?url={ref_link}"
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Ulashish (Share)", url=share_url)]
    ])
    await msg.reply(text, reply_markup=reply_markup, disable_web_page_preview=True)


# ==========================================
#            LEADERBOARD
# ==========================================

async def get_leaderboard_text():
    top_users = list(users_col.find({"referrals": {"$gte": 5}}).sort("referrals", -1).limit(10))
    text = "🏆 <b>HAFTALIK TOP 10 REYTING</b>\n"
    text += "______________________________________\n\n"
    if not top_users:
        text += "😔 Hozircha VIP talablariga mos (5+ do'st) userlar yo'q.\n"
    else:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for i, u in enumerate(top_users):
            name = u.get("first_name", "Foydalanuvchi")
            count = u.get("referrals", 0)
            status = " ✨" if u.get("is_vip") else ""
            text += f"{medals[i]} {name[:15]}{status} — <b>{count} ta</b>\n"
    text += "\n______________________________________\n"
    text += "🎁 <b>VIP Imtiyozlari:</b>\n"
    text += "✅ Majburiy obunalarsiz foydalanish\n"
    text += "✅ 1 hafta davomida amal qiladi\n\n"
    text += "⏰ <i>Har yakshanba soat 20:00 da yangilanadi.</i>"
    return text


# ==========================================
#                RUN BOT
# ==========================================

async def run():
    scheduler.start()
    scheduler.add_job(
        send_weekly_highlights,
        "cron",
        day_of_week="sun",
        hour=20,
        minute=0
    )
    await app.start()
    print("✅ Bot muvaffaqiyatli ishga tushdi!")
    await idle()

if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    app.run(run())
