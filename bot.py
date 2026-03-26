import os
import time
import threading
import psycopg2
import telebot
from telebot import types

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True


def db_execute(query, params=(), fetch=False, fetchone=False):
    with conn.cursor() as cur:
        cur.execute(query, params)
        if fetchone:
            return cur.fetchone()
        if fetch:
            return cur.fetchall()
    return None


# =========================
# DB INIT
# =========================

db_execute("""
CREATE TABLE IF NOT EXISTS groups (
    group_id BIGINT PRIMARY KEY,
    title TEXT,
    interval_sec INTEGER NOT NULL DEFAULT 30,
    is_running BOOLEAN NOT NULL DEFAULT FALSE,
    rule_index INTEGER NOT NULL DEFAULT 0,
    user_index INTEGER NOT NULL DEFAULT 0
)
""")

db_execute("""
CREATE TABLE IF NOT EXISTS rules (
    id SERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL,
    text TEXT NOT NULL
)
""")

db_execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    mentions INTEGER NOT NULL DEFAULT 0,
    UNIQUE(group_id, user_id)
)
""")


# =========================
# HELPERS
# =========================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def is_private(message) -> bool:
    return message.chat.type == "private"


def ensure_group(group_id: int, title: str = ""):
    db_execute("""
        INSERT INTO groups (group_id, title)
        VALUES (%s, %s)
        ON CONFLICT (group_id) DO UPDATE
        SET title = COALESCE(NULLIF(EXCLUDED.title, ''), groups.title)
    """, (group_id, title))


def get_all_groups():
    return db_execute("""
        SELECT group_id, COALESCE(title, ''), interval_sec, is_running, rule_index, user_index
        FROM groups
        ORDER BY group_id
    """, fetch=True) or []


def get_group(group_id: int):
    return db_execute("""
        SELECT group_id, COALESCE(title, ''), interval_sec, is_running, rule_index, user_index
        FROM groups
        WHERE group_id = %s
    """, (group_id,), fetchone=True)


def get_rules(group_id: int):
    return db_execute("""
        SELECT text FROM rules
        WHERE group_id = %s
        ORDER BY id
    """, (group_id,), fetch=True) or []


def add_rule(group_id: int, text: str):
    db_execute("""
        INSERT INTO rules (group_id, text)
        VALUES (%s, %s)
    """, (group_id, text.strip()))


def get_users(group_id: int):
    return db_execute("""
        SELECT user_id, name, mentions
        FROM users
        WHERE group_id = %s
        ORDER BY id
    """, (group_id,), fetch=True) or []


def add_or_update_user(group_id: int, user_id: int, name: str):
    db_execute("""
        INSERT INTO users (group_id, user_id, name)
        VALUES (%s, %s, %s)
        ON CONFLICT (group_id, user_id) DO UPDATE
        SET name = EXCLUDED.name
    """, (group_id, user_id, name.strip()))


def delete_user(group_id: int, user_id: int):
    db_execute("""
        DELETE FROM users
        WHERE group_id = %s AND user_id = %s
    """, (group_id, user_id))


def add_mention(group_id: int, user_id: int):
    db_execute("""
        UPDATE users
        SET mentions = mentions + 1
        WHERE group_id = %s AND user_id = %s
    """, (group_id, user_id))


def get_stats(group_id: int):
    return db_execute("""
        SELECT user_id, name, mentions
        FROM users
        WHERE group_id = %s
        ORDER BY mentions DESC, id ASC
    """, (group_id,), fetch=True) or []


def update_group_interval(group_id: int, seconds: int):
    db_execute("""
        UPDATE groups
        SET interval_sec = %s
        WHERE group_id = %s
    """, (seconds, group_id))


def update_group_running(group_id: int, is_running: bool):
    db_execute("""
        UPDATE groups
        SET is_running = %s
        WHERE group_id = %s
    """, (is_running, group_id))


def update_group_indexes(group_id: int, rule_index: int, user_index: int):
    db_execute("""
        UPDATE groups
        SET rule_index = %s, user_index = %s
        WHERE group_id = %s
    """, (rule_index, user_index, group_id))


def medal(i: int) -> str:
    if i == 0:
        return "🥇"
    if i == 1:
        return "🥈"
    if i == 2:
        return "🥉"
    return f"{i+1}."


def groups_menu():
    markup = types.InlineKeyboardMarkup()
    groups = get_all_groups()

    for group_id, title, interval_sec, is_running, _, _ in groups:
        status = "🟢" if is_running else "🔴"
        label = title if title else str(group_id)
        markup.add(
            types.InlineKeyboardButton(
                f"{status} {label}",
                callback_data=f"manage_group:{group_id}"
            )
        )

    markup.add(types.InlineKeyboardButton("🔄 Yangilash", callback_data="refresh_groups"))
    return markup


def group_admin_menu(group_id: int):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("➕ Qoida", callback_data=f"add_rule:{group_id}"),
        types.InlineKeyboardButton("📋 Qoidalar", callback_data=f"list_rules:{group_id}")
    )
    markup.add(
        types.InlineKeyboardButton("👥 User qo‘sh", callback_data=f"add_user:{group_id}"),
        types.InlineKeyboardButton("❌ User o‘chir", callback_data=f"del_user:{group_id}")
    )
    markup.add(
        types.InlineKeyboardButton("👀 Userlar", callback_data=f"list_users:{group_id}"),
        types.InlineKeyboardButton("📊 Stat", callback_data=f"stat:{group_id}")
    )
    markup.add(
        types.InlineKeyboardButton("⏱ Interval", callback_data=f"time:{group_id}")
    )
    markup.add(
        types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back_groups")
    )
    return markup


def group_info_text(group_id: int) -> str:
    group = get_group(group_id)
    if not group:
        return "Guruh topilmadi."

    _, title, interval_sec, is_running, _, _ = group
    rules_count = len(get_rules(group_id))
    users_count = len(get_users(group_id))
    status = "Ishlayapti" if is_running else "To‘xtagan"

    return (
        f"⚙️ <b>Guruh paneli</b>\n\n"
        f"<b>Nomi:</b> {title or 'Nomsiz'}\n"
        f"<b>ID:</b> <code>{group_id}</code>\n"
        f"<b>Holati:</b> {status}\n"
        f"<b>Interval:</b> {interval_sec} sekund\n"
        f"<b>Qoidalar:</b> {rules_count}\n"
        f"<b>Userlar:</b> {users_count}"
    )


# =========================
# PRIVATE START
# =========================

@bot.message_handler(commands=["start"])
def start_cmd(message):
    if not is_private(message):
        return
    if not is_admin(message.from_user.id):
        return

    bot.send_message(
        message.chat.id,
        "⚙️ <b>Admin panel</b>\nPastdan guruh tanlang.",
        reply_markup=groups_menu()
    )


# =========================
# GROUP COMMANDS
# =========================

@bot.message_handler(commands=["startbot"])
def start_bot(message):
    if message.chat.type == "private":
        return

    ensure_group(message.chat.id, getattr(message.chat, "title", "") or "")
    update_group_running(message.chat.id, True)
    bot.reply_to(message, "▶️ Bot ishga tushdi")


@bot.message_handler(commands=["stopbot"])
def stop_bot(message):
    if message.chat.type == "private":
        return

    ensure_group(message.chat.id, getattr(message.chat, "title", "") or "")
    update_group_running(message.chat.id, False)
    bot.reply_to(message, "⏸ Bot to‘xtatildi")


# =========================
# CALLBACKS
# =========================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Ruxsat yo‘q")
        return

    data = call.data

    if data == "refresh_groups" or data == "back_groups":
        try:
            bot.edit_message_text(
                "⚙️ <b>Admin panel</b>\nPastdan guruh tanlang.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=groups_menu()
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                "⚙️ <b>Admin panel</b>\nPastdan guruh tanlang.",
                reply_markup=groups_menu()
            )
        bot.answer_callback_query(call.id)
        return

    if data.startswith("manage_group:"):
        group_id = int(data.split(":")[1])
        ensure_group(group_id)
        try:
            bot.edit_message_text(
                group_info_text(group_id),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=group_admin_menu(group_id)
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                group_info_text(group_id),
                reply_markup=group_admin_menu(group_id)
            )
        bot.answer_callback_query(call.id)
        return

    action, group_id_str = data.split(":")
    group_id = int(group_id_str)
    ensure_group(group_id)

    if action == "add_rule":
        msg = bot.send_message(call.message.chat.id, "Qoida yozing:")
        bot.register_next_step_handler(msg, save_rule_step, group_id)

    elif action == "list_rules":
        rules = get_rules(group_id)
        text = "\n".join([f"{i+1}. {r[0]}" for i, r in enumerate(rules)]) if rules else "Bo‘sh"
        bot.send_message(call.message.chat.id, f"📋 <b>Qoidalar</b>\n\n{text}")

    elif action == "add_user":
        msg = bot.send_message(
            call.message.chat.id,
            "User qo‘shish uchun 3 usul bor:\n\n"
            "1) Shu yerga <b>ID,Ism</b> yubor\n"
            "Misol: <code>123456789,Ali</code>\n\n"
            "2) Guruhdagi user xabarini menga <b>forward</b> qil\n\n"
            "3) Guruhdagi user xabariga <b>reply</b> qilib menga yubor"
        )
        bot.register_next_step_handler(msg, save_user_step, group_id)

    elif action == "del_user":
        msg = bot.send_message(call.message.chat.id, "O‘chirish uchun user ID yubor:")
        bot.register_next_step_handler(msg, delete_user_step, group_id)

    elif action == "list_users":
        users = get_users(group_id)
        if users:
            text = "\n".join([
                f"{i+1}. {name} (<code>{uid}</code>)"
                for i, (uid, name, _) in enumerate(users)
            ])
        else:
            text = "Bo‘sh"
        bot.send_message(call.message.chat.id, f"👀 <b>Userlar</b>\n\n{text}")

    elif action == "stat":
        stats = get_stats(group_id)
        if stats:
            lines = []
            for i, (_, name, mentions) in enumerate(stats):
                lines.append(f"{medal(i)} {name} — {mentions}")
            text = "\n".join(lines)
        else:
            text = "Bo‘sh"
        bot.send_message(call.message.chat.id, f"📊 <b>Leaderboard</b>\n\n{text}")

    elif action == "time":
        msg = bot.send_message(call.message.chat.id, "Yangi intervalni sekundda yubor:")
        bot.register_next_step_handler(msg, set_time_step, group_id)

    bot.answer_callback_query(call.id)


# =========================
# STEPS
# =========================

def save_rule_step(message, group_id):
    if not is_private(message) or not is_admin(message.from_user.id):
        return

    text = (message.text or "").strip()
    if not text:
        bot.send_message(message.chat.id, "Qoida bo‘sh bo‘lmasin.")
        return

    add_rule(group_id, text)
    bot.send_message(message.chat.id, "✅ Qoida qo‘shildi")


def save_user_step(message, group_id):
    if not is_private(message) or not is_admin(message.from_user.id):
        return

    # Variant 1: forward qilingan xabar
    if getattr(message, "forward_from", None):
        user = message.forward_from
        user_id = user.id
        name = " ".join(filter(None, [user.first_name, user.last_name])) or user.username or str(user.id)
        add_or_update_user(group_id, user_id, name)
        bot.send_message(message.chat.id, f"✅ Qo‘shildi: {name} (<code>{user_id}</code>)")
        return

    # Variant 2: reply qilingan xabar
    if getattr(message, "reply_to_message", None) and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        user_id = user.id
        name = " ".join(filter(None, [user.first_name, user.last_name])) or user.username or str(user.id)
        add_or_update_user(group_id, user_id, name)
        bot.send_message(message.chat.id, f"✅ Qo‘shildi: {name} (<code>{user_id}</code>)")
        return

    # Variant 3: ID,Ism
    text = (message.text or "").strip()
    if "," in text:
        left, right = text.split(",", 1)
        try:
            user_id = int(left.strip())
            name = right.strip()
            if not name:
                raise ValueError
            add_or_update_user(group_id, user_id, name)
            bot.send_message(message.chat.id, f"✅ Qo‘shildi: {name} (<code>{user_id}</code>)")
            return
        except Exception:
            pass

    bot.send_message(
        message.chat.id,
        "❌ Noto‘g‘ri format.\n"
        "To‘g‘ri misol: <code>123456789,Ali</code>\n"
        "Yoki user xabarini forward/reply qiling."
    )


def delete_user_step(message, group_id):
    if not is_private(message) or not is_admin(message.from_user.id):
        return

    try:
        user_id = int((message.text or "").strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ User ID noto‘g‘ri")
        return

    delete_user(group_id, user_id)
    bot.send_message(message.chat.id, "🗑 User o‘chirildi")


def set_time_step(message, group_id):
    if not is_private(message) or not is_admin(message.from_user.id):
        return

    try:
        sec = int((message.text or "").strip())
        if sec < 5:
            bot.send_message(message.chat.id, "❌ Minimum 5 sekund qo‘ying")
            return
    except Exception:
        bot.send_message(message.chat.id, "❌ Raqam yuboring")
        return

    update_group_interval(group_id, sec)
    bot.send_message(message.chat.id, f"⏱ Interval {sec} sekund bo‘ldi")


# =========================
# AUTO SEND LOOP
# =========================

def auto_send_loop():
    while True:
        try:
            groups = get_all_groups()

            for group_id, title, interval_sec, is_running, rule_index, user_index in groups:
                if not is_running:
                    continue

                rules = get_rules(group_id)
                users = get_users(group_id)

                if not rules or not users:
                    continue

                r_idx = rule_index % len(rules)
                u_idx = user_index % len(users)

                rule_text = rules[r_idx][0]
                user_id, name, _mentions = users[u_idx]

                text = f'<a href="tg://user?id={user_id}">{name}</a>\n{rule_text}'
                bot.send_message(group_id, text, parse_mode="HTML")

                add_mention(group_id, user_id)
                update_group_indexes(
                    group_id,
                    (r_idx + 1) % len(rules),
                    (u_idx + 1) % len(users)
                )

            time.sleep(5)

        except Exception as e:
            print(f"AUTO_SEND_ERROR: {e}")
            time.sleep(5)


threading.Thread(target=auto_send_loop, daemon=True).start()
bot.infinity_polling(skip_pending=True)
