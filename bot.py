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
max_mcap = 50000
tracked_tokens = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pumpfun Trading Bot\n\n"
        "Setting:\n"
        "Buy: 0.2 SOL\n"
        "Max MCap: $50,000\n"
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
        "Scanning via WebSocket...\n"
        "Filter: MCap < $50,000 | TP: 2x"
    )

    uri = "wss://pumpportal.fun/api/data"

    while scan_active:
        try:
            async with websockets.connect(uri) as ws:
                payload = {"method": "subscribeNewToken"}
                await ws.send(json.dumps(payload))
                await app.bot.send_message(chat_id, "Terhubung ke Pump.fun!")

                while scan_active:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)

                        mint = data.get("mint", "")
                        if not mint or mint in seen_mints:
                            continue

                        name = data.get("name", "Unknown")
                        symbol = data.get("symbol", "???")
                        mcap = data.get("marketCapSol", 0) * 150

                        if mcap > max_mcap:
                            continue

                        seen_mints.add(mint)
                        target_mcap = mcap * 2

                        tracked_tokens[mint] = {
                            "name": name,
                            "symbol": symbol,
                            "buy_mcap": mcap,
                            "target_mcap": target_mcap,
                        }

                        msg_text = (
                            f"TOKEN BARU!\n\n"
                            f"Nama: {name} ({symbol})\n"
                            f"MCap: ${mcap:,.0f}\n"
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
