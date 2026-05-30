import os
import logging
import asyncio
import json
import aiohttp
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
    await app.bot.send_message(chat_id, "Scanning...")
    while scan_active:
        try:
            async with websockets.connect("wss://pumpportal.fun/api/data") as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                async with aiohttp.ClientSession() as session:
                    while scan_active:
                        try:
                            data = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                            mint = data.get("mint", "")
                            if not mint or mint in seen:
                                continue
                            seen.add(mint)
                            name = data.get("name", "?")
                            symbol = data.get("symbol", "?")
                            async with session.get(f"https://frontend-api.pump.fun/coins/{mint}", timeout=aiohttp.ClientTimeout(total=5)) as r:
                                if r.status != 200:
                                    continue
                                info = await r.json()
                                mcap = info.get("usd_market_cap", 0)
                                twitter = info.get("twitter", "")
                                nsfw = info.get("nsfw", True)
                                if nsfw or not twitter or mcap > 100000:
                                    continue
                                await app.bot.send_message(chat_id,
                                    f"TOKEN DITEMUKAN!\n"
                                    f"{name} ({symbol})\n"
                                    f"MCap: ${mcap:,.0f}\n"
                                    f"Target 2x: ${mcap*2:,.0f}\n"
                                    f"Twitter: {twitter}\n"
                                    f"pump.fun/{mint}"
                                )
                        except asyncio.TimeoutError:
                            continue
        except Exception as e:
            logging.error(e)
            if scan_active:
                await asyncio.sleep(5)

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
