import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = "8674356495:AAFpl3M37CHNcicdHLszPtlb0K6V-L8AZY8"

async def spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /spam <текст>")
        return
    
    text = " ".join(context.args)
    
    for i in range(99):
        await update.message.reply_text(text)
        await asyncio.sleep(0.1)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("spam", spam))
app.run_polling()
