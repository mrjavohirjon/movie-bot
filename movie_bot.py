import json, os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== CONFIG =====

API_ID = 38119035
API_HASH = "0f84597433eacb749fd482ad238a104e"
BOT_TOKEN = "8509897503:AAE54so0a3oUImP9psT_-3IpETGCogo_c-A"

MOVIE_CHANNEL = "@hshhshshshdgegeuejje"
MANDATORY_CHANNEL = "@TG_Manager_uz"

ADMIN_IDS = [5014031582]

MOVIES_FILE = "movies.json"
REQUEST_FILE = "requests.json"
USERS_FILE = "users.json"
FAV_FILE = "favorites.json"

# ==================

app = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== INIT FILES =====

def init(file, default):
    if not os.path.exists(file):
        json.dump(default, open(file,"w"))

init(MOVIES_FILE, [])
init(REQUEST_FILE, [])
init(USERS_FILE, [])
init(FAV_FILE, {})

def load(f):
    try:
        return json.load(open(f))
    except:
        return {} if f==FAV_FILE else []

def save(f,d):
    json.dump(d, open(f,"w"), indent=4)

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

# ===== MENUS =====

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
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

# ===== START =====

@app.on_message(filters.command("start"))
async def start(client,msg):

    users = load(USERS_FILE)
    if msg.from_user.id not in users:
        users.append(msg.from_user.id)
        save(USERS_FILE,users)

    if not await joined(client,msg.from_user.id):
        await msg.reply("⚠ Join channel first:", reply_markup=join_btn())
        return

    await msg.reply(
        "🎬 Send movie code or name to search",
        reply_markup=user_menu(msg.from_user.id in ADMIN_IDS)
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
async def save_movie(client,msg):

    movies = load(MOVIES_FILE)
    code = 1 if not movies else movies[-1]["code"] + 1

    title = msg.caption or f"Movie {code}"

    movies.append({
        "code":code,
        "file_id":msg.video.file_id,
        "title":title,
        "downloads":0,
        "msg_id":msg.id
    })

    save(MOVIES_FILE,movies)

    await msg.reply(
        f"✅ Saved!\n🎬 Code: {code}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Remove Movie", callback_data=f"remove_{code}")]
        ])
    )

# ===== REMOVE =====

@app.on_callback_query(filters.regex("^remove_"))
async def remove_movie(client,cb):

    code=int(cb.data.split("_")[1])
    movies=load(MOVIES_FILE)

    movie = next((m for m in movies if m["code"]==code),None)
    if not movie:
        await cb.answer("Already removed",show_alert=True)
        return

    try:
        await client.delete_messages(MOVIE_CHANNEL, movie["msg_id"])
    except:
        pass

    movies=[m for m in movies if m["code"]!=code]
    save(MOVIES_FILE,movies)

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

@app.on_message(filters.text & ~filters.regex("^/"))
async def search(client,msg):

    if not await joined(client,msg.from_user.id):
        await msg.reply("⚠ Join first:", reply_markup=join_btn())
        return

    q=msg.text.lower()
    movies=load(MOVIES_FILE)

    for m in movies:
        if (q.isdigit() and int(q)==m["code"]) or q in m["title"].lower():

            await client.send_video(
                msg.chat.id,
                m["file_id"],
                caption=f"🎬 {m['title']}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⭐ Add Favorite", callback_data=f"fav_{m['code']}")]
                ])
            )

            m["downloads"]+=1
            save(MOVIES_FILE,movies)
            return

    await msg.reply("❌ Movie not found")

# ===== FAVORITES =====

@app.on_callback_query(filters.regex("^fav_"))
async def add_fav(client,cb):

    code=cb.data.split("_")[1]
    fav=load(FAV_FILE)
    uid=str(cb.from_user.id)

    fav.setdefault(uid,[])

    if code in fav[uid]:
        await cb.answer("Already added ⭐",show_alert=True)
        return

    fav[uid].append(code)
    save(FAV_FILE,fav)

    await cb.answer("Added to favorites ⭐",show_alert=True)

@app.on_callback_query(filters.regex("myfav"))
async def myfav(client,cb):

    fav=load(FAV_FILE).get(str(cb.from_user.id),[])
    movies=load(MOVIES_FILE)

    if not fav:
        await cb.answer("No favorites yet!",show_alert=True)
        return

    text="⭐ Favorites:\n\n"
    for c in fav:
        for m in movies:
            if str(m["code"])==str(c):
                text+=f"{m['title']} (Code {m['code']})\n"

    await cb.message.edit_text(text,reply_markup=user_menu(cb.from_user.id in ADMIN_IDS))

# ===== STATS =====

@app.on_callback_query(filters.regex("stats"))
async def stats(client,cb):

    movies=load(MOVIES_FILE)
    users=load(USERS_FILE)

    await cb.message.edit_text(
        f"📊 Statistics\n\n"
        f"👥 Users: {len(users)}\n"
        f"🎬 Movies: {len(movies)}\n"
        f"⬇ Downloads: {sum(m['downloads'] for m in movies)}",
        reply_markup=user_menu(cb.from_user.id in ADMIN_IDS)
    )

# ===== TOP (NAME + CODE ONLY) =====

@app.on_callback_query(filters.regex("top"))
async def top(client, cb):

    movies = load(MOVIES_FILE)

    if not movies:
        await cb.answer("No movies yet", show_alert=True)
        return

    top = sorted(movies, key=lambda x: x.get("downloads", 0), reverse=True)[:5]

    text = "📈 Top Movies:\n\n"

    for i, m in enumerate(top, 1):
        title = m["title"].splitlines()[0]   # only first line
        text += f"{i}. {title} (Code: {m['code']})\n"

    await cb.message.edit_text(
        text,
        reply_markup=user_menu(cb.from_user.id in ADMIN_IDS)
    )

# ===== REQUEST AUTO APPROVE =====

@app.on_message(filters.command("request"))
async def request_movie(client,msg):

    name=msg.text.replace("/request","").strip().lower()
    movies=load(MOVIES_FILE)

    for m in movies:
        if name in m["title"].lower():
            await client.send_video(msg.chat.id,m["file_id"],caption=m["title"])
            return

    req=load(REQUEST_FILE)
    req.append(name)
    save(REQUEST_FILE,req)

    await msg.reply("📥 Requested! Will be added soon")

# ===== ADMIN PANEL =====

@app.on_callback_query(filters.regex("admin"))
async def admin_panel(client,cb):
    if cb.from_user.id not in ADMIN_IDS: return
    await cb.message.edit_text("⭐ Admin Panel",reply_markup=admin_menu())

@app.on_callback_query(filters.regex("back"))
async def back(client,cb):
    await cb.message.edit_text("🎬 Menu",reply_markup=user_menu(cb.from_user.id in ADMIN_IDS))

@app.on_callback_query(filters.regex("view_requests"))
async def view_req(client,cb):

    if cb.from_user.id not in ADMIN_IDS: return
    req=load(REQUEST_FILE)

    if not req:
        await cb.message.edit_text("No requests",reply_markup=admin_menu())
        return

    text="📥 Requests:\n\n"
    for i,r in enumerate(req,1):
        text+=f"{i}. {r}\n"

    await cb.message.edit_text(text,reply_markup=admin_menu())

# ===== RUN =====

print("🤖 Movie bot running...")
app.run()
