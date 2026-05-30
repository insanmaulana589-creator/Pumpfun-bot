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
positions = {}
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
            age_minutes = pair.get("pairAge", 0)

            if liquidity < 10000:
                return None
            if volume_5m < 1000:
                return None
            if buys <= sells:
                return None
            if mcap > 100000:
                return None
            if age_minutes < 5:
                return None

            return {
                "price": price,
                "liquidity": liquidity,
                "volume_5m": volume_5m,
                "buys": buys,
                "sells": sells,
                "mcap": mcap,
                "age": age_minutes,
            }
    except Exception as e:
        logging.error(f"Token data error: {e}")
        return None

async def monitor_position(mint, name, buy_price, chat_id, app):
    await app.bot.send_message(chat_id,
        f"Memantau: {name}\n"
        f"Buy: ${buy_price:.8f}\n"
        f"Target 2x: ${buy_price*2:.8f}\n"
        f"Stop loss: ${buy_price*0.5:.8f}"
    )
    async with aiohttp.ClientSession() as session:
        while mint in positions:
            await asyncio.sleep(20)
            try:
                data = await get_token_data(mint, session)
                if not data:
                    continue
                current = data["price"]
                change = current / buy_price
                if change >= TAKE_PROFIT:
                    await app.bot.send_message(chat_id,
                        f"TAKE PROFIT!\n"
                        f"{name}\n"
                        f"Buy: ${buy_price:.8f}\n"
                        f"Sell: ${current:.8f}\n"
                        f"Profit: +{((change-1)*100):.1f}%\n"
                        f"Est profit: +{BUY_AMOUNT*(change-1):.3f} SOL"
                    )
                    positions.pop(mint, None)
                    break
                elif change <= STOP_LOSS:
                    await app.bot.send_message(chat_id,
                        f"STOP LOSS!\n"
                        f"{name}\n"
                        f"Buy: ${buy_price:.8f}\n"
                        f"Sell: ${current:.8f}\n"
                        f"Loss: {((change-1)*100):.1f}%\n"
                        f"Est loss: -{BUY_AMOUNT*(1-change):.3f} SOL"
                    )
                    positions.pop(mint, None)
                    break
            except Exception as e:
                logging.error(e)

async def scan_tokens(chat_id, app):
    global scan_active, seen, positions
    await app.bot.send_message(chat_id,
        "Scanner dimulai!\n"
        "Filter ketat:\n"
        "Liquidity lebih dari $10k\n"
        "Volume 5m lebih dari $1k\n"
        "Buy lebih banyak dari sell\n"
        "Umur lebih dari 5 menit\n"
        "MCap kurang dari $100k"
    )

    while scan_active:
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.dexscreener.com/token-profiles/latest/v1"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
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
                        for link in links:
                            if link.get("type") == "twitter":
                                twitter = link.get("url", "")
                        if not twitter:
                            continue
                        data = await get_token_data(mint, session)
                        if not data:
                            continue
                        name = token.get("description", mint[:8])[:30]
                        positions[mint] = {
                            "name": name,
                            "buy_price": data["price"],
                        }
                        await app.bot.send_message(chat_id,
                            f"TOKEN LOLOS FILTER!\n\n"
                            f"Nama: {name}\n"
                            f"MCap: ${data['mcap']:,.0f}\n"
                            f"Liquidity: ${data['liquidity']:,.0f}\n"
                            f"Volume 5m: ${data['volume_5m']:,.0f}\n"
                            f"Buy/Sell: {data['buys']}/{data['sells']}\n"
                            f"Umur: {data['age']} menit\n"
                            f"Twitter: {twitter}\n"
                            f"CA: {mint}\n"
                            f"dexscreener.com/solana/{mint}\n\n"
                            f"Simulasi buy {BUY_AMOUNT} SOL"
                        )
                        asyncio.create_task(
                            monitor_position(mint, name, data["price"], chat_id, app)
                        )
        except Exception as e:
            logging.error(e)
        await asyncio.sleep(10)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pumpfun Smart Scanner\n\n"
        f"Buy: {BUY_AMOUNT} SOL\n"
        f"Take Profit: {TAKE_PROFIT}x\n"
        f"Stop Loss: {int(STOP_LOSS*100)}%\n\n"
        "/scan - Mulai\n"
        "/stopscan - Stop\n"
        "/positions - Posisi aktif"
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
        msg += f"{data['name']}\nBuy: ${data['buy_price']:.8f}\n\n"
    await update.message.reply_text(msg)

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
