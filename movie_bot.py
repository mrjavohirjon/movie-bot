from pyrogram import Client, filters
from pymongo import MongoClient
import time
from pyrogram.errors import FloodWait
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)

MONGO_URL = "mongodb+srv://moviebot:ATQmOjn0TCdyKtTM@cluster0.xvvfs8t.mongodb.net/?appName=Cluster0"

mongo = MongoClient(MONGO_URL)
db = mongo.moviebot

movies_col = db.movies
users_col = db.users
fav_col = db.favorites
req_col = db.requests

# ===== CONFIG =====

API_ID = 38119035
API_HASH = "0f84597433eacb749fd482ad238a104e"
BOT_TOKEN = "5449865657:AAHm5lhjyYiieEdW1fpJTIde2D_daOlFJKc"

MOVIE_CHANNEL = "@hshhshshshdgegeuejje"
MANDATORY_CHANNEL = "@TG_Manager_uz"

ADMIN_IDS = [5014031582]


# ==================

app = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ===== JOIN CHECK =====

async def joined(client, uid):
    try:
        m = await client.get_chat_member(MANDATORY_CHANNEL, uid)
        return m.status not in ["left","kicked"]
    except:
        return False

def join_btn():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{MANDATORY_CHANNEL[1:]}")],
        [InlineKeyboardButton("✅ Check", callback_data="check")]
    ])

#=======JOIN FORCE=====#

async def force_join(client, msg):
    if not msg.from_user:
        return False

    if not await joined(client, msg.from_user.id):
        await msg.reply(
            "⚠ You must join the channel to use this bot.",
            reply_markup=join_btn()
        )
        return False

    return True


# ===== MENUS =====

def user_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📈 Top Movies"), KeyboardButton("📊 Statistics")],
            [KeyboardButton("⭐ Favorites")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📈 Top Movies"), KeyboardButton("📊 Statistics")],
            [KeyboardButton("📥 Requests")],
            [KeyboardButton("⬅ Back")]
        ],
        resize_keyboard=True
    )

# ===== START =====

@app.on_message(filters.command("start"))
async def start(client, msg):

    if not await force_join(client, msg):
        return

    users_col.update_one(
        {"user_id": msg.from_user.id},
        {"$setOnInsert": {"user_id": msg.from_user.id}},
        upsert=True
    )

    if msg.from_user.id in ADMIN_IDS:
        await msg.reply(
            "⭐ Admin Panel\n\n🎬 Send movie code or name to search",
            reply_markup=admin_menu()
        )
    else:
        await msg.reply(
            "🎬 Send movie code or name to search",
            reply_markup=user_menu()
        )


@app.on_callback_query(filters.regex("check"))
async def check(client,cb):
    if await joined(client,cb.from_user.id):
        await cb.message.delete()
        await client.send_message(cb.from_user.id,"✅ Access granted!")
    else:
        await cb.answer("❌ Join channel first!",show_alert=True)

# ===== SAVE MOVIE =====

@app.on_message(filters.video & filters.chat(MOVIE_CHANNEL))
async def save_movie(client, msg):

    last = movies_col.find_one(sort=[("code", -1)])
    code = 1 if not last else last["code"] + 1

    title = msg.caption or f"Movie {code}"

    movies_col.insert_one({
        "code": code,
        "file_id": msg.video.file_id,
        "title": title,
        "downloads": 0,
        "msg_id": msg.id
    })

    await msg.reply(
        f"✅ Saved!\n🎬 Code: {code}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Remove Movie", callback_data=f"remove_{code}")]
        ])
    )

# ===== REMOVE =====

@app.on_callback_query(filters.regex("^remove_"))
async def remove_movie(client, cb):

    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Not allowed", show_alert=True)
        return

    code = int(cb.data.split("_")[1])

    movie = movies_col.find_one({"code": code})
    if not movie:
        await cb.answer("Already removed", show_alert=True)
        return

    try:
        await client.delete_messages(MOVIE_CHANNEL, movie["msg_id"])
    except:
        pass

    movies_col.delete_one({"code": code})

    await cb.message.edit_text("🗑 Movie removed")

# ===== BROADCAST =====

broadcast_wait=set()

@app.on_callback_query(filters.regex("broadcast"))
async def ask_broadcast(client,cb):
    if cb.from_user.id not in ADMIN_IDS:
        return
    broadcast_wait.add(cb.from_user.id)
    await cb.message.edit_text("📢 Send text/image/video/file to broadcast (or /cancel)")

@app.on_message(filters.user(ADMIN_IDS))
async def handle_broadcast(client,msg):

    if msg.from_user.id not in broadcast_wait:
        return

    if msg.text and msg.text.lower()=="/cancel":
        broadcast_wait.remove(msg.from_user.id)
        await msg.reply("❌ Broadcast cancelled")
        return

    users = load(USERS_FILE)

    for u in users:
        try:
            await msg.copy(u)
        except:
            pass

    broadcast_wait.remove(msg.from_user.id)
    await msg.reply("✅ Broadcast sent!")

# ===== SEARCH =====

@app.on_message(
    filters.text
    & ~filters.regex("^/")
    & ~filters.regex("^(📈 Top Movies|📊 Statistics|⭐ Favorites|⭐ Admin Panel|⬅ Back)$")
)
async def search(client, msg):

    # ignore messages without user (channels, anonymous)
    if not msg.from_user:
        return

    # force join check (reply only once)
    if not await force_join(client, msg):
        return

    q = msg.text.strip()

    # find movie
    if q.isdigit():
        movie = movies_col.find_one({"code": int(q)})
    else:
        movie = movies_col.find_one(
            {"title": {"$regex": q, "$options": "i"}}
        )

    # ❌ no movie found → reply once
    if not movie:
        await msg.reply("❌ No movie found")
        return

    # ✅ send movie
    await client.send_video(
        msg.chat.id,
        movie["file_id"],
        caption=f"🎬 {movie['title']}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Add Favorite", callback_data=f"fav_{movie['code']}")]
        ])
    )

    # update downloads
    movies_col.update_one(
        {"code": movie["code"]},
        {"$inc": {"downloads": 1}}
    )

# ===== FAVORITES =====

@app.on_callback_query(filters.regex("^fav_"))
async def add_fav(client, cb):

    if not await joined(client, cb.from_user.id):
        await cb.answer("⚠ Join the channel first", show_alert=True)
        return

    code = int(cb.data.split("_")[1])
    uid = cb.from_user.id

    fav_col.update_one(
        {"user_id": uid},
        {"$addToSet": {"movies": code}},
        upsert=True
    )

    await cb.answer("⭐ Added to favorites", show_alert=True)


@app.on_message(filters.text & filters.regex("^⭐ Favorites$"))
async def myfav_text(client, msg):

    if not await force_join(client, msg):
        return

    fav = fav_col.find_one({"user_id": msg.from_user.id})

    if not fav or not fav.get("movies"):
        await msg.reply("⭐ No favorites yet!")
        return

    text = "⭐ Your Favorites:\n\n"
    for code in fav["movies"]:
        movie = movies_col.find_one({"code": code})
        if movie:
            text += f"{movie['title']} (Code {movie['code']})\n"

    await msg.reply(text)

# ===== STATS =====

@app.on_message(filters.text & filters.regex("^📊 Statistics$"))
async def stats_text(client, msg):

    if not await force_join(client, msg):
        return

    users = users_col.count_documents({})
    movies = movies_col.count_documents({})
    downloads = sum(m.get("downloads", 0) for m in movies_col.find())

    await msg.reply(
        f"📊 Statistics\n\n"
        f"👥 Users: {users}\n"
        f"🎬 Movies: {movies}\n"
        f"⬇ Downloads: {downloads}"
    )

# ===== TOP (NAME + CODE ONLY) =====

@app.on_message(filters.text & filters.regex("^📈 Top Movies$"))
async def top_text(client, msg):

    if not await force_join(client, msg):
        return

    movies = list(
        movies_col.find().sort("downloads", -1).limit(5)
    )

    if not movies:
        await msg.reply("No movies yet")
        return

    text = "📈 Top Movies:\n\n"
    for i, m in enumerate(movies, 1):
        text += f"{i}. {m['title']} (Code {m['code']})\n"

    await msg.reply(text)


# ===== REQUEST AUTO APPROVE =====

@app.on_message(filters.command("request"))
async def request_movie(client, msg):

    if not await force_join(client, msg):
        return

    name = msg.text.replace("/request", "").strip().lower()

    movie = movies_col.find_one({"title": {"$regex": name, "$options": "i"}})
    if movie:
        await client.send_video(msg.chat.id, movie["file_id"], caption=movie["title"])
        return

    req_col.insert_one({"name": name})
    await msg.reply("📥 Requested! Will be added soon")


# ===== ADMIN PANEL =====

@app.on_callback_query(filters.regex("admin"))
async def admin_panel(client,cb):
    if cb.from_user.id not in ADMIN_IDS: return
    await cb.message.edit_text("⭐ Admin Panel",reply_markup=admin_menu())

@app.on_callback_query(filters.regex("back"))
async def back(client,cb):
    await cb.message.edit_text("🎬 Menu",reply_markup=user_menu(cb.from_user.id in ADMIN_IDS))

# ===== VIEW REQUESTS =====

@app.on_callback_query(filters.regex("view_requests"))
async def view_req(client, cb):

    if cb.from_user.id not in ADMIN_IDS:
        return

    reqs = list(req_col.find())

    if not reqs:
        await cb.message.edit_text("No requests", reply_markup=admin_menu())
        return

    text = "📥 Requests:\n\n"
    for i, r in enumerate(reqs, 1):
        text += f"{i}. {r['name']}\n"

    await cb.message.edit_text(text, reply_markup=admin_menu())

# ===== RUN =====

print("🤖 Movie bot running...")
app.run()
