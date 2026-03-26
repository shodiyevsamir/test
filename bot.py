import telebot
import time
import threading
import os
import psycopg2
from telebot import types

TOKEN = os.getenv("TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

bot = telebot.TeleBot(TOKEN)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# =========================
# DB TABLES
# =========================

cur.execute("""
CREATE TABLE IF NOT EXISTS rules (
    id SERIAL PRIMARY KEY,
    text TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    mentions INTEGER DEFAULT 0
)
""")

conn.commit()

# =========================
# DB FUNCS
# =========================

def add_rule(text):
    cur.execute("INSERT INTO rules (text) VALUES (%s)", (text,))
    conn.commit()

def get_rules():
    cur.execute("SELECT text FROM rules")
    return [x[0] for x in cur.fetchall()]

def add_user(user_id):
    cur.execute("INSERT INTO users (user_id) VALUES (%s)", (user_id,))
    conn.commit()

def get_users():
    cur.execute("SELECT user_id FROM users")
    return [x[0] for x in cur.fetchall()]

def delete_user(user_id):
    cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
    conn.commit()

def add_mention(user_id):
    cur.execute("UPDATE users SET mentions = mentions + 1 WHERE user_id=%s", (user_id,))
    conn.commit()

def get_stats():
    cur.execute("SELECT user_id, mentions FROM users ORDER BY mentions DESC")
    return cur.fetchall()

# =========================
# SETTINGS
# =========================

interval = 30
is_running = False
index = 0
user_index = 0

def is_admin(user_id):
    return user_id == ADMIN_ID

# =========================
# ADMIN PANEL
# =========================

@bot.message_handler(commands=['start'])
def start(message):
    if not is_admin(message.from_user.id):
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Qoida", "📋 Qoidalar")
    markup.add("👥 User qo‘sh", "❌ User o‘chir")
    markup.add("👀 Userlar", "📊 Stat")
    markup.add("⏱ Interval")

    bot.send_message(message.chat.id, "Admin panel", reply_markup=markup)

# ➕ qoida
@bot.message_handler(func=lambda m: m.text == "➕ Qoida")
def add_rule_btn(message):
    msg = bot.send_message(message.chat.id, "Qoida yoz:")
    bot.register_next_step_handler(msg, save_rule)

def save_rule(message):
    add_rule(message.text)
    bot.send_message(message.chat.id, "✅ Qoida qo‘shildi")

# 📋 rules
@bot.message_handler(func=lambda m: m.text == "📋 Qoidalar")
def list_rules(message):
    rules = get_rules()
    text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(rules)]) or "Bo‘sh"
    bot.send_message(message.chat.id, text)

# 👥 add user
@bot.message_handler(func=lambda m: m.text == "👥 User qo‘sh")
def add_user_btn(message):
    msg = bot.send_message(message.chat.id, "User ID yubor:")
    bot.register_next_step_handler(msg, save_user)

def save_user(message):
    add_user(int(message.text))
    bot.send_message(message.chat.id, "✅ User qo‘shildi")

# ❌ delete user
@bot.message_handler(func=lambda m: m.text == "❌ User o‘chir")
def del_user_btn(message):
    msg = bot.send_message(message.chat.id, "User ID yoz:")
    bot.register_next_step_handler(msg, remove_user)

def remove_user(message):
    delete_user(int(message.text))
    bot.send_message(message.chat.id, "🗑 User o‘chirildi")

# 👀 users
@bot.message_handler(func=lambda m: m.text == "👀 Userlar")
def list_users(message):
    users = get_users()
    text = "\n".join([str(u) for u in users]) or "Bo‘sh"
    bot.send_message(message.chat.id, text)

# 📊 stats
@bot.message_handler(func=lambda m: m.text == "📊 Stat")
def stats(message):
    data = get_stats()
    text = "\n".join([f"{u} → {m}" for u, m in data]) or "Bo‘sh"
    bot.send_message(message.chat.id, text)

# ⏱ interval
@bot.message_handler(func=lambda m: m.text == "⏱ Interval")
def ask_time(message):
    msg = bot.send_message(message.chat.id, "Sekund:")
    bot.register_next_step_handler(msg, set_time)

def set_time(message):
    global interval
    interval = int(message.text)
    bot.send_message(message.chat.id, f"{interval} sekund")

# =========================
# GROUP
# =========================

@bot.message_handler(commands=['startbot'])
def start_bot(message):
    global is_running
    if message.chat.id == GROUP_ID:
        is_running = True
        bot.reply_to(message, "▶️ Ishga tushdi")

@bot.message_handler(commands=['stopbot'])
def stop_bot(message):
    global is_running
    if message.chat.id == GROUP_ID:
        is_running = False
        bot.reply_to(message, "⏸ To‘xtadi")

# =========================
# AUTO SEND
# =========================

def auto_send():
    global index, user_index

    while True:
        if is_running:
            rules = get_rules()
            users = get_users()

            if rules and users:
                user_id = users[user_index]

                text = f'<a href="tg://user?id={user_id}">User</a>\n{rules[index]}'

                bot.send_message(GROUP_ID, text, parse_mode="HTML")

                add_mention(user_id)

                index = (index + 1) % len(rules)
                user_index = (user_index + 1) % len(users)

        time.sleep(interval)

threading.Thread(target=auto_send).start()

bot.infinity_polling()
