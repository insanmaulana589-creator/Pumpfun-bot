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

async def get_token_data(mint, session):
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            data = await r.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
            pair = pairs[0]
            liquidity = pair.get("liquidity", {}).get("usd", 0)
            volume_5m = pair.get("volume", {}).get("m5", 0)
            txns_5m = pair.get("txns", {}).get("m5", {})
            buys = txns_5m.get("buys", 0)
            sells = txns_5m.get("sells", 0)
            price = float(pair.get("priceUsd", 0))
            mcap = pair.get("marketCap", 0)
            age = pair.get("pairAge", 0)
            if liquidity < 5000:
                return None
            if volume_5m < 500:
                return None
            if buys <= sells:
                return None
            if mcap > 100000:
                return None
            if age < 5:
                return None
            return {
                "price": price,
                "liquidity": liquidity,
                "volume_5m": volume_5m,
                "buys": buys,
                "sells": sells,
                "mcap": mcap,
                "age": age,
            }
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

async def monitor_and_exit(mint, name, buy_price, chat_id, app):
    global current_position, scan_active
    async with aiohttp.ClientSession() as session:
        while current_position:
            await asyncio.sleep(15)
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    pairs = data.get("pairs", [])
                    if not pairs:
                        continue
                    current = float(pairs[0].get("priceUsd", 0))
                    if not current:
                        continue
                    change = current / buy_price
                    if change >= TAKE_PROFIT:
                        await app.bot.send_message(chat_id,
                            f"TAKE PROFIT!\n"
                            f"{name}\n"
                            f"Buy: ${buy_price:.8f}\n"
                            f"Sell: ${current:.8f}\n"
                            f"Profit: +{((change-1)*100):.1f}%\n"
                            f"Est profit: +{BUY_AMOUNT*(change-1):.3f} SOL\n\n"
                            f"Mencari token berikutnya..."
                        )
                        current_position = None
                        break
                    elif change <= STOP_LOSS:
                        await app.bot.send_message(chat_id,
                            f"STOP LOSS!\n"
                            f"{name}\n"
                            f"Buy: ${buy_price:.8f}\n"
                            f"Sell: ${current:.8f}\n"
                            f"Loss: {((change-1)*100):.1f}%\n"
                            f"Est loss: -{BUY_AMOUNT*(1-change):.3f} SOL\n\n"
                            f"Mencari token berikutnya..."
                        )
                        current_position = None
                        break
            except Exception as e:
                logging.error(e)

async def scan_tokens(chat_id, app):
    global scan_active, seen, current_position
    await app.bot.send_message(chat_id, "Scanner 1-token aktif!\nMencari token terbaik...")

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
                        data = await get_token_data(mint, session)
                        if not data:
                            continue
                        name = token.get("description", mint[:8])[:30]
                        current_position = {
                            "mint": mint,
                            "name": name,
                            "buy_price": data["price"],
                        }
                        await app.bot.send_message(chat_id,
                            f"TOKEN DITEMUKAN!\n\n"
                            f"Nama: {name}\n"
                            f"MCap: ${data['mcap']:,.0f}\n"
                            f"Liquidity: ${data['liquidity']:,.0f}\n"
                            f"Volume 5m: ${data['volume_5m']:,.0f}\n"
                            f"Buy/Sell: {data['buys']}/{data['sells']}\n"
                            f"Twitter: {twitter}\n"
                            f"CA: {mint}\n\n"
                            f"Simulasi buy {BUY_AMOUNT} SOL\n"
                            f"Memantau harga..."
                        )
                        asyncio.create_task(
                            monitor_and_exit(mint, name, data["price"], chat_id, app)
                        )
                        break
        except Exception as e:
            logging.error(e)
        await asyncio.sleep(10)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "Ada posisi aktif" if current_position else "Tidak ada posisi"
    await update.message.reply_text(
        f"Pumpfun 1-Token Bot\n\n"
        f"Buy: {BUY_AMOUNT} SOL\n"
        f"Take Profit: {TAKE_PROFIT}x\n"
        f"Stop Loss: {int(STOP_LOSS*100)}%\n"
        f"Status: {status}\n\n"
        "/scan - Mulai\n"
        "/stopscan - Stop\n"
        "/status - Cek posisi\n"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("Stop!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not current_position:
        await update.message.reply_text("Tidak ada posisi aktif. Bot sedang mencari token...")
        return
    await update.message.reply_text(
        f"Posisi Aktif:\n\n"
        f"Nama: {current_position['name']}\n"
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
