import os
import time
import threading
import psycopg2
import telebot
from flask import Flask, request, redirect, render_template_string

# =========================
# ENV
# =========================
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", "3000"))
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "12345")

# =========================
# BOT
# =========================
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# =========================
# DB
# =========================
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True

def db(query, params=(), fetch=False, one=False):
    with conn.cursor() as cur:
        cur.execute(query, params)
        if one:
            return cur.fetchone()
        if fetch:
            return cur.fetchall()
    return None

db("""
CREATE TABLE IF NOT EXISTS rules (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL
)
""")

db("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    mentions INT NOT NULL DEFAULT 0
)
""")

db("""
CREATE TABLE IF NOT EXISTS settings (
    id INT PRIMARY KEY,
    interval_sec INT NOT NULL DEFAULT 30,
    running BOOLEAN NOT NULL DEFAULT FALSE,
    rule_index INT NOT NULL DEFAULT 0,
    user_index INT NOT NULL DEFAULT 0
)
""")

db("""
INSERT INTO settings (id, interval_sec, running, rule_index, user_index)
VALUES (1, 30, FALSE, 0, 0)
ON CONFLICT (id) DO NOTHING
""")

# =========================
# HELPERS
# =========================
def get_rules():
    return db("SELECT id, text FROM rules ORDER BY id ASC", fetch=True) or []

def get_users():
    return db("SELECT id, user_id, name, mentions FROM users ORDER BY id ASC", fetch=True) or []

def get_settings():
    row = db(
        "SELECT interval_sec, running, rule_index, user_index FROM settings WHERE id = 1",
        one=True
    )
    return {
        "interval_sec": row[0],
        "running": row[1],
        "rule_index": row[2],
        "user_index": row[3],
    }

def update_settings(interval_sec=None, running=None, rule_index=None, user_index=None):
    s = get_settings()
    interval_sec = s["interval_sec"] if interval_sec is None else interval_sec
    running = s["running"] if running is None else running
    rule_index = s["rule_index"] if rule_index is None else rule_index
    user_index = s["user_index"] if user_index is None else user_index

    db("""
    UPDATE settings
    SET interval_sec = %s,
        running = %s,
        rule_index = %s,
        user_index = %s
    WHERE id = 1
    """, (interval_sec, running, rule_index, user_index))

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# =========================
# TELEGRAM COMMANDS
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    if message.chat.type != "private" or not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "Admin buyruqlari:\n\n"
        "/addrule text\n"
        "/adduser id,ism\n"
        "/adduser  (reply yoki forward bilan ham ishlaydi)\n"
        "/deluser id\n"
        "/users\n"
        "/stat\n"
        "/time sekund\n"
        "/status"
    )

@bot.message_handler(commands=["addrule"])
def add_rule_cmd(message):
    if not is_admin(message.from_user.id):
        return

    text = message.text.replace("/addrule", "", 1).strip()
    if not text:
        bot.send_message(message.chat.id, "Format: /addrule matn")
        return

    db("INSERT INTO rules(text) VALUES(%s)", (text,))
    bot.send_message(message.chat.id, "✅ Qoida qo‘shildi")

@bot.message_handler(commands=["adduser"])
def add_user_cmd(message):
    if not is_admin(message.from_user.id):
        return

    # reply orqali
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        name = " ".join(x for x in [u.first_name, u.last_name] if x).strip() or "User"
        db("""
        INSERT INTO users(user_id, name) VALUES(%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET name = EXCLUDED.name
        """, (u.id, name))
        bot.send_message(message.chat.id, f"✅ Qo‘shildi: {name} ({u.id})")
        return

    # forward orqali
    if getattr(message, "forward_from", None):
        u = message.forward_from
        name = " ".join(x for x in [u.first_name, u.last_name] if x).strip() or "User"
        db("""
        INSERT INTO users(user_id, name) VALUES(%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET name = EXCLUDED.name
        """, (u.id, name))
        bot.send_message(message.chat.id, f"✅ Qo‘shildi: {name} ({u.id})")
        return

    # id,ism
    try:
        raw = message.text.replace("/adduser", "", 1).strip()
        user_id_str, name = raw.split(",", 1)
        user_id = int(user_id_str.strip())
        name = name.strip()
        if not name:
            raise ValueError

        db("""
        INSERT INTO users(user_id, name) VALUES(%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET name = EXCLUDED.name
        """, (user_id, name))
        bot.send_message(message.chat.id, "✅ User qo‘shildi")
    except Exception:
        bot.send_message(message.chat.id, "Format: /adduser 123456789,Ali")

@bot.message_handler(commands=["deluser"])
def del_user_cmd(message):
    if not is_admin(message.from_user.id):
        return

    try:
        user_id = int(message.text.split()[1])
        db("DELETE FROM users WHERE user_id = %s", (user_id,))
        bot.send_message(message.chat.id, "🗑 User o‘chirildi")
    except Exception:
        bot.send_message(message.chat.id, "Format: /deluser 123456789")

@bot.message_handler(commands=["users"])
def users_cmd(message):
    if not is_admin(message.from_user.id):
        return

    users = get_users()
    if not users:
        bot.send_message(message.chat.id, "Bo‘sh")
        return

    text = "\n".join([f"{u[2]} ({u[1]})" for u in users])
    bot.send_message(message.chat.id, f"👥 USERLAR:\n\n{text}")

@bot.message_handler(commands=["stat"])
def stat_cmd(message):
    if not is_admin(message.from_user.id):
        return

    users = db("SELECT name, mentions FROM users ORDER BY mentions DESC, id ASC", fetch=True) or []
    if not users:
        bot.send_message(message.chat.id, "Bo‘sh")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (name, mentions) in enumerate(users):
        prefix = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{prefix} {name} - {mentions}")

    bot.send_message(message.chat.id, "📊 STAT:\n\n" + "\n".join(lines))

@bot.message_handler(commands=["time"])
def time_cmd(message):
    if not is_admin(message.from_user.id):
        return

    try:
        sec = int(message.text.split()[1])
        if sec < 5:
            bot.send_message(message.chat.id, "Minimum 5 sekund")
            return
        update_settings(interval_sec=sec)
        bot.send_message(message.chat.id, f"⏱ Interval: {sec} sekund")
    except Exception:
        bot.send_message(message.chat.id, "Format: /time 30")

@bot.message_handler(commands=["status"])
def status_cmd(message):
    if not is_admin(message.from_user.id):
        return

    s = get_settings()
    bot.send_message(
        message.chat.id,
        f"Holat: {'ON' if s['running'] else 'OFF'}\n"
        f"Interval: {s['interval_sec']} sekund\n"
        f"Rules: {len(get_rules())}\n"
        f"Users: {len(get_users())}"
    )

@bot.message_handler(commands=["startbot"])
def startbot_cmd(message):
    if message.chat.id != GROUP_ID:
        return
    update_settings(running=True)
    bot.reply_to(message, "▶️ Bot ishga tushdi")

@bot.message_handler(commands=["stopbot"])
def stopbot_cmd(message):
    if message.chat.id != GROUP_ID:
        return
    update_settings(running=False)
    bot.reply_to(message, "⏸ Bot to‘xtadi")

# =========================
# AUTO LOOP
# =========================
def sender_loop():
    while True:
        try:
            s = get_settings()
            if not s["running"]:
                time.sleep(2)
                continue

            rules = get_rules()
            users = get_users()

            if not rules or not users:
                time.sleep(2)
                continue

            r_idx = s["rule_index"] % len(rules)
            u_idx = s["user_index"] % len(users)

            rule_text = rules[r_idx][1]
            user_id = users[u_idx][1]
            user_name = users[u_idx][2]

            bot.send_message(
                GROUP_ID,
                f'<a href="tg://user?id={user_id}">{user_name}</a>\n{rule_text}'
            )

            db("UPDATE users SET mentions = mentions + 1 WHERE user_id = %s", (user_id,))
            update_settings(
                rule_index=(r_idx + 1) % len(rules),
                user_index=(u_idx + 1) % len(users)
            )

            time.sleep(s["interval_sec"])
        except Exception as e:
            print("LOOP ERROR:", e)
            time.sleep(5)

# =========================
# WEB APP
# =========================
app = Flask(__name__)

LOGIN_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Login</title>
  <style>
    body { font-family: Arial; max-width: 420px; margin: 60px auto; }
    input, button { width: 100%; padding: 12px; margin-top: 10px; }
  </style>
</head>
<body>
  <h2>Admin Login</h2>
  <form method="post">
    <input type="password" name="password" placeholder="Password">
    <button type="submit">Kirish</button>
  </form>
  {% if error %}<p style="color:red">{{ error }}</p>{% endif %}
</body>
</html>
"""

PANEL_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Bot Panel</title>
  <style>
    body { font-family: Arial; margin: 30px; }
    .box { border: 1px solid #ddd; padding: 16px; margin-bottom: 18px; border-radius: 10px; }
    input, button { padding: 10px; margin-top: 8px; }
    .full { width: 100%; }
    ul { padding-left: 18px; }
    a.btn, button { background: #111; color: #fff; border: none; border-radius: 8px; text-decoration: none; cursor: pointer; }
    a.btn { padding: 10px 14px; display: inline-block; }
  </style>
</head>
<body>
  <h1>Bot Admin Panel</h1>

  <div class="box">
    <b>Status:</b> {{ "ON" if settings.running else "OFF" }}<br>
    <b>Interval:</b> {{ settings.interval_sec }} sekund<br>
    <b>Rules:</b> {{ rules|length }}<br>
    <b>Users:</b> {{ users|length }}<br><br>
    <a class="btn" href="/toggle?password={{ password }}">ON/OFF almashtir</a>
  </div>

  <div class="box">
    <h3>Qoida qo‘shish</h3>
    <form action="/addrule_web" method="post">
      <input class="full" type="hidden" name="password" value="{{ password }}">
      <input class="full" type="text" name="text" placeholder="Qoida matni">
      <button type="submit">Qo‘shish</button>
    </form>
  </div>

  <div class="box">
    <h3>User qo‘shish</h3>
    <form action="/adduser_web" method="post">
      <input type="hidden" name="password" value="{{ password }}">
      <input class="full" type="text" name="user_id" placeholder="Telegram user id">
      <input class="full" type="text" name="name" placeholder="Ismi">
      <button type="submit">Qo‘shish</button>
    </form>
  </div>

  <div class="box">
    <h3>Interval</h3>
    <form action="/time_web" method="post">
      <input type="hidden" name="password" value="{{ password }}">
      <input class="full" type="text" name="interval" placeholder="Sekund">
      <button type="submit">Saqlash</button>
    </form>
  </div>

  <div class="box">
    <h3>Qoidalar</h3>
    <ul>
      {% for r in rules %}
        <li>
          {{ r[1] }}
          <a href="/delrule/{{ r[0] }}?password={{ password }}">[o‘chir]</a>
        </li>
      {% endfor %}
    </ul>
  </div>

  <div class="box">
    <h3>Userlar</h3>
    <ul>
      {% for u in users %}
        <li>
          {{ u[2] }} ({{ u[1] }}) - mentions: {{ u[3] }}
          <a href="/deluser_web/{{ u[1] }}?password={{ password }}">[o‘chir]</a>
        </li>
      {% endfor %}
    </ul>
  </div>

  <div class="box">
    <h3>Leaderboard</h3>
    <ul>
      {% for item in stat %}
        <li>{{ item }}</li>
      {% endfor %}
    </ul>
  </div>
</body>
</html>
"""

def check_web_password(req):
    p = req.values.get("password", "")
    return p == WEB_PASSWORD

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == WEB_PASSWORD:
            return redirect(f"/panel?password={WEB_PASSWORD}")
        return render_template_string(LOGIN_HTML, error="Password xato")
    return render_template_string(LOGIN_HTML, error=None)

@app.route("/panel")
def panel():
    if not check_web_password(request):
        return redirect("/")

    settings = get_settings()
    rules = get_rules()
    users = get_users()

    medals = ["🥇", "🥈", "🥉"]
    sorted_users = sorted(users, key=lambda x: (-x[3], x[0]))
    stat = []
    for i, u in enumerate(sorted_users):
        prefix = medals[i] if i < 3 else f"{i+1}."
        stat.append(f"{prefix} {u[2]} - {u[3]}")

    return render_template_string(
        PANEL_HTML,
        settings=settings,
        rules=rules,
        users=users,
        stat=stat,
        password=WEB_PASSWORD
    )

@app.route("/toggle")
def toggle():
    if not check_web_password(request):
        return redirect("/")
    s = get_settings()
    update_settings(running=not s["running"])
    return redirect(f"/panel?password={WEB_PASSWORD}")

@app.route("/addrule_web", methods=["POST"])
def addrule_web():
    if not check_web_password(request):
        return redirect("/")
    text = request.form.get("text", "").strip()
    if text:
        db("INSERT INTO rules(text) VALUES(%s)", (text,))
    return redirect(f"/panel?password={WEB_PASSWORD}")

@app.route("/adduser_web", methods=["POST"])
def adduser_web():
    if not check_web_password(request):
        return redirect("/")
    try:
        user_id = int(request.form.get("user_id", "").strip())
        name = request.form.get("name", "").strip()
        if name:
            db("""
            INSERT INTO users(user_id, name) VALUES(%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET name = EXCLUDED.name
            """, (user_id, name))
    except Exception:
        pass
    return redirect(f"/panel?password={WEB_PASSWORD}")

@app.route("/time_web", methods=["POST"])
def time_web():
    if not check_web_password(request):
        return redirect("/")
    try:
        sec = int(request.form.get("interval", "").strip())
        if sec >= 5:
            update_settings(interval_sec=sec)
    except Exception:
        pass
    return redirect(f"/panel?password={WEB_PASSWORD}")

@app.route("/delrule/<int:rule_id>")
def delrule(rule_id):
    if not check_web_password(request):
        return redirect("/")
    db("DELETE FROM rules WHERE id = %s", (rule_id,))
    return redirect(f"/panel?password={WEB_PASSWORD}")

@app.route("/deluser_web/<int:user_id>")
def deluser_web(user_id):
    if not check_web_password(request):
        return redirect("/")
    db("DELETE FROM users WHERE user_id = %s", (user_id,))
    return redirect(f"/panel?password={WEB_PASSWORD}")

# =========================
# RUN
# =========================
def run_flask():
    app.run(host="0.0.0.0", port=PORT)

threading.Thread(target=sender_loop, daemon=True).start()
threading.Thread(target=run_flask, daemon=True).start()

bot.infinity_polling(skip_pending=True)
