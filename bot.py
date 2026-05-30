import os
import logging
import asyncio
import aiohttp
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

async def monitor_and_exit(mint, name, buy_price, chat_id, app):
    global current_position
    async with aiohttp.ClientSession() as session:
        while current_position:
            await asyncio.sleep(10)
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    pairs = data.get("pairs", [])
                    if not pairs:
                        continue
                    current = float(pairs[0].get("priceUsd", 0) or 0)
                    if not current:
                        continue
                    change = current / buy_price
                    pct = (change - 1) * 100
                    if change >= TAKE_PROFIT:
                        await app.bot.send_message(chat_id,
                            f"TAKE PROFIT!\n"
                            f"{name}\n"
                            f"Profit: +{pct:.1f}%\n"
                            f"Est: +{BUY_AMOUNT*(change-1):.3f} SOL\n\n"
                            f"Mencari token berikutnya..."
                        )
                        current_position = None
                        break
                    elif change <= STOP_LOSS:
                        await app.bot.send_message(chat_id,
                            f"STOP LOSS!\n"
                            f"{name}\n"
                            f"Loss: {pct:.1f}%\n"
                            f"Mencari token berikutnya..."
                        )
                        current_position = None
                        break
            except Exception as e:
                logging.error(e)

async def scan_tokens(chat_id, app):
    global scan_active, seen, current_position
    await app.bot.send_message(chat_id, "Scanner aktif! Mencari token di Raydium...")

    while scan_active:
        if current_position:
            await asyncio.sleep(5)
            continue
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.dexscreener.com/token-profiles/latest/v1"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        await asyncio.sleep(5)
                        continue
                    tokens = await r.json()
                    for token in tokens:
                        if current_position:
                            break
                        mint = token.get("tokenAddress", "")
                        chain = token.get("chainId", "")
                        if not mint or mint in seen or chain != "solana":
                            continue
                        seen.add(mint)
                        links = token.get("links", [])
                        twitter = ""
                        for link in links:
                            if link.get("type") == "twitter":
                                twitter = link.get("url", "")
                        if not twitter:
                            continue
                        url2 = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                        async with session.get(url2, timeout=aiohttp.ClientTimeout(total=8)) as r2:
                            if r2.status != 200:
                                continue
                            data = await r2.json()
                            pairs = data.get("pairs", [])
                            if not pairs:
                                continue
                            pair = pairs[0]
                            dex = pair.get("dexId", "")
                            price = float(pair.get("priceUsd", 0) or 0)
                            mcap = float(pair.get("marketCap", 0) or 0)
                            liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                            buys = pair.get("txns", {}).get("m5", {}).get("buys", 0)
                            sells = pair.get("txns", {}).get("m5", {}).get("sells", 0)

                            if dex != "raydium":
                                continue
                            if price <= 0:
                                continue
                            if liquidity < 3000:
                                continue

                            name = token.get("description", mint[:8])[:30]
                            current_position = {
                                "mint": mint,
                                "name": name,
                                "buy_price": price,
                            }

                            await app.bot.send_message(chat_id,
                                f"TOKEN RAYDIUM!\n\n"
                                f"{name}\n"
                                f"MCap: ${mcap:,.0f}\n"
                                f"Liquidity: ${liquidity:,.0f}\n"
                                f"Buy/Sell 5m: {buys}/{sells}\n"
                                f"Twitter: {twitter}\n"
                                f"CA: {mint}\n\n"
                                f"Simulasi buy {BUY_AMOUNT} SOL\n"
                                f"Target 2x | Stop loss 50%\n"
                                f"dexscreener.com/solana/{mint}"
                            )
                            asyncio.create_task(
                                monitor_and_exit(mint, name, price, chat_id, app)
                            )
                            break
        except Exception as e:
            logging.error(e)
        await asyncio.sleep(8)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = f"Posisi: {current_position['name']}" if current_position else "Tidak ada posisi"
    await update.message.reply_text(
        f"Pumpfun Migration Bot\n\n"
        f"Buy: {BUY_AMOUNT} SOL\n"
        f"Take Profit: {TAKE_PROFIT}x\n"
        f"Stop Loss: {int(STOP_LOSS*100)}%\n"
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
