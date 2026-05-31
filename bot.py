import os
import logging
import asyncio
import aiohttp
import json
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
scan_active = False
seen = set()

async def scan_tokens(chat_id, app):
    global scan_active, seen
    await app.bot.send_message(chat_id,
        "Scanner New Pair aktif!\n"
        "Filter: MCap $10k-$100k\n"
        "Liquidity lebih dari $5k\n"
        "Buy lebih dari sell\n"
        "Ada Twitter"
    )

    uri = "wss://pumpportal.fun/api/data"

    while scan_active:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                await app.bot.send_message(chat_id, "Terhubung! Memantau token baru...")

                async with aiohttp.ClientSession() as session:
                    while scan_active:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(msg)
                            mint = data.get("mint", "")
                            if not mint or mint in seen:
                                continue
                            seen.add(mint)
                            name = data.get("name", "Unknown")
                            symbol = data.get("symbol", "???")
                            twitter = data.get("twitter", "")
                            website = data.get("website", "")
                            telegram = data.get("telegram", "")

                            asyncio.create_task(
                                check_and_notify(mint, name, symbol, twitter, website, telegram, chat_id, app, session)
                            )

                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            logging.error(e)

        except Exception as e:
            logging.error(f"WS error: {e}")
            if scan_active:
                await app.bot.send_message(chat_id, "Reconnecting...")
                await asyncio.sleep(5)

async def check_and_notify(mint, name, symbol, twitter, website, telegram, chat_id, app, session):
    try:
        await asyncio.sleep(30)
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return
            data = await r.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return
            for pair in pairs:
                dex = pair.get("dexId", "")
                mcap = float(pair.get("marketCap", 0) or 0)
                liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                buys = pair.get("txns", {}).get("m5", {}).get("buys", 0)
                sells = pair.get("txns", {}).get("m5", {}).get("sells", 0)
                change5m = float(pair.get("priceChange", {}).get("m5", 0) or 0)
                change1h = float(pair.get("priceChange", {}).get("h1", 0) or 0)
                volume5m = float(pair.get("volume", {}).get("m5", 0) or 0)

                if dex not in ["raydium", "pumpswap"]:
                    continue
                if mcap < 10000 or mcap > 100000:
                    continue
                if liquidity < 5000:
                    continue
                if buys < sells:
                    continue

                socials = []
                if twitter:
                    socials.append(f"Twitter: {twitter}")
                if website:
                    socials.append(f"Web: {website}")
                if telegram:
                    socials.append(f"TG: {telegram}")

                if not socials:
                    continue

                await app.bot.send_message(chat_id,
                    f"NEW PAIR BAGUS!\n\n"
                    f"{name} ({symbol})\n"
                    f"DEX: {dex}\n"
                    f"MCap: ${mcap:,.0f}\n"
                    f"Target 2x: ${mcap*2:,.0f}\n"
                    f"Liquidity: ${liquidity:,.0f}\n"
                    f"Volume 5m: ${volume5m:,.0f}\n"
                    f"Pump 5m: {change5m:.1f}%\n"
                    f"Pump 1h: {change1h:.1f}%\n"
                    f"Buy/Sell: {buys}/{sells}\n"
                    f"\n".join(socials) + "\n"
                    f"CA: {mint}\n\n"
                    f"dexscreener.com/solana/{mint}\n"
                    f"pump.fun/{mint}"
                )
                break
    except Exception as e:
        logging.error(f"Check error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pumpfun New Pair Scanner\n\n"
        "Filter:\n"
        "MCap $10k-$100k\n"
        "Liquidity lebih dari $5k\n"
        "Buy lebih dari sell\n"
        "Ada sosial media\n\n"
        "/scan - Mulai\n"
        "/stopscan - Stop"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("Stop!")

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
