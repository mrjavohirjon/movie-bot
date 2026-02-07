from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# ================= MONGODB =================

MONGO_URL = "mongodb+srv://moviebot:ATQmOjn0TCdyKtTM@cluster0.xvvfs8t.mongodb.net/moviebot"

mongo = MongoClient(MONGO_URL)
db = mongo.moviebot

movies_col = db.movies
users_col = db.users
fav_col = db.favorites
req_col = db.requests

# ================= CONFIG =================

API_ID = 38119035
API_HASH = "0f84597433eacb749fd482ad238a104e"
BOT_TOKEN = "8509897503:AAE54so0a3oUImP9psT_-3IpETGCogo_c-A"

MOVIE_CHANNEL = "@hshhshshshdgegeuejje"
MANDATORY_CHANNEL = "@TG_Manager_uz"
ADMIN_IDS = [5014031582]

app = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ================= JOIN CHECK =================

async def joined(client, uid):
    try:
        m = await client.get_chat_member(MANDATORY_CHANNEL, uid)
        return m.status not in ("left", "kicked")
    except:
        return False

def join_btn():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{MANDATORY_CHANNEL[1:]}")],
        [InlineKeyboardButton("✅ Check", callback_data="check")]
    ])

# ================= MENUS =================

def user_menu(admin=False):
    btn = [
        [InlineKeyboardButton("📈 Top Movies", callback_data="top")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton("⭐ Favorites", callback_data="myfav")]
    ]
    if admin:
        btn.append([InlineKeyboardButton("⭐ Admin Panel", callback_data="admin")])
    return InlineKeyboardMarkup(btn)

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton("📈 Top Movies", callback_data="top")],
        [InlineKeyboardButton("📥 Requests", callback_data="view_requests")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

# ================= START =================

@app.on_message(filters.command("start"))
async def start(client, msg):

    users_col.update_one(
        {"user_id": msg.from_user.id},
        {"$setOnInsert": {"user_id": msg.from_user.id}},
        upsert=True
    )

    if not await joined(client, msg.from_user.id):
        await msg.reply("⚠ Join channel first:", reply_markup=join_btn())
        return

    await msg.reply(
        "🎬 Send movie code or name to search",
        reply_markup=user_menu(msg.from_user.id in ADMIN_IDS)
    )

@app.on_callback_query(filters.regex("^check$"))
async def check_join(client, cb):
    if await joined(client, cb.from_user.id):
        await cb.message.delete()
        await client.send_message(cb.from_user.id, "✅ Access granted!")
    else:
        await cb.answer("❌ Join channel first!", show_alert=True)

# ================= SAVE MOVIE =================

@app.on_message(filters.video & filters.chat(MOVIE_CHANNEL))
async def save_movie(client, msg):

    last = movies_col.find_one(sort=[("code", -1)])
    code = 1 if not last else last["code"] + 1

    title = (msg.caption or f"Movie {code}").strip()

    movies_col.insert_one({
        "code": code,
        "title": title,
        "file_id": msg.video.file_id,
        "msg_id": msg.id,
        "downloads": 0
    })

    await msg.reply(f"✅ Movie saved\n🎬 Code: {code}")

# ================= SEARCH =================

@app.on_message(filters.text & ~filters.command)
async def search(client, msg):

    if not await joined(client, msg.from_user.id):
        return

    q = msg.text.strip().lower()

    movie = movies_col.find_one(
        {"code": int(q)} if q.isdigit()
        else {"title": {"$regex": q, "$options": "i"}}
    )

    if not movie:
        return

    await client.send_video(
        msg.chat.id,
        movie["file_id"],
        caption=f"🎬 {movie['title']}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Add Favorite", callback_data=f"fav_{movie['code']}")]
        ])
    )

    movies_col.update_one(
        {"code": movie["code"]},
        {"$inc": {"downloads": 1}}
    )

# ================= FAVORITES =================

@app.on_callback_query(filters.regex("^fav_"))
async def add_fav(client, cb):
    code = int(cb.data.split("_")[1])
    uid = cb.from_user.id

    fav_col.update_one(
        {"user_id": uid},
        {"$addToSet": {"movies": code}},
        upsert=True
    )

    await cb.answer("⭐ Added to favorites", show_alert=True)

@app.on_callback_query(filters.regex("^myfav$"))
async def myfav(client, cb):
    fav = fav_col.find_one({"user_id": cb.from_user.id})
    if not fav or not fav.get("movies"):
        await cb.answer("No favorites yet", show_alert=True)
        return

    text = "⭐ Favorites:\n\n"
    for code in fav["movies"]:
        m = movies_col.find_one({"code": code})
        if m:
            text += f"{m['title']} (Code {m['code']})\n"

    await cb.message.edit_text(text, reply_markup=user_menu(cb.from_user.id in ADMIN_IDS))

# ================= STATS =================

@app.on_callback_query(filters.regex("^stats$"))
async def stats(client, cb):
    await cb.message.edit_text(
        f"📊 Statistics\n\n"
        f"👥 Users: {users_col.count_documents({})}\n"
        f"🎬 Movies: {movies_col.count_documents({})}\n"
        f"⬇ Downloads: {sum(m.get('downloads',0) for m in movies_col.find())}",
        reply_markup=user_menu(cb.from_user.id in ADMIN_IDS)
    )

# ================= TOP MOVIES =================

@app.on_callback_query(filters.regex("^top$"))
async def top_movies(client, cb):

    top = movies_col.find().sort("downloads", -1).limit(5)

    text = "📈 Top Movies:\n\n"
    i = 1
    for m in top:
        title = m["title"].splitlines()[0]
        text += f"{i}. {title} (Code: {m['code']})\n"
        i += 1

    await cb.message.edit_text(text, reply_markup=user_menu(cb.from_user.id in ADMIN_IDS))

# ================= ADMIN PANEL =================

@app.on_callback_query(filters.regex("^admin$"))
async def admin_panel(client, cb):
    if cb.from_user.id not in ADMIN_IDS:
        return
    await cb.message.edit_text("⭐ Admin Panel", reply_markup=admin_menu())

@app.on_callback_query(filters.regex("^back$"))
async def back(client, cb):
    await cb.message.edit_text("🎬 Menu", reply_markup=user_menu(cb.from_user.id in ADMIN_IDS))

# ================= RUN =================

print("🤖 Movie bot running...")
app.run()
