import os
import logging
import asyncio
import json
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
scan_active = False
seen = set()

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
    global scan_active, seen
    await app.bot.send_message(chat_id, "Scanning realtime via DexScreener...")
    
    while scan_active:
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.dexscreener.com/token-profiles/latest/v1"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status != 200:
                        await asyncio.sleep(3)
                        continue
                    tokens = await r.json()
                    for token in tokens:
                        mint = token.get("tokenAddress", "")
                        chain = token.get("chainId", "")
                        if not mint or mint in seen:
                            continue
                        if chain != "solana":
                            continue
                        seen.add(mint)
                        name = token.get("description", "Unknown")
                        links = token.get("links", [])
                        twitter = ""
                        website = ""
                        for link in links:
                            if link.get("type") == "twitter":
                                twitter = link.get("url", "")
                            if link.get("type") == "website":
                                website = link.get("url", "")
                        if not twitter:
                            continue
                        await app.bot.send_message(chat_id,
                            f"TOKEN BARU SOLANA!\n"
                            f"{name}\n"
                            f"Twitter: {twitter}\n"
                            f"Website: {website if website else 'Tidak ada'}\n"
                            f"dexscreener.com/solana/{mint}\n"
                            f"Target 2x!"
                        )
        except Exception as e:
            logging.error(e)
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
