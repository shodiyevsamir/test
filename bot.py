import telebot
import time
import threading
import os

TOKEN = os.getenv("TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

🔥 8. Done!
bot = telebot.TeleBot(TOKEN)

FILE = "rules.txt"
open(FILE, "a", encoding="utf-8").close()

interval = 30
is_running = True
sent_count = 0
index = 0

def load_rules():
    with open(FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

# 🔒 admin tekshiruv
def is_admin(user_id):
    return user_id == ADMIN_ID

# ➕ add
@bot.message_handler(commands=['add'])
def add_rule(message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.replace("/add", "").strip()
    if text:
        with open(FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        bot.reply_to(message, "✅ Qoida qo‘shildi")

# 📋 list
@bot.message_handler(commands=['list'])
def list_rules(message):
    rules = load_rules()
    if not rules:
        bot.reply_to(message, "❌ Qoida yo‘q")
        return
    text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(rules)])
    bot.reply_to(message, text)

# 🗑 delete
@bot.message_handler(commands=['del'])
def delete_rule(message):
    if not is_admin(message.from_user.id):
        return
    try:
        index = int(message.text.split()[1]) - 1
        rules = load_rules()
        removed = rules.pop(index)

        with open(FILE, "w", encoding="utf-8") as f:
            for r in rules:
                f.write(r + "\n")

        bot.reply_to(message, f"🗑 O‘chirildi: {removed}")
    except:
        bot.reply_to(message, "❌ Format: /del 1")

# ⏱ time
@bot.message_handler(commands=['time'])
def change_time(message):
    global interval
    if not is_admin(message.from_user.id):
        return
    try:
        sec = int(message.text.split()[1])
        interval = sec
        bot.reply_to(message, f"⏱ Interval {sec} sekundga o‘zgardi")
    except:
        bot.reply_to(message, "❌ Format: /time 30")

# ▶️ start
@bot.message_handler(commands=['startbot'])
def start_bot(message):
    global is_running
    if not is_admin(message.from_user.id):
        return
    is_running = True
    bot.reply_to(message, "▶️ Bot ishga tushdi")

# ⏸ stop
@bot.message_handler(commands=['stopbot'])
def stop_bot(message):
    global is_running
    if not is_admin(message.from_user.id):
        return
    is_running = False
    bot.reply_to(message, "⏸ Bot to‘xtatildi")

# 📊 stat
@bot.message_handler(commands=['stat'])
def stats(message):
    bot.reply_to(message, f"📊 Yuborilgan qoidalar soni: {sent_count}")

# 🔁 auto send
def auto_send():
    global index, sent_count
    while True:
        if is_running:
            rules = load_rules()
            if rules:
                bot.send_message(GROUP_ID, rules[index])
                index = (index + 1) % len(rules)
                sent_count += 1

        time.sleep(interval)

threading.Thread(target=auto_send).start()

bot.infinity_polling()
