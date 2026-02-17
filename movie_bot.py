import asyncio
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote
from pyrogram.enums import ChatMemberStatus
from pyrogram import Client, filters, idle
from pyrogram.errors import MessageNotModified, UserNotParticipant, ChatAdminRequired
from pyrogram.errors import FloodWait
from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton
)
from pymongo import MongoClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==========================================
#                  CONFIG
# ==========================================
API_ID = 38119035
API_HASH = "0f84597433eacb749fd482ad238a104e"
BOT_TOKEN = "8371879333:AAFVl-wjRT0SlFo563CR9SpI3Ml8lb_Y2Qo"
MONGO_URL = "mongodb+srv://moviebot:ATQmOjn0TCdyKtTM@cluster0.xvvfs8t.mongodb.net/?appName=Cluster0"

UZ_TZ = ZoneInfo("Asia/Tashkent")
SAVED_MOVIE = -1003797574060
# version 8 correct.txt fayliga qo'shimcha
KINO1CHRA_CHANNEL = -1003897814741
MAIN_CHANNEL = "@KinoDrift"
SAVE_SHORTS = -1003822143783

# BOTDA MAVJUD BO'LISHI KERAK BO'LGAN 11 TA JANR
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
settings_col = db.settings  # Yangi sozlamalar kolleksiyasi
requests_col = db.requests    # So'rovlar (Kelgan buyurtmalar) uchun

app = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
broadcast_wait = set()
pending_broadcasts = {}
request_wait = set()
approve_wait = {} 


def is_admin(uid):
    conf = get_config() # Har safar bazadan yangi adminlar ro'yxatini oladi
    main_admin = conf.get("main_admin")
    admin_ids = conf.get("admin_ids", [])
    
    # Agar main_admin ro'yxat bo'lsa (sizda [5014031582] ko'rinishida saqlangan)
    if isinstance(main_admin, list):
        return uid in main_admin or uid in admin_ids
    return uid == main_admin or uid in admin_ids

def is_main_admin(uid):
    """Faqat asosiy adminni tekshirish (Admin o'tkazish huquqiga ega bo'lgan shaxs)"""
    conf = get_config()
    main_admin = conf.get("main_admin")
    
    # Agar main_admin bazada list bo'lsa [5014031582]
    if isinstance(main_admin, list):
        return uid in main_admin
    # Agar main_admin bazada bitta raqam bo'lsa 5014031582
    return uid == main_admin

# Vaqtinchalik xabarni saqlash uchun
pending_broadcasts = {}

def get_bot_config():
    """Bazadan sozlamalarni yuklash, agar bo'sh bo'lsa standartlarini yaratish"""
    config = settings_col.find_one({"id": "main_config"})
    if not config:
        # Baza bo'sh bo'lgan birinchi holatda yaratiladigan qiymatlar
        default_data = {
            "id": "main_config",
            "bot_token": "TOKENDINGIZNI_YORDAMCHI_SIFATIDA_YOZING",
            "admin_ids": [123456789, 987654321], # Adminlar
            "mandatory_channels": ["@kanal1", "@kanal2"], # Kanallar
        }
        settings_col.insert_one(default_data)
        return default_data
    return config

# ==========================================
#           CHANNEL CONFIG
# ==========================================

config = get_bot_config()


# ==========================================
#               KEYBOARDS
# ==========================================

def user_menu(user_id):
    buttons = [
        [KeyboardButton("📂 Barcha Kinolar"), KeyboardButton("🎭 Janrlar")],
        [KeyboardButton("📈 Top Kinolar"), KeyboardButton("📥 Kino so'rash")],
        [KeyboardButton("⭐ Sevimlilar"), KeyboardButton("📊 Statistika")],
        [KeyboardButton("🔗 Taklifnoma"), KeyboardButton("🏆 Leaderboard")],
        [KeyboardButton("📢 Reklama")]
    ]
    if is_admin(user_id): 
        buttons.append([KeyboardButton("⚙️ Admin Menu")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def genres_keyboard():
    """11 ta janrni klaviaturada chiroyli chiqarish"""
    buttons = []
    for i in range(0, len(ALLOWED_GENRES), 2):
        row = [KeyboardButton(f"📁 {g.capitalize()}") for g in ALLOWED_GENRES[i:i+2]]
        buttons.append(row)
    buttons.append([KeyboardButton("⬅️ Orqaga")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def movie_extra_kb(code, is_admin=False, insta_link=None):
    buttons = [
        [
            InlineKeyboardButton("⭐ 1", callback_data=f"rate_{code}_1"),
            InlineKeyboardButton("⭐ 2", callback_data=f"rate_{code}_2"),
            InlineKeyboardButton("⭐ 3", callback_data=f"rate_{code}_3"),
            InlineKeyboardButton("⭐ 4", callback_data=f"rate_{code}_4"),
            InlineKeyboardButton("⭐ 5", callback_data=f"rate_{code}_5")
        ]
    ]
    
    # Agar Instagram link bo'lsa, uni Sevimlilardan tepaga qo'shamiz
    if insta_link:
        buttons.append([InlineKeyboardButton("🎬 Kinodan parcha (Video)", url=insta_link)])
        
    buttons.append([InlineKeyboardButton("⭐ Sevimlilarga saqlash", callback_data=f"fav_{code}")])
    
    if is_admin:
        buttons.append([InlineKeyboardButton("🗑 O'chirish (Admin)", callback_data=f"rm_{code}")])
    return InlineKeyboardMarkup(buttons)


def admin_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Admin Panel"), KeyboardButton("📢 Xabar yuborish")],
        [KeyboardButton("👤 Admin qo'shish"), KeyboardButton("👤 Admin o'chirish")],
        [KeyboardButton("➕ Kanal qo'shish"), KeyboardButton("➖ Kanal o'chirish")],
        [KeyboardButton("🎬 Kino kanalni sozlash"), KeyboardButton("👑 Adminlikni o'tkazish")],
        [KeyboardButton("📥 Kelgan So'rovlar"), KeyboardButton("🗑 So'rovlarni tozalash")],
        [KeyboardButton("👤 User Menu ga qaytish")]
    ], resize_keyboard=True)

def cancel_menu():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Bekor qilish")]], resize_keyboard=True)


# ==========================================
#                SETTINGS
# ==========================================


def get_config():
    """
    MongoDB dan bot sozlamalarini yuklash.
    Agar baza bo'sh bo'lsa, 5014031582 ID-sini asosiy admin sifatida saqlaydi.
    """
    config = db.settings.find_one({"type": "bot_config"})
    if not config:
        # Baza birinchi marta ishga tushganda yaratiladigan ma'lumotlar
        default_data = {
            "type": "bot_config",
            "mandatory_channels": [
                {"id": "@TG_Manager_uz", "name": "✨ TG Manager Uz", "link": "https://t.me/TG_Manager_uz"},
                {"id": "@hshhshshshdgegeuejje", "name": "🎬 Zayafka Kanali", "link": "https://t.me/hshhshshshdgegeuejje"}
            ],
            "main_admin": 5014031582, # Siz aytgan boshlang'ich ID
            "admin_ids": [] # Yordamchi adminlar hozircha bo'sh
        }
        db.settings.insert_one(default_data)
        return default_data
    return config

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

    # 1. Admin va VIP bo'lsa tekshirib o'tirmaymiz [cite: 86, 87]
    if is_admin(uid):
        return True
        
    user_db_data = users_col.find_one({"user_id": uid})
    if user_db_data and user_db_data.get("is_vip", False):
        return True

    # 2. Sozlamalarni yuklaymiz (settings kolleksiyasidan) [cite: 87]
    conf = get_config()
    channels = conf.get("mandatory_channels", [])
    
    unsubscribed = []

    # 3. Obunani tekshirish
    for chan in channels:
        try:
            chat_id = chan["id"]

            try:
                chat = await client.get_chat(chat_id)
                print("CHAT TOPILDI:", chat.title)
            except Exception as e:
                print("CHAT ERROR:", chat_id, e)

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
            print("FORCE JOIN ERROR:", chan["id"], e)
            unsubscribed.append(chan)

    # 4. Agar obuna bo'lmagan bo'lsa tugmalarni chiqarish
    if unsubscribed:
        buttons = []
        for index, ch in enumerate(unsubscribed, start=1):
            # DIQQAT: Faylingizda 'link' deb saqlangan, 'invite_link' emas! [cite: 90]
            link = ch.get('link') 
            buttons.append([InlineKeyboardButton(text=f"➕ {index}-kanal", url=link)])
        
        # Tasdiqlash tugmasiga deep link parametrini qo'shish
        # check_force_join funksiyasi ichida (90-91 qatorlar atrofida)
        start_param = msg.command[1] if hasattr(msg, "command") and len(msg.command) > 1 else "start"
        me = await client.get_me()
        # Agar parametr bo'lmasa, shunchaki ?start=start qilib yuboramiz
        join_url = f"https://t.me/{me.username}?start={start_param}"
        buttons.append([InlineKeyboardButton(text="✅ Tasdiqlash", url=join_url)])
        
        text = "<b>👋 Assalomu alaykum!</b>\n\nBotdan foydalanish uchun homiy kanallarga a'zo bo'ling:"
        
        # Xabarni yuborish yoki tahrirlash
        if hasattr(msg, "data"): # Agar callback bo'lsa
            await msg.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await msg.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
        
        return False

    return True

def get_movie_list(page=1, genre=None):
    """Faqat birinchi qator va kodni ko'rsatish mantiqi"""
    items_per_page = 10
    query = {"genres": genre} if genre else {}
    total_movies = movies_col.count_documents(query)
    
    if total_movies == 0:
        return "😔 Hozircha bazada kinolar yo'q.", None
    
    total_pages = math.ceil(total_movies / items_per_page)
    movies = list(movies_col.find(query).skip((page - 1) * items_per_page).limit(items_per_page))
    
    text = f"🎬 <b>Kinolar ro'yxati:</b>\n"
    if genre:
        text += f"📂 Janr: #{genre}\n"
    text += "─────────────────\n\n"
    
    for m in movies:
        # RASMDA KO'RSATILGANDEK: Birinchi qatorni ajratish
        title_line = m['title'].split('\n')[0]
        text += f"🎬 {title_line}\n🔑 FILM KODI: <code>{m['code']}</code>\n\n"
        
    buttons = []
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}_{genre or ''}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}_{genre or ''}"))
    buttons.append(nav_row)
    
    return text, InlineKeyboardMarkup(buttons)


# ==========================================
#          WEEKLY MAINTENANCE FUNCTIONS
# ==========================================

async def update_weekly_vip_winners():
    """VIP g'oliblarni yangilash va xabardor qilish"""
    print("Haftalik VIP yangilanishi boshlandi...")
    
    # 1. Eski VIP-larni aniqlash (Adminlar emas)
    old_vips = [u["user_id"] for u in users_col.find({"is_vip": True, "user_id": {"$nin": is_admin(u_id)}})]
    
    # 2. Hammani VIP-dan tushirish
    users_col.update_many({"user_id": {"$nin": is_admin(u_id)}}, {"$set": {"is_vip": False}})
    
    # 3. Yangi TOP 10 ni topish (kamida 5 ta referal)
    new_top_10 = list(users_col.find({"referrals": {"$gte": 5}}).sort("referrals", -1).limit(10))
    new_vip_ids = [u["user_id"] for u in new_top_10]
    
    # 4. Yangi g'oliblarni VIP qilish va tabriklash
    for user in new_top_10:
        u_id = user["user_id"]
        users_col.update_one({"user_id": u_id}, {"$set": {"is_vip": True}})
        try:
            await app.send_message(
                u_id, 
                "🎉 <b>TABRIKLAYMIZ!</b>\n\nSiz haftalik TOP 10 talikka kirdingiz va <b>VIP status</b> oldingiz! "
                "1 hafta davomida majburiy obunalarsiz botdan foydalana olasiz. 💪"
            )
        except: continue

    # 5. Ro'yxatdan tushganlarga xabar yuborish
    # MUHIM: old_vip_ids o'rniga yuqoridagi ro'yxat nomini (old_vips) ishlating
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
    """Haftaning eng mashhur kinolarini yuborish"""
    print("Haftalik tavsiyanoma yuborilmoqda...")
    
    top_3 = list(movies_col.find().sort([("weekly_downloads", -1), ("avg_rating", -1)]).limit(3))
    if not top_3: return

    text = "🌟 <b>HAFTA TAVSIYASI</b>\n______________________________________\n\n"
    text += "🔥 Ushbu haftaning eng mashhur kinolari:\n\n"
    for i, m in enumerate(top_3, 1):
        # Nomi split qilinishini f-stringdan tashqariga chiqaramiz
        movie_title = m['title'].split('\n')[0] 
        text += f"{i}. 🎬 <b>{movie_title}</b>\n🔑 Kod: <code>{m['code']}</code>\n\n"
    text += "🍿 <i>Kino kodini botga yuboring!</i>"

    # Hamma foydalanuvchilarga tarqatish
    async for user in users_col.find():
        try:
            await app.send_message(user["user_id"], text)
            await asyncio.sleep(0.05)
        except: continue

    # Haftalik yuklashlar sonini nolga tushirish
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


# --- MAJBURIY OBUNA FUNKSIYALARI ---

# ==========================================
#      YAGONA MAJBURIY OBUNA TIZIMI
# ==========================================


async def handle_movie_delivery(client, user_id, movie_code):
    """Kinoni qidirish va yuborish (Tugmalar bilan)"""
    movie = movies_col.find_one({
        "$or": [
            {"code": movie_code},
            {"code": int(movie_code) if str(movie_code).isdigit() else None}
        ]
    })
    
    if movie:
        # Tugmalarni yasash (Insta link bo'lsa parcha tugmasi ham chiqadi)
        kb = movie_extra_kb(
            code=movie['code'], 
            is_admin=is_admin(user_id), 
            insta_link=movie.get('insta_link')
        )
        
        await client.send_video(
            chat_id=user_id,
            video=movie['file_id'],
            caption=f"🎬 <b>{movie['title']}</b>\n\n🔑 Kod: <code>{movie['code']}</code>",
            reply_markup=kb # Tugmalar shu yerda qo'shiladi
        )
        movies_col.update_one({"_id": movie["_id"]}, {"$inc": {"downloads": 1}})
        return True
    return False

# ==========================================
#               INSTAGRAM LINK
# ==========================================


@app.on_message(filters.text & filters.chat(SAVED_MOVIE))
async def save_insta_link(client, msg):
    # Agar xabar biror videoga reply qilib yozilgan bo'lsa
    if msg.reply_to_message and msg.reply_to_message.video:
        link = msg.text
        if "instagram.com" in link:
            # O'sha videoning file_id si orqali bazadan topamiz
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

@app.on_message(filters.command("start") & filters.private)
async def start(client, msg):
    user = msg.from_user
    user_id = user.id

    # 1. Bazadan tekshirish yoki yaratish
    user_data = users_col.find_one({"user_id": user_id})
    
    if not user_data:
        # Yangi foydalanuvchini vaqtincha saqlaymiz (hali ball bermaymiz)
        users_col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "first_name": user.first_name,
                    "username": user.username,
                    "is_counted": False, # Ball hali berilmagan
                    "referrals": 0
                },
                "$setOnInsert": {"joined_at": datetime.utcnow()}
            },
            upsert=True
        )
        user_data = {"is_counted": False}

    is_subscribed = await check_force_join(client, msg)

    # 2. Majburiy obuna (Yuqoridagi yangi funksiya)
    if not await check_force_join(client, msg):
        return 
    
    if is_subscribed:
        try:
            # Bot yuborgan oxirgi xabarni (obuna talabini) o'chiradi
            await client.delete_messages(msg.chat.id, msg.id - 1)
        except:
            pass

    # 3. Agar obunadan o'tgan bo'lsa va hali ball berilmagan bo'lsa
    if user_data.get("is_counted") == False and len(msg.command) > 1:
        ref_id_str = msg.command[1]
        if ref_id_str.isdigit():
            ref_id = int(ref_id_str)
            if ref_id != user_id:
                # Referalga ball berish
                users_col.update_one({"user_id": ref_id}, {"$inc": {"referrals": 1}})
                # Bu foydalanuvchini "hisoblandi" deb belgilash
                users_col.update_one({"user_id": user_id}, {"$set": {"is_counted": True}})
                try:
                    await client.send_message(ref_id, "🎉 Do'stingiz obuna bo'ldi! +1 ball.")
                except: pass

    # 4. Kino kodi yoki oddiy salomlashish (Davomi...)
    if len(msg.command) > 1:
        # Kino kodini tekshirish
        if await handle_movie_delivery(client, user_id, msg.command[1]):
            return

    await msg.reply(f"Assalomu alaykum {user.first_name}!", reply_markup=user_menu(user_id))

# 1. Kanalga video tashlanganda
@app.on_message(filters.chat(KINO1CHRA_CHANNEL) & (filters.video | filters.document))
async def on_movie_upload(client, msg):
    await msg.reply_text(
        f"✅ <b>Kino yuklandi!</b> (ID: {msg.id})\n\n"
        "Endi ushbu xabarga <b>Reply</b> qilib, foydalanuvchi ID-sini yuboring."
    )

# 2. Admin ID yozib reply qilganda
@app.on_message(filters.chat(KINO1CHRA_CHANNEL) & filters.reply)
async def handle_admin_id_reply(client, msg):
    # Agar xabar faqat raqamlardan iborat bo'lsa
    if msg.text and msg.text.strip().isdigit():
        user_id = int(msg.text.strip())
        
        # Kinoning asl xabar ID-sini aniqlash
        # msg.reply_to_message - bu botning "Kino yuklandi" degan xabari
        # msg.reply_to_message.reply_to_message_id - bu haqiqiy kinoning ID-si
        
        movie_id = None
        if msg.reply_to_message.reply_to_message:
            movie_id = msg.reply_to_message.reply_to_message.id
        elif msg.reply_to_message.video or msg.reply_to_message.document:
            movie_id = msg.reply_to_message.id

        if movie_id:
            # Callback_data ichiga foydalanuvchi ID va kino ID joylanadi
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
            await msg.reply_text("❌ Xato: Kino xabarini topa olmadim. Iltimos, botning xabariga reply qilib ID yuboring.")

# 3. Tugma bosilganda ishlash
@app.on_callback_query(filters.regex(r"^sendv_(\d+)_(\d+)"))
async def send_movie_final(client, cb):
    data = cb.data.split("_")
    user_id = int(data[1])
    movie_id = int(data[2])
    
    try:
        # Kinoni kanal ID va xabar ID orqali to'g'ridan-to'g'ri nusxalash
        await client.copy_message(
            chat_id=user_id,
            from_chat_id=KINO1CHRA_CHANNEL,
            message_id=movie_id
        )
        
        # Foydalanuvchiga xabar
        await client.send_message(
            chat_id=user_id,
            text="🎬 <b>Siz so'ragan kinoyingiz botimizga yuklandi!</b>\n\nMarhamat, tomosha qilishingiz mumkin."
        )
        
        await cb.message.edit_text(f"✅ Muvaffaqiyatli yuborildi!\n👤 Foydalanuvchi: {user_id}")
        await cb.answer("Yuborildi!", show_alert=True)

    except Exception as e:
        await cb.answer(f"Xatolik: {str(e)}", show_alert=True)

@app.on_callback_query(filters.regex("check"))
async def check_callback(client, query):
    code = query.data.split("_")[1]
    
    if await check_force_join(client, query):
        # Agar a'zo bo'lsa, ogohlantirishni o'chiramiz
        await query.message.delete()
        
        # Foydalanuvchini botga xush kelibsiz deymiz
        uid = query.from_user.id
        if code != "none":
            # Agar kino kodi bo'lsa, o'sha kinoni yuboramiz
            await handle_movie_delivery(client, uid, code)
        else:
            # Oddiy /start bo'lsa, menyuni yuboramiz
            await client.send_message(
                uid, 
                f"✅ Obuna tasdiqlandi! Xush kelibsiz.",
                reply_markup=user_menu(uid)
            )

# ==========================================
#               HANDLERS
# ==========================================

@app.on_callback_query(filters.regex("^check_"))
async def check_callback(client, query):
    code = query.data.split("_")[1]
    
    if await check_force_join(client, query):
        # Agar a'zo bo'lsa, ogohlantirishni o'chiramiz
        await query.message.delete()
        
        # Foydalanuvchini botga xush kelibsiz deymiz
        uid = query.from_user.id
        if code != "none":
            # Agar kino kodi bo'lsa, o'sha kinoni yuboramiz
            await handle_movie_delivery(client, uid, code)
        else:
            # Oddiy /start bo'lsa, menyuni yuboramiz
            await client.send_message(
                uid, 
                f"✅ Obuna tasdiqlandi! Xush kelibsiz.",
                reply_markup=user_menu(uid)
            )

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
    await cb.message.edit_text(t, reply_markup=m)

@app.on_callback_query(filters.regex(r"^found_(\d+)"))
async def movie_found_callback(client, cb):
    user_id = int(cb.data.split("_")[1])
    
    # 1. Admin reply qilgan original xabarni (kinoni) topamiz
    # cb.message - "Foydalanuvchi ID..." xabari
    # cb.message.reply_to_message - Admin yozgan ID xabari
    # cb.message.reply_to_message.reply_to_message - Haqiqiy kino (Video/Fayl)
    
    try:
        admin_id_msg = cb.message.reply_to_message
        movie_msg = admin_id_msg.reply_to_message
        
        if movie_msg:
            # Kinoni faqat so'ragan foydalanuvchiga yuborish
            await movie_msg.copy(chat_id=user_id)
            
            # Xabar yuborish
            await client.send_message(
                chat_id=user_id,
                text="✅ <b>Siz so'ragan kinoyingiz botimizga yuklandi!</b>"
            )
            
            await cb.message.edit_text(f"✅ Kino {user_id} ga yuborildi va foydalanuvchi ogohlantirildi.")
        else:
            await cb.answer("Xato: Kino fayli topilmadi!", show_alert=True)
            
    except Exception as e:
        await cb.answer(f"Xatolik: {str(e)}", show_alert=True)

@app.on_callback_query(filters.regex(r"^star_(\d+)_(\d+)"))
async def handle_star_rating(client, cb):
    # Callback ma'lumotlarini ajratib olish
    _, stars, code = cb.data.split("_")
    stars = int(stars)
    code = int(code)
    
    movie = movies_col.find_one({"code": code})
    if not movie:
        return await cb.answer("Kino topilmadi!", show_alert=True)

    # Yangi reytingni hisoblash
    new_votes = movie.get("votes_count", 0) + 1
    new_total = movie.get("total_stars", 0) + stars
    new_avg = round(new_total / new_votes, 1)

    # Bazani yangilash
    movies_col.update_one(
        {"code": code},
        {"$set": {"votes_count": new_votes, "total_stars": new_total, "rating": new_avg}}
    )

    # Xabar matnini yangilash
    current_caption = cb.message.caption if cb.message.caption else cb.message.text
    # Oxirgi qatorni (reyting qatorini) yangisiga almashtirish
    lines = current_caption.split('\n')
    if "📊 Reyting:" in lines[-1]:
        lines[-1] = f"📊 <b>Reyting:</b> {new_avg} ({new_votes} ta ovoz)"
    else:
        lines.append(f"📊 <b>Reyting:</b> {new_avg} ({new_votes} ta ovoz)")
    
    updated_text = "\n".join(lines)

    try:
        await cb.edit_message_text(updated_text, reply_markup=cb.message.reply_markup)
        await cb.answer(f"Siz {stars} yulduz berdingiz!")
    except Exception:
        # Agar matn rasm/video caption bo'lsa edit_message_caption ishlatish kerak
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

@app.on_callback_query(filters.regex("^rm_"))
async def rm_cb(client, cb):
    # Foydalanuvchi admin ekanligini tekshirish
    if is_admin(cb.from_user.id):
        try:
            # Kodni ajratib olish va o'chirish
            code_str = cb.data.split("_")[1]
            code = int(code_str) if code_str.isdigit() else code_str
            
            result = movies_col.delete_one({"code": code})
            
            if result.deleted_count > 0:
                await cb.message.edit_text(f"🗑 Kino (Kod: {code}) bazadan muvaffaqiyatli o'chirildi.")
            else:
                await cb.answer("❌ Bu kodli kino bazada topilmadi.", show_alert=True)
                
        except Exception as e:
            await cb.answer(f"❌ Xatolik yuz berdi: {e}", show_alert=True)
    else:
        await cb.answer("🚫 Bu amal faqat adminlar uchun!", show_alert=True)

@app.on_callback_query(filters.regex("^approve_"))
async def approve_cb(client, cb):
    if is_admin(cb.from_user.id):
        data = cb.data.split("_")
        uid, req_name = int(data[1]), "_".join(data[2:])
        
        try:
            
            # So'rovni o'chirish
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
            # Limitni qaytarish (referral +1)
            users_col.update_one({"user_id": uid}, {"$inc": {"referrals": 1}})
            
            # Userga xabar
            await client.send_message(
                chat_id=uid,
                text=f"😔 <b>Uzur, siz so'ragan '{req_name}' kinosini topa olmadik.</b>\n\n"
                     f"Sizga boshqa kino so'rash uchun qaytadan imkoniyat berildi. "
                     f"Bemalol boshqa film so'rashingiz mumkin! 🚀"
            )
            # So'rovni o'chirish
            req_col.delete_one({"user_id": uid, "name": req_name})
            await cb.message.edit_text(f"❌ '{req_name}' topilmadi. Limit qaytarildi.")
            
        except Exception as e:
            await cb.answer(f"Xato: {e}", show_alert=True)
            

@app.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    uid = callback_query.from_user.id

    if not is_admin(uid):
        return await callback_query.answer("Siz admin emassiz!", show_alert=True)

    if data == "confirm_clear_requests":
        # Bazadagi barcha so'rovlarni (requests) o'chirish
        # Eslatma: requests_col bu sizning so'rovlar saqlanadigan kolleksiyangiz nomi
        requests_col.delete_many({}) 
        
        await callback_query.message.edit_text("✅ Barcha so'rovlar muvaffaqiyatli tozalandi!")
        await callback_query.answer("Tozalandi", show_alert=False)

    elif data == "cancel_clear_requests":
        await callback_query.message.edit_text("❌ Tozalash amali bekor qilindi.")
        await callback_query.answer("Bekor qilindi")

# ==========================================
#                BOT HANDLERS
# ==========================================

# ⬇️ YANGI FUNKSIYANI SHU YERGA QO'YING ⬇️
@app.on_message(filters.chat(SAVE_SHORTS) & filters.reply, group=-1)
async def handle_shorts_processing(client, msg):
    if not msg.reply_to_message.video:
        return

    import re
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
        f"🎬 <b>{movie['title']}</b>\n\n"
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
        await msg.reply("✅ Private kanalga muvaffaqiyatli yuborildi!")
    except Exception as e:
        await msg.reply(f"❌ Xatolik turi: {type(e).__name__}\nHabar: {e}")      

@app.on_message((filters.text | filters.video | filters.photo) & filters.private)
async def handle_text(client, msg):
    
    if not msg.from_user:
        return

    uid = msg.from_user.id
    txt = msg.text

    user_state = next((s for s in broadcast_wait if isinstance(s, str) and s.endswith(f"_{uid}")), None)
    if user_state:
    
        if broadcast_wait:
            # broadcast_wait ichida aynan shu user bormi yoki yo'qligini tekshirish xavfsizroq
            # Biz sizning kodingizdagi "state" mantiqini user ID bilan tekshiramiz:
            user_state = next((s for s in broadcast_wait if isinstance(s, str) and s.endswith(f"_{uid}")), None)
            
        if user_state:
            if txt == "❌ Bekor qilish":
                broadcast_wait.remove(user_state)
                return await msg.reply("Bekor qilindi.", reply_markup=admin_menu())


            if user_state.startswith("remadmin_"):
                broadcast_wait.remove(user_state)
                try:
                    rem_id = int(txt)
                    # Bazadagi admin_ids ro'yxatidan ushbu IDni o'chiramiz ($pull)
                    result = db.settings.update_one(
                        {"type": "bot_config"}, 
                        {"$pull": {"admin_ids": rem_id}}
                    )
                    
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
                    # --- KANALNI ANIQLASH QISMI (4 TA USUL) ---
                    
                    # 1-USUL: Kanal ID-si orqali (-100123456789)
                    if txt_input.startswith("-100"):
                        chat = await client.get_chat(txt_input)
                        ch_id = chat.id
                        title = chat.title
                        link = chat.invite_link or f"https://t.me/c/{str(ch_id)[4:]}/1"

                    # 2-USUL: Username orqali (@KanalNomi)
                    elif txt_input.startswith("@"):
                        chat = await client.get_chat(txt_input)
                        ch_id = chat.id
                        title = chat.title
                        link = f"https://t.me/{txt_input[1:]}"

                    # 3-USUL: Public Link orqali (https://t.me/KanalNomi)
                    elif "t.me/" in txt_input and not "+" in txt_input and "/joinchat/" not in txt_input:
                        # Username-ni linkdan ajratib olish
                        path = txt_input.split("t.me/")[1].split("/")[0]
                        chat = await client.get_chat(f"@{path}")
                        ch_id = chat.id
                        title = chat.title
                        link = txt_input

                    # 4-USUL: Private Link orqali (https://t.me/+abc... yoki /joinchat/...)
                    elif "t.me/+" in txt_input or "joinchat" in txt_input:
                        chat = await client.get_chat(txt_input)
                        ch_id = chat.id
                        title = chat.title
                        link = txt_input

                    else:
                        # Hech qaysi formatga tushmasa, state-ni o'chirmasdan xato qaytaramiz
                        return await msg.reply(
                            "❌ **Noto'g'ri format!**\n\nIltimos, ID, Username yoki Link yuboring.\n"
                            "Misol: `-100...`, `@username`, `https://t.me/...`",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_action")
                            ]])
                        )

                except Exception as e:
                    # Xatolik bo'lsa, state o'chmaydi (return ishlaydi), admin qayta urinishi mumkin
                    return await msg.reply(
                        f"❌ **Bot kanalni topa olmadi!**\n\n"
                        f"**Sababi:** Bot kanalda admin emas yoki ma'lumot noto'g'ri.\n"
                        f"**Xatolik:** `{e}`\n\n"
                        "To'g'rilab qaytadan yuboring yoki bekor qiling:",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_action")
                        ]])
                    )

                # --- BAZAGA SAQLASH QISMI ---
                if ch_id and link:
                    new_ch = {
                        "id": str(ch_id), 
                        "link": link, 
                        "title": title or "Nomsiz kanal"
                    }
                    
                    db.settings.update_one(
                        {"type": "bot_config"}, 
                        {"$addToSet": {"mandatory_channels": new_ch}},
                        upsert=True
                    )
                    
                    # FAQAT muvaffaqiyatli yakunlangandagina state-ni o'chiramiz
                    if user_state in broadcast_wait:
                        broadcast_wait.remove(user_state)
                    
                    return await msg.reply(
                        f"✅ **Kanal muvaffaqiyatli qo'shildi!**\n\n"
                        f"📢 Nomi: {title}\n"
                        f"🆔 ID: <code>{ch_id}</code>\n"
                        f"🔗 Link: {link}", 
                        reply_markup=admin_menu()
                    )

            elif user_state.startswith("remchan_"):
                ch_id_input = txt.strip()
                
                # 1. Bazadan config-ni olamiz
                conf = db.settings.find_one({"type": "bot_config"})
                if not conf:
                    return await msg.reply("❌ Sozlamalar topilmadi!")

                channels = conf.get("mandatory_channels", [])
                
                # 2. Kanalni qidirish (ID ni ham string, ham int holatida tekshiramiz)
                target_channel = None
                for c in channels:
                    # Har ikkala tomonni string-ga o'tkazib solishtirish eng xavfsiz yo'l
                    if str(c.get('id')) == str(ch_id_input):
                        target_channel = c
                        break

                if target_channel:
                    # 3. Bazadan o'chirish
                    # MongoDB-da ham string, ham int bo'lishi mumkinligini hisobga olamiz
                    db.settings.update_one(
                        {"type": "bot_config"},
                        {
                            "$pull": {
                                "mandatory_channels": {
                                    # Bu yerda aynan o'sha ob'ektni o'chiramiz
                                    "id": target_channel['id'] 
                                }
                            }
                        }
                    )
                    
                    # State-ni tozalash
                    if user_state in broadcast_wait:
                        broadcast_wait.remove(user_state)
                        
                    return await msg.reply(
                        f"🗑 **Kanal muvaffaqiyatli o'chirildi!**\n\n"
                        f"🆔 ID: <code>{target_channel['id']}</code>\n"
                        f"🔗 Link: {target_channel.get('link', 'Mavjud emas')}",
                        reply_markup=admin_menu()
                    )
                else:
                    # Topilmasa, ro'yxatni ko'rsatish foydali bo'ladi
                    available_ids = ", ".join([f"<code>{c.get('id')}</code>" for c in channels])
                    return await msg.reply(
                        f"❌ **Bunday ID dagi kanal topilmadi!**\n\n"
                        f"Mavjud ID lar: {available_ids}\n\n"
                        "Iltimos, ID ni aniq ko'chirib yuboring:",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_action")
                        ]])
                    )
                
            elif user_state.startswith("setmoviechan_"):
                broadcast_wait.remove(user_state)
                link = txt.strip()
                
                # Linkdan ID yoki Username ajratish
                if link.startswith("-100"):
                    movie_ch = int(link)
                elif link.startswith("@"):
                    movie_ch = link
                elif "t.me/" in link:
                    # t.me/username yoki t.me/c/12345/678 linklaridan ID/Username olish
                    part = link.split("t.me/")[1].split("/")[0]
                    movie_ch = f"@{part}" if not part.startswith("+") else link
                else:
                    return await msg.reply("❌ Noto'g'ri format! @username yoki kanal ID yuboring.")

                db.settings.update_one({"type": "bot_config"}, {"$set": {"movie_channel": movie_ch}})
                return await msg.reply(f"✅ Kino kanali yangilandi: <code>{movie_ch}</code>", reply_markup=admin_menu())

            if user_state.startswith("addadmin_"):
                broadcast_wait.remove(user_state)
                try:
                    new_id = int(txt)
                    
                    # 1. Bazaga yordamchi admin sifatida qo'shish
                    db.settings.update_one(
                        {"type": "bot_config"}, 
                        {"$addToSet": {"admin_ids": new_id}}
                    )

                    # 2. YANGI YORDAMCHI ADMINGA XABAR YUBORISH
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
                            reply_markup=admin_menu() # Unga admin panel klaviaturasini yuboramiz
                        )
                    except Exception as e:
                        print(f"Yordamchi adminga xabar yuborib bo'lmadi: {e}")

                    # 3. ASOSIY ADMINGA TASDIQ
                    return await msg.reply(
                        f"✅ <code>{new_id}</code> yordamchi adminlar ro'yxatiga qo'shildi va xabardor qilindi.", 
                        reply_markup=admin_menu()
                    )
                except ValueError:
                    return await msg.reply("❌ Xato! Faqat ID raqam yuboring.")

            elif user_state.startswith("transfer_"):
                broadcast_wait.remove(user_state)
                try:
                    new_main_id = int(txt)
                    
                    # 1. Bazada asosiy adminni yangilash
                    db.settings.update_one(
                        {"type": "bot_config"}, 
                        {"$set": {"main_admin": new_main_id}}
                    )
                    
                    # 2. Yangi adminni yordamchilar ro'yxatidan o'chirish (agar u yerda bo'lsa)
                    db.settings.update_one(
                        {"type": "bot_config"}, 
                        {"$pull": {"admin_ids": new_main_id}}
                    )

                    # 3. YANGI ADMINGA XABAR YUBORISH
                    try:
                        await client.send_message(
                            chat_id=new_main_id,
                            text=(
                                "👑 <b>Tabriklaymiz!</b>\n\n"
                                "Siz ushbu botning <b>Asosiy Admini</b> etib tayinlandingiz. "
                                "Endi barcha sozlamalarni boshqarish huquqi sizda.\n\n"
                                "👉 /start tugmasini bosing."
                            ),
                            reply_markup=admin_menu() # Unga darhol admin menyusini yuboramiz
                        )
                    except Exception as e:
                        # Agar yangi admin botni bloklagan bo'lsa yoki hali start bosmagan bo'lsa
                        print(f"Yangi adminga xabar yuborib bo'lmadi: {e}")

                    # 4. ESKI ADMINGA TASDIQ XABARI
                    await msg.reply(
                        f"✅ <b>Egalik huquqi muvaffaqiyatli o'tkazildi!</b>\n\n"
                        f"Yangi admin (ID: <code>{new_main_id}</code>) xabardor qilindi.", 
                        reply_markup=user_menu(uid)
                    )
                    return 
                except ValueError:
                    return await msg.reply("❌ Xato! Iltimos, faqat raqamli ID yuboring.")
                    

            # Boshqa statelar (reklama, transfer va hokazo)...

    # 2. Keyin oddiy buyruqlarni tekshiramiz
    if not await check_force_join(client, msg): return

    if txt == "🏆 Leaderboard":

        # Leaderboard funksiyasini chaqiramiz

        res_text = await get_leaderboard_text()

        return await msg.reply(res_text)

# Kod orqali qidirish qismi
    if txt and txt.isdigit():
        code = int(txt)
        movie = movies_col.find_one({"code": code})
        if movie:
            # Ham umumiy, ham haftalik yuklashlarni +1 qilamiz
            movies_col.update_one(
                {"code": code}, 
                {"$inc": {"downloads": 1, "weekly_downloads": 1}} 
            )
            
            insta = movie.get("insta_link")
            await msg.reply_video(
                video=movie["file_id"],
                caption=movie["title"],
                reply_markup=movie_extra_kb(code, is_admin(uid), insta_link=insta)
            )
            return

# --- ADMIN APPROVE LOGIC ---
    if uid in approve_wait:
        if txt == "❌ Bekor qilish":
            approve_wait.pop(uid)
            return await msg.reply("Bekor qilindi.", reply_markup=admin_menu())
        
        data = approve_wait.pop(uid)
        try:
            code = int(txt)
            # Foydalanuvchiga yuboriladigan avtomatik matn
            user_text = (
                f"✅ <b>Siz so'ragan kino {SAVED_MOVIE} kanaliga yuklandi!</b>\n\n"
                f"🍿 Kino kodi: <code>{code}</code>\n"
                f"🎬 Nomi: {data['name']}\n\n"
                f"<i>Botga kodni yuborib kinoni yuklab olishingiz mumkin.</i>"
            )
            await client.send_message(data["target"], user_text)
            
            # So'rovni bazadan o'chirish
            req_col.delete_one({"user_id": data["target"], "name": data["name"]})
            
            await msg.reply("✅ Foydalanuvchiga xabar va kino kodi yuborildi.", reply_markup=admin_menu())
        except:
            await msg.reply("Xato! Faqat raqamli kod yuboring.")
        return


# --- STATISTIKA (USERLAR UCHUN) ---
    if txt == "📊 Statistika":
        u_dat = users_col.find_one({"user_id": uid})
        refs = u_dat.get("referrals", 0) if u_dat else 0
        
        # VIP Statusni aniqlash
        vip_status = "✅ Faol" if refs >= 5 or is_admin(uid) else "❌ Faol emas"
        
        # Jami yuklab olishlarni hisoblash (Userlar ko'rishi uchun)
        all_movies = list(movies_col.find({}, {"downloads": 1}))
        total_downloads = sum(m.get("downloads", 0) for m in all_movies)
        
        u_count = users_col.count_documents({})
        now = datetime.now(UZ_TZ)

        res = (
            f"📊 <b>Statistika:</b>\n"
            f"______________________________________\n\n"
            f"💎 <b>VIP Status:</b> {vip_status}\n"
            f"👥 Do'stlaringiz: <code>{refs} ta</code>\n\n"
            f"👤 Jami Userlar: {u_count}\n"
            f"📥 Jami yuklab olishlar: {total_downloads}\n" # Siz so'ragan o'zgarish
            f"⏰ Vaqt: {now.strftime('%H:%M / %d.%m.%Y')}"
        )
        return await msg.reply(res)

    # --- ADMIN PANEL (FAQAT ADMIN UCHUN) ---
    if txt == "📊 Admin Panel" and is_admin(uid):
        # Admin uchun ham yuklab olishlarni hisoblash
        all_movies = list(movies_col.find({}, {"downloads": 1}))
        total_downloads = sum(m.get("downloads", 0) for m in all_movies)
        
        u_count = users_col.count_documents({})
        m_count = movies_col.count_documents({})
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_u = users_col.count_documents({"joined_at": {"$gte": today_start}})
        
        now = datetime.now(UZ_TZ)

        res = (
            f"📊 <b>Admin Panel Statistika</b>\n"
            f"______________________________________\n\n"
            f"🆕 Bugun qo'shildi: {today_u}\n"
            f"👥 Jami Userlar: {u_count}\n"
            f"🎬 Jami yuklangan kinolar: {m_count}\n"
            f"📥 Jami yuklab olishlar: {total_downloads}\n\n"
            f"⏰ Vaqt: {now.strftime('%Y-%m-%d %H:%M')}"
        )
        return await msg.reply(res, reply_markup=admin_menu())


    # --- MAIN MENU ACTIONS ---
    if txt == "🎭 Janrlar":
        return await msg.reply("🎭 Janrni tanlang:", reply_markup=genres_keyboard())

    if txt == "📂 Barcha Kinolar":
        t, m = get_movie_list(1)
        return await msg.reply(t, reply_markup=m)

    if txt == "📈 Top Kinolar":
        top = list(movies_col.find().sort([("avg_rating", -1), ("downloads", -1)]).limit(10))
        res = "📈 <b>Top 10 Kinolar:</b>\n\n"
        for x in top:
            t_line = x['title'].split('\n')[0]
            res += f"🎬 {t_line}\n🔑 FILM KODI: <code>{x['code']}</code>\n\n"
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

    if txt == "📥 Kino so'rash":
        u_dat = users_col.find_one({"user_id": uid})
        refs = u_dat.get("referrals", 0) if u_dat else 0
        
        # VIP TEKSHIRUVI (5 ta do'st)
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

        # VIP bo'lsa yoki Admin bo'lsa
        request_wait.add(uid)
        return await msg.reply("✍🏻 <b>Kino nomini yozing:</b>", reply_markup=cancel_menu())
        

    if txt == "📢 Reklama":
        return await msg.reply("📢 Reklama xizmati bo'yicha admin bilan bog'laning: @Mr_Javohirjon")

    if txt == "⬅️ Orqaga":
        return await msg.reply("Bosh menyu:", reply_markup=user_menu(uid))

    if txt == "⚙️ Admin Menu" and is_admin(uid):
        return await msg.reply("⚙️ Admin paneliga xush kelibsiz.", reply_markup=admin_menu())

    if txt == "⚙️ Sozlamalar":
        await msg.reply("⚙️ Sozlamalar bo'limi:", reply_markup=admin_settings_menu())

    if txt == "📋 Kanallar ro'yxati":
        conf = get_config()
        channels = conf.get("mandatory_channels", [])
        text = "📢 **Majburiy kanallar:**\n\n" + ("\n".join(channels) if channels else "Hozircha kanallar yo'q")
        await msg.reply(text)

    if txt == "👤 User Menu ga qaytish":
        return await msg.reply("👤 Foydalanuvchi menyusi.", reply_markup=user_menu(uid))

     # --- GENRE CLICKS ---
    if txt and txt.startswith("📁 "):
        genre_name = txt.replace("📁 ", "").lower()
        t, m = get_movie_list(1, genre_name)
        return await msg.reply(t, reply_markup=m)    

    # --- STATES ---
    if uid in request_wait:
        request_wait.remove(uid)
        if txt == "❌ Bekor qilish": return await msg.reply("Bekor qilindi.", reply_markup=user_menu(uid))
        req_col.insert_one({"name": txt, "username": msg.from_user.first_name, "user_id": uid})
        return await msg.reply("✅ So'rov yuborildi! Tez orada bazaga qo'shiladi.", reply_markup=user_menu(uid))

    if uid in broadcast_wait:


        broadcast_wait.remove(uid)
        if txt == "❌ Bekor qilish": return await msg.reply("Bekor qilindi.", reply_markup=admin_menu())
        sent = 0
        for user in users_col.find():
            try:
                await msg.copy(user["user_id"])
                sent += 1
                await asyncio.sleep(0.05)
            except: pass
        return await msg.reply(f"✅ Xabar {sent} ta foydalanuvchiga yuborildi.")

#=====ReferalButton=====#

    if txt == "🔗 Taklifnoma":
        await send_referral_info(client, msg)
        return

    if is_admin(uid):

        # --- ADMIN BOSHQARUVI ---
        if txt == "👤 Admin qo'shish":
            broadcast_wait.add(f"addadmin_{uid}") # kutish holati
            return await msg.reply("➕ Yangi admin ID raqamini yuboring:", reply_markup=cancel_menu())

        if txt == "👤 Admin o'chirish":
            conf = get_config()
            admins = conf.get("admin_ids", [])
            if not admins: return await msg.reply("Yordamchi adminlar mavjud emas.")
            res = "👤 **O'chirish uchun ID'ni yuboring:**\n\n"
            for a in admins: res += f"• <code>{a}</code>\n"
            broadcast_wait.add(f"remadmin_{uid}")
            return await msg.reply(res, reply_markup=cancel_menu())

        # --- KANALLAR BOSHQARUVI ---
        if txt == "➕ Kanal qo'shish":
            broadcast_wait.add(f"addchan_{uid}")
            return await msg.reply("📢 Kanal ma'lumotlarini formatda yuboring:\n\n`@kanal_username | Kanal Nomi | https://t.me/link`", reply_markup=cancel_menu())

        elif txt == "➖ Kanal o'chirish" and is_admin(uid):
            conf = get_config()
            chans = conf.get("mandatory_channels", [])
            
            if not chans:
                return await msg.reply("❌ Hozircha majburiy kanallar yo'q.")
            
            res = "➖ **O'chirish uchun kanal linkini nusxalab yuboring:**\n\n"
            for index, c in enumerate(chans, start=1):
                # Linkni bosganda nusxa ko'chiriladigan formatda chiqaramiz
                res += f"{index}. <code>{c['link']}</code>\n"
            
            broadcast_wait.add(f"remchan_{uid}")
            return await msg.reply(res, reply_markup=cancel_menu())

        # --- KINO KANAL (Sizning 3-talabingiz) ---
        if txt == "🎬 Kino kanalni sozlash":
            broadcast_wait.add(f"setmoviechan_{uid}")
            return await msg.reply("🎬 Kinolar yuboriladigan kanal ID sini yuboring (Masalan: -100...):", reply_markup=cancel_menu())

        # --- ADMIN TRANSFER (Sizning 4-talabingiz) ---
        if txt == "👑 Adminlikni o'tkazish" and is_main_admin(uid):
            broadcast_wait.add(f"transfer_{uid}")
            return await msg.reply("⚠️ **DIQQAT!** Yangi Asosiy Admin ID raqamini yuboring. Shundan so'ng sizning huquqlaringiz cheklanadi!", reply_markup=cancel_menu())


        if txt == "📥 Kelgan So'rovlar":
            reqs = list(req_col.find().limit(5))
            if not reqs: 
                return await msg.reply("Hozircha so'rovlar yo'q.")
            
            for r in reqs:
                tid = r.get('user_id')
                req_name = r.get('name', 'Noma\'lum foydalanuvchi')
                # Tugmalarga "Topilmadi" variantini qo'shamiz
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Topildi", callback_data=f"approve_{tid}_{req_name}"),
                        InlineKeyboardButton("❌ Topilmadi", callback_data=f"notfound_{tid}_{req_name}")
                    ]
                ])
                await msg.reply(f"🎬 <b>So'rov:</b> {req_name}\n👤 Kimdan: {tid}", reply_markup=kb)
            return

        if txt == "🗑 So'rovlarni tozalash" and is_admin(uid):
            confirm_markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Ha, o'chirilsin", callback_data="confirm_clear_requests"),
                    InlineKeyboardButton("❌ Yo'q, bekor qilish", callback_data="cancel_clear_requests")
                ]
            ])
            return await msg.reply(
                "⚠️ <b>DIQQAT!</b>\n\nBarcha kelgan so'rovlarni o'chirib tashlamoqchimisiz? "
                "Bu amalni ortga qaytarib bo'lmaydi!", 
                reply_markup=confirm_markup
            )

        if txt == "📢 Xabar yuborish" and is_admin(uid):
            broadcast_wait.add(uid)
            return await msg.reply(
                "✍️ Yuboriladigan xabarni yuboring (rasm, video yoki tekst):",
                reply_markup=cancel_menu()
            )



    # --- SEARCH MOVIE BY CODE ---

    if not txt.isdigit() and len(txt) > 2:
        # Kinolarni nomi bo'yicha qidirish (regex - qisman mos kelsa ham topadi)
        movies = list(movies_col.find({"title": {"$regex": txt, "$options": "i"}}).limit(5))
        
        if movies:
            res_text = f"🔍 <b>'{txt}' bo'yicha topilgan kinolar:</b>\n\n"
            for m in movies:
                t_line = m['title'].split('\n')[0]
                res_text += f"🎬 {t_line}\n🔑 Kod: <code>{m['code']}</code>\n\n"
            return await msg.reply(res_text)
        # Agar topilmasa, hech narsa qilmaydi yoki "Topilmadi" deb qaytaradi

#========Referal======#

async def send_referral_info(client, msg):
    """
    Faqat referal (Taklifnoma) qismi uchun funksiya.
    Rasmda ko'rsatilgan VIP mantiqi va dizayni asosida.
    """
    uid = msg.from_user.id
    bot_obj = await client.get_me()
    bot_username = bot_obj.username
    
    # Foydalanuvchi ma'lumotlarini bazadan olish
    user_data = users_col.find_one({"user_id": uid})
    referrals_count = user_data.get("referrals", 0) if user_data else 0
    
    # VIP mantiqini hisoblash: Har 5 ta do'st uchun 1 ta limit
    current_limit = referrals_count // 5
    next_limit_step = 5 - (referrals_count % 5)
    
    # Referal havola yaratish
    ref_link = f"https://t.me/{bot_username}?start={uid}"
    
    # Rasmda ko'rsatilgan matn formati
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
        f"<i>Havolani do'stlaringizga yuboring va kino olamini birga kashf qiling! 🚀</i>"
    )
    
    # Ulashish tugmasi (Share)
    share_url = f"https://t.me/share/url?url={ref_link}"
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Ulashish (Share)", url=share_url)]
    ])
    
    await msg.reply(text, reply_markup=reply_markup, disable_web_page_preview=True)

#=======Haftalik Doska=======#

async def get_leaderboard_text():
    # TOP 10 (Referral >= 5)
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
            # Agar foydalanuvchi hozirda VIP bo'lsa, yoniga belgi qo'yamiz
            status = " ✨" if u.get("is_vip") else ""
            text += f"{medals[i]} {name[:15]}{status} — <b>{count} ta</b>\n"

    text += "\n______________________________________\n"
    text += "🎁 <b>VIP Imtiyozlari:</b>\n"
    text += "✅ Majburiy obunalarsiz foydalanish\n"
    text += "✅ 1 hafta davomida amal qiladi\n\n"
    text += "⏰ <i>Har yakshanba soat 20:00 da yangilanadi.</i>"
    
    return text


@app.on_message(filters.text & filters.private)
async def all_movies_list(client, msg):
    if msg.text == "Barcha kinolar":
        # Bazadan oxirgi 10 ta kinoni olish
        movies = list(movies_col.find().sort("_id", -1).limit(10))
        
        if not movies:
            return await msg.reply("Hozircha bazada kinolar yo'q.")

        text = "🎬 **Oxirgi yuklangan kinolar ro'yxati:**\n\n"
        buttons = []
        row = []

        for i, movie in enumerate(movies, 1):
            title = movie.get("title", "Nomsiz kino").split('\n')[0][:30]
            text += f"{i}. {title} (Kod: `{movie['code']}`)\n"
            
            # Har bir raqam uchun callback_data (masalan: showmovie_123)
            row.append(InlineKeyboardButton(str(i), callback_data=f"showmovie_{movie['code']}"))
            
            if i % 5 == 0: # Har 5 ta tugmadan keyin yangi qator
                buttons.append(row)
                row = []
        
        if row: buttons.append(row)

        await msg.reply(text, reply_markup=InlineKeyboardMarkup(buttons))



@app.on_callback_query(filters.regex(r"^showmovie_(\d+)"))
async def show_movie_by_button(client, cb):
    movie_code = int(cb.data.split("_")[1])
    movie = movies_col.find_one({"code": movie_code})

    if not movie:
        return await cb.answer("Kino topilmadi!", show_alert=True)

    await cb.answer("Kino yuborilmoqda...")

    # Kinoni yuborish (Bitta video yoki guruhli ekanini tekshirish)
    if movie.get("is_group"):
        # Guruhli kino bo'lsa, birinchi qismini yoki tanlash menyusini yuboring
        first_part = movie["file_ids"][0]
        await client.send_video(
            cb.from_user.id, 
            video=first_part, 
            caption=f"🎬 {movie['title']}\n\n🍿 Bu ko'p qismli kino. Barcha qismlarni bot orqali ko'rishingiz mumkin."
        )
    else:
        # Oddiy bitta videoli kino
        await client.send_video(
            cb.from_user.id, 
            video=movie["file_id"], 
            caption=f"🎬 {movie['title']}\n\n🔑 Kod: {movie['code']}"
        )

# ==========================================
#         AUTO SAVE FROM CHANNEL
# ==========================================

@app.on_message(filters.video & filters.chat(SAVED_MOVIE))
async def save_movie_from_channel(client, msg):
    caption = msg.caption or ""
    # Hashtag orqali 11 ta janrdan birini aniqlash
    found_genres = [word.strip("#").lower() for word in caption.split() if word.startswith("#") and word.strip("#").lower() in ALLOWED_GENRES]
    
    if not found_genres:
        found_genres = ["boshqa"]

    
        
    last_movie = movies_col.find_one(sort=[("code", -1)])
    new_code = 1 if not last_movie else last_movie["code"] + 1
    
    # --- 1272-qatordan boshlab yangi kod ---
        
    # 1. 5 Yulduzli tugmalarni yasash
    star_buttons = [
        InlineKeyboardButton("⭐ 1", callback_data=f"star_1_{new_code}"),
        InlineKeyboardButton("⭐ 2", callback_data=f"star_2_{new_code}"),
        InlineKeyboardButton("⭐ 3", callback_data=f"star_3_{new_code}"),
        InlineKeyboardButton("⭐ 4", callback_data=f"star_4_{new_code}"),
        InlineKeyboardButton("⭐ 5", callback_data=f"star_5_{new_code}")
    ]
    
    movie_buttons = InlineKeyboardMarkup([
        star_buttons, # Birinchi qatorda yulduzlar
        [
            InlineKeyboardButton("🎬 Kinodan parcha", callback_data=f"trailer_none"), # Hozircha bo'sh
            InlineKeyboardButton("⭐ Sevimlilar", callback_data=f"fav_{new_code}")
        ]
    ])

    # 2. Bazaga saqlash (Aniq fakt: file_id birlikda bo'lishi shart)
    movies_col.insert_one({
        "code": new_code, 
        "file_id": msg.video.file_id, 
        "title": caption, 
        "downloads": 0, 
        "weekly_downloads": 0,
        "genres": found_genres,
        "rating": 0.0,       # O'rtacha ball boshida 0
        "votes_count": 0,    # Ovozlar soni boshida 0
        "total_stars": 0     # Jami yig'ilgan yulduzlar boshida 0
    })

    # 3. Kanalga javob yuborish (Tugmalar bilan)
    await msg.reply(
        f"✅ <b>Bot bazasiga saqlandi!</b>\n\n"
        f"🔑 <b>FILM KODI:</b> <code>{new_code}</code>\n"
        f"🎭 <b>Janrlar:</b> #{' #'.join(found_genres)}\n"
        f"📊 <b>Reyting:</b> 0.0 (0 ta ovoz)",
        reply_markup=movie_buttons
    )
    # --- Blok tugadi ---

@app.on_message(filters.chat(SAVED_MOVIE) & filters.reply & filters.text)
async def update_trailer_link(client, msg):
    # Agar reply qilingan xabar botniki bo'lsa va unda "FILM KODI" so'zi bo'lsa
    if msg.reply_to_message.from_user.is_self and "FILM KODI:" in msg.reply_to_message.text:
        # Linkni tekshirish (faqat instagram bo'lsa)
        if "instagram.com" in msg.text:
            try:
                # Xabar matnidan kodni ajratib olish (FILM KODI: 123)
                text = msg.reply_to_message.text
                movie_code = int(text.split("FILM KODI:")[1].split()[0].strip())
                
                # Bazani yangilash
                link = msg.text.strip()
                movies_col.update_one({"code": movie_code}, {"$set": {"trailer": link}})
                
                # Tugmalarni yangilash (Endi tugma Instagramga olib boradi)
                # Oldingi tugmalarni olib, 'trailer' tugmasini URL tugmaga aylantiramiz
                new_markup = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("⭐ 1", callback_data=f"star_1_{movie_code}"),
                        InlineKeyboardButton("⭐ 2", callback_data=f"star_2_{movie_code}"),
                        InlineKeyboardButton("⭐ 3", callback_data=f"star_3_{movie_code}"),
                        InlineKeyboardButton("⭐ 4", callback_data=f"star_4_{movie_code}"),
                        InlineKeyboardButton("⭐ 5", callback_data=f"star_5_{movie_code}")
                    ],
                    [
                        InlineKeyboardButton("🎬 Kinodan parcha", url=link), # Endi bu URL tugma
                        InlineKeyboardButton("⭐ Sevimlilar", callback_data=f"fav_{movie_code}")
                    ]
                ])
                
                await msg.reply_to_message.edit_reply_markup(reply_markup=new_markup)
                await msg.reply("✅ Kinodan parcha (link) muvaffaqiyatli bog'landi!")
                await msg.delete() # Siz yuborgan link xabarini o'chirib tashlaydi
                
            except Exception as e:
                await msg.reply(f"❌ Xatolik: {str(e)}")

#=====Inline Search======#

from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent

@app.on_inline_query()
async def inline_search(client, query):
    string = query.query.strip()
    
    # Bot username'ini keshdan olamiz
    bot_username = client.me.username if client.me else "bot_username"

    # Agar qidiruv bo'sh bo'lsa, eng ko'p yuklangan 5 ta kinoni ko'rsatadi
    if not string:
        movies = list(movies_col.find().sort("downloads", -1).limit(5))
    
    # Agar faqat raqam yozilgan bo'lsa (Kod bo'yicha qidiruv)
    elif string.isdigit():
        movies = list(movies_col.find({"code": int(string)}))
    
    # Agar raqam bo'lmasa, hech narsa ko'rsatmaydi (yoki bo'sh ro'yxat)
    else:
        movies = []

    results = []
    for m in movies:
        # Kinoning birinchi qatorini nom sifatida olamiz
        movie_title = m['title'].split('\n')[0]
        
        results.append(
            InlineQueryResultArticle(
                title=f"🎬 {movie_title}",
                description=f"🔑 Kod: {m['code']} | 📥 Yuklangan: {m.get('downloads', 0)} marta",
                input_message_content=InputTextMessageContent(
                    f"🎬 <b>{m['title']}</b>\n\n"
                    f"🔑 <b>Film kodi:</b> <code>{m['code']}</code>\n"
                    f"🤖 <b>Botimiz:</b> @{bot_username}"
                ),
                thumb_url="https://img.icons8.com/fluency/48/movie.png",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎬 Kinoni ko'rish", url=f"https://t.me/{bot_username}?start={m['code']}")]
                ])
            )
        )

    await query.answer(results, cache_time=5)    

# ==========================================
#                RUN BOT
# ==========================================

async def run():
    # Schedulerni ishga tushiramiz
    scheduler.start()
    
    # 🌟 HAFTALIK TAVSIYANOMA JOBINI SHU YERDA QO'SHAMIZ:
    # Yakshanba kuni soat 20:00 da send_weekly_highlights funksiyasini chaqiradi
    scheduler.add_job(
        send_weekly_highlights, 
        "cron", 
        day_of_week="sun", 
        hour=20, 
        minute=0
    )
    
    await app.start()
    print("Bot muvaffaqiyatli ishga tushdi!")
    await idle()

if __name__ == "__main__":
    app.run(run())
