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
current_position = None
BUY_AMOUNT = 0.2
TAKE_PROFIT = 2.0
STOP_LOSS = 0.5

async def get_price(mint, session):
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            data = await r.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
            return float(pairs[0].get("priceUsd", 0) or 0)
    except:
        return None

async def monitor_and_exit(mint, name, buy_price, chat_id, app):
    global current_position
    async with aiohttp.ClientSession() as session:
        while current_position:
            await asyncio.sleep(10)
            try:
                current = await get_price(mint, session)
                if not current or current <= 0:
                    continue
                change = current / buy_price
                pct = (change - 1) * 100
                if change >= TAKE_PROFIT:
                    await app.bot.send_message(chat_id,
                        f"TAKE PROFIT!\n"
                        f"{name}\n"
                        f"Buy: ${buy_price:.8f}\n"
                        f"Sell: ${current:.8f}\n"
                        f"Profit: +{pct:.1f}%\n"
                        f"Est: +{BUY_AMOUNT*(change-1):.3f} SOL\n\n"
                        f"Mencari token migrasi berikutnya..."
                    )
                    current_position = None
                    break
                elif change <= STOP_LOSS:
                    await app.bot.send_message(chat_id,
                        f"STOP LOSS!\n"
                        f"{name}\n"
                        f"Buy: ${buy_price:.8f}\n"
                        f"Sell: ${current:.8f}\n"
                        f"Loss: {pct:.1f}%\n"
                        f"Est: -{BUY_AMOUNT*(1-change):.3f} SOL\n\n"
                        f"Mencari token migrasi berikutnya..."
                    )
                    current_position = None
                    break
            except Exception as e:
                logging.error(e)

async def scan_tokens(chat_id, app):
    global scan_active, seen, current_position
    await app.bot.send_message(chat_id,
        "Scanner Migrasi Pump.fun ke Raydium!\n"
        "Menunggu token yang baru migrasi...\n"
        "1 token at a time!"
    )

    uri = "wss://pumpportal.fun/api/data"

    while scan_active:
        if current_position:
            await asyncio.sleep(5)
            continue
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"method": "subscribeTokenTrade"}))
                await ws.send(json.dumps({"method": "subscribeMigration"}))
                await app.bot.send_message(chat_id, "Terhubung! Memantau migrasi...")

                async with aiohttp.ClientSession() as session:
                    while scan_active:
                        if current_position:
                            await asyncio.sleep(5)
                            continue
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(msg)

                            if data.get("txType") != "migrate":
                                continue

                            mint = data.get("mint", "")
                            if not mint or mint in seen:
                                continue
                            seen.add(mint)

                            name = data.get("name", "Unknown")
                            symbol = data.get("symbol", "???")

                            await app.bot.send_message(chat_id,
                                f"TOKEN MIGRASI TERDETEKSI!\n"
                                f"{name} ({symbol})\n"
                                f"Mengecek harga..."
                            )

                            await asyncio.sleep(3)
                            price = await get_price(mint, session)
                            if not price or price <= 0:
                                await app.bot.send_message(chat_id, f"Harga belum tersedia, skip.")
                                continue

                            current_position = {
                                "mint": mint,
                                "name": name,
                                "buy_price": price,
                            }

                            await app.bot.send_message(chat_id,
                                f"BELI SETELAH MIGRASI!\n\n"
                                f"{name} ({symbol})\n"
                                f"CA: {mint}\n"
                                f"Buy price: ${price:.8f}\n"
                                f"Simulasi buy {BUY_AMOUNT} SOL\n"
                                f"Target 2x | Stop loss 50%\n"
                                f"dexscreener.com/solana/{mint}"
                            )

                            asyncio.create_task(
                                monitor_and_exit(mint, name, price, chat_id, app)
                            )

                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            logging.error(e)

        except Exception as e:
            logging.error(f"WebSocket error: {e}")
            if scan_active:
                await app.bot.send_message(chat_id, "Reconnecting...")
                await asyncio.sleep(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = f"Posisi: {current_position['name']}" if current_position else "Tidak ada posisi"
    await update.message.reply_text(
        f"Pumpfun Migration Bot\n\n"
        f"Buy: {BUY_AMOUNT} SOL\n"
        f"Take Profit: {TAKE_PROFIT}x\n"
        f"Stop Loss: {int(STOP_LOSS*100)}%\n"
        f"Strategi: Beli saat migrasi ke Raydium\n"
        f"{status}\n\n"
        "/scan - Mulai\n"
        "/stopscan - Stop\n"
        "/status - Cek posisi"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("Stop!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not current_position:
        await update.message.reply_text("Tidak ada posisi aktif.")
        return
    await update.message.reply_text(
        f"Posisi Aktif:\n"
        f"{current_position['name']}\n"
        f"Buy: ${current_position['buy_price']:.8f}\n"
        f"CA: {current_position['mint']}"
    )

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
    app.add_handler(CommandHandler("status", status))
    app.run_polling()

if __name__ == "__main__":
    main()
