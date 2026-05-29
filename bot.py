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
buy_amount = 0.2
tracked_tokens = {}

async def check_token_safety(mint, session):
    try:
        url = f"https://frontend-api.pump.fun/coins/{mint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

            mcap = data.get("usd_market_cap", 0)
            nsfw = data.get("nsfw", True)
            complete = data.get("complete", False)
            total_supply = data.get("total_supply", 1)
            dev_holdings = data.get("creator_token_holdings", 0)
            reply_count = data.get("reply_count", 0)

            if nsfw:
                return None
            if complete:
                return None
            if mcap < 5000 or mcap > 50000:
                return None
            if total_supply > 0:
                dev_pct = (dev_holdings / total_supply) * 100
                if dev_pct > 10:
                    return None

            return {
                "mcap": mcap,
                "reply_count": reply_count,
                "dev_pct": dev_pct if total_supply > 0 else 0,
            }
    except Exception as e:
        logging.error(f"Safety check error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pumpfun Safety Bot\n\n"
        "Filter aktif:\n"
        "MCap $5k-$50k\n"
        "Dev holdings kurang dari 10 persen\n"
        "Bukan NSFW\n"
        "Belum bonding curve selesai\n"
        "Take Profit: 2x\n\n"
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
        await update.message.reply_text("Tidak ada posisi aktif.")
        return
    msg = "Posisi Aktif:\n\n"
    for mint, data in tracked_tokens.items():
        msg += (
            f"Nama: {data['name']} ({data['symbol']})\n"
            f"Buy MCap: ${data['buy_mcap']:,.0f}\n"
            f"Target 2x: ${data['target_mcap']:,.0f}\n\n"
        )
    await update.message.reply_text(msg)

async def scan_tokens(chat_id, app):
    global scan_active, tracked_tokens
    seen_mints = set()

    await app.bot.send_message(chat_id,
        "Scanning dimulai dengan filter safety!\n"
        "MCap $5k-$50k\n"
        "Dev kurang dari 10 persen\n"
        "Anti NSFW dan rugpull"
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

                            await asyncio.sleep(2)
                            safety = await check_token_safety(mint, session)

                            if not safety:
                                continue

                            mcap = safety["mcap"]
                            dev_pct = safety["dev_pct"]
                            replies = safety["reply_count"]
                            target_mcap = mcap * 2

                            tracked_tokens[mint] = {
                                "name": name,
                                "symbol": symbol,
                                "buy_mcap": mcap,
                                "target_mcap": target_mcap,
                            }

                            msg_text = (
                                f"TOKEN AMAN DITEMUKAN!\n\n"
                                f"Nama: {name} ({symbol})\n"
                                f"MCap: ${mcap:,.0f}\n"
                                f"Dev holdings: {dev_pct:.1f} persen\n"
                                f"Replies: {replies}\n"
                                f"Target 2x: ${target_mcap:,.0f}\n"
                                f"Simulasi buy {buy_amount} SOL\n"
                                f"Link: pump.fun/{mint}"
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
        "/positions - Posisi aktif"
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
