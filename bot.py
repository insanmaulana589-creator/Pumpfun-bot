import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Selamat datang di Pumpfun Bot!\n\n"
        "Perintah tersedia:\n"
        "/start - Mulai bot\n"
        "/buy - Beli token\n"
        "/sell - Jual token\n"
        "/balance - Cek saldo\n"
        "/help - Bantuan"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 Ketik /start untuk melihat semua perintah.")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Fitur cek saldo sedang dalam pengembangan.")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 Fitur beli token sedang dalam pengembangan.")

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔴 Fitur jual token sedang dalam pengembangan.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("sell", sell))
    print("Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
