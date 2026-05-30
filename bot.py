import os
import logging
import asyncio
import aiohttp
import base58
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

scan_active = False
seen = set()
positions = {}
BUY_AMOUNT = 0.2
TAKE_PROFIT = 2.0
STOP_LOSS = 0.5

def get_keypair():
    try:
        key_bytes = base58.b58decode(PRIVATE_KEY)
        return Keypair.from_bytes(key_bytes)
    except:
        return None

async def get_sol_price():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd") as r:
                data = await r.json()
                return data["solana"]["usd"]
    except:
        return 150

async def get_token_price(mint, session):
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status != 200:
                return None
            data = await r.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
            return float(pairs[0].get("priceUsd", 0))
    except:
        return None

async def monitor_position(mint, name, symbol, buy_price, chat_id, app):
    await app.bot.send_message(chat_id,
        f"Memantau posisi:\n"
        f"{name} ({symbol})\n"
        f"Buy price: ${buy_price:.8f}\n"
        f"Target 2x: ${buy_price*2:.8f}\n"
        f"Stop loss 50%: ${buy_price*0.5:.8f}"
    )

    async with aiohttp.ClientSession() as session:
        while mint in positions:
            await asyncio.sleep(15)
            current_price = await get_token_price(mint, session)
            if not current_price:
                continue

            change = current_price / buy_price

            if change >= TAKE_PROFIT:
                await app.bot.send_message(chat_id,
                    f"TAKE PROFIT!\n"
                    f"{name} ({symbol})\n"
                    f"Buy: ${buy_price:.8f}\n"
                    f"Sell: ${current_price:.8f}\n"
                    f"Profit: +{((change-1)*100):.1f}%\n"
                    f"Estimasi profit: +{BUY_AMOUNT*(change-1):.3f} SOL"
                )
                positions.pop(mint, None)
                break

            elif change <= STOP_LOSS:
                await app.bot.send_message(chat_id,
                    f"STOP LOSS!\n"
                    f"{name} ({symbol})\n"
                    f"Buy: ${buy_price:.8f}\n"
                    f"Sell: ${current_price:.8f}\n"
                    f"Loss: {((change-1)*100):.1f}%\n"
                    f"Estimasi loss: {BUY_AMOUNT*(1-change):.3f} SOL"
                )
                positions.pop(mint, None)
                break

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pumpfun Auto Trading Bot\n\n"
        f"Buy: {BUY_AMOUNT} SOL\n"
        f"Take Profit: {TAKE_PROFIT}x\n"
        f"Stop Loss: {STOP_LOSS*100}%\n\n"
        "/scan - Mulai scan\n"
        "/stopscan - Stop scan\n"
        "/positions - Lihat posisi\n"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("Stop!")

async def show_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not positions:
        await update.message.reply_text("Tidak ada posisi aktif.")
        return
    msg = "Posisi Aktif:\n\n"
    for mint, data in positions.items():
        msg += f"{data['name']} ({data['symbol']})\nBuy: ${data['buy_price']:.8f}\n\n"
    await update.message.reply_text(msg)

async def scan_tokens(chat_id, app):
    global scan_active, seen, positions
    await app.bot.send_message(chat_id, "Scanning via DexScreener...")

    while scan_active:
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.dexscreener.com/token-profiles/latest/v1"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status != 200:
                        await asyncio.sleep(5)
                        continue
                    tokens = await r.json()
                    for token in tokens:
                        mint = token.get("tokenAddress", "")
                        chain = token.get("chainId", "")
                        if not mint or mint in seen or chain != "solana":
                            continue
                        seen.add(mint)
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

                        price = await get_token_price(mint, session)
                        if not price:
                            continue

                        name = token.get("description", "Unknown")[:30]
                        symbol = mint[:6]

                        positions[mint] = {
                            "name": name,
                            "symbol": symbol,
                            "buy_price": price,
                        }

                        await app.bot.send_message(chat_id,
                            f"TOKEN DIBELI!\n"
                            f"{name}\n"
                            f"CA: {mint}\n"
                            f"Twitter: {twitter}\n"
                            f"Website: {website if website else 'Tidak ada'}\n"
                            f"Buy price: ${price:.8f}\n"
                            f"Buy: {BUY_AMOUNT} SOL\n"
                            f"Target 2x | Stop loss 50%\n"
                            f"dexscreener.com/solana/{mint}"
                        )

                        asyncio.create_task(
                            monitor_position(mint, name, symbol, price, chat_id, app)
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
    app.add_handler(CommandHandler("positions", show_positions))
    app.run_polling()

if __name__ == "__main__":
    main()
