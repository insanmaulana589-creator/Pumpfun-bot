import os
import logging
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
BIRDEYE_KEY = os.environ.get("BIRDEYE_KEY")
scan_active = False
seen = set()
current_position = None
BUY_AMOUNT = 0.2
TAKE_PROFIT = 2.0
STOP_LOSS = 0.5

HEADERS = {
    "X-API-KEY": BIRDEYE_KEY,
    "x-chain": "solana"
}

async def get_token_info(mint, session):
    try:
        url = f"https://public-api.birdeye.so/defi/token_overview?address={mint}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            data = await r.json()
            token = data.get("data", {})
            price = float(token.get("price", 0) or 0)
            mcap = float(token.get("mc", 0) or 0)
            liquidity = float(token.get("liquidity", 0) or 0)
            v5m = float(token.get("v5mUSD", 0) or 0)
            buy5m = int(token.get("buy5m", 0) or 0)
            sell5m = int(token.get("sell5m", 0) or 0)
            change5m = float(token.get("priceChange5mPercent", 0) or 0)
            change1h = float(token.get("priceChange1hPercent", 0) or 0)

            if price <= 0:
                return None
            if mcap <= 0 or mcap > 500000:
                return None
            if liquidity < 5000:
                return None
            if v5m < 1000:
                return None
            if buy5m < sell5m:
                return None
            if change5m < 5:
                return None

            return {
                "price": price,
                "mcap": mcap,
                "liquidity": liquidity,
                "v5m": v5m,
                "buy5m": buy5m,
                "sell5m": sell5m,
                "change5m": change5m,
                "change1h": change1h,
            }
    except Exception as e:
        logging.error(f"Birdeye error: {e}")
        return None

async def monitor_and_exit(mint, name, buy_price, chat_id, app):
    global current_position
    async with aiohttp.ClientSession() as session:
        while current_position:
            await asyncio.sleep(10)
            try:
                url = f"https://public-api.birdeye.so/defi/price?address={mint}"
                async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    current = float(data.get("data", {}).get("value", 0) or 0)
                    if not current:
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
                            f"Loss: {pct:.1f}%\n"
                            f"Est: -{BUY_AMOUNT*(1-change):.3f} SOL\n\n"
                            f"Mencari token berikutnya..."
                        )
                        current_position = None
                        break
            except Exception as e:
                logging.error(e)

async def scan_tokens(chat_id, app):
    global scan_active, seen, current_position
    await app.bot.send_message(chat_id,
        "Birdeye Scanner aktif!\n"
        "Filter:\n"
        "Pump lebih dari 5% per 5m\n"
        "Buy lebih dari sell\n"
        "Liquidity lebih dari $5k\n"
        "Volume 5m lebih dari $1k\n"
        "1 token at a time!"
    )

    while scan_active:
        if current_position:
            await asyncio.sleep(5)
            continue
        try:
            async with aiohttp.ClientSession() as session:
                url = (
                    "https://public-api.birdeye.so/defi/tokenlist"
                    "?sort_by=v5mUSD&sort_type=desc&offset=0&limit=20"
                    "&min_liquidity=5000"
                )
                async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        await asyncio.sleep(5)
                        continue
                    data = await r.json()
                    tokens = data.get("data", {}).get("tokens", [])
                    for token in tokens:
                        if current_position:
                            break
                        mint = token.get("address", "")
                        if not mint or mint in seen:
                            continue
                        seen.add(mint)
                        name = token.get("name", "Unknown")[:30]
                        symbol = token.get("symbol", "???")
                        info = await get_token_info(mint, session)
                        if not info:
                            continue
                        current_position = {
                            "mint": mint,
                            "name": name,
                            "buy_price": info["price"],
                        }
                        await app.bot.send_message(chat_id,
                            f"TOKEN DITEMUKAN!\n\n"
                            f"{name} ({symbol})\n"
                            f"MCap: ${info['mcap']:,.0f}\n"
                            f"Liquidity: ${info['liquidity']:,.0f}\n"
                            f"Volume 5m: ${info['v5m']:,.0f}\n"
                            f"Pump 5m: +{info['change5m']:.1f}%\n"
                            f"Pump 1h: +{info['change1h']:.1f}%\n"
                            f"Buy/Sell 5m: {info['buy5m']}/{info['sell5m']}\n"
                            f"CA: {mint}\n\n"
                            f"Simulasi buy {BUY_AMOUNT} SOL\n"
                            f"Target 2x | Stop loss 50%\n"
                            f"birdeye.so/token/{mint}"
                        )
                        asyncio.create_task(
                            monitor_and_exit(mint, name, info["price"], chat_id, app)
                        )
                        break
        except Exception as e:
            logging.error(e)
        await asyncio.sleep(8)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = f"Posisi: {current_position['name']}" if current_position else "Tidak ada posisi"
    await update.message.reply_text(
        f"Pumpfun Birdeye Bot\n\n"
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
