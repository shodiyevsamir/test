import telebot
import time
import threading
import os
import psycopg2
from telebot import types

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
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

db("""CREATE TABLE IF NOT EXISTS groups(
group_id BIGINT PRIMARY KEY,
title TEXT,
interval INT DEFAULT 30,
running BOOLEAN DEFAULT FALSE,
ri INT DEFAULT 0,
ui INT DEFAULT 0)""")

db("""CREATE TABLE IF NOT EXISTS rules(
id SERIAL PRIMARY KEY,
group_id BIGINT,
text TEXT)""")

db("""CREATE TABLE IF NOT EXISTS users(
id SERIAL PRIMARY KEY,
group_id BIGINT,
user_id BIGINT,
name TEXT,
mentions INT DEFAULT 0,
UNIQUE(group_id,user_id))""")

# ================= HELPERS =================

def is_admin(u): return u == ADMIN_ID

def groups(): return db("SELECT * FROM groups", fetch=True) or []

def ensure(gid, title=""):
    db("INSERT INTO groups(group_id,title) VALUES(%s,%s) ON CONFLICT DO NOTHING",(gid,title))

def rules(gid): return db("SELECT text FROM rules WHERE group_id=%s",(gid,),True)

def users(gid): return db("SELECT user_id,name,mentions FROM users WHERE group_id=%s",(gid,),True)

# ================= MENU =================

def main_menu():
    m = types.InlineKeyboardMarkup()
    for g in groups():
        gid,title,_,run,_,_ = g
        m.add(types.InlineKeyboardButton(
            f"{'🟢' if run else '🔴'} {title or gid}",
            callback_data=f"g:{gid}"
        ))
    return m

def panel(gid):
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("➕ Qoida",callback_data=f"ar:{gid}"))
    m.add(types.InlineKeyboardButton("📋 Qoidalar",callback_data=f"lr:{gid}"))
    m.add(types.InlineKeyboardButton("👥 User",callback_data=f"au:{gid}"))
    m.add(types.InlineKeyboardButton("❌ O‘chir",callback_data=f"du:{gid}"))
    m.add(types.InlineKeyboardButton("👀 Userlar",callback_data=f"lu:{gid}"))
    m.add(types.InlineKeyboardButton("📊 Stat",callback_data=f"st:{gid}"))
    m.add(types.InlineKeyboardButton("⏱ Interval",callback_data=f"ti:{gid}"))
    m.add(types.InlineKeyboardButton("⬅️ Back",callback_data="back"))
    return m

# ================= START =================

@bot.message_handler(commands=['start'])
def start(m):
    if m.chat.type!="private" or not is_admin(m.from_user.id): return
    bot.send_message(m.chat.id,"⚙️ Admin panel",reply_markup=main_menu())

# ================= CALLBACK (FIXED) =================

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    try:
        data = call.data
    except:
        return

    if data == "back":
        try:
            bot.edit_message_text("⚙️ Admin panel",call.message.chat.id,call.message.id,reply_markup=main_menu())
        except:
            bot.send_message(call.message.chat.id,"⚙️ Admin panel",reply_markup=main_menu())

        bot.answer_callback_query(call.id)
        return

    if data.startswith("g:"):
        gid=int(data.split(":")[1])
        ensure(gid)
        try:
            bot.edit_message_text(f"Guruh {gid}",call.message.chat.id,call.message.id,reply_markup=panel(gid))
        except:
            bot.send_message(call.message.chat.id,f"Guruh {gid}",reply_markup=panel(gid))

        bot.answer_callback_query(call.id)
        return

    if ":" not in data:
        bot.answer_callback_query(call.id)
        return

    act,gid=data.split(":")
    gid=int(gid)

    if act=="ar":
        msg=bot.send_message(call.message.chat.id,"Qoida yoz:")
        bot.register_next_step_handler(msg,lambda m:add_rule(m,gid))

    elif act=="lr":
        r=rules(gid)
        bot.send_message(call.message.chat.id,"\n".join([x[0] for x in r]) or "Bo‘sh")

    elif act=="au":
        msg=bot.send_message(call.message.chat.id,"Forward yoki ID,Ism")
        bot.register_next_step_handler(msg,lambda m:add_user(m,gid))

    elif act=="du":
        msg=bot.send_message(call.message.chat.id,"User ID:")
        bot.register_next_step_handler(msg,lambda m:del_user(m,gid))

    elif act=="lu":
        u=users(gid)
        txt="\n".join([f"{n} ({i})" for i,n,_ in u]) or "Bo‘sh"
        bot.send_message(call.message.chat.id,txt)

    elif act=="st":
        u=users(gid)
        u=sorted(u,key=lambda x:-x[2])
        medals=["🥇","🥈","🥉"]
        txt="\n".join([f"{medals[i] if i<3 else i+1}. {x[1]} - {x[2]}" for i,x in enumerate(u)]) or "Bo‘sh"
        bot.send_message(call.message.chat.id,txt)

    elif act=="ti":
        msg=bot.send_message(call.message.chat.id,"Sekund:")
        bot.register_next_step_handler(msg,lambda m:set_time(m,gid))

    bot.answer_callback_query(call.id)

# ================= ACTIONS =================

def add_rule(m,gid):
    db("INSERT INTO rules(group_id,text) VALUES(%s,%s)",(gid,m.text))
    bot.send_message(m.chat.id,"✅ Qo‘shildi")

def add_user(m,gid):
    if m.forward_from:
        u=m.forward_from
        name=(u.first_name or "")+" "+(u.last_name or "")
        db("INSERT INTO users(group_id,user_id,name) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",(gid,u.id,name))
    else:
        try:
            i,n=m.text.split(",")
            db("INSERT INTO users(group_id,user_id,name) VALUES(%s,%s,%s)",(gid,int(i),n))
        except:
            bot.send_message(m.chat.id,"❌ Format xato")
            return
    bot.send_message(m.chat.id,"✅ OK")

def del_user(m,gid):
    db("DELETE FROM users WHERE group_id=%s AND user_id=%s",(gid,int(m.text)))
    bot.send_message(m.chat.id,"🗑 OK")

def set_time(m,gid):
    db("UPDATE groups SET interval=%s WHERE group_id=%s",(int(m.text),gid))
    bot.send_message(m.chat.id,"⏱ OK")

# ================= GROUP =================

@bot.message_handler(commands=['startbot'])
def startb(m):
    if m.chat.type=="private": return
    ensure(m.chat.id,m.chat.title)
    db("UPDATE groups SET running=TRUE WHERE group_id=%s",(m.chat.id,))
    bot.reply_to(m,"▶️ ON")

@bot.message_handler(commands=['stopbot'])
def stopb(m):
    if m.chat.type=="private": return
    db("UPDATE groups SET running=FALSE WHERE group_id=%s",(m.chat.id,))
    bot.reply_to(m,"⏸ OFF")

# ================= LOOP =================

def loop():
    while True:
        try:
            for g in groups():
                gid,_,t,r,ri,ui=g
                if not r: continue

                rs=rules(gid)
                us=users(gid)
                if not rs or not us: continue

                ri%=len(rs)
                ui%=len(us)

                uid,name,_=us[ui]
                bot.send_message(gid,f'<a href="tg://user?id={uid}">{name}</a>\n{rs[ri][0]}')

                db("UPDATE users SET mentions=mentions+1 WHERE user_id=%s AND group_id=%s",(uid,gid))
                db("UPDATE groups SET ri=%s,ui=%s WHERE group_id=%s",((ri+1)%len(rs),(ui+1)%len(us),gid))

            time.sleep(5)

        except Exception as e:
            print("ERROR:",e)
            time.sleep(5)

threading.Thread(target=loop,daemon=True).start()
bot.infinity_polling(skip_pending=True)
