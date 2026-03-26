import telebot
import time
import threading
import os
import psycopg2

# ================= ENV =================

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True

def db(q, p=(), fetch=False):
    with conn.cursor() as c:
        c.execute(q, p)
        if fetch:
            return c.fetchall()

# ================= DB =================

db("""CREATE TABLE IF NOT EXISTS rules(
id SERIAL PRIMARY KEY,
text TEXT)""")

db("""CREATE TABLE IF NOT EXISTS users(
id SERIAL PRIMARY KEY,
user_id BIGINT,
name TEXT,
mentions INT DEFAULT 0)""")

# ================= ADMIN PANEL =================

@bot.message_handler(commands=['start'])
def start(m):
    if m.chat.type != "private" or m.from_user.id != ADMIN_ID:
        return

    bot.send_message(
        m.chat.id,
        "⚙️ ADMIN PANEL\n\n"
        "/addrule text\n"
        "/adduser id,ism\n"
        "/deluser id\n"
        "/users\n"
        "/stat\n"
        "/time sekund"
    )

# ================= RULE =================

@bot.message_handler(commands=['addrule'])
def add_rule(m):
    if m.from_user.id != ADMIN_ID:
        return

    text = m.text.replace("/addrule", "").strip()

    if not text:
        bot.send_message(m.chat.id, "❌ Qoida yoz")
        return

    db("INSERT INTO rules(text) VALUES(%s)", (text,))
    bot.send_message(m.chat.id, "✅ Qoida qo‘shildi")

# ================= ADD USER =================

@bot.message_handler(commands=['adduser'])
def add_user(m):
    if m.from_user.id != ADMIN_ID:
        return

    try:
        data = m.text.replace("/adduser", "").strip()
        uid, name = data.split(",")

        db(
            "INSERT INTO users(user_id,name) VALUES(%s,%s)",
            (int(uid), name)
        )

        bot.send_message(m.chat.id, "✅ User qo‘shildi")

    except:
        bot.send_message(m.chat.id, "❌ Format: /adduser id,ism")

# ================= DELETE USER =================

@bot.message_handler(commands=['deluser'])
def del_user(m):
    if m.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(m.text.split()[1])

        db(
            "DELETE FROM users WHERE user_id=%s",
            (user_id,)
        )

        bot.send_message(m.chat.id, "🗑 User o‘chirildi")

    except:
        bot.send_message(m.chat.id, "❌ Format: /deluser 123456789")

# ================= USERS =================

@bot.message_handler(commands=['users'])
def list_users(m):
    if m.from_user.id != ADMIN_ID:
        return

    u = db("SELECT user_id,name FROM users", fetch=True)

    text = "\n".join([f"{n} ({i})" for i, n in u]) or "Bo‘sh"

    bot.send_message(m.chat.id, f"👥 USERLAR:\n\n{text}")

# ================= STAT =================

@bot.message_handler(commands=['stat'])
def stat(m):
    if m.from_user.id != ADMIN_ID:
        return

    u = db(
        "SELECT name,mentions FROM users ORDER BY mentions DESC",
        fetch=True
    )

    medals = ["🥇", "🥈", "🥉"]

    text = "\n".join([
        f"{medals[i] if i < 3 else i+1}. {x[0]} - {x[1]}"
        for i, x in enumerate(u)
    ]) or "Bo‘sh"

    bot.send_message(m.chat.id, f"📊 STAT:\n\n{text}")

# ================= INTERVAL =================

interval = 30

@bot.message_handler(commands=['time'])
def set_time(m):
    global interval

    if m.from_user.id != ADMIN_ID:
        return

    try:
        interval = int(m.text.split()[1])
        bot.send_message(m.chat.id, "⏱ Interval o‘zgardi")
    except:
        bot.send_message(m.chat.id, "❌ Format: /time 30")

# ================= GROUP =================

running = False

@bot.message_handler(commands=['startbot'])
def startb(m):
    global running

    if m.chat.id != GROUP_ID:
        return

    running = True
    bot.reply_to(m, "▶️ Bot ishga tushdi")

@bot.message_handler(commands=['stopbot'])
def stopb(m):
    global running

    if m.chat.id != GROUP_ID:
        return

    running = False
    bot.reply_to(m, "⏸ Bot to‘xtadi")

# ================= LOOP =================

ri = 0
ui = 0

def loop():
    global ri, ui

    while True:
        try:
            if running:
                rs = db("SELECT text FROM rules", fetch=True)
                us = db("SELECT user_id,name FROM users", fetch=True)

                if rs and us:
                    ri %= len(rs)
                    ui %= len(us)

                    uid, name = us[ui]

                    bot.send_message(
                        GROUP_ID,
                        f'<a href="tg://user?id={uid}">{name}</a>\n{rs[ri][0]}'
                    )

                    db(
                        "UPDATE users SET mentions=mentions+1 WHERE user_id=%s",
                        (uid,)
                    )

                    ri += 1
                    ui += 1

            time.sleep(interval)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(5)

threading.Thread(target=loop, daemon=True).start()
bot.infinity_polling()
