import os
import logging
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

scan_active = False
buy_amount = 0.1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Pumpfun Trading Bot\n\n"
        "/scan - Mulai scan token baru\n"
        "/stopscan - Stop scanning\n"
        "/setamount 0.1 - Set jumlah SOL per buy\n"
        "/balance - Cek saldo\n"
        "/help - Bantuan"
    )

async def setamount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global buy_amount
    try:
        buy_amount = float(context.args[0])
        await update.message.reply_text(f"✅ Buy amount diset: {buy_amount} SOL")
    except:
        await update.message.reply_text("❌ Format: /setamount 0.1")

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("🛑 Scanning dihentikan!")

async def scan_tokens(chat_id, app):
    global scan_active
    await app.bot.send_message(chat_id, "🔍 Scanning token baru di Pump.fun...")
    
    while scan_active:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://frontend-api.pump.fun/coins/latest",
                    params={"limit": 5, "includeNsfw": "false"}
                ) as resp:
                    if resp.status == 200:
                        coins = await resp.json()
                        for coin in coins:
                            name = coin.get("name", "Unknown")
                            symbol = coin.get("symbol", "???")
                            mcap = coin.get("usd_market_cap", 0)
                            mint = coin.get("mint", "")
                            
                            if mcap and mcap < 10000:
                                msg = (
                                    f"🎯 Token Baru Ditemukan!\n"
                                    f"📛 {name} (${symbol})\n"
                                    f"💰 Market Cap: ${mcap:.0f}\n"
                                    f"🔗 Mint: {mint[:20]}...\n"
                                    f"⚡ Buying {buy_amount} SOL..."
                                )
                                await app.bot.send_message(chat_id, msg)
        except Exception as e:
            logging.error(f"Scan error: {e}")
        
        await asyncio.sleep(10)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    if scan_active:
        await update.message.reply_text("⚠️ Scan sudah berjalan!")
        return
    scan_active = True
    chat_id = update.effective_chat.id
    asyncio.create_task(scan_tokens(chat_id, context.application))

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Fitur balance segera hadir!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ketik /start untuk melihat perintah.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("stopscan", stopscan))
    app.add_handler(CommandHandler("setamount", setamount))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("help", help_command))
    print("Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
