import os
import logging
import asyncio
import json
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
scan_active = False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pumpfun Scanner\n"
        "/scan - Mulai\n"
        "/stopscan - Stop\n"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("Stop!")

async def scan_tokens(chat_id, app):
    global scan_active
    seen = set()
    await app.bot.send_message(chat_id, "Scanning realtime...")
    while scan_active:
        try:
            async with websockets.connect("wss://pumpportal.fun/api/data") as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                while scan_active:
                    try:
                        data = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                        mint = data.get("mint", "")
                        if not mint or mint in seen:
                            continue
                        seen.add(mint)
                        name = data.get("name", "?")
                        symbol = data.get("symbol", "?")
                        twitter = data.get("twitter", "")
                        website = data.get("website", "")
                        mcap_sol = data.get("initialBuy", 0)
                        if not twitter:
                            continue
                        await app.bot.send_message(chat_id,
                            f"TOKEN BARU!\n"
                            f"{name} ({symbol})\n"
                            f"Twitter: {twitter}\n"
                            f"Website: {website if website else 'Tidak ada'}\n"
                            f"pump.fun/{mint}\n"
                            f"Target 2x - keputusan di tangan Anda!"
                        )
                    except asyncio.TimeoutError:
                        continue
        except Exception as e:
            logging.error(e)
            if scan_active:
                await asyncio.sleep(3)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    if scan_active:
        await update.message.reply_text("Sudah jalan!")
        return
    scan_active = True
    asyncio.create_task(scan_tokens(update.effective_chat.id, context.application))

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("stopscan", stopscan))
    app.run_polling()

if __name__ == "__main__":
    main()
