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
tracked_tokens = {}

async def check_token(mint, session):
    try:
        url = f"https://frontend-api.pump.fun/coins/{mint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

            mcap = data.get("usd_market_cap", 0)
            nsfw = data.get("nsfw", True)
            complete = data.get("complete", False)
            reply_count = data.get("reply_count", 0)
            twitter = data.get("twitter", "")
            website = data.get("website", "")
            telegram = data.get("telegram", "")
            description = data.get("description", "")

            if nsfw:
                return None
            if complete:
                return None
            if mcap < 5000 or mcap > 30000:
                return None
            if reply_count < 5:
                return None

            score = 0
            socials = []

            if twitter:
                score += 30
                socials.append("X/Twitter")
            if website:
                score += 20
                socials.append("Website")
            if telegram:
                score += 20
                socials.append("Telegram")
            if reply_count > 10:
                score += 15
            if reply_count > 20:
                score += 15
            if description and len(description) > 50:
                score += 10

            if score < 50:
                return None

            return {
                "mcap": mcap,
                "reply_count": reply_count,
                "twitter": twitter,
                "website": website,
                "telegram": telegram,
                "description": description[:100],
                "score": score,
                "socials": socials,
            }
    except Exception as e:
        logging.error(f"Check error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pumpfun Safety Scanner\n\n"
        "Filter aktif:\n"
        "MCap $5k-$30k\n"
        "Reply lebih dari 5\n"
        "Punya Twitter/X\n"
        "Score minimal 50\n"
        "Bukan NSFW\n\n"
        "/scan - Mulai scan\n"
        "/stopscan - Stop scan\n"
        "/positions - Lihat posisi\n"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("Scanning dihentikan!")

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not tracked_tokens:
        await update.message.reply_text("Tidak ada token yang ditemukan.")
        return
    msg = "Token Ditemukan:\n\n"
    for mint, data in tracked_tokens.items():
        msg += (
            f"Nama: {data['name']} ({data['symbol']})\n"
            f"MCap: ${data['mcap']:,.0f}\n"
            f"Score: {data['score']}\n"
            f"Link: pump.fun/{mint}\n\n"
        )
    await update.message.reply_text(msg)

async def scan_tokens(chat_id, app):
    global scan_active, tracked_tokens
    seen_mints = set()

    await app.bot.send_message(chat_id,
        "Scanner dimulai!\n"
        "Mencari token safe dengan potensi 1M mcap..."
    )

    uri = "wss://pumpportal.fun/api/data"

    while scan_active:
        try:
            async with websockets.connect(uri) as ws:
                payload = {"method": "subscribeNewToken"}
                await ws.send(json.dumps(payload))
                await app.bot.send_message(chat_id, "Terhubung ke Pump.fun!")

                async with aiohttp.ClientSession() as session:
                    while scan_active:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(msg)

                            mint = data.get("mint", "")
                            if not mint or mint in seen_mints:
                                continue

                            name = data.get("name", "Unknown")
                            symbol = data.get("symbol", "???")
                            seen_mints.add(mint)

                            await asyncio.sleep(3)
                            info = await check_token(mint, session)

                            if not info:
                                continue

                            tracked_tokens[mint] = {
                                "name": name,
                                "symbol": symbol,
                                "mcap": info["mcap"],
                                "score": info["score"],
                            }

                            socials_text = ", ".join(info["socials"]) if info["socials"] else "Tidak ada"

                            msg_text = (
                                f"TOKEN POTENSIAL!\n\n"
                                f"Nama: {name} ({symbol})\n"
                                f"MCap: ${info['mcap']:,.0f}\n"
                                f"Replies: {info['reply_count']}\n"
                                f"Socials: {socials_text}\n"
                                f"Score: {info['score']}/100\n"
                                f"Deskripsi: {info['description']}\n\n"
                                f"Link: pump.fun/{mint}\n\n"
                                f"Keputusan buy ada di tangan Anda!"
                            )
                            await app.bot.send_message(chat_id, msg_text)

                        except asyncio.TimeoutError:
                            continue

        except Exception as e:
            logging.error(f"WebSocket error: {e}")
            if scan_active:
                await app.bot.send_message(chat_id, "Reconnecting...")
                await asyncio.sleep(5)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    if scan_active:
        await update.message.reply_text("Scan sudah berjalan!")
        return
    scan_active = True
    chat_id = update.effective_chat.id
    asyncio.create_task(scan_tokens(chat_id, context.application))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Info bot\n"
        "/scan - Mulai scan\n"
        "/stopscan - Stop scan\n"
        "/positions - Token ditemukan"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("stopscan", stopscan))
    app.add_handler(CommandHandler("positions", positions))
    app.add_handler(CommandHandler("help", help_command))
    print("Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
